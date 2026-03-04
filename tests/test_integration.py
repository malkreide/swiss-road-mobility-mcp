"""
Integration Tests für den Swiss Road & Mobility MCP Server.

Diese Tests laufen gegen die ECHTEN APIs – kein Mocking!
Warum? Weil wir sicherstellen wollen, dass die APIs noch
so antworten, wie wir es erwarten.

Metapher: Wie eine Probefahrt – wir testen nicht die Theorie,
sondern ob das Auto wirklich fährt.

Ausführen: pytest tests/test_integration.py -v
"""

import json
import pytest
import pytest_asyncio

from swiss_road_mobility_mcp.api_infrastructure import (
    MobilityHTTPClient,
    RateLimiter,
    haversine_km,
)
from swiss_road_mobility_mcp.shared_mobility import (
    find_nearby_vehicles,
    search_stations,
    list_providers,
)
from swiss_road_mobility_mcp.ev_charging import (
    find_nearby_chargers,
    get_charger_status,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest_asyncio.fixture
async def client():
    """Erstellt einen HTTP-Client für die Tests."""
    c = MobilityHTTPClient()
    c.register_limiter("sharedmobility", RateLimiter(max_requests=10, window_seconds=60))
    c.register_limiter("ev_charging", RateLimiter(max_requests=5, window_seconds=60))
    yield c
    await c.close()


# Zürich HB Koordinaten
ZH_HB_LAT = 47.3769
ZH_HB_LON = 8.5417

# Bern Bahnhof Koordinaten
BERN_LAT = 46.9480
BERN_LON = 7.4474


# ===========================================================================
# Haversine Tests
# ===========================================================================

class TestHaversine:
    """Teste die Distanzberechnung."""

    def test_same_point(self):
        assert haversine_km(47.0, 8.0, 47.0, 8.0) == 0.0

    def test_zurich_bern(self):
        """Zürich → Bern ≈ 95 km Luftlinie."""
        dist = haversine_km(ZH_HB_LAT, ZH_HB_LON, BERN_LAT, BERN_LON)
        assert 90 < dist < 110, f"Zürich-Bern sollte ~95km sein, ist {dist:.1f}km"

    def test_short_distance(self):
        """100m Distanz prüfen."""
        # ~0.001° ≈ 100m
        dist = haversine_km(47.0, 8.0, 47.001, 8.0)
        assert 0.05 < dist < 0.2


# ===========================================================================
# Shared Mobility Tests
# ===========================================================================

class TestSharedMobility:
    """Tests gegen die sharedmobility.ch API."""

    @pytest.mark.asyncio
    async def test_find_nearby_zurich(self, client):
        """Finde Sharing-Angebote am Zürich HB."""
        result = await find_nearby_vehicles(
            client, longitude=ZH_HB_LON, latitude=ZH_HB_LAT,
            radius_meters=1000, only_available=False,
        )
        assert "count" in result
        assert "vehicles" in result
        assert "by_type" in result
        # Zürich HB hat immer irgendwas
        assert result["count"] > 0, "Am Zürich HB sollte es Sharing-Angebote geben"

    @pytest.mark.asyncio
    async def test_find_nearby_with_filter(self, client):
        """Filtere nach E-Bike."""
        result = await find_nearby_vehicles(
            client, longitude=ZH_HB_LON, latitude=ZH_HB_LAT,
            radius_meters=2000, vehicle_type="E-Bike", only_available=False,
        )
        assert "count" in result
        # Wenn Ergebnisse, dann nur E-Bikes
        for v in result.get("vehicles", []):
            assert "E-Bike" in v.get("vehicle_type", [])

    @pytest.mark.asyncio
    async def test_search_stations(self, client):
        """Suche nach 'Bahnhof'."""
        result = await search_stations(client, search_text="Bahnhof")
        assert "count" in result
        assert result["count"] > 0, "'Bahnhof' sollte Ergebnisse liefern"

    @pytest.mark.asyncio
    async def test_list_providers(self, client):
        """Liste alle Anbieter auf."""
        result = await list_providers(client)
        assert "count" in result
        assert "providers" in result
        assert result["count"] > 5, "Es sollte mehrere Anbieter geben"
        # Jeder Anbieter hat eine ID und einen Namen
        for p in result["providers"]:
            assert "id" in p
            assert "name" in p


# ===========================================================================
# EV Charging Tests
# ===========================================================================

class TestEVCharging:
    """Tests gegen die ich-tanke-strom.ch API."""

    @pytest.mark.asyncio
    async def test_find_nearby_zurich(self, client):
        """Finde Ladestationen am Zürich HB."""
        result = await find_nearby_chargers(
            client, longitude=ZH_HB_LON, latitude=ZH_HB_LAT,
            radius_km=2.0, include_details=False,
        )
        assert "total_found" in result
        assert "stations" in result
        assert result["total_found"] > 0, "In Zürich sollte es Ladestationen geben"

    @pytest.mark.asyncio
    async def test_find_nearby_with_details(self, client):
        """Finde Ladestationen MIT Detaildaten."""
        result = await find_nearby_chargers(
            client, longitude=ZH_HB_LON, latitude=ZH_HB_LAT,
            radius_km=1.0, include_details=True, limit=5,
        )
        assert "stations" in result
        if result["stations"]:
            station = result["stations"][0]
            assert "distance_km" in station
            assert station["distance_km"] <= 1.0

    @pytest.mark.asyncio
    async def test_charger_overall_status(self, client):
        """Gesamtstatistik aller Ladepunkte."""
        result = await get_charger_status(client)
        assert "total_charging_points" in result
        assert result["total_charging_points"] > 1000, \
            "Die Schweiz hat >1000 Ladepunkte"

    @pytest.mark.asyncio
    async def test_find_only_available(self, client):
        """Nur freie Stationen in Bern."""
        result = await find_nearby_chargers(
            client, longitude=BERN_LON, latitude=BERN_LAT,
            radius_km=5.0, only_available=True, include_details=False,
        )
        assert "stations" in result
        for station in result["stations"]:
            assert station.get("status") == "Available"
