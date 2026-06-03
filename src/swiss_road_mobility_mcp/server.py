"""Swiss Road & Mobility MCP Server – Phase 1 + Phase 2 + Phase 3.

MCP Server for Swiss road mobility data.

Metapher: Wenn der Swiss Transport MCP das GA für die Schiene ist,
dann ist dieser Server die Vignette + Sharing-Abo + Park-&-Rail-Karte
für die Strasse. Zusammen: Das vollständige multimodale Schweizer Mobilitätsbild.

Phase 1 (6 Tools, kein API-Key nötig):
  - Shared Mobility: Velos, E-Bikes, E-Trottis, Autos (api.sharedmobility.ch)
  - E-Ladestationen: Standorte + Echtzeit-Verfügbarkeit (ich-tanke-strom.ch)

Phase 2 (3 Tools, API-Key nötig – kostenlos):
  - DATEX II: Verkehrsmeldungen (Unfälle, Baustellen, Staus) vom ASTRA/VMZ-CH
  - Traffic Counters: Echtzeit-Verkehrsaufkommen an Schweizer Zählstellen

  API-Key (Phase 2): Kostenlos auf api-manager.opentransportdata.swiss
  → Umgebungsvariable OPENTRANSPORTDATA_API_KEY setzen

Phase 3 (3 Tools, kein API-Key nötig):
  - Park & Rail: SBB Parkplätze an Bahnhöfen (SBB Open Data)
  - Mobilitäts-Snapshot: Vollständiges Lagebild für einen Standort
  - Multimodaler Reiseplan: Auto → Park & Rail → ÖV → Ziel
"""

import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, ConfigDict, Field

from . import ev_charging, geo_admin, multimodal, park_rail, shared_mobility, traffic_counters, traffic_situations
from .api_infrastructure import APIError, MobilityHTTPClient
from .client_lifecycle import build_client, managed_client
from .egress import async_client
from .errors import unexpected_error, upstream_error
from .logging_config import configure_logging
from .security import BearerAuthMiddleware, RateLimitMiddleware, middleware_config
from .tracing import configure_tracing, instrument_asgi

logger = logging.getLogger("swiss-road-mobility-mcp")

# ---------------------------------------------------------------------------
# Server initialization
# ---------------------------------------------------------------------------

# Shared HTTP client, owned by the lifespan (SDK-001). Created at startup,
# closed deterministically at shutdown.
_client: MobilityHTTPClient | None = None


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """SDK-001: manage the shared HTTP client for the server's lifetime."""
    global _client
    async with managed_client() as client:
        _client = client
        try:
            yield {}
        finally:
            _client = None


mcp = FastMCP(
    "swiss_road_mobility_mcp",
    instructions=(
        "Swiss road and mobility data server with 15 tools (Phase 1 + Phase 2 + Phase 3 + Phase 4). "
        "Phase 1 (no API key): shared vehicles (road_find_sharing, road_search_sharing, road_sharing_providers), "
        "EV chargers (road_find_charger, road_charger_status), system check (road_check_status). "
        "Phase 2 (free API key from api-manager.opentransportdata.swiss): "
        "traffic events/accidents/roadworks (road_traffic_situations), "
        "real-time vehicle counts (road_traffic_counters), "
        "measurement site locations (road_counter_sites). "
        "Phase 3 (no API key – fully open): "
        "Park+Rail facilities at train stations (road_park_rail), "
        "complete mobility snapshot for a location (road_mobility_snapshot), "
        "multimodal trip planner combining car+park+rail+PT (road_multimodal_plan). "
        "Set OPENTRANSPORTDATA_API_KEY environment variable for Phase 2 tools. "
        "Data sources: sharedmobility.ch, ich-tanke-strom.ch, opentransportdata.swiss (ASTRA DATEX II), "
        "SBB Open Data (data.sbb.ch), transport.opendata.ch. "
        "Phase 4 (no API key – fully open): "
        "Swiss address geocoding from official federal registry (road_geocode_address), "
        "reverse geocoding to nearest official address (road_reverse_geocode), "
        "official road classification via swissTLM3D (road_classify_road). "
        "Data source: geo.admin.ch / swisstopo. "
        "<use_case>User: 'Find an e-bike near Zürich HB' -> road_find_sharing.</use_case> "
        "<use_case>User: 'Where can I charge my EV near Bern?' -> road_find_charger.</use_case> "
        "<use_case>User: 'I'm in Dietikon with a car and need to get to Bern' -> "
        "road_multimodal_plan.</use_case> "
        "<use_case>User: 'Show me everything mobility-related at this location' -> "
        "road_mobility_snapshot.</use_case>"
    ),
    lifespan=_lifespan,
)


# ===========================================================================
# Shared HTTP Client accessor
# ===========================================================================

def _get_client() -> MobilityHTTPClient:
    """Return the lifespan-managed shared client.

    Normally the FastMCP lifespan creates it at startup. The lazy fallback only
    triggers when a tool function is called outside a running server (e.g. unit
    tests that import and call tools directly); such a client is not lifespan-
    closed, which is acceptable in those short-lived contexts.
    """
    global _client
    if _client is None:
        _client = build_client()
    return _client


def _get_api_key() -> str | None:
    """Liest den opentransportdata.swiss API-Key aus der Umgebungsvariable."""
    return os.environ.get("OPENTRANSPORTDATA_API_KEY")


def _require_api_key() -> str:
    """
    Gibt den API-Key zurück oder wirft einen sprechenden APIError.

    Metapher: Wie ein Ticketautomat – ohne Ticket kein Durchgang,
    aber der Automat erklärt genau, wo das Ticket erhältlich ist.
    """
    key = _get_api_key()
    if not key:
        raise APIError(
            "Für dieses Phase-2-Tool ist ein kostenloser API-Key von "
            "opentransportdata.swiss erforderlich. "
            "Registrierung: https://api-manager.opentransportdata.swiss "
            "Nach Erhalt: OPENTRANSPORTDATA_API_KEY als Umgebungsvariable setzen. "
            "Claude Desktop: In claude_desktop_config.json unter 'env' eintragen."
        )
    return key



# ===========================================================================
# Input Models – Shared Mobility
# ===========================================================================

