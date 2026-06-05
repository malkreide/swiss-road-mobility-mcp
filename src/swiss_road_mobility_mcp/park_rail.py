"""
Park & Rail Daten – Phase 3 Modul.

Metapher: Phase 1 zeigt das Velo an der Ecke.
          Phase 2 erklärt, warum die Strasse gesperrt ist.
          Phase 3 zeigt, wo du dein Auto parkierst und in den Zug steigst.
          Zusammen: das vollständige multimodale Bild der Schweizer Mobilität.

Datenquelle: SBB Open Data Portal (data.sbb.ch / Opendatasoft API)
Format: JSON (REST, kein SOAP, kein XML!)
API-Key: KEINER – komplett offen! (Phase-1-Philosophie beibehalten)
Update: Kapazitäten täglich; Belegung wo vorhanden in Echtzeit

API-Endpunkt (v0.4.0):
  https://data.sbb.ch/api/explore/v2.1/catalog/datasets/station-mobility/records
  Das frühere Dataset 'park-and-rail' wurde von SBB entfernt (→ HTTP 404).
  Ersatz: 'station-mobility' enthält Park+Rail-Daten unter den Feldern
  parkrail_anzahl, parkrail_preis_tag, parkrail_preis_monat usw.
  Geofilter (ODSQL v2):
    ?where=parkrail_anzahl>0 AND distance(geopos,geom'POINT(lon lat)',{r}km)
"""

import logging
import time

import httpx

from . import USER_AGENT
from .api_infrastructure import APIError, haversine_km
from .egress import async_client

logger = logging.getLogger("swiss-road-mobility-mcp")

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# SBB Open Data hat den Park+Rail-Datensatz mehrfach umbenannt; die
# Park+Rail-Felder (parkrail_anzahl, parkrail_preis_tag, geopos …) stecken
# heute in den Datensätzen 'mobilitat' bzw. 'station-mobility'.
#
# Wir kennen NICHT garantiert, welche API-Version (Explore v2.1 oder die
# Legacy Records-API v1) auf data.sbb.ch je Datensatz aktiv ist – und welche
# Geofilter-Syntax akzeptiert wird. Frühere Versionen mischten v1-Parameter
# (geofilter.distance) mit dem v2.1-Pfad, was HTTP 404/400 auslöste.
# Darum probieren wir pro Datensatz BEIDE API-Stile durch und nehmen die
# erste 2xx-Antwort. _format_facility versteht beide Response-Formen
# (v2.1: flache Felder; v1: verschachtelt unter "fields").
_PARK_RAIL_DATASETS = ["mobilitat", "station-mobility", "park-and-rail"]

# Explore API v2.1 – Datensatz-Records (flache Felder, geopos als geo_point).
_V21_RECORDS = "https://data.sbb.ch/api/explore/v2.1/catalog/datasets/{ds}/records"
# Legacy Records API v1 – unterstützt nativ geofilter.distance (lat,lon,Meter).
_V1_SEARCH = "https://data.sbb.ch/api/records/1.0/search/"

# Primärer Endpunkt (für die Textsuche / Backwards-Kompatibilität).
PARK_RAIL_URL = _V21_RECORDS.format(ds="mobilitat")

_CACHE_TTL = 300.0  # 5 Minuten (Kapazitätsdaten ändern sich selten)
_cache: dict = {}
_cache_ts: float = 0.0


# ---------------------------------------------------------------------------
# Daten-Formatierung
# ---------------------------------------------------------------------------

