"""Unit tests for the Swiss Road & Mobility MCP Server (OPS-001).

These tests mock all HTTP traffic with `respx` and run fully offline — they
are the suite that runs in CI on every PR (`pytest -m "not live"`). The
companion `test_integration.py` / `test_phase3.py` hit the real APIs and are
marked `@pytest.mark.live` (nightly / manual only).

Coverage per layer:
  - api_infrastructure: pure logic (haversine, RateLimiter, SimpleCache) +
    HTTP error mapping (500 -> APIError).
  - shared_mobility: nearby search, availability filter, providers, malformed
    response handling.
  - ev_charging: distance filtering + status enrichment, overall statistics.
  - geo_admin: address geocoding happy-path + empty result.
"""

import httpx
import pytest
import respx

from swiss_road_mobility_mcp.api_infrastructure import (
    APIError,
    MobilityHTTPClient,
    RateLimiter,
    SimpleCache,
    haversine_km,
)
from swiss_road_mobility_mcp import ev_charging, geo_admin, shared_mobility
from swiss_road_mobility_mcp.shared_mobility import BASE_URL


@pytest.fixture
async def client():
    c = MobilityHTTPClient()
    yield c
    await c.close()


# ===========================================================================
# api_infrastructure — pure logic (no network)
# ===========================================================================

class TestInfraPureLogic:
    def test_haversine_zero_distance(self):
        assert haversine_km(47.3769, 8.5417, 47.3769, 8.5417) == pytest.approx(0.0, abs=1e-9)

    def test_haversine_known_distance_zurich_bern(self):
        # Zürich HB -> Bern HB ist ~95 km Luftlinie.
        d = haversine_km(47.3769, 8.5417, 46.9480, 7.4474)
        assert 90 < d < 100

    def test_rate_limiter_blocks_after_max(self):
        rl = RateLimiter(max_requests=2, window_seconds=60)
        assert rl.can_proceed()
        rl.record()
        rl.record()
        assert not rl.can_proceed()
        assert rl.wait_time() > 0

    def test_cache_set_get_roundtrip(self):
        cache = SimpleCache()
        cache.set("p", {"q": 1}, {"v": 42}, ttl=60)
        assert cache.get("p", {"q": 1}) == {"v": 42}

    def test_cache_miss_returns_none(self):
        cache = SimpleCache()
        assert cache.get("p", {"q": "absent"}) is None

    def test_cache_expired_returns_none(self):
        cache = SimpleCache()
        cache.set("p", {"q": 1}, {"v": 1}, ttl=0)  # expires immediately
        assert cache.get("p", {"q": 1}) is None


class TestInfraHTTP:
    @respx.mock
    async def test_get_json_maps_500_to_apierror(self, client):
        respx.get("https://example.test/data").respond(500, text="boom")
        with pytest.raises(APIError):
            await client.get_json("https://example.test/data")

    @respx.mock
    async def test_get_json_caches_second_call(self, client):
        route = respx.get("https://example.test/data").respond(200, json={"ok": True})
        first = await client.get_json("https://example.test/data", cache_prefix="t", cache_ttl=60)
        second = await client.get_json("https://example.test/data", cache_prefix="t", cache_ttl=60)
        assert first == second == {"ok": True}
        assert route.call_count == 1  # second call served from cache


# ===========================================================================
# shared_mobility
# ===========================================================================

def _vehicle(vid, lon, lat, available=True, vtype="E-Bike"):
    return {
        "attributes": {
            "id": vid,
            "provider_name": "PubliBike",
            "vehicle_type": [vtype],
            "pickup_type": "station_based",
            "available": available,
        },
        "geometry": {"x": lon, "y": lat},
    }


