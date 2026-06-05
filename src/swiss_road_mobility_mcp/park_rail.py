"""
Park & Rail Daten – Phase 3 Modul.

Metapher: Phase 1 zeigt das Velo an der Ecke.
          Phase 2 erklärt, warum die Strasse gesperrt ist.
          Phase 3 zeigt, wo du dein Auto parkierst und in den Zug steigst.
          Zusammen: das vollständige multimodale Bild der Schweizer Mobilität.

Datenquelle: Open-Data-Plattform Mobilität Schweiz (opentransportdata.swiss).
Format: GeoJSON (FeatureCollection) – KEINE Opendatasoft-/data.sbb.ch-API!
API-Key: KEINER – komplett offen (Phase-1-Philosophie beibehalten).
Update: täglich aus der SBB-Datenbank P+Rail.

Warum nicht data.sbb.ch?
  Die Opendatasoft-API auf data.sbb.ch liefert die Park+Rail-Anlagen NICHT
  (alle Datensatz-/Endpunkt-Varianten antworten mit HTTP 404). Die offizielle
  Quelle ist ein statisches GeoJSON, das via CKAN auf opentransportdata.swiss
  publiziert wird.

Abruf-Strategie:
  1. CKAN-API (api.opentransportdata.swiss) befragen, um die aktuelle
     Download-URL der GeoJSON-Resource zu ermitteln (keine fragile
     Hardcoded-Resource-UUID).
  2. GeoJSON laden, FeatureCollection parsen.
  Neuer konsolidierter Datensatz ('bike-and-car-parking') zuerst, der ältere
  'parking-facilities' (Abschaltung 2026-06-30) als Fallback.
  Schlägt alles fehl, liefern die Funktionen ein strukturiertes
  „nicht erreichbar“-Resultat statt einer Exception (Graceful Degradation),
  damit das MCP-Tool nie hart abstürzt.
"""

import logging
import time

import httpx

from . import USER_AGENT
from .api_infrastructure import APIError, haversine_km
from .egress import EgressBlockedError, async_client

logger = logging.getLogger("swiss-road-mobility-mcp")

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# CKAN-API der Open-Data-Plattform Mobilität Schweiz (kein API-Key nötig).
_CKAN_PACKAGE_SHOW = "https://api.opentransportdata.swiss/ckan-api/package_show"

# Reihenfolge: neuer konsolidierter Datensatz zuerst, alter als Fallback.
_PARK_RAIL_DATASETS = ["bike-and-car-parking", "parking-facilities"]

_DATA_SOURCE = "Park+Rail GeoJSON (opentransportdata.swiss) – kein API-Key nötig"

_CACHE_TTL = 300.0  # 5 Minuten (Kapazitätsdaten ändern sich selten)
# Wir cachen die komplette Feature-Liste (das GeoJSON ist mehrere MB groß –
# einmal laden, dann clientseitig nach Position/Name filtern).
_features_cache: list[dict] | None = None
_features_cache_ts: float = 0.0


# ---------------------------------------------------------------------------
# Daten-Formatierung
# ---------------------------------------------------------------------------