def _format_facility(record: dict, lat_center: float, lon_center: float) -> dict | None:
    """
    Wandelt einen rohen SBB-Open-Data-Datensatz (station-mobility) in ein
    sauberes, LLM-freundliches Format um.

    Metapher: Wie ein Concierge, der aus einem technischen Parkplatz-
    Datenblatt eine nützliche Reisebeschreibung macht.

    Feldmapping (station-mobility):
      geopos → Koordinaten (lon/lat)
      stationsbezeichnung → Name/Bahnhof
      parkrail_anzahl → Anzahl Parkplätze
      parkrail_preis_tag / _monat / _jahr → Preise CHF
      parkrail_pflichtig_zeit1/2/3 → Öffnungszeiten
      parkrail_app / _webshop / _lokal / _automat → Buchungskanäle
    """
    # station-mobility liefert die Felder flach (kein verschachteltes 'fields')
    fields = record.get("fields", {}) or record

    # ── Koordinaten ────────────────────────────────────────────────────────
    # station-mobility: geopos = {"lon": ..., "lat": ...}
    geo = fields.get("geopos") or fields.get("geo_point_2d") or {}
    if isinstance(geo, dict):
        lat = geo.get("lat") or geo.get("latitude")
        lon = geo.get("lon") or geo.get("longitude")
    elif isinstance(geo, list) and len(geo) == 2:
        lat, lon = geo[0], geo[1]
    else:
        lat, lon = None, None

    if lat is None or lon is None:
        return None

    distance_km = haversine_km(lat_center, lon_center, float(lat), float(lon))

    # ── Kapazität ──────────────────────────────────────────────────────────
    # station-mobility: parkrail_anzahl (float, z.B. 58.0)
    total = (
        fields.get("parkrail_anzahl")
        or fields.get("anzahl_pp_total")
        or fields.get("total_pp")
        or 0
    )
    free = fields.get("anzahl_pp_frei") or fields.get("free_pp") or None

    # ── Preise ─────────────────────────────────────────────────────────────
    price_day = fields.get("parkrail_preis_tag")
    price_month = fields.get("parkrail_preis_monat")
    price_year = fields.get("parkrail_preis_jahr")

    # ── Öffnungszeiten ─────────────────────────────────────────────────────
    # station-mobility: parkrail_pflichtig_zeit1/2/3
    opening_parts = [
        fields.get("parkrail_pflichtig_zeit1"),
        fields.get("parkrail_pflichtig_zeit2"),
        fields.get("parkrail_pflichtig_zeit3"),
    ]
    opening_parts = [p for p in opening_parts if p]
    opening = (
        " / ".join(opening_parts)
        or fields.get("oeffnungszeiten")
        or fields.get("opening_hours")
        or "nicht angegeben"
    )

    # ── Name / Bahnhof ─────────────────────────────────────────────────────
    # station-mobility: stationsbezeichnung
    name = (
        fields.get("stationsbezeichnung")
        or fields.get("bezeichnung")
        or fields.get("name")
        or fields.get("bahnhof")
        or "Unbekannt"
    )
    station = name  # In station-mobility ist Name = Bahnhof

    result: dict = {
        "name": str(name),
        "station": str(station),
        "latitude": float(lat),
        "longitude": float(lon),
        "distance_km": round(distance_km, 3),
        "total_spaces": int(float(total)) if total else 0,
        "opening_hours": str(opening),
        "data_source": "SBB Open Data – station-mobility (data.sbb.ch)",
    }

    # Preise als strukturiertes Objekt
    if any(p is not None for p in [price_day, price_month, price_year]):
        result["price_chf"] = {
            k: float(v)
            for k, v in [
                ("day", price_day),
                ("month", price_month),
                ("year", price_year),
            ]
            if v is not None
        }

    # Buchungskanäle
    booking_channels = []
    if fields.get("parkrail_app"):
        booking_channels.append("App")
    if fields.get("parkrail_webshop"):
        booking_channels.append("Webshop")
    if fields.get("parkrail_lokal"):
        booking_channels.append("Vor Ort")
    if fields.get("parkrail_automat"):
        booking_channels.append("Automat")
    if booking_channels:
        result["booking_channels"] = booking_channels

    # Hinweis/Bemerkung
    remark = fields.get("parkrail_bemerkung")
    if remark:
        result["remark"] = str(remark)

    # Optionale Felder nur wenn vorhanden
    if free is not None:
        result["free_spaces"] = int(free)
        result["occupancy_pct"] = (
            round((1 - int(float(free)) / int(float(total))) * 100, 1)
            if float(total) > 0
            else None
        )

    for optional_key, field_name in [
        ("bike_parking", "veloabstellplaetze"),
    ]:
        val = fields.get(field_name)
        if val is not None:
            result[optional_key] = val

    return result