class FindSharingInput(BaseModel):
    """Input for finding nearby shared mobility vehicles/stations."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    latitude: float = Field(
        ...,
        description=(
            "Latitude (Breitengrad) of search center. "
            "Examples: 47.3769 (Zürich HB), 46.9480 (Bern), 47.5596 (Winterthur)"
        ),
        ge=45.5,
        le=48.0,
    )
    longitude: float = Field(
        ...,
        description=(
            "Longitude (Längengrad) of search center. "
            "Examples: 8.5417 (Zürich HB), 7.4474 (Bern), 8.7240 (Winterthur)"
        ),
        ge=5.5,
        le=10.8,
    )
    radius_meters: int = Field(
        default=500,
        description="Search radius in meters (50–5000). Default: 500m",
        ge=50,
        le=5000,
    )
    vehicle_type: str | None = Field(
        default=None,
        description=(
            "Filter by vehicle type. Options: "
            "Bicycle, E-Bike, E-Scooter, E-Moped, Car, E-Car, Cargo-Bicycle. "
            "Leave empty for all types."
        ),
    )
    pickup_type: str | None = Field(
        default=None,
        description=(
            "Filter by pickup type: 'free_floating' (überall abstellen) "
            "or 'station_based' (an Station zurückgeben). Leave empty for both."
        ),
    )
    only_available: bool = Field(
        default=True,
        description="Only show currently available vehicles/stations (default: true)",
    )


class SearchSharingInput(BaseModel):
    """Input for searching shared mobility stations by name."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    search_text: str = Field(
        ...,
        description=(
            "Search text for station name or address. "
            "Examples: 'Bahnhof', 'ETH', 'Bellevue', 'Hauptbahnhof'"
        ),
        min_length=2,
        max_length=200,
    )
    provider_id: str | None = Field(
        default=None,
        description=(
            "Filter by provider ID (e.g., 'publibike_zurich', 'voiscooters.com'). "
            "Use road_sharing_providers to get available IDs."
        ),
    )
    limit: int = Field(
        default=20,
        description="Maximum number of results (1–50)",
        ge=1,
        le=50,
    )


# ===========================================================================
# Input Models – EV Charging
# ===========================================================================

class FindChargerInput(BaseModel):
    """Input for finding nearby EV charging stations."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    latitude: float = Field(
        ...,
        description=(
            "Latitude of search center. "
            "Examples: 47.3769 (Zürich HB), 46.9480 (Bern)"
        ),
        ge=45.5,
        le=48.0,
    )
    longitude: float = Field(
        ...,
        description=(
            "Longitude of search center. "
            "Examples: 8.5417 (Zürich HB), 7.4474 (Bern)"
        ),
        ge=5.5,
        le=10.8,
    )
    radius_km: float = Field(
        default=2.0,
        description="Search radius in kilometers (0.1–50). Default: 2 km",
        ge=0.1,
        le=50.0,
    )
    only_available: bool = Field(
        default=False,
        description=(
            "Only show stations with status 'Available' (free). "
            "Default: false (show all, including occupied/unknown)"
        ),
    )
    include_details: bool = Field(
        default=True,
        description=(
            "Include full details (plug types, power, operator). "
            "Set to false for faster, smaller response."
        ),
    )
    limit: int = Field(
        default=20,
        description="Maximum number of results (1–50)",
        ge=1,
        le=50,
    )


class ChargerStatusInput(BaseModel):
    """Input for checking EV charger real-time status."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    station_ids: list[str] = Field(
        default=[],
        description=(
            "List of charging station IDs to check (e.g., ['CH*SWI*E10382']). "
            "Leave empty for overall statistics of ALL Swiss charging points."
        ),
        max_length=20,
    )


# ===========================================================================
# Tool 1: Find Nearby Sharing Vehicles
# ===========================================================================