def _format_feature(
    feature: dict,
    lat_center: float | None = None,
    lon_center: float | None = None,
) -> dict | None:
    """Wandelt ein GeoJSON-Feature in ein sauberes, LLM-freundliches dict um.

    Erwartete Struktur (Park+Rail GeoJSON):
        {
          "type": "Feature",
          "geometry": {"type": "Point", "coordinates": [lon, lat]},
          "properties": {
            "displayName": "Horgen",
            "operator": "SBB",
            "bookingSystem": {"type": "...", "id": "..."},
            "address": {"addressLine": "...", "city": "...", "postalCode": "..."},
            "capacities": [{"categoryType": "STANDARD", "total": 44}, ...]
          }
        }

    ``distance_km`` wird nur gesetzt, wenn ein Suchzentrum übergeben wird.
    """
    if not isinstance(feature, dict):
        return None

    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    # GeoJSON-Reihenfolge ist [lon, lat]
    if not (isinstance(coords, list) and len(coords) >= 2):
        return None
    try:
        lon = float(coords[0])
        lat = float(coords[1])
    except (TypeError, ValueError):
        return None

    props = feature.get("properties") or {}

    name = (
        props.get("displayName")
        or props.get("name")
        or props.get("label")
        or "Unbekannt"
    )

    # ── Kapazität ──────────────────────────────────────────────────────────
    # capacities[] kann mehrere Kategorien (STANDARD, DISABLED, …) enthalten.
    total = 0
    by_category: dict[str, int] = {}
    capacities = props.get("capacities") or []
    if isinstance(capacities, list):
        for cap in capacities:
            if not isinstance(cap, dict):
                continue
            value = cap.get("total")
            if isinstance(value, (int, float)):
                category = str(cap.get("categoryType") or "UNKNOWN")
                total += int(value)
                by_category[category] = by_category.get(category, 0) + int(value)

    result: dict = {
        "name": str(name),
        "station": str(name),
        "latitude": lat,
        "longitude": lon,
        "total_spaces": int(total),
        "data_source": _DATA_SOURCE,
    }

    if lat_center is not None and lon_center is not None:
        result["distance_km"] = round(haversine_km(lat_center, lon_center, lat, lon), 3)

    if by_category:
        result["spaces_by_category"] = by_category

    operator = props.get("operator")
    if operator:
        result["operator"] = str(operator)

    address = props.get("address")
    if isinstance(address, dict):
        parts = [address.get("addressLine"), address.get("postalCode"), address.get("city")]
        joined = ", ".join(str(p) for p in parts if p)
        if joined:
            result["address"] = joined

    booking = props.get("bookingSystem")
    if isinstance(booking, dict) and booking.get("type"):
        result["booking_system"] = str(booking.get("type"))

    return result


# ---------------------------------------------------------------------------
# Netzwerk: GeoJSON via CKAN beschaffen (mit Cache)
# ---------------------------------------------------------------------------

async def _discover_geojson_url(client: httpx.AsyncClient, dataset_id: str) -> str | None:
    """Ermittelt die Download-URL der (Geo)JSON-Resource eines CKAN-Datensatzes."""
    response = await client.get(_CKAN_PACKAGE_SHOW, params={"id": dataset_id})
    response.raise_for_status()
    payload = response.json()
    result = payload.get("result") or {}
    # CKAN: "resources"; manche Spiegel verwenden "ressources".
    resources = result.get("resources") or result.get("ressources") or []
    if not isinstance(resources, list):
        return None

    # GeoJSON bevorzugen, sonst JSON.
    for preferred in ("geojson", "json"):
        for res in resources:
            if not isinstance(res, dict):
                continue
            fmt = str(res.get("format") or "").lower()
            url = res.get("url") or res.get("download_url")
            if url and preferred in fmt:
                return str(url)

    # Fallback: erste Resource, deren URL auf .json/.geojson endet.
    for res in resources:
        if not isinstance(res, dict):
            continue
        url = str(res.get("url") or "")
        if url.endswith((".json", ".geojson")):
            return url

    return None


async def _fetch_park_rail_features() -> list[dict]:
    """Lädt die Park+Rail-GeoJSON-Features. Wirft APIError, wenn alles scheitert."""
    last_error = ""
    async with async_client(
        timeout=30.0,  # die Datei ist mehrere MB groß
        follow_redirects=True,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, application/geo+json",
        },
    ) as client:
        for dataset_id in _PARK_RAIL_DATASETS:
            try:
                url = await _discover_geojson_url(client, dataset_id)
                if not url:
                    last_error = f"Keine (Geo)JSON-Resource im Datensatz '{dataset_id}'"
                    logger.warning("Park+Rail: %s", last_error)
                    continue

                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                # FeatureCollection → features[]; manche Feeds liefern direkt eine Liste.
                if isinstance(data, dict):
                    features = data.get("features")
                elif isinstance(data, list):
                    features = data
                else:
                    features = None

                if features:
                    logger.debug("Park+Rail: %d Features aus '%s'", len(features), dataset_id)
                    return features

                last_error = f"Datensatz '{dataset_id}' enthielt keine Features"
                logger.warning("Park+Rail: %s", last_error)
            except httpx.HTTPStatusError as e:
                # OBS-002: rohen Upstream-Body nur server-seitig loggen.
                logger.warning(
                    "Park+Rail: HTTP %s bei Datensatz '%s': %s",
                    e.response.status_code, dataset_id, e.response.text[:200],
                )
                last_error = f"HTTP {e.response.status_code} bei Datensatz '{dataset_id}'"
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = f"Verbindungsfehler bei Datensatz '{dataset_id}': {e}"
                logger.warning("Park+Rail: %s", last_error)
            except EgressBlockedError as e:
                last_error = f"Egress blockiert für Datensatz '{dataset_id}': {e}"
                logger.warning("Park+Rail: %s", last_error)
            except ValueError as e:
                # JSON-Decode-Fehler
                last_error = f"Ungültiges JSON bei Datensatz '{dataset_id}': {e}"
                logger.warning("Park+Rail: %s", last_error)

    raise APIError(
        f"Park+Rail-Daten (opentransportdata.swiss) nicht erreichbar. "
        f"Letzter Fehler: {last_error}. "
        "Bitte prüfe https://opentransportdata.swiss für den aktuellen Datensatz."
    )


