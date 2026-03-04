"""
Multimodale Mobilitätslogik – Phase 3 Cross-Server-Modul.

Metapher: Phase 1 ist der Veloständer. Phase 2 ist die Signalanlage.
          Phase 3 ist der Reiseplaner, der beides kennt und sagt:
          «Fahr mit dem Auto bis Dietikon, park dort, nimm die S-Bahn –
          und an der Ecke wartet noch ein E-Trottinett auf dich.»

Das ist die Verknüpfungsschicht: Kein eigener KI-Agent,
sondern ein Datenaggregator, der aus mehreren Quellen ein
konsistentes, multimodales Bild zeichnet.

Datenquellen:
  1. transport.opendata.ch – ÖV-Fahrplanabfragen (kein API-Key)
  2. Interne Module: shared_mobility, ev_charging, park_rail (Phase 1+3)
  3. Optional: traffic_situations (Phase 2, API-Key)

transport.opendata.ch API:
  GET /v1/locations?x={lon}&y={lat} → Nächster Bahnhof
  GET /v1/connections?from=...&to=... → ÖV-Verbindungen
  Keine Authentifizierung nötig!
"""

import asyncio
import logging
import time

import httpx

from .api_infrastructure import APIError, haversine_km

logger = logging.getLogger("swiss-road-mobility-mcp")

# ---------------------------------------------------------------------------
# Konstanten: transport.opendata.ch
# ---------------------------------------------------------------------------

TRANSPORT_API_BASE = "https://transport.opendata.ch/v1"
LOCATIONS_URL = f"{TRANSPORT_API_BASE}/locations"
CONNECTIONS_URL = f"{TRANSPORT_API_BASE}/connections"

_TRANSPORT_TIMEOUT = 20.0

# ---------------------------------------------------------------------------
# Hilfsfunktionen: transport.opendata.ch
# ---------------------------------------------------------------------------