# ---------------------------------------------------------------------------
# Netzwerk-Helfer
# ---------------------------------------------------------------------------

async def _fetch_records(attempts: list[tuple[str, dict]]) -> list[dict]:
    """Probiert eine Liste von (URL, params)-Versuchen durch.

    Gibt die rohen Records der ersten 2xx-Antwort zurück (auch wenn leer –
    ein leeres, aber gültiges Resultat ist Erfolg). HTTP 400/404 und
    Netzwerkfehler führen zum nächsten Versuch. Erst wenn ALLE Versuche
    scheitern, wird ein APIError geworfen.
    """
    last_error = ""
    async with async_client(
        timeout=15.0,
        follow_redirects=True,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    ) as client:
        for url, params in attempts:
            try:
                response = await client.get(url, params=params)
                # 404 = Datensatz/Pfad unbekannt, 400 = Query-Feld passt nicht
                # zu diesem Datensatz/dieser API-Version → nächster Versuch.
                if response.status_code in (400, 404):
                    logger.warning(
                        "Park+Rail: %s liefert HTTP %s – nächster Kandidat wird versucht.",
                        url, response.status_code,
                    )
                    last_error = f"HTTP {response.status_code} bei {url}"
                    continue
                response.raise_for_status()
                data = response.json()
                # v2.1: results[]; v1: records[]
                return data.get("results") or data.get("records") or []
            except httpx.HTTPStatusError as e:
                # OBS-002: rohen Upstream-Body nur server-seitig loggen.
                logger.warning(
                    "Park+Rail: HTTP %s bei %s: %s",
                    e.response.status_code, url, e.response.text[:200],
                )
                last_error = f"HTTP {e.response.status_code} bei {url}"
            except httpx.TimeoutException:
                last_error = f"Timeout (15s) bei {url}"
                logger.warning("Park+Rail: %s", last_error)
            except httpx.ConnectError as e:
                last_error = f"Verbindungsfehler bei {url}: {e}"
                logger.warning("Park+Rail: %s", last_error)

    raise APIError(
        f"Alle SBB Park+Rail-Endpunkte nicht erreichbar. "
        f"Letzter Fehler: {last_error}. "
        "Bitte prüfe https://data.sbb.ch für den aktuellen Datensatz-Namen "
        "oder nutze opendata.swiss als Alternative."
    )


