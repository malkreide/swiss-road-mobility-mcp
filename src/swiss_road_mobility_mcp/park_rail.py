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

from .api_infrastructure import APIError, haversine_km

logger = logging.getLogger("swiss-road-mobility-mcp")

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# Verifizierter Endpunkt (Stand März 2026).
# Das ursprüngliche Dataset 'park-and-rail' wurde von SBB entfernt (HTTP 404).
# Ersatz: 'station-mobility' enthält alle Park+Rail-Felder:
#   parkrail_anzahl, parkrail_preis_tag, parkrail_preis_monat, parkrail_preis_jahr,
#   parkrail_app, parkrail_webshop, parkrail_lokal, parkrail_automat, geopos usw.
# Geofilter-Syntax (Opendatasoft ODSQL v2):
#   ?where=parkrail_anzahl>0 AND distance(geopos,geom'POINT(lon lat)',Xkm)
PARK_RAIL_URL = (
    "https://data.sbb.ch/api/explore/v2.1/catalog/datasets/station-mobility/records"
)

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
        ("bike_parking", "veloabstellplaetze"),
    ]:
        val = fields.get(field_name)
        if val is not None:
            result[optional_key] = val

    return result


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

    radius_m = int(radius_km * 1000)

    # ── SBB Open Data API-Abfrage ──────────────────────────────────────────
    # Geofilter im Opendatasoft-Format
    params = {
        "limit": min(limit * 2, 100),  # Mehr holen, dann filtern
        "offset": 0,
        "geofilter.distance": f"{latitude},{longitude},{radius_m}",
        "order_by": "anzahl_pp_total desc",
        "timezone": "Europe/Zurich",
    }

    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=True,
        headers={
            "User-Agent": "swiss-road-mobility-mcp/0.3.1",
            "Accept": "application/json",
        },
    ) as client:
        # Bug #1 Fix: Fallback-Kette über mehrere Endpunkt-Namen.
        # SBB hat den Datensatz «park-and-rail» umbenannt; wir probieren
        # alle bekannten Kandidaten durch, bis einer antwortet.
        data = None
        last_error: str = ""
        for candidate_url in _PARK_RAIL_CANDIDATES:
            try:
                response = await client.get(candidate_url, params=params)
                if response.status_code == 404:
                    logger.warning(
                        f"Park+Rail: Endpunkt {candidate_url} liefert 404 – "
                        "nächster Kandidat wird versucht."
                    )
                    last_error = f"HTTP 404 bei {candidate_url}"
                    continue
                response.raise_for_status()
                data = response.json()
                break  # Erfolg – Schleife verlassen
            except httpx.HTTPStatusError as e:
                last_error = (
                    f"SBB Open Data HTTP {e.response.status_code} "
                    f"bei {candidate_url}: {e.response.text[:200]}"
                )
                logger.warning(f"Park+Rail: {last_error}")
            except httpx.TimeoutException:
                last_error = f"Timeout (15s) bei {candidate_url}"
                logger.warning(f"Park+Rail: {last_error}")
            except httpx.ConnectError as e:
                last_error = f"Verbindungsfehler bei {candidate_url}: {e}"
                logger.warning(f"Park+Rail: {last_error}")

        if data is None:
            raise APIError(
                f"Alle SBB Park+Rail-Endpunkte nicht erreichbar. "
                f"Letzter Fehler: {last_error}. "
                "Bitte prüfe https://data.sbb.ch für den aktuellen Datensatz-Namen "
                "oder nutze opendata.swiss als Alternative."
            )

    # ── JSON-Parsing ───────────────────────────────────────────────────────
    # Opendatasoft v2 gibt records[] zurück
    raw_records = data.get("results") or data.get("records") or []

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
    # Textbasierte Suche via Opendatasoft WHERE-Klausel
    params = {
        "limit": limit,
        "where": f"search(bezeichnung, \"{station_name}\") or search(bahnhof, \"{station_name}\")",
        "timezone": "Europe/Zurich",
    }

    async with httpx.AsyncClient(
        timeout=15.0,
        follow_redirects=True,
        headers={
            "User-Agent": "swiss-road-mobility-mcp/0.3.1",
            "Accept": "application/json",
        },
    ) as client:
        try:
            response = await client.get(PARK_RAIL_URL, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            raise APIError(
                f"SBB Open Data HTTP {e.response.status_code}: "
                f"{e.response.text[:200]}"
            )
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            raise APIError(f"Verbindungsfehler zur SBB Open Data API: {e}")

    raw_records = data.get("results") or data.get("records") or []

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