@mcp.tool(
    name="road_find_sharing",
    annotations={
        "title": "Find Shared Mobility Nearby",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def road_find_sharing(params: FindSharingInput) -> dict[str, Any]:
    """Find shared mobility vehicles and stations near a location in Switzerland.

    Searches for bikes, e-bikes, e-scooters, cars, and other shared
    vehicles within a radius around GPS coordinates. Returns real-time
    availability data from sharedmobility.ch.

    Like checking a mobility app: "What sharing options are near me?"

    Data source: sharedmobility.ch (Swiss Federal Office of Energy).
    No API key required – completely open data!

    Returns:
        JSON with nearby vehicles/stations, grouped by type,
        with availability status and booking app links.
    """
    try:
        result = await shared_mobility.find_nearby_vehicles(
            client=_get_client(),
            longitude=params.longitude,
            latitude=params.latitude,
            radius_meters=params.radius_meters,
            vehicle_type=params.vehicle_type,
            pickup_type=params.pickup_type,
            only_available=params.only_available,
        )
        return result
    except APIError as e:
        return upstream_error(e)
    except Exception:
        return unexpected_error()


# ===========================================================================
# Tool 2: Search Sharing Stations by Name
# ===========================================================================

@mcp.tool(
    name="road_search_sharing",
    annotations={
        "title": "Search Shared Mobility Stations",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def road_search_sharing(params: SearchSharingInput) -> dict[str, Any]:
    """Search for shared mobility stations by name or address.

    Full-text search across all Swiss shared mobility stations.
    Useful when you know the station name but not the coordinates.

    Example: "Find all PubliBike stations near 'Bahnhof'"

    Returns:
        JSON with matching stations, their locations, and availability.
    """
    try:
        result = await shared_mobility.search_stations(
            client=_get_client(),
            search_text=params.search_text,
            provider_id=params.provider_id,
            limit=params.limit,
        )
        return result
    except APIError as e:
        return upstream_error(e)
    except Exception:
        return unexpected_error()


# ===========================================================================
# Tool 3: List Sharing Providers
# ===========================================================================

@mcp.tool(
    name="road_sharing_providers",
    annotations={
        "title": "List Shared Mobility Providers",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def road_sharing_providers() -> dict[str, Any]:
    """List all shared mobility providers operating in Switzerland.

    Shows which companies offer shared bikes, e-scooters, cars etc.,
    what vehicle types they have, and links to their booking apps.

    Like checking the "About" page of a mobility platform.

    Returns:
        JSON with all providers, their vehicle types, and app links.
    """
    try:
        result = await shared_mobility.list_providers(_get_client())
        return result
    except APIError as e:
        return upstream_error(e)
    except Exception:
        return unexpected_error()


# ===========================================================================
# Tool 4: Find Nearby EV Chargers
# ===========================================================================

@mcp.tool(
    name="road_find_charger",
    annotations={
        "title": "Find EV Charging Stations",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def road_find_charger(params: FindChargerInput, ctx: Context) -> dict[str, Any]:
    """Find EV charging stations near a location in Switzerland.

    Searches ich-tanke-strom.ch data for nearby charging stations
    with real-time availability, plug types, and charging power.

    Like the "nearest charger" feature in an electric car's navigation.

    Data source: ich-tanke-strom.ch (Swiss Federal Office of Energy).
    No API key required – completely open data!

    Returns:
        JSON with nearby charging stations sorted by distance,
        including real-time status (free/occupied), plug types,
        charging power (kW), and operator information.
    """
    try:
        await ctx.info(
            f"Searching EV chargers within {params.radius_km} km of "
            f"({params.latitude}, {params.longitude})"
        )

        async def _progress(done: float, total: float, message: str) -> None:
            await ctx.report_progress(progress=done, total=total, message=message)

        result = await ev_charging.find_nearby_chargers(
            client=_get_client(),
            longitude=params.longitude,
            latitude=params.latitude,
            radius_km=params.radius_km,
            only_available=params.only_available,
            include_details=params.include_details,
            limit=params.limit,
            on_progress=_progress,
        )
        await ctx.info(f"Found {result.get('total_found', 0)} charging stations")
        return result
    except APIError as e:
        return upstream_error(e)
    except Exception:
        return unexpected_error()


# ===========================================================================
# Tool 5: Check Charger Status
# ===========================================================================

@mcp.tool(
    name="road_charger_status",
    annotations={
        "title": "Check EV Charger Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def road_charger_status(params: ChargerStatusInput) -> dict[str, Any]:
    """Check real-time availability of EV charging stations.

    Can check specific stations by ID, or get overall statistics
    for ALL charging points in Switzerland.

    Use road_find_charger first to get station IDs, then use this
    tool to check their current status.

    Returns:
        JSON with real-time status per station, or overall
        statistics (how many free/occupied/out of service).
    """
    try:
        result = await ev_charging.get_charger_status(
            client=_get_client(),
            station_ids=params.station_ids if params.station_ids else None,
        )
        return result
    except APIError as e:
        return upstream_error(e)
    except Exception:
        return unexpected_error()


# ===========================================================================
# Tool 6: System Status
# ===========================================================================

@mcp.tool(
    name="road_check_status",
    annotations={
        "title": "Check Road Mobility Server Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def road_check_status(ctx: Context) -> dict[str, Any]:
    """Check the health of all road mobility data sources.

    Tests connectivity to sharedmobility.ch and ich-tanke-strom.ch.
    Useful for diagnosing connection issues.

    Returns:
        JSON with status of each API endpoint.
    """

    checks = {
        "shared_mobility_api": {
            "url": "https://api.sharedmobility.ch/v1/sharedmobility/providers",
            "description": "Shared Mobility (Velos, E-Trottis, Autos)",
            "api_key_required": False,
        },
        "ev_charging_status": {
            "url": ev_charging.STATUS_URL,
            "description": "E-Ladestationen Echtzeit-Status",
            "api_key_required": False,
        },
        "ev_charging_geojson": {
            "url": ev_charging.GEOJSON_URL,
            "description": "E-Ladestationen Standorte (GeoJSON)",
            "api_key_required": False,
        },
        "datex2_traffic_situations": {
            "url": traffic_situations.SITUATIONS_URL,
            "description": "Verkehrsmeldungen DATEX II (Phase 2)",
            "api_key_required": True,
        },
        "datex2_traffic_counters": {
            "url": traffic_counters.COUNTERS_URL,
            "description": "Verkehrszähler DATEX II (Phase 2)",
            "api_key_required": True,
        },
        "geo_admin_search": {
            "url": "https://api3.geo.admin.ch/rest/services/api/SearchServer?searchText=Bern&type=locations&limit=1",
            "description": "geo.admin.ch Adresssuche – amtl. Gebäudeadressverzeichnis (Phase 4)",
            "api_key_required": False,
        },
        "geo_admin_roads": {
            "url": "https://api3.geo.admin.ch/rest/services/ech/MapServer/identify?geometry=8.5,47.3&geometryType=esriGeometryPoint&imageDisplay=100,100,96&mapExtent=8.4,47.2,8.6,47.4&tolerance=20&layers=all:ch.swisstopo.swisstlm3d-strassen&sr=4326",
            "description": "geo.admin.ch swissTLM3D Strassenklassifikation (Phase 4)",
            "api_key_required": False,
        },
    }

    await ctx.info(f"Checking {len(checks)} data-source endpoints")
    results = {}
    async with async_client(timeout=10.0) as test_client:
        for idx, (name, info) in enumerate(checks.items(), start=1):
            await ctx.report_progress(progress=idx, total=len(checks), message=f"Checking {name}")
            needs_key = info.get("api_key_required", False)
            has_key = bool(os.environ.get("OPENTRANSPORTDATA_API_KEY"))
            if needs_key and not has_key:
                results[name] = {
                    "status": "⚠️ API-Key fehlt",
                    "description": info["description"],
                    "api_key_required": True,
                    "how_to_get_key": "Kostenlos: https://api-manager.opentransportdata.swiss",
                }
                continue
            try:
                # Bug #6 Fix: sharedmobility.ch API unterstützt kein HEAD.
                # Lösung: GET verwenden und HTTP 405 als Warnsignal werten.
                # Alle anderen Endpunkte bleiben bei HEAD (schonender).
                use_get = name == "shared_mobility_api"
                if use_get:
                    resp = await test_client.get(info["url"])
                else:
                    resp = await test_client.head(info["url"])
                results[name] = {
                    "status": "✅ OK" if resp.status_code < 400 else f"⚠️ HTTP {resp.status_code}",
                    "description": info["description"],
                    "api_key_required": needs_key,
                }
            except Exception as e:
                results[name] = {
                    "status": f"❌ Fehler: {type(e).__name__}",
                    "description": info["description"],
                }

    return {
        "server": "swiss-road-mobility-mcp",
        "version": "0.4.0",
        "phase": "Phase 1 + Phase 2 + Phase 3 (Shared Mobility + E-Charging + DATEX II + Park & Rail + Multimodal)",
        "api_keys": {
            "phase_1": "KEINE – alle APIs sind komplett offen!",
            "phase_2": "OPENTRANSPORTDATA_API_KEY erforderlich (kostenlos: api-manager.opentransportdata.swiss)",
            "phase_2_configured": bool(os.environ.get("OPENTRANSPORTDATA_API_KEY")),
            "phase_3": "KEINE – SBB Open Data + transport.opendata.ch sind vollständig offen!",
        },
        "endpoints": results,
        "phase_3_tools": [
            "road_park_rail: Park+Rail Anlagen via SBB Open Data (kein Key)",
            "road_mobility_snapshot: Vollständiges Mobilitäts-Lagebild für einen Standort",
            "road_multimodal_plan: Auto → Park+Rail → ÖV → Ziel (multimodal)",
        ],
        "phase_4_tools": [
            "road_geocode_address: Adresse → GPS via amtl. Gebäudeadressverzeichnis (geo.admin.ch)",
            "road_reverse_geocode: GPS → amtliche Adresse mit EGID/EGAID (geo.admin.ch)",
            "road_classify_road: swissTLM3D Strassenklassifikation (geo.admin.ch)",
        ],
    }



# ===========================================================================
# Input Models – Phase 2: Traffic Situations
# ===========================================================================

class TrafficSituationsInput(BaseModel):
    """Input für Verkehrsmeldungen (DATEX II Phase 2)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    filter_type: str = Field(
        default="all",
        description=(
            "Ereignis-Typ-Filter. Optionen: "
            "'accident' (Unfälle), "
            "'roadwork' (Baustellen und Wartungsarbeiten), "
            "'congestion' (Stau und stockender Verkehr), "
            "'obstruction' (Hindernisse, Tiere, Fahrzeuge auf Strasse), "
            "'weather' (Wetterbedingte Strassenzustände), "
            "'road_management' (Spurreduktionen, Umleitungen), "
            "'infrastructure' (Schäden, Gerätefehler), "
            "'all' (alle Typen). Default: 'all'"
        ),
    )
    active_only: bool = Field(
        default=True,
        description=(
            "Nur aktive Meldungen anzeigen (nicht widerrufene). "
            "Default: true. Auf false setzen für Verlaufsdaten."
        ),
    )
    limit: int = Field(
        default=50,
        description="Maximale Anzahl Resultate (1–200). Default: 50",
        ge=1,
        le=200,
    )


# ===========================================================================
# Input Models – Phase 2: Traffic Counters
# ===========================================================================

class TrafficCountersInput(BaseModel):
    """Input für Echtzeit-Verkehrsaufkommen (DATEX II Phase 2)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    latitude: float = Field(
        ...,
        description=(
            "Breitengrad des Suchzentrums. "
            "Beispiele: 47.3769 (Zürich HB), 46.9480 (Bern), 47.5596 (Winterthur)"
        ),
        ge=45.5,
        le=48.0,
    )
    longitude: float = Field(
        ...,
        description=(
            "Längengrad des Suchzentrums. "
            "Beispiele: 8.5417 (Zürich HB), 7.4474 (Bern), 8.7240 (Winterthur)"
        ),
        ge=5.5,
        le=10.8,
    )
    radius_km: float = Field(
        default=5.0,
        description="Suchradius in Kilometern (0.5–50). Default: 5 km",
        ge=0.5,
        le=50.0,
    )
    limit: int = Field(
        default=10,
        description="Maximale Anzahl Messstellen (1–30). Default: 10",
        ge=1,
        le=30,
    )


class CounterSitesInput(BaseModel):
    """Input für Messstellen-Suche (DATEX II Phase 2)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    latitude: float = Field(
        ...,
        description="Breitengrad des Suchzentrums.",
        ge=45.5,
        le=48.0,
    )
    longitude: float = Field(
        ...,
        description="Längengrad des Suchzentrums.",
        ge=5.5,
        le=10.8,
    )
    radius_km: float = Field(
        default=10.0,
        description="Suchradius in Kilometern (0.5–100). Default: 10 km",
        ge=0.5,
        le=100.0,
    )
    limit: int = Field(
        default=20,
        description="Maximale Anzahl Resultate (1–50). Default: 20",
        ge=1,
        le=50,
    )


# ===========================================================================
# Tool 7: Traffic Situations (Phase 2 – API-Key erforderlich)
# ===========================================================================

@mcp.tool(
    name="road_traffic_situations",
    annotations={
        "title": "Swiss Traffic Events & Roadworks",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def road_traffic_situations(params: TrafficSituationsInput) -> dict[str, Any]:
    """Get current Swiss traffic events: accidents, roadworks, congestion.

    Fetches real-time traffic messages from ASTRA's DATEX II platform.
    Data is updated live by Swiss Traffic Management Center (VMZ-CH),
    cantonal police, and road operation units.

    Complements Phase 1: While road_find_sharing shows WHERE vehicles
    are available, this tool shows WHY a road is currently blocked.

    REQUIRES: OPENTRANSPORTDATA_API_KEY environment variable.
    Free registration: https://api-manager.opentransportdata.swiss

    Data source: ASTRA VMZ-CH via opentransportdata.swiss (DATEX II v2.3).
    Cache TTL: 2 minutes (real-time updates).

    Returns:
        JSON with list of traffic situations, each containing:
        - id: Situation identifier
        - records: List of situation records with:
          - category: Event type (accident/roadwork/congestion/etc.)
          - validity_status: active/revoked
          - start_time / end_time: Validity period
          - severity: highest/high/medium/low/lowest
          - description: Human-readable text (German preferred)
          - creation_time: When situation was created
    """
    try:
        api_key = _require_api_key()
        result = await traffic_situations.fetch_situations(
            api_key=api_key,
            filter_type=params.filter_type if params.filter_type != "all" else None,
            active_only=params.active_only,
            limit=params.limit,
        )
        return result
    except APIError as e:
        return upstream_error(e)
    except Exception:
        return unexpected_error()


# ===========================================================================
# Tool 8: Traffic Counters – Geo-Suche + Echtzeit-Daten (Phase 2)
# ===========================================================================

@mcp.tool(
    name="road_traffic_counters",
    annotations={
        "title": "Real-time Traffic Flow at Swiss Counting Stations",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def road_traffic_counters(params: TrafficCountersInput) -> dict[str, Any]:
    """Get real-time vehicle counts and speeds at Swiss traffic measurement stations.

    Finds nearby counting stations and returns live traffic flow data:
    vehicles per hour (separated by light/heavy vehicles) and average speeds.

    Data is updated every minute by ASTRA and cantonal road authorities.
    This is the «digital tally counter» of Swiss roads – precise, live,
    distinguishing passenger cars from trucks.

    Use case: «How busy is the A1 near Zurich right now?»
    or «How much truck traffic passes through Lucerne hourly?»

    REQUIRES: OPENTRANSPORTDATA_API_KEY environment variable.
    Free registration: https://api-manager.opentransportdata.swiss

    Data source: ASTRA & cantonal authorities via opentransportdata.swiss (DATEX II).
    Cache TTL: Site table 24h (static) + measurements 1 minute (real-time).

    Returns:
        JSON with nearby counting stations and their current measurements:
        - site_id: Unique station identifier
        - name: Station name
        - distance_km: Distance from search center
        - latitude / longitude: Station coordinates
        - supplier: Data provider (ASTRA, Kanton ZH, etc.)
        - measurement_time: Timestamp of latest measurement
        - flow_light_vehicles_per_hour: Cars, motorcycles, buses
        - flow_heavy_vehicles_per_hour: Trucks, articulated lorries
        - flow_total_per_hour: Combined flow
        - avg_speed_light_kmh: Average speed of light vehicles
        - avg_speed_heavy_kmh: Average speed of heavy vehicles
    """
    try:
        api_key = _require_api_key()

        # 1. Messstellen laden (24h gecached)
        sites = await traffic_counters.fetch_measurement_sites(api_key)

        if not sites:
            return {
                "error": "Keine Messstellen in der Messstellentabelle gefunden.",
                "hint": "Möglicherweise ist der API-Key ungültig oder die API nicht erreichbar.",
            }

        # 2. Geo-Suche: Nahe Messstellen finden
        nearby = traffic_counters.find_nearby_sites(
            sites=sites,
            latitude=params.latitude,
            longitude=params.longitude,
            radius_km=params.radius_km,
            limit=params.limit,
        )

        if not nearby:
            return {
                "search": {
                    "latitude": params.latitude,
                    "longitude": params.longitude,
                    "radius_km": params.radius_km,
                },
                "found": 0,
                "message": (
                    f"Keine Verkehrszählstellen im Umkreis von {params.radius_km} km gefunden. "
                    "Tipp: Radius vergrössern oder road_counter_sites für Überblick nutzen."
                ),
                "total_swiss_stations": len(sites),
            }

        # 3. Echtzeit-Messdaten für nahe Stationen holen
        site_ids = [s["id"] for s in nearby]
        measurements = await traffic_counters.fetch_measured_data(api_key, site_ids)

        # 4. Messdaten mit Stationsdaten zusammenführen
        meas_by_id = {m["site_id"]: m for m in measurements}
        enriched = []
        for site in nearby:
            meas = meas_by_id.get(site["id"], {})
            combined = {**site}
            if meas:
                combined.update({
                    k: v for k, v in meas.items()
                    if k != "site_id"
                })
            enriched.append(combined)

        return {
            "search": {
                "latitude": params.latitude,
                "longitude": params.longitude,
                "radius_km": params.radius_km,
            },
            "found": len(enriched),
            "stations_with_data": sum(1 for e in enriched if "measurement_time" in e),
            "total_swiss_stations": len(sites),
            "data_source": "ASTRA & Kantone via opentransportdata.swiss (DATEX II)",
            "stations": enriched,
        }

    except APIError as e:
        return upstream_error(e)
    except Exception:
        return unexpected_error()


# ===========================================================================
# Tool 9: Counter Sites – Messstellen in der Nähe (Phase 2)
# ===========================================================================

@mcp.tool(
    name="road_counter_sites",
    annotations={
        "title": "List Swiss Traffic Counting Stations Near Location",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def road_counter_sites(params: CounterSitesInput) -> dict[str, Any]:
    """List Swiss traffic counting stations near a location (without real-time data).

    Returns the measurement site metadata (name, coordinates, supplier)
    without fetching the live measurement data. Use this to discover
    available stations before querying road_traffic_counters.

    Site table is cached for 24 hours (rarely changes).

    REQUIRES: OPENTRANSPORTDATA_API_KEY environment variable.
    Free registration: https://api-manager.opentransportdata.swiss

    Returns:
        JSON with list of nearby counting stations:
        - id: DATEX II station identifier (use in road_traffic_counters)
        - name: Human-readable station name (German)
        - latitude / longitude: GPS coordinates
        - distance_km: Distance from your search location
        - supplier: Data provider (ASTRA, Kanton ZH, Kanton BE, etc.)
    """
    try:
        api_key = _require_api_key()

        # Messstellentabelle laden (24h gecached)
        sites = await traffic_counters.fetch_measurement_sites(api_key)

        if not sites:
            return {"error": "Messstellentabelle ist leer oder API nicht erreichbar."}

        nearby = traffic_counters.find_nearby_sites(
            sites=sites,
            latitude=params.latitude,
            longitude=params.longitude,
            radius_km=params.radius_km,
            limit=params.limit,
        )

        return {
            "search": {
                "latitude": params.latitude,
                "longitude": params.longitude,
                "radius_km": params.radius_km,
            },
            "found": len(nearby),
            "total_swiss_stations": len(sites),
            "hint": (
                "Nutze road_traffic_counters mit denselben Koordinaten "
                "für Echtzeit-Messdaten (Fahrzeuge/h, km/h)."
            ),
            "stations": nearby,
        }

    except APIError as e:
        return upstream_error(e)
    except Exception:
        return unexpected_error()

# ===========================================================================
# Input Models – Phase 3: Park & Rail
# ===========================================================================

class ParkRailNearbyInput(BaseModel):
    """Input für Park & Rail Suche nach Position."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    latitude: float = Field(
        ...,
        description=(
            "Breitengrad des Suchzentrums. "
            "Beispiele: 47.3769 (Zürich HB), 46.9480 (Bern), 47.5596 (Winterthur)"
        ),
        ge=45.5,
        le=48.0,
    )
    longitude: float = Field(
        ...,
        description=(
            "Längengrad des Suchzentrums. "
            "Beispiele: 8.5417 (Zürich HB), 7.4474 (Bern), 8.7240 (Winterthur)"
        ),
        ge=5.5,
        le=10.8,
    )
    radius_km: float = Field(
        default=5.0,
        description="Suchradius in Kilometern (0.5–30). Default: 5 km",
        ge=0.5,
        le=30.0,
    )
    limit: int = Field(
        default=10,
        description="Maximale Anzahl Resultate (1–20). Default: 10",
        ge=1,
        le=20,
    )


class ParkRailByNameInput(BaseModel):
    """Input für Park & Rail Suche nach Bahnhofsname."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    station_name: str = Field(
        ...,
        description=(
            "Bahnhofsname für die Suche. "
            "Beispiele: 'Zürich HB', 'Winterthur', 'Dietikon', 'Bern'"
        ),
        min_length=2,
        max_length=100,
    )
    limit: int = Field(
        default=5,
        description="Maximale Anzahl Resultate (1–10). Default: 5",
        ge=1,
        le=10,
    )


# ===========================================================================
# Input Models – Phase 3: Mobility Snapshot
# ===========================================================================

class MobilitySnapshotInput(BaseModel):
    """Input für vollständiges Mobilitäts-Lagebild."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    latitude: float = Field(
        ...,
        description="Breitengrad des Standorts.",
        ge=45.5,
        le=48.0,
    )
    longitude: float = Field(
        ...,
        description="Längengrad des Standorts.",
        ge=5.5,
        le=10.8,
    )
    sharing_radius_m: int = Field(
        default=500,
        description="Suchradius für Sharing-Fahrzeuge in Metern (50–2000). Default: 500m",
        ge=50,
        le=2000,
    )
    ev_radius_km: float = Field(
        default=1.0,
        description="Suchradius für EV-Ladestationen in km (0.1–10). Default: 1 km",
        ge=0.1,
        le=10.0,
    )
    park_rail_radius_km: float = Field(
        default=5.0,
        description="Suchradius für Park & Rail in km (0.5–30). Default: 5 km",
        ge=0.5,
        le=30.0,
    )


# ===========================================================================
# Input Models – Phase 3: Multimodaler Reiseplan
# ===========================================================================

class MultimodalPlanInput(BaseModel):
    """Input für den multimodalen Reiseplaner."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    start_latitude: float = Field(
        ...,
        description=(
            "Breitengrad der Startposition (wo du gerade bist / auto parkierst). "
            "Beispiel: 47.4558 (Dietikon), 47.3769 (Zürich HB)"
        ),
        ge=45.5,
        le=48.0,
    )
    start_longitude: float = Field(
        ...,
        description=(
            "Längengrad der Startposition. "
            "Beispiel: 8.4034 (Dietikon), 8.5417 (Zürich HB)"
        ),
        ge=5.5,
        le=10.8,
    )
    destination: str = Field(
        ...,
        description=(
            "Zielort als Name (Bahnhof oder Stadt). "
            "Beispiele: 'Bern', 'Zürich HB', 'Basel SBB', 'Luzern', 'Winterthur'"
        ),
        min_length=2,
        max_length=100,
    )
    park_rail_radius_km: float = Field(
        default=10.0,
        description=(
            "Suchradius für Park & Rail-Anlagen ab Startposition in km (1–30). "
            "Default: 10 km – für pendlertypische Distanzen"
        ),
        ge=1.0,
        le=30.0,
    )


# ===========================================================================
# Tool 10: Park & Rail in der Nähe (Phase 3 – kein API-Key!)
# ===========================================================================

@mcp.tool(
    name="road_park_rail",
    annotations={
        "title": "Find Park & Rail Facilities at Swiss Train Stations",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def road_park_rail(params: ParkRailNearbyInput) -> dict[str, Any]:
    """Find Park & Rail parking facilities near Swiss train stations.

    Returns SBB-operated Park & Rail lots with capacity, pricing,
    and opening hours. Data from SBB Open Data Portal.

    Phase 3 tool – the link between road and rail:
    «Park here, then take the train.»

    No API key required – completely open SBB data!

    Data source: SBB Open Data Portal (data.sbb.ch).
    Cache TTL: 5 minutes.

    Returns:
        JSON with nearby Park & Rail facilities sorted by distance,
        including total spaces, tarif category, opening hours,
        and optional real-time occupancy if available.
    """
    try:
        result = await park_rail.find_nearby_park_rail(
            latitude=params.latitude,
            longitude=params.longitude,
            radius_km=params.radius_km,
            limit=params.limit,
        )
        return result
    except APIError as e:
        return upstream_error(e)
    except Exception:
        return unexpected_error()


# ===========================================================================
# Tool 11: Mobility Snapshot – Vollständiges Lagebild (Phase 3)
# ===========================================================================

@mcp.tool(
    name="road_mobility_snapshot",
    annotations={
        "title": "Complete Mobility Picture for a Swiss Location",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def road_mobility_snapshot(params: MobilitySnapshotInput, ctx: Context) -> dict[str, Any]:
    """Get a complete mobility picture for any Swiss location in one call.

    Aggregates in parallel:
    - Shared vehicles nearby (bikes, e-scooters, cars)
    - EV charging stations
    - Park & Rail facilities at nearby train stations
    - Nearest train station (transport.opendata.ch)
    - Traffic situations if Phase 2 API key is configured (optional)

    This is the «mobility cockpit» – the control tower view.
    Instead of calling 5 different tools, get everything at once.

    Phase 3 cross-server tool: No extra API key needed beyond
    what Phase 2 already requires (and Phase 2 data is optional).

    Perfect for demos: «Show me everything mobility-related at [location].»

    Data sources:
      - sharedmobility.ch (no key)
      - ich-tanke-strom.ch (no key)
      - SBB Open Data / data.sbb.ch (no key)
      - transport.opendata.ch (no key)
      - opentransportdata.swiss DATEX II (optional, Phase 2 key)

    Returns:
        JSON with nearest_station, shared_mobility, ev_charging,
        park_rail, and optional traffic_situations – all for one location.
    """
    try:
        api_key = _get_api_key()
        await ctx.info(
            f"Aggregating mobility snapshot for ({params.latitude}, {params.longitude}) "
            f"across shared mobility, EV charging, Park & Rail and rail"
        )
        result = await multimodal.build_mobility_snapshot(
            latitude=params.latitude,
            longitude=params.longitude,
            radius_meters=params.sharing_radius_m,
            radius_km_ev=params.ev_radius_km,
            radius_km_park=params.park_rail_radius_km,
            has_api_key=bool(api_key),
            api_key=api_key,
        )
        await ctx.report_progress(progress=1.0, total=1.0, message="Snapshot complete")
        return result
    except APIError as e:
        return upstream_error(e)
    except Exception:
        return unexpected_error()


# ===========================================================================
# Tool 12: Multimodaler Reiseplan (Phase 3 – Cross-Server-Logik)
# ===========================================================================

@mcp.tool(
    name="road_multimodal_plan",
    annotations={
        "title": "Multimodal Trip Planner: Car + Park & Rail + Public Transport",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def road_multimodal_plan(params: MultimodalPlanInput, ctx: Context) -> dict[str, Any]:
    """Plan a multimodal trip: Drive → Park & Rail → Train → Destination.

    The «Holy Grail» of Phase 3: combines all data sources into a
    complete door-to-door multimodal route plan.

    Workflow (all in parallel where possible):
    1. Find the nearest train station from your start location
    2. Find Park & Rail facilities near the start (where to park your car)
    3. Get public transport connections from nearest station to destination
    4. Check shared mobility options at start for last-mile to station
    5. Assemble everything into a step-by-step route plan

    Use case: «I'm in Dietikon with a car. I need to get to Bern.
               Where can I park? Which train should I take?»

    No API key required – uses:
    - SBB Open Data (Park & Rail) – free
    - transport.opendata.ch (PT connections) – free
    - sharedmobility.ch (sharing options) – free

    Data sources:
      - SBB Open Data Portal (data.sbb.ch) – Park & Rail
      - transport.opendata.ch – Journey planning
      - sharedmobility.ch – Sharing last mile

    Returns:
        JSON with:
        - nearest_station: Closest train station from start
        - recommended_park_rail: Best P+R option
        - plan_steps: Step-by-step multimodal route
        - all_ov_connections: All available PT connections
        - last_mile_sharing: Sharing options at start location
    """
    try:
        await ctx.info(
            f"Planning multimodal trip from ({params.start_latitude}, "
            f"{params.start_longitude}) to {params.destination!r}"
        )
        result = await multimodal.plan_multimodal_trip(
            start_latitude=params.start_latitude,
            start_longitude=params.start_longitude,
            destination=params.destination,
            park_rail_radius_km=params.park_rail_radius_km,
        )
        await ctx.report_progress(progress=1.0, total=1.0, message="Trip plan ready")
        return result
    except APIError as e:
        return upstream_error(e)
    except Exception:
        return unexpected_error()


# ===========================================================================
# Input Models – Phase 4: geo.admin.ch
# ===========================================================================

class GeocodeAddressInput(BaseModel):
    """Input für Adress-Geocoding via amtliches Gebäudeadressverzeichnis."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    search_text: str = Field(
        ...,
        description=(
            "Schweizer Adresse als Suchtext. Unterstützte Formate:\n"
            "  - «Bahnhofstrasse 1 Zürich»\n"
            "  - «Bundesgasse 3 3003 Bern»\n"
            "  - «Weinbergstrasse 5 8001»\n"
            "Tipp: PLZ + Ort erhöht die Treffsicherheit."
        ),
        min_length=3,
        max_length=200,
    )
    limit: int = Field(
        default=5,
        description="Maximale Anzahl Treffer (1–10). Default: 5",
        ge=1,
        le=10,
    )


class ReverseGeocodeInput(BaseModel):
    """Input für Reverse Geocoding: GPS-Koordinaten → amtliche Adresse."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    latitude: float = Field(
        ...,
        description=(
            "Breitengrad (WGS84). "
            "Beispiele: 47.3769 (Zürich HB), 46.9480 (Bern), 47.0503 (Fribourg)"
        ),
        ge=45.5,
        le=48.0,
    )
    longitude: float = Field(
        ...,
        description=(
            "Längengrad (WGS84). "
            "Beispiele: 8.5417 (Zürich HB), 7.4474 (Bern), 7.1560 (Fribourg)"
        ),
        ge=5.5,
        le=10.8,
    )
    limit: int = Field(
        default=3,
        description="Maximale Anzahl nächstgelegener Adressen (1–5). Default: 3",
        ge=1,
        le=5,
    )


class ClassifyRoadInput(BaseModel):
    """Input für Strassenklassifikation via swissTLM3D."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", strict=True)

    latitude: float = Field(
        ...,
        description=(
            "Breitengrad des Standorts. "
            "Beispiele: 47.3769 (Zürich HB), 47.0061 (A1 bei Lausanne)"
        ),
        ge=45.5,
        le=48.0,
    )
    longitude: float = Field(
        ...,
        description=(
            "Längengrad des Standorts. "
            "Beispiele: 8.5417 (Zürich HB), 6.6335 (A1 bei Lausanne)"
        ),
        ge=5.5,
        le=10.8,
    )
    tolerance: int = Field(
        default=50,
        description=(
            "Suchtoleranz in Pixeln (bei 1000×1000px Render ≈ 5–200m). "
            "Kleiner Wert (20): nur direkt anliegende Strassen. "
            "Grosser Wert (100): breiter Umkreis. Default: 50"
        ),
        ge=10,
        le=200,
    )
    limit: int = Field(
        default=5,
        description="Maximale Anzahl gefundener Strassensegmente (1–10). Default: 5",
        ge=1,
        le=10,
    )


# ===========================================================================
# Tool 13: Adress-Geocoding (Phase 4 – kein API-Key)
# ===========================================================================

@mcp.tool(
    name="road_geocode_address",
    annotations={
        "title": "Geocode Swiss Address (Official Federal Registry)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def road_geocode_address(params: GeocodeAddressInput) -> dict[str, Any]:
    """Convert a Swiss address to GPS coordinates using the official federal address registry.

    Uses swisstopo's amtliches Gebäudeadressverzeichnis (GWR-based) –
    the authoritative Swiss federal building address register containing
    every officially registered address in Switzerland.

    Unlike general geocoders, this returns only verified, legally registered
    addresses. Every result has an EGAID (Eidgenössischer Adressidentifikator)
    and EGID (Gebäudeidentifikator) from the federal GWR register.

    Think of it as the «official digital postman»: if the address exists in
    Switzerland, it's here. If it's not here, it may not be officially registered.

    Phase 4 tool – no API key required!
    Data source: geo.admin.ch / swisstopo amtliches Gebäudeadressverzeichnis.

    Returns:
        JSON with matching addresses, each containing:
        - address: Full address string (e.g. «Bahnhofstrasse 1 8001 Zürich»)
        - latitude / longitude: WGS84 coordinates
        - feature_id: ID in the federal address register
        - source: Layer ID (ch.swisstopo.amtliches-gebaeudeadressverzeichnis)
    """
    try:
        result = await geo_admin.geocode_address(
            search_text=params.search_text,
            limit=params.limit,
        )
        return result
    except Exception:
        return unexpected_error("road_geocode_address")


# ===========================================================================
# Tool 14: Reverse Geocoding (Phase 4 – kein API-Key)
# ===========================================================================

@mcp.tool(
    name="road_reverse_geocode",
    annotations={
        "title": "Reverse Geocode Coordinates to Official Swiss Address",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def road_reverse_geocode(params: ReverseGeocodeInput) -> dict[str, Any]:
    """Find the nearest official Swiss addresses for given GPS coordinates.

    Uses the federal building address register (amtliches Gebäudeadressverzeichnis)
    to identify the nearest registered building addresses to any point in Switzerland.

    Returns official GWR (Gebäude- und Wohnungsregister) data including:
    - EGID (Eidgenössischer Gebäudeidentifikator) – unique federal building ID
    - EGAID (Eidgenössischer Adressidentifikator) – unique federal address ID
    - Building category (residential / non-residential)
    - Official address status

    Especially useful for enriching mobility data: finding the exact legal
    address of a charging station, Park & Rail facility, or sharing station.

    Phase 4 tool – no API key required!
    Data source: geo.admin.ch / swisstopo amtliches Gebäudeadressverzeichnis (GWR).

    Returns:
        JSON with nearest official addresses including EGID/EGAID identifiers,
        municipality data, and building category.
    """
    try:
        result = await geo_admin.reverse_geocode(
            latitude=params.latitude,
            longitude=params.longitude,
            limit=params.limit,
        )
        return result
    except Exception:
        return unexpected_error("road_reverse_geocode")


# ===========================================================================
# Tool 15: Strassenklassifikation (Phase 4 – kein API-Key)
# ===========================================================================

@mcp.tool(
    name="road_classify_road",
    annotations={
        "title": "Classify Swiss Roads via swissTLM3D (Official Road Network)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def road_classify_road(params: ClassifyRoadInput) -> dict[str, Any]:
    """Classify roads at a location using the official Swiss topographic road network (swissTLM3D).

    The swissTLM3D is the authoritative federal road network dataset from swisstopo.
    It classifies every road in Switzerland by:

    Road type (Objektart):
      🛣️ Autobahn · 🚗 Hauptstrasse · 🏘️ Nebenstrasse · 🚶 Weg/Pfad …

    Functional class (Verkehrsbedeutung):
      Hauptverbindungsstrasse · Verbindungsstrasse · Sammelstrasse · Zufahrtstrasse

    Surface (Belagsart): Hartbelag (Asphalt/Beton) · Weich-/Naturbelag

    Ownership (Eigentümer): Bund · Kanton · Gemeinde · Privat

    Access restriction (Verkehrsbeschränkung):
      Keine Beschränkung · Einsatzkräfte · Landwirtschaft ·
      Fussgänger und Radfahrer · Kein öffentlicher Verkehr …

    Use cases:
      - «Is this a motorway or a local road?»
      - «Who maintains this road – canton or municipality?»
      - Enriching traffic counter data with official road classification

    Phase 4 tool – no API key required!
    Data source: geo.admin.ch / swisstopo swissTLM3D Strassen.

    Returns:
        JSON with road segments at the location, each containing:
        - road_name: Official road name (if assigned)
        - road_type: {code, label_de, label_en, emoji, network_importance}
        - surface, functional_class, ownership, access_restriction
        Plus a type_summary overview.
    """
    try:
        result = await geo_admin.classify_road(
            latitude=params.latitude,
            longitude=params.longitude,
            tolerance=params.tolerance,
            limit=params.limit,
        )
        return result
    except Exception:
        return unexpected_error("road_classify_road")


# ===========================================================================
# Resources & Prompts (ARCH-008)
# ===========================================================================
# This server is intentionally tools-first: its value is real-time, parameterised
# queries against live Swiss open-data APIs, not static documents. We still expose
# one Resource (a stable catalogue of data sources — ideal read-only reference
# context) and one Prompt (a reusable multimodal-planning template) so the read
# and templating MCP primitives are covered. Full rationale + capability audit:
# docs/ARCHITECTURE.md.

@mcp.resource("roadmobility://data-sources")
def data_sources_catalog() -> str:
    """Catalogue of the upstream open-data sources this server aggregates.

    Read-only, stable, non-parameterised reference data — exactly what an MCP
    Resource is for (as opposed to the live queries handled by Tools).
    """
    return json.dumps(
        {
            "data_sources": [
                {"name": "sharedmobility.ch", "host": "api.sharedmobility.ch",
                 "api_key": False, "domain": "Shared mobility (bikes, e-scooters, cars)"},
                {"name": "ich-tanke-strom.ch", "host": "data.geo.admin.ch",
                 "api_key": False, "domain": "EV charging (locations + realtime status)"},
                {"name": "geo.admin.ch / swisstopo", "host": "api3.geo.admin.ch",
                 "api_key": False, "domain": "Geocoding + road classification"},
                {"name": "SBB Open Data", "host": "data.sbb.ch",
                 "api_key": False, "domain": "Park & Rail facilities"},
                {"name": "transport.opendata.ch", "host": "transport.opendata.ch",
                 "api_key": False, "domain": "Public-transport journey planning"},
                {"name": "opentransportdata.swiss (ASTRA DATEX II)",
                 "host": "api.opentransportdata.swiss",
                 "api_key": True, "domain": "Traffic situations + counters"},
            ],
            "note": (
                "All hosts are egress allow-listed (SEC-004/021). Phase-2 sources "
                "require a free OPENTRANSPORTDATA_API_KEY."
            ),
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.prompt()
def plan_trip(start: str, destination: str) -> str:
    """Reusable template for a car -> Park & Rail -> train -> destination plan."""
    return (
        f"Plan a door-to-door trip from {start} to {destination} in Switzerland.\n"
        "Suggested steps:\n"
        "1. Geocode the start address with road_geocode_address.\n"
        "2. Call road_multimodal_plan with the start coordinates and destination.\n"
        "3. Check road_find_sharing at the start for last-mile options.\n"
        "4. Summarise: where to park, which train to take, and total journey."
    )


# ===========================================================================
# Entry point
# ===========================================================================

def _in_container() -> bool:
    """Heuristik: läuft der Prozess in einem Container / Cloud-Runtime?

    Nur dann ist ein 0.0.0.0-Binding legitim (Netzwerk-Isolation durch die
    Plattform). Lokal ist es ein Sicherheitsrisiko (siehe SEC-016).
    """
    return (
        os.path.exists("/.dockerenv")
        or bool(os.environ.get("KUBERNETES_SERVICE_HOST"))
        or bool(os.environ.get("RENDER"))
        or bool(os.environ.get("RAILWAY_PROJECT_ID"))
    )


def main():
    """Start the Swiss Road & Mobility MCP Server."""
    configure_logging()  # OBS-003/OBS-004: structured option + explicit stderr
    configure_tracing()  # OBS-006: optional OpenTelemetry (off unless configured)

    transport = os.environ.get("MCP_TRANSPORT", "stdio")

    if transport == "sse":
        # SEC-016: Default auf 127.0.0.1 (localhost only). Das Binden an alle
        # Interfaces (0.0.0.0) gehört ausschliesslich in den Container-Kontext
        # (Dockerfile / render.yaml setzen MCP_HOST=0.0.0.0 explizit). Ein
        # 0.0.0.0-Default im Code würde einen lokal gestarteten SSE-Server für
        # das gesamte Subnetz erreichbar machen (NeighborJack).
        host = os.environ.get("MCP_HOST", "127.0.0.1")
        port = int(os.environ.get("MCP_PORT", "8001"))
        if host in ("0.0.0.0", "::") and not _in_container():
            logger.warning(
                "Binding to %s outside a container context exposes this MCP "
                "server to the local network (NeighborJack risk). Use "
                "MCP_HOST=127.0.0.1 for local development.",
                host,
            )
        logger.info(f"Starting SSE server on {host}:{port}")
        _run_sse(host, port)
    else:
        logger.info("Starting stdio server")
        mcp.run(transport="stdio")


def _run_sse(host: str, port: int) -> None:
    """Start the SSE transport with CORS, auth and rate limiting.

    On top of FastMCP's own SSE Starlette app we layer three pure-ASGI
    middlewares (request flow outermost -> innermost):

      CORS (SDK-004) -> RateLimit (SEC-009) -> BearerAuth (SEC-009) -> app

    - CORS exposes `Mcp-Session-Id` so browser clients on another origin can
      read it (SDK-004). Origins via ALLOWED_ORIGINS (default wildcard, safe
      while no credentials are used).
    - RateLimit caps requests per client IP (MCP_RATE_LIMIT / MCP_RATE_WINDOW)
      to dampen abuse / upstream-quota exhaustion even in unauthenticated mode.
    - BearerAuth requires `Authorization: Bearer <MCP_AUTH_TOKEN>` when that
      env var is set; otherwise it is a pass-through and we warn loudly.

    Served via uvicorn — the same path FastMCP.run uses internally. Falls back
    to the plain FastMCP SSE runner if the app/middleware wiring is unavailable
    (e.g. a future SDK API change), so SSE never silently breaks.
    """
    allowed = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    cfg = middleware_config()
    if not cfg.auth_token:
        logger.warning(
            "MCP_AUTH_TOKEN is not set — the SSE endpoint is UNAUTHENTICATED and "
            "reachable by anyone who can connect. Set MCP_AUTH_TOKEN to require a "
            "Bearer token (SEC-009). Rate limiting (%s req / %ss per IP) stays active.",
            cfg.rate_limit_max,
            int(cfg.rate_limit_window),
        )
    try:
        import uvicorn
        from starlette.middleware.cors import CORSMiddleware

        app = mcp.sse_app()
        # add_middleware prepends, so the LAST added is outermost. Desired
        # request flow: CORS -> RateLimit -> BearerAuth -> app.
        app.add_middleware(BearerAuthMiddleware, token=cfg.auth_token)
        app.add_middleware(
            RateLimitMiddleware,
            max_requests=cfg.rate_limit_max,
            window_seconds=cfg.rate_limit_window,
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed or ["*"],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Mcp-Session-Id", "Authorization"],
            expose_headers=["Mcp-Session-Id"],  # SDK-004: critical for browser clients
        )
        # OBS-006: outermost wrapper so server spans cover the full request and
        # W3C trace-context is extracted from inbound headers (no-op if tracing off).
        app = instrument_asgi(app)
        uvicorn.run(app, host=host, port=port)
    except Exception:
        logger.exception("Hardened SSE app unavailable; falling back to plain SSE")
        mcp.run(transport="sse", host=host, port=port)


if __name__ == "__main__":
    main()