async def _find_nearest_station(latitude: float, longitude: float) -> dict | None:
    """
    Findet den nächsten ÖV-Haltepunkt zu gegebenen Koordinaten.

    Nutzt transport.opendata.ch /locations Endpunkt.
    Gibt None zurück wenn kein Bahnhof gefunden.
    """
    params = {
        "x": longitude,  # Achtung: API nimmt x=lon, y=lat
        "y": latitude,
        "type": "station",
    }

    async with httpx.AsyncClient(
        timeout=_TRANSPORT_TIMEOUT,
        headers={"User-Agent": "swiss-road-mobility-mcp/0.3.1"},
    ) as client:
        try:
            resp = await client.get(LOCATIONS_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
            logger.warning(f"transport.opendata.ch Locations-Fehler: {e}")
            return None

    stations = data.get("stations", [])
    if not stations:
        return None

    # Ersten (nächsten) Treffer nehmen
    best = stations[0]
    coord = best.get("coordinate", {})
    station_lat = coord.get("y")  # Achtung: API gibt y=lat zurück
    station_lon = coord.get("x")

    if station_lat is None or station_lon is None:
        return None

    dist = haversine_km(latitude, longitude, float(station_lat), float(station_lon))

    return {
        "id": best.get("id", ""),
        "name": best.get("name", ""),
        "latitude": float(station_lat),
        "longitude": float(station_lon),
        "distance_from_search_km": round(dist, 3),
    }


async def _find_stations_by_name(query: str, limit: int = 5) -> list[dict]:
    """
    Sucht ÖV-Stationen nach Name.
    Gibt Liste möglicher Treffer zurück.
    """
    params = {
        "query": query,
        "type": "station",
        "limit": limit,
    }

    async with httpx.AsyncClient(
        timeout=_TRANSPORT_TIMEOUT,
        headers={"User-Agent": "swiss-road-mobility-mcp/0.3.1"},
    ) as client:
        try:
            resp = await client.get(LOCATIONS_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Stations-Suche fehlgeschlagen: {e}")
            return []

    results = []
    for s in data.get("stations", []):
        coord = s.get("coordinate", {})
        results.append({
            "id": s.get("id", ""),
            "name": s.get("name", ""),
            "latitude": coord.get("y"),
            "longitude": coord.get("x"),
        })
    return results


async def _get_connections(
    from_station: str,
    to_destination: str,
    limit: int = 3,
) -> list[dict]:
    """
    Holt ÖV-Verbindungen zwischen zwei Punkten.

    Nutzt transport.opendata.ch /connections.
    Gibt formatierte Verbindungsliste zurück.
    """
    params = {
        "from": from_station,
        "to": to_destination,
        "limit": limit,
    }

    async with httpx.AsyncClient(
        timeout=_TRANSPORT_TIMEOUT,
        headers={"User-Agent": "swiss-road-mobility-mcp/0.3.1"},
    ) as client:
        try:
            resp = await client.get(CONNECTIONS_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            raise APIError(
                f"transport.opendata.ch HTTP {e.response.status_code}: "
                f"{e.response.text[:200]}"
            )
        except httpx.TimeoutException:
            raise APIError(f"Timeout bei ÖV-Abfrage ({from_station} → {to_destination}).")
        except httpx.ConnectError as e:
            raise APIError(f"Verbindungsfehler zu transport.opendata.ch: {e}")

    connections = []
    for conn in data.get("connections", []):
        # From / To
        from_info = conn.get("from", {})
        to_info = conn.get("to", {})

        # Sections (Teilabschnitte)
        sections = []
        for sec in conn.get("sections", []):
            sec_journey = sec.get("journey", {})
            sec_from = sec.get("departure", {})
            sec_to = sec.get("arrival", {})
            sec_walk = sec.get("walk")

            if sec_walk:
                sections.append({
                    "type": "walk",
                    "duration_min": sec_walk.get("duration", 0) // 60,
                })
            elif sec_journey:
                sections.append({
                    "type": "transit",
                    "line": sec_journey.get("name", ""),
                    "category": sec_journey.get("category", ""),
                    "departure": sec_from.get("departure", ""),
                    "arrival": sec_to.get("arrival", ""),
                    "from_station": sec_from.get("station", {}).get("name", ""),
                    "to_station": sec_to.get("station", {}).get("name", ""),
                })

        # Bug #3 Fix: transport.opendata.ch gibt 'duration' als String
        # im Format 'HH:MM:SS' zurück, nicht als Integer (Sekunden).
        # Robuste Konvertierung: String → Sekunden → Minuten.
        dur_raw = conn.get("duration", 0) or 0
        if isinstance(dur_raw, str) and ":" in dur_raw:
            try:
                parts = dur_raw.split(":")
                dur_seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            except (ValueError, IndexError):
                logger.warning(f"Unbekanntes Duration-Format: '{dur_raw}', setze 0.")
                dur_seconds = 0
        else:
            try:
                dur_seconds = int(dur_raw)
            except (TypeError, ValueError):
                dur_seconds = 0
        duration_min = dur_seconds // 60

        connections.append({
            "departure": from_info.get("departure", ""),
            "arrival": to_info.get("arrival", ""),
            "duration_min": duration_min,
            "transfers": conn.get("transfers", 0),
            "sections": sections,
        })

    return connections


# ---------------------------------------------------------------------------
# Mobility Snapshot (aggregiert alle verfügbaren Quellen)
# ---------------------------------------------------------------------------

async def build_mobility_snapshot(
    latitude: float,
    longitude: float,
    radius_meters: int = 500,
    radius_km_ev: float = 1.0,
    radius_km_park: float = 5.0,
    has_api_key: bool = False,
    api_key: str | None = None,
) -> dict:
    """
    Erstellt eine vollständige Mobilitäts-Momentaufnahme für einen Standort.

    Aggregiert parallel:
    - Shared Mobility (Phase 1)
    - EV-Ladestationen (Phase 1)
    - Park & Rail (Phase 3, SBB Open Data)
    - Nächster Bahnhof (transport.opendata.ch)
    - Optionale Verkehrsmeldungen (Phase 2, API-Key nötig)

    Metapher: Der Kontrollturm, der alle Signale gleichzeitig empfängt
    und dem Piloten ein einheitliches Lagebild gibt.

    Returns:
        dict mit snapshot_at, location, und allen Mobilitätsdaten
    """
    from . import shared_mobility, ev_charging, park_rail
    from .api_infrastructure import MobilityHTTPClient, RateLimiter

    client = MobilityHTTPClient()
    client.register_limiter("sharedmobility", RateLimiter(max_requests=30, window_seconds=60))
    client.register_limiter("ev_charging", RateLimiter(max_requests=10, window_seconds=60))

    # ── Parallele Abfragen ─────────────────────────────────────────────────
    tasks = {
        "sharing": shared_mobility.find_nearby_vehicles(
            client=client,
            longitude=longitude,
            latitude=latitude,
            radius_meters=radius_meters,
            vehicle_type=None,
            pickup_type=None,
            only_available=True,
        ),
        "ev": ev_charging.find_nearby_chargers(
            client=client,
            longitude=longitude,
            latitude=latitude,
            radius_km=radius_km_ev,
            only_available=False,
            include_details=False,
            limit=5,
        ),
        "park_rail": park_rail.find_nearby_park_rail(
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km_park,
            limit=5,
        ),
        "nearest_station": _find_nearest_station(latitude, longitude),
    }

    results = {}
    for key, coro in tasks.items():
        try:
            results[key] = await coro
        except Exception as e:
            logger.warning(f"Snapshot-Teilabfrage '{key}' fehlgeschlagen: {e}")
            results[key] = {"error": str(e)}

    # ── Optionale Phase-2-Daten ────────────────────────────────────────────
    if has_api_key and api_key:
        from . import traffic_situations
        try:
            results["traffic_situations"] = await traffic_situations.fetch_situations(
                api_key=api_key,
                filter_type=None,
                active_only=True,
                limit=5,
            )
        except Exception as e:
            results["traffic_situations"] = {"error": str(e)}
    else:
        results["traffic_situations"] = {
            "note": "Phase-2-Daten (Verkehrsmeldungen) benötigen OPENTRANSPORTDATA_API_KEY.",
            "register": "https://api-manager.opentransportdata.swiss",
        }

    await client.close()

    return {
        "snapshot_location": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "search_radii": {
            "shared_mobility_m": radius_meters,
            "ev_charging_km": radius_km_ev,
            "park_rail_km": radius_km_park,
        },
        "nearest_station": results.get("nearest_station"),
        "shared_mobility": results.get("sharing"),
        "ev_charging": results.get("ev"),
        # Bug #4 Fix: park_rail kann None oder {"error": ...} sein, wenn
        # die SBB-API nicht erreichbar ist. Immer auf None prüfen, bevor
        # wir .get() aufrufen – sonst AttributeError «NoneType has no attribute get».
        "park_rail": results.get("park_rail") or {
            "found": 0,
            "facilities": [],
            "note": "Park+Rail-Daten nicht verfügbar (SBB-Endpunkt nicht erreichbar).",
        },
        "traffic_situations": results.get("traffic_situations"),
        "data_sources": [
            "sharedmobility.ch (kein Key)",
            "ich-tanke-strom.ch (kein Key)",
            "SBB Open Data – data.sbb.ch (kein Key)",
            "transport.opendata.ch (kein Key)",
            "opentransportdata.swiss DATEX II (Key nötig, optional)",
        ],
    }


# ---------------------------------------------------------------------------
# Multimodaler Reiseplan
# ---------------------------------------------------------------------------

async def plan_multimodal_trip(
    start_latitude: float,
    start_longitude: float,
    destination: str,
    park_rail_radius_km: float = 10.0,
) -> dict:
    """
    Plant eine multimodale Reise: Auto → Park & Rail → ÖV → Ziel.

    Workflow:
    1. Nächster Bahnhof zum Start finden (als Park & Rail Kandidat)
    2. Park & Rail Anlagen in der Nähe des Starts prüfen
    3. ÖV-Verbindungen vom nächsten Bahnhof zum Ziel abfragen
    4. Sharing-Optionen am Start für «letzte Meile zum Bahnhof»
    5. Alles zu einem Reiseplan zusammenführen

    Metapher: Der Reiseplaner kombiniert alle Zutaten –
    Parkplatz, Bahn, Bus, Velo – zu einem einzigen Rezept.

    Args:
        start_latitude: Startposition (Breitengrad)
        start_longitude: Startposition (Längengrad)
        destination: Zielort (Bahnhofsname oder Stadt, z.B. 'Bern', 'Zürich HB')
        park_rail_radius_km: Suchradius für Park & Rail ab Startposition

    Returns:
        dict mit vollständigem multimodalem Reiseplan
    """
    from . import shared_mobility, park_rail
    from .api_infrastructure import MobilityHTTPClient, RateLimiter

    client = MobilityHTTPClient()
    client.register_limiter("sharedmobility", RateLimiter(max_requests=30, window_seconds=60))

    # ── Schritt 1: Nächster Bahnhof + Park & Rail + Sharing parallel ───────
    nearest_station_task = _find_nearest_station(start_latitude, start_longitude)
    park_rail_task = park_rail.find_nearby_park_rail(
        latitude=start_latitude,
        longitude=start_longitude,
        radius_km=park_rail_radius_km,
        limit=3,
    )
    sharing_task = shared_mobility.find_nearby_vehicles(
        client=client,
        longitude=start_longitude,
        latitude=start_latitude,
        radius_meters=500,
        vehicle_type=None,
        pickup_type=None,
        only_available=True,
    )

    nearest_station, park_rail_result, sharing_result = await asyncio.gather(
        nearest_station_task,
        park_rail_task,
        sharing_task,
        return_exceptions=True,
    )

    await client.close()

    # Fehlerbehandlung für parallele Tasks
    if isinstance(nearest_station, Exception):
        nearest_station = None
    if isinstance(park_rail_result, Exception):
        park_rail_result = {"error": str(park_rail_result), "facilities": []}
    if isinstance(sharing_result, Exception):
        sharing_result = {"error": str(sharing_result), "vehicles": []}

    # ── Schritt 2: ÖV-Verbindungen vom nächsten Bahnhof zum Ziel ──────────
    connections = []
    connection_from = None

    if nearest_station and nearest_station.get("name"):
        connection_from = nearest_station["name"]
        try:
            connections = await _get_connections(
                from_station=connection_from,
                to_destination=destination,
                limit=3,
            )
        except APIError as e:
            logger.warning(f"ÖV-Verbindung fehlgeschlagen: {e}")

    # ── Schritt 3: Empfohlene Park & Rail Anlage ───────────────────────────
    facilities = (
        park_rail_result.get("facilities", [])
        if isinstance(park_rail_result, dict)
        else []
    )
    recommended_facility = facilities[0] if facilities else None

    # ── Schritt 4: Last-Mile-Optionen am Start ─────────────────────────────
    sharing_vehicles = []
    if isinstance(sharing_result, dict):
        for item in (sharing_result.get("vehicles") or sharing_result.get("stations") or []):
            if isinstance(item, dict):
                sharing_vehicles.append({
                    "type": item.get("vehicle_type") or item.get("type", ""),
                    "provider": item.get("provider_name") or item.get("provider", ""),
                    "distance_m": item.get("distance_m"),
                    "available": item.get("available"),
                })
        sharing_vehicles = sharing_vehicles[:3]

    # ── Schritt 5: Reiseplan zusammenführen ───────────────────────────────
    plan_steps = []

    if sharing_vehicles:
        plan_steps.append({
            "step": 1,
            "mode": "shared_vehicle",
            "description": f"Sharing-Option zum Bahnhof: {sharing_vehicles[0].get('type', 'Fahrzeug')} ({sharing_vehicles[0].get('provider', '')})",
            "options": sharing_vehicles,
        })

    if recommended_facility:
        plan_steps.append({
            "step": len(plan_steps) + 1,
            "mode": "park_and_rail",
            "description": (
                f"Parkieren bei: {recommended_facility.get('name', 'P+R Anlage')} "
                f"({recommended_facility.get('total_spaces', '?')} Plätze, "
                f"Tarif: {recommended_facility.get('tarif_category', 'unbekannt')})"
            ),
            "facility": recommended_facility,
        })

    if connection_from and connections:
        best_conn = connections[0]
        plan_steps.append({
            "step": len(plan_steps) + 1,
            "mode": "public_transport",
            "description": (
                f"ÖV ab {connection_from}: "
                f"Abfahrt {best_conn.get('departure', '?')}, "
                f"Ankunft {best_conn.get('arrival', '?')}, "
                f"Dauer {best_conn.get('duration_min', '?')} min, "
                f"{best_conn.get('transfers', 0)} Umsteigen"
            ),
            "connections": connections,
        })
    elif not connections:
        plan_steps.append({
            "step": len(plan_steps) + 1,
            "mode": "public_transport",
            "description": f"Keine ÖV-Verbindung von '{connection_from}' nach '{destination}' gefunden.",
            "hint": "Versuche einen anderen Zielort oder prüfe transport.opendata.ch direkt.",
        })

    return {
        "route": {
            "start": {"latitude": start_latitude, "longitude": start_longitude},
            "destination": destination,
        },
        "nearest_station": nearest_station,
        "recommended_park_rail": recommended_facility,
        "plan_steps": plan_steps,
        "all_park_rail_options": facilities,
        "all_ov_connections": connections,
        "last_mile_sharing": sharing_vehicles,
        "data_sources": [
            "SBB Open Data – Park & Rail (kein Key)",
            "transport.opendata.ch – ÖV-Verbindungen (kein Key)",
            "sharedmobility.ch – Sharing (kein Key)",
        ],
        "api_keys_required": "keine – Phase-3-Tools sind vollständig offen",
    }