def _geo_search_attempts(
    latitude: float, longitude: float, radius_km: float, limit: int
) -> list[tuple[str, dict]]:
    """Baut die (URL, params)-Versuche für eine Umkreissuche.

    Pro Datensatz zwei Stile:
      1. Explore API v2.1 – Geofilter via ``within_distance()`` in ``where``.
      2. Legacy Records API v1 – nativer ``geofilter.distance`` (lat,lon,Meter).
    """
    radius_m = int(radius_km * 1000)
    rows = min(limit * 2, 100)  # mehr holen, dann clientseitig filtern/sortieren
    attempts: list[tuple[str, dict]] = []
    for ds in _PARK_RAIL_DATASETS:
        attempts.append((
            _V21_RECORDS.format(ds=ds),
            {
                # WKT-Reihenfolge: POINT(lon lat)
                "where": (
                    f"within_distance(geopos, geom'POINT({longitude} {latitude})', "
                    f"{radius_km}km)"
                ),
                "limit": rows,
                "offset": 0,
                "timezone": "Europe/Zurich",
            },
        ))
        attempts.append((
            _V1_SEARCH,
            {
                "dataset": ds,
                "geofilter.distance": f"{latitude},{longitude},{radius_m}",
                "rows": rows,
            },
        ))
    return attempts


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

    Nutzt den SBB Open Data Geofilter für Umkreissuche.
    Resultate sind nach Distanz sortiert.

    Args:
        latitude: Breitengrad des Suchzentrums
        longitude: Längengrad des Suchzentrums
        radius_km: Suchradius in Kilometern
        limit: Maximale Anzahl Resultate

    Returns:
        dict mit facilities-Liste, sortiert nach Distanz
    """
    global _cache, _cache_ts

    # ── Cache-Prüfung ──────────────────────────────────────────────────────
    cache_key = f"{latitude:.4f}_{longitude:.4f}_{radius_km}_{limit}"
    now = time.monotonic()
    if _cache and (now - _cache_ts) < _CACHE_TTL:
        if cache_key in _cache:
            logger.debug("Cache HIT: park_rail")
            return _cache[cache_key]

    # ── SBB Open Data API-Abfrage ──────────────────────────────────────────
    # Probiert v2.1- und v1-Stil über alle bekannten Datensätze durch und
    # liefert die Records der ersten erfolgreichen Antwort.
    raw_records = await _fetch_records(
        _geo_search_attempts(latitude, longitude, radius_km, limit)
    )

    facilities = []
    for rec in raw_records:
        # v2: direkt die Felder; v1: unter "fields"
        formatted = _format_facility(rec, latitude, longitude)
        if formatted is None:
            continue
        # Distanz-Filter als Sicherheitsnetz (API-Geofilter kann ungenau sein)
        if formatted["distance_km"] <= radius_km:
            facilities.append(formatted)

    # Nach Distanz sortieren
    facilities.sort(key=lambda x: x["distance_km"])
    facilities = facilities[:limit]

    result = {
        "search": {
            "latitude": latitude,
            "longitude": longitude,
            "radius_km": radius_km,
        },
        "found": len(facilities),
        "api_key_required": False,
        "data_source": "SBB Open Data Portal (data.sbb.ch) – kein API-Key nötig",
        "facilities": facilities,
    }

    # ── Cache befüllen ─────────────────────────────────────────────────────
    _cache[cache_key] = result
    _cache_ts = now

    return result


async def find_park_rail_by_station(station_name: str, limit: int = 5) -> dict:
    """
    Findet Park & Rail Anlagen für einen Bahnhof per Textsuche.

    Nützlich wenn man den Namen des Bahnhofs kennt, aber nicht die Koordinaten.

    Args:
        station_name: Bahnhofsname (z.B. 'Zürich HB', 'Winterthur', 'Bern')
        limit: Maximale Anzahl Resultate

    Returns:
        dict mit passenden Park & Rail Anlagen
    """
    # Volltextsuche über beide API-Stile / alle Datensätze. Anführungszeichen
    # im Suchbegriff werden entfernt, damit der ODSQL-where-Ausdruck nicht
    # zerbricht.
    safe_name = station_name.replace('"', "").replace("'", "")
    attempts: list[tuple[str, dict]] = []
    for ds in _PARK_RAIL_DATASETS:
        # Explore API v2.1: ein bloßer String in `where` ist Volltextsuche.
        attempts.append((
            _V21_RECORDS.format(ds=ds),
            {"where": f'"{safe_name}"', "limit": limit, "timezone": "Europe/Zurich"},
        ))
        # Legacy Records API v1: Freitextparameter `q`.
        attempts.append((
            _V1_SEARCH,
            {"dataset": ds, "q": safe_name, "rows": limit},
        ))

    raw_records = await _fetch_records(attempts)

    facilities = []
    for rec in raw_records:
        fields = rec.get("fields", {}) or rec
        geo = fields.get("geo_point_2d") or {}
        if isinstance(geo, dict):
            lat = geo.get("lat") or geo.get("latitude") or 0
            lon = geo.get("lon") or geo.get("longitude") or 0
        else:
            lat, lon = 0, 0
        formatted = _format_facility(rec, float(lat), float(lon))
        if formatted:
            facilities.append(formatted)

    return {
        "query": station_name,
        "found": len(facilities),
        "api_key_required": False,
        "data_source": "SBB Open Data Portal (data.sbb.ch)",
        "facilities": facilities,
    }
