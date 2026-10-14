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
import re

import httpx

from . import USER_AGENT
from .api_infrastructure import APIError, haversine_km
from .egress import async_client

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

    Achtung Achsen: Bei transport.opendata.ch ist `x` der Breitengrad und `y`
    der Laengengrad — in der Anfrage wie in der Antwort (docs.html: «x
    Latitude», «y Longitude»). Hier stand bis 14.10.2026 das Umgekehrte. Die
    Quelle hat die vertauschte Anfrage lange stillschweigend richtig
    beantwortet (Aufzeichnung vom 15.8.2026: Bern, Distanz 0); seit dem
    naechtlichen Lauf vom 6.10.2026 nimmt sie sie woertlich und lieferte fuer
    Zuerich HB «Ancona», 4971 km.

    `type=station` wirkt laut derselben Doku nur zusammen mit `query`. Bei der
    Koordinatensuche kommen deshalb auch Adressen zurueck — ohne `id` und
    zum Teil ohne Koordinaten, und oft zuoberst. Genommen wird darum der
    erste Treffer mit `id` und Koordinaten, nicht der erste ueberhaupt; der
    erste ueberhaupt war am 15.8.2026 eine Adresse ohne Koordinaten, und die
    Funktion gab still `None` zurueck.
    """
    params = {
        "x": latitude,
        "y": longitude,
        "type": "station",
    }

    async with async_client(
        timeout=_TRANSPORT_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        try:
            resp = await client.get(LOCATIONS_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as e:
            logger.warning(f"transport.opendata.ch Locations-Fehler: {e}")
            return None

    # Ersten Haltepunkt nehmen (die Quelle sortiert nach Distanz); Adressen
    # tragen keine `id`.
    best = next(
        (
            s
            for s in data.get("stations") or []
            if s.get("id")
            and (s.get("coordinate") or {}).get("x") is not None
            and (s.get("coordinate") or {}).get("y") is not None
        ),
        None,
    )
    if best is None:
        return None

    coord = best["coordinate"]
    station_lat = coord["x"]
    station_lon = coord["y"]

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

    async with async_client(
        timeout=_TRANSPORT_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
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
        results.append(
            {
                "id": s.get("id", ""),
                "name": s.get("name", ""),
                "latitude": coord.get("x"),  # x = Breitengrad, siehe oben
                "longitude": coord.get("y"),
            }
        )
    return results


# Die Dauer einer Verbindung, wie transport.opendata.ch sie schreibt:
# Tage, ein «d», dann Stunden:Minuten:Sekunden — «00d01:11:00» (docs.html,
# Connection Object: «duration … 00d00:43:00»). Gemessen am 14.10.2026 an
# sieben Verbindungen (Zuerich–Bern, Zuerich–Genf, Basel–Lugano): alle in
# dieser Form. Der Tagesteil bleibt optional, damit auch «01:11:00» traegt.
_DAUER = re.compile(r"^(?:(\d+)d)?(\d+):(\d{2}):(\d{2})$")


def _dauer_in_sekunden(roh: object) -> int | None:
    """
    `duration` einer Verbindung in Sekunden, oder `None`, wenn unlesbar.

    Bis 14.10.2026 erwartete der Parser «HH:MM:SS» und scheiterte an jedem
    «00d…»: `int("00d01")` wirft, und der Fehlerzweig setzte 0. Jede
    Verbindung stand damit mit «Dauer 0 min» im Reiseplan.

    `None` statt 0 fuer das Unlesbare: «0 Minuten» ist eine Auskunft, und
    zwar eine falsche, die ein Modell ungeprueft weitergibt. «Unbekannt» ist
    die richtige.
    """
    if roh is None or roh == "":
        return None
    if isinstance(roh, bool):
        return None
    if isinstance(roh, int):
        return roh
    if isinstance(roh, str):
        treffer = _DAUER.match(roh.strip())
        if treffer:
            tage, stunden, minuten, sekunden = treffer.groups()
            return ((int(tage or 0) * 24 + int(stunden)) * 60 + int(minuten)) * 60 + int(sekunden)
    logger.warning("Unbekanntes Duration-Format: %r — Dauer bleibt unbekannt.", roh)
    return None


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

    async with async_client(
        timeout=_TRANSPORT_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        try:
            resp = await client.get(CONNECTIONS_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "transport.opendata.ch HTTP %s: %s",
                e.response.status_code,
                e.response.text[:200],
            )
            raise APIError(f"transport.opendata.ch antwortete mit HTTP {e.response.status_code}.")
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
                sections.append(
                    {
                        "type": "walk",
                        "duration_min": sec_walk.get("duration", 0) // 60,
                    }
                )
            elif sec_journey:
                sections.append(
                    {
                        "type": "transit",
                        "line": sec_journey.get("name", ""),
                        "category": sec_journey.get("category", ""),
                        "departure": sec_from.get("departure", ""),
                        "arrival": sec_to.get("arrival", ""),
                        "from_station": sec_from.get("station", {}).get("name", ""),
                        "to_station": sec_to.get("station", {}).get("name", ""),
                    }
                )

        dur_seconds = _dauer_in_sekunden(conn.get("duration"))
        duration_min = None if dur_seconds is None else dur_seconds // 60

        connections.append(
            {
                "departure": from_info.get("departure", ""),
                "arrival": to_info.get("arrival", ""),
                "duration_min": duration_min,
                "transfers": conn.get("transfers", 0),
                "sections": sections,
            }
        )

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
    from . import ev_charging, park_rail, shared_mobility
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
            results[key] = {"error": "Diese Teilquelle ist momentan nicht verfügbar."}

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
            logger.warning("Snapshot Phase-2 'traffic_situations' fehlgeschlagen: %s", e)
            results["traffic_situations"] = {"error": "Verkehrsmeldungen momentan nicht verfügbar."}
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
        "park_rail": results.get("park_rail")
        or {
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
    from . import park_rail, shared_mobility
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
    facilities = park_rail_result.get("facilities", []) if isinstance(park_rail_result, dict) else []
    recommended_facility = facilities[0] if facilities else None

    # ── Schritt 4: Last-Mile-Optionen am Start ─────────────────────────────
    sharing_vehicles = []
    if isinstance(sharing_result, dict):
        for item in sharing_result.get("vehicles") or sharing_result.get("stations") or []:
            if isinstance(item, dict):
                sharing_vehicles.append(
                    {
                        "type": item.get("vehicle_type") or item.get("type", ""),
                        "provider": item.get("provider_name") or item.get("provider", ""),
                        "distance_m": item.get("distance_m"),
                        "available": item.get("available"),
                    }
                )
        sharing_vehicles = sharing_vehicles[:3]

    # ── Schritt 5: Reiseplan zusammenführen ───────────────────────────────
    plan_steps = []

    if sharing_vehicles:
        plan_steps.append(
            {
                "step": 1,
                "mode": "shared_vehicle",
                "description": f"Sharing-Option zum Bahnhof: {sharing_vehicles[0].get('type', 'Fahrzeug')} ({sharing_vehicles[0].get('provider', '')})",
                "options": sharing_vehicles,
            }
        )

    if recommended_facility:
        plan_steps.append(
            {
                "step": len(plan_steps) + 1,
                "mode": "park_and_rail",
                "description": (
                    f"Parkieren bei: {recommended_facility.get('name', 'P+R Anlage')} "
                    f"({recommended_facility.get('total_spaces', '?')} Plätze, "
                    f"Tarif: {recommended_facility.get('tarif_category', 'unbekannt')})"
                ),
                "facility": recommended_facility,
            }
        )

    if connection_from and connections:
        best_conn = connections[0]
        plan_steps.append(
            {
                "step": len(plan_steps) + 1,
                "mode": "public_transport",
                "description": (
                    f"ÖV ab {connection_from}: "
                    f"Abfahrt {best_conn.get('departure', '?')}, "
                    f"Ankunft {best_conn.get('arrival', '?')}, "
                    + (
                        f"Dauer {best_conn['duration_min']} min, "
                        if best_conn.get("duration_min") is not None
                        else "Dauer unbekannt, "
                    )
                    + f"{best_conn.get('transfers', 0)} Umsteigen"
                ),
                "connections": connections,
            }
        )
    elif not connections:
        plan_steps.append(
            {
                "step": len(plan_steps) + 1,
                "mode": "public_transport",
                "description": f"Keine ÖV-Verbindung von '{connection_from}' nach '{destination}' gefunden.",
                "hint": "Versuche einen anderen Zielort oder prüfe transport.opendata.ch direkt.",
            }
        )

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