async def _get_features() -> list[dict]:
    """Liefert die Features aus dem Cache oder lädt sie neu."""
    global _features_cache, _features_cache_ts

    now = time.monotonic()
    if _features_cache is not None and (now - _features_cache_ts) < _CACHE_TTL:
        logger.debug("Cache HIT: park_rail features")
        return _features_cache

    features = await _fetch_park_rail_features()
    _features_cache = features
    _features_cache_ts = now
    return features


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def find_nearby_park_rail(
    latitude: float,
    longitude: float,
    radius_km: float = 5.0,
    limit: int = 10,
) -> dict:
    """
    Findet Park & Rail Anlagen in der Nähe einer Position.

    Lädt das offizielle Park+Rail-GeoJSON und filtert clientseitig per
    Haversine-Distanz. Resultate sind nach Distanz sortiert.

    Bei nicht erreichbarer Datenquelle wird ein strukturiertes Resultat mit
    ``found: 0`` und einem ``note``/``error``-Hinweis zurückgegeben – KEINE
    Exception (Graceful Degradation).

    Args:
        latitude: Breitengrad des Suchzentrums
        longitude: Längengrad des Suchzentrums
        radius_km: Suchradius in Kilometern
        limit: Maximale Anzahl Resultate

    Returns:
        dict mit facilities-Liste, sortiert nach Distanz
    """
    search = {"latitude": latitude, "longitude": longitude, "radius_km": radius_km}

    try:
        features = await _get_features()
    except APIError as e:
        return {
            "search": search,
            "found": 0,
            "api_key_required": False,
            "data_source": _DATA_SOURCE,
            "facilities": [],
            "note": "Park+Rail-Datenquelle momentan nicht erreichbar.",
            "error": str(e),
        }

    facilities = []
    for feature in features:
        formatted = _format_feature(feature, latitude, longitude)
        if formatted is None:
            continue
        if formatted["distance_km"] <= radius_km:
            facilities.append(formatted)

    facilities.sort(key=lambda x: x["distance_km"])
    facilities = facilities[:limit]

    return {
        "search": search,
        "found": len(facilities),
        "api_key_required": False,
        "data_source": _DATA_SOURCE,
        "facilities": facilities,
    }


async def find_park_rail_by_station(station_name: str, limit: int = 5) -> dict:
    """
    Findet Park & Rail Anlagen für einen Bahnhof per Textsuche.

    Nützlich wenn man den Namen des Bahnhofs kennt, aber nicht die Koordinaten.
    Sucht (case-insensitiv) im Anlagennamen.

    Args:
        station_name: Bahnhofsname (z.B. 'Zürich HB', 'Winterthur', 'Bern')
        limit: Maximale Anzahl Resultate

    Returns:
        dict mit passenden Park & Rail Anlagen
    """
    try:
        features = await _get_features()
    except APIError as e:
        return {
            "query": station_name,
            "found": 0,
            "api_key_required": False,
            "data_source": _DATA_SOURCE,
            "facilities": [],
            "note": "Park+Rail-Datenquelle momentan nicht erreichbar.",
            "error": str(e),
        }

    needle = station_name.strip().lower()
    facilities = []
    for feature in features:
        formatted = _format_feature(feature)
        if formatted is None:
            continue
        if needle in formatted["name"].lower():
            facilities.append(formatted)
            if len(facilities) >= limit:
                break

    return {
        "query": station_name,
        "found": len(facilities),
        "api_key_required": False,
        "data_source": _DATA_SOURCE,
        "facilities": facilities,
    }