class TestSharedMobility:
    @respx.mock
    async def test_find_nearby_happy_path(self, client):
        respx.get(f"{BASE_URL}/identify").respond(
            200, json=[_vehicle("v1", 8.54, 47.37), _vehicle("v2", 8.55, 47.38)]
        )
        result = await shared_mobility.find_nearby_vehicles(
            client, longitude=8.54, latitude=47.37, radius_meters=500
        )
        assert result["count"] == 2
        assert result["by_type"] == {"E-Bike": 2}
        assert result["vehicles"][0]["provider"] == "PubliBike"

    @respx.mock
    async def test_find_nearby_only_available_filters(self, client):
        respx.get(f"{BASE_URL}/identify").respond(
            200, json=[_vehicle("v1", 8.54, 47.37, available=True),
                       _vehicle("v2", 8.55, 47.38, available=False)]
        )
        result = await shared_mobility.find_nearby_vehicles(
            client, longitude=8.54, latitude=47.37, only_available=True
        )
        assert result["count"] == 1

    @respx.mock
    async def test_find_nearby_malformed_response(self, client):
        # API returns a dict instead of the expected list -> graceful hint.
        respx.get(f"{BASE_URL}/identify").respond(200, json={"unexpected": "shape"})
        result = await shared_mobility.find_nearby_vehicles(client, longitude=8.54, latitude=47.37)
        assert result["count"] == 0
        assert "hint" in result

    @respx.mock
    async def test_find_nearby_500_raises_apierror(self, client):
        respx.get(f"{BASE_URL}/identify").respond(503, text="down")
        with pytest.raises(APIError):
            await shared_mobility.find_nearby_vehicles(client, longitude=8.54, latitude=47.37)

    @respx.mock
    async def test_list_providers_happy_path(self, client):
        respx.get(f"{BASE_URL}/providers").respond(
            200, json=[{"provider_id": "publibike", "name": "PubliBike",
                        "vehicle_type": ["E-Bike", "Bicycle"], "timezone": "Europe/Zurich"}]
        )
        result = await shared_mobility.list_providers(client)
        assert result["count"] == 1
        assert result["providers"][0]["name"] == "PubliBike"
        assert "Bundesamt für Energie" in result["source"]


# ===========================================================================
# ev_charging
# ===========================================================================

class TestEvCharging:
    @respx.mock
    async def test_find_nearby_chargers_distance_and_status(self, client):
        respx.get(ev_charging.GEOJSON_URL).respond(200, json={"features": [
            {"id": "st-near", "geometry": {"coordinates": [8.5417, 47.3769]}, "properties": {}},
            {"id": "st-far", "geometry": {"coordinates": [6.1432, 46.2044]}, "properties": {}},  # Genf
        ]})
        respx.get(ev_charging.STATUS_URL).respond(200, json={"EVSEStatuses": [
            {"EVSEStatusRecord": [{"EvseID": "st-near", "EVSEStatus": "Available"}]}
        ]})
        result = await ev_charging.find_nearby_chargers(
            client, longitude=8.5417, latitude=47.3769, radius_km=2.0, include_details=False
        )
        ids = [s["id"] for s in result["stations"]]
        assert "st-near" in ids and "st-far" not in ids
        near = next(s for s in result["stations"] if s["id"] == "st-near")
        assert near["status"] == "Available"

    @respx.mock
    async def test_get_charger_status_overall_statistics(self, client):
        respx.get(ev_charging.STATUS_URL).respond(200, json={"EVSEStatuses": [
            {"EVSEStatusRecord": [
                {"EvseID": "a", "EVSEStatus": "Available"},
                {"EvseID": "b", "EVSEStatus": "Occupied"},
                {"EvseID": "c", "EVSEStatus": "Available"},
            ]}
        ]})
        result = await ev_charging.get_charger_status(client, station_ids=None)
        assert result["total_charging_points"] == 3
        assert sum(result["status_distribution"].values()) == 3

    @respx.mock
    async def test_load_stations_empty_raises(self, client):
        respx.get(ev_charging.GEOJSON_URL).respond(200, json={"features": []})
        respx.get(ev_charging.STATUS_URL).respond(200, json={"EVSEStatuses": []})
        with pytest.raises(APIError):
            await ev_charging.find_nearby_chargers(
                client, longitude=8.54, latitude=47.37, include_details=False
            )


# ===========================================================================
# geo_admin (uses per-call httpx.AsyncClient — respx intercepts globally)
# ===========================================================================

class TestGeoAdmin:
    @respx.mock
    async def test_geocode_address_happy_path(self):
        respx.get(geo_admin.SEARCH_URL).respond(200, json={"results": [
            {"attrs": {"label": "<b>Bahnhofstrasse 1</b> 8001 Zürich",
                       "lat": 47.3769, "lon": 8.5417, "featureId": "123", "detail": "x"}}
        ]})
        result = await geo_admin.geocode_address("Bahnhofstrasse 1 Zürich")
        assert result["found"] == 1
        hit = result["results"][0]
        assert hit["latitude"] == 47.3769 and hit["longitude"] == 8.5417
        assert "<b>" not in hit["address"]  # label HTML cleaned

    @respx.mock
    async def test_geocode_address_empty(self):
        respx.get(geo_admin.SEARCH_URL).respond(200, json={"results": []})
        result = await geo_admin.geocode_address("Nonexistent Place 9999")
        assert result["found"] == 0
        assert result["results"] == []
