"""
Integration Tests – Swiss Road Mobility MCP Phase 3.

Testet die neuen Phase-3-Module:
  - park_rail: SBB Open Data Park & Rail
  - multimodal: Mobilitäts-Snapshot + Multimodaler Reiseplaner

Alle Phase-3-Tests benötigen KEINEN API-Key.
Echte Netzwerk-Abfragen werden durchgeführt (Live-Tests gegen offene APIs).

Ausführen:
  pytest tests/test_phase3.py -v
  pytest tests/test_phase3.py -v -k "park"       # Nur Park & Rail Tests
  pytest tests/test_phase3.py -v -k "multimodal"  # Nur Multimodal Tests

Hinweis: Live-Tests können bei Netzwerkproblemen fehlschlagen.
         Bei CI/CD: --ignore=tests/test_phase3.py für isolierte Umgebungen.
"""

import json
import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Test-Konfiguration
# ---------------------------------------------------------------------------

# Koordinaten für Tests
ZURICH_HB = {"lat": 47.3769, "lon": 8.5417, "name": "Zürich HB"}
WINTERTHUR = {"lat": 47.4997, "lon": 8.7241, "name": "Winterthur"}
BERN_HB = {"lat": 46.9491, "lon": 7.4386, "name": "Bern"}
DIETIKON = {"lat": 47.4036, "lon": 8.4003, "name": "Dietikon"}


# ===========================================================================
# Park & Rail Tests
# ===========================================================================

class TestParkRailModule:
    """Tests für das park_rail Modul (SBB Open Data)."""

    @pytest.mark.asyncio
    async def test_find_nearby_returns_valid_structure(self):
        """Testet ob find_nearby_park_rail eine valide Struktur zurückgibt."""
        from src.swiss_road_mobility_mcp import park_rail

        result = await park_rail.find_nearby_park_rail(
            latitude=ZURICH_HB["lat"],
            longitude=ZURICH_HB["lon"],
            radius_km=10.0,
            limit=5,
        )

        assert isinstance(result, dict), "Resultat muss ein dict sein"
        assert "search" in result, "Muss 'search' enthalten"
        assert "found" in result, "Muss 'found' enthalten"
        assert "facilities" in result, "Muss 'facilities' enthalten"
        assert "api_key_required" in result, "Muss 'api_key_required' enthalten"
        assert result["api_key_required"] is False, "Park & Rail darf keinen API-Key erfordern"

    @pytest.mark.asyncio
    async def test_find_nearby_search_params(self):
        """Testet ob die Suchparameter korrekt zurückgegeben werden."""
        from src.swiss_road_mobility_mcp import park_rail

        result = await park_rail.find_nearby_park_rail(
            latitude=47.5,
            longitude=8.5,
            radius_km=3.0,
            limit=5,
        )

        search = result.get("search", {})
        assert abs(search.get("latitude", 0) - 47.5) < 0.001
        assert abs(search.get("longitude", 0) - 8.5) < 0.001
        assert search.get("radius_km") == 3.0

    @pytest.mark.asyncio
    async def test_facility_structure_when_found(self):
        """Testet die Struktur einer einzelnen P+R-Anlage."""
        from src.swiss_road_mobility_mcp import park_rail

        result = await park_rail.find_nearby_park_rail(
            latitude=ZURICH_HB["lat"],
            longitude=ZURICH_HB["lon"],
            radius_km=15.0,
            limit=3,
        )

        facilities = result.get("facilities", [])
        if not facilities:
            pytest.skip("Keine Park & Rail Anlagen gefunden – API möglicherweise nicht erreichbar")

        for facility in facilities:
            assert "name" in facility, "Muss 'name' haben"
            assert "latitude" in facility, "Muss 'latitude' haben"
            assert "longitude" in facility, "Muss 'longitude' haben"
            assert "distance_km" in facility, "Muss 'distance_km' haben"
            assert "total_spaces" in facility, "Muss 'total_spaces' haben"
            assert facility["distance_km"] >= 0, "Distanz muss >= 0 sein"

    @pytest.mark.asyncio
    async def test_facilities_sorted_by_distance(self):
        """Testet ob Anlagen nach Distanz sortiert sind."""
        from src.swiss_road_mobility_mcp import park_rail

        result = await park_rail.find_nearby_park_rail(
            latitude=BERN_HB["lat"],
            longitude=BERN_HB["lon"],
            radius_km=20.0,
            limit=10,
        )

        facilities = result.get("facilities", [])
        if len(facilities) < 2:
            pytest.skip("Weniger als 2 Anlagen gefunden")

        distances = [f["distance_km"] for f in facilities]
        assert distances == sorted(distances), "Anlagen müssen nach Distanz aufsteigend sortiert sein"

    @pytest.mark.asyncio
    async def test_find_by_station_name(self):
        """Testet die Textsuche nach Bahnhofsnamen."""
        from src.swiss_road_mobility_mcp import park_rail

        result = await park_rail.find_park_rail_by_station(
            station_name="Zürich",
            limit=5,
        )

        assert isinstance(result, dict)
        assert "found" in result
        assert "facilities" in result
        assert result["api_key_required"] is False

    @pytest.mark.asyncio
    async def test_empty_area_returns_zero_found(self):
        """Testet dass kein Absturz bei leerer Suche (sehr kleiner Radius)."""
        from src.swiss_road_mobility_mcp import park_rail

        result = await park_rail.find_nearby_park_rail(
            latitude=46.8,
            longitude=9.5,  # Graubünden – selten P+R
            radius_km=0.5,
            limit=5,
        )

        assert "found" in result
        assert isinstance(result["found"], int)
        assert result["found"] >= 0


# ===========================================================================
# Multimodal Tests
# ===========================================================================

class TestMultimodalModule:
    """Tests für das multimodal Modul."""

    @pytest.mark.asyncio
    async def test_find_nearest_station_zurich(self):
        """Testet ob der nächste Bahnhof bei Zürich HB gefunden wird."""
        from src.swiss_road_mobility_mcp import multimodal

        result = await multimodal._find_nearest_station(
            latitude=ZURICH_HB["lat"],
            longitude=ZURICH_HB["lon"],
        )

        if result is None:
            pytest.skip("transport.opendata.ch nicht erreichbar")

        assert isinstance(result, dict)
        assert "name" in result
        assert "latitude" in result
        assert "longitude" in result
        assert "distance_from_search_km" in result
        assert result["distance_from_search_km"] < 1.0, "Zürich HB muss <1km vom HB-Koordinat sein"

    @pytest.mark.asyncio
    async def test_find_stations_by_name(self):
        """Testet die Bahnhofs-Namenssuche."""
        from src.swiss_road_mobility_mcp import multimodal

        results = await multimodal._find_stations_by_name("Bern", limit=3)

        if not results:
            pytest.skip("transport.opendata.ch nicht erreichbar")

        assert isinstance(results, list)
        for station in results:
            assert "name" in station
            assert "id" in station

    @pytest.mark.asyncio
    async def test_get_connections_valid_route(self):
        """Testet ÖV-Verbindungen zwischen zwei bekannten Bahnhöfen."""
        from src.swiss_road_mobility_mcp import multimodal

        try:
            connections = await multimodal._get_connections(
                from_station="Zürich HB",
                to_destination="Bern",
                limit=2,
            )
        except multimodal.APIError:
            pytest.skip("transport.opendata.ch nicht erreichbar")

        if not connections:
            pytest.skip("Keine Verbindungen zurückgegeben")

        for conn in connections:
            assert "departure" in conn
            assert "arrival" in conn
            assert "transfers" in conn
            assert "sections" in conn
            assert isinstance(conn["sections"], list)

    @pytest.mark.asyncio
    async def test_mobility_snapshot_structure(self):
        """Testet die Struktur des Mobilitäts-Snapshots."""
        from src.swiss_road_mobility_mcp import multimodal

        result = await multimodal.build_mobility_snapshot(
            latitude=ZURICH_HB["lat"],
            longitude=ZURICH_HB["lon"],
            radius_meters=500,
            radius_km_ev=1.0,
            radius_km_park=5.0,
            has_api_key=False,
            api_key=None,
        )

        assert isinstance(result, dict)

        # Pflichtfelder
        assert "snapshot_location" in result
        assert "search_radii" in result
        assert "nearest_station" in result
        assert "shared_mobility" in result
        assert "ev_charging" in result
        assert "park_rail" in result
        assert "traffic_situations" in result
        assert "data_sources" in result

        # Ohne API-Key muss traffic_situations einen Hinweis haben
        ts = result.get("traffic_situations", {})
        assert "note" in ts or "error" in ts or "situations" in ts

    @pytest.mark.asyncio
    async def test_mobility_snapshot_no_key_no_crash(self):
        """Testet dass der Snapshot ohne API-Key nicht abstürzt."""
        from src.swiss_road_mobility_mcp import multimodal

        # Sollte nie eine Exception werfen
        result = await multimodal.build_mobility_snapshot(
            latitude=WINTERTHUR["lat"],
            longitude=WINTERTHUR["lon"],
            radius_meters=300,
            radius_km_ev=0.5,
            radius_km_park=3.0,
            has_api_key=False,
            api_key=None,
        )

        assert isinstance(result, dict), "Snapshot muss immer ein dict zurückgeben"

    @pytest.mark.asyncio
    async def test_multimodal_plan_structure(self):
        """Testet die Struktur des multimodalen Reiseplans."""
        from src.swiss_road_mobility_mcp import multimodal

        result = await multimodal.plan_multimodal_trip(
            start_latitude=DIETIKON["lat"],
            start_longitude=DIETIKON["lon"],
            destination="Bern",
            park_rail_radius_km=10.0,
        )

        assert isinstance(result, dict)
        assert "route" in result
        assert "nearest_station" in result
        assert "plan_steps" in result
        assert "all_ov_connections" in result
        assert "last_mile_sharing" in result
        assert "data_sources" in result
        assert "api_keys_required" in result

        # Plan-Schritte müssen nummeriert sein
        steps = result.get("plan_steps", [])
        for i, step in enumerate(steps):
            assert "step" in step
            assert "mode" in step
            assert "description" in step

    @pytest.mark.asyncio
    async def test_multimodal_plan_route_info(self):
        """Testet ob die Route-Infos korrekt gesetzt werden."""
        from src.swiss_road_mobility_mcp import multimodal

        result = await multimodal.plan_multimodal_trip(
            start_latitude=47.4,
            start_longitude=8.6,
            destination="Luzern",
            park_rail_radius_km=8.0,
        )

        route = result.get("route", {})
        assert route.get("destination") == "Luzern"
        assert "start" in route
        start = route["start"]
        assert abs(start.get("latitude", 0) - 47.4) < 0.001
        assert abs(start.get("longitude", 0) - 8.6) < 0.001

    @pytest.mark.asyncio
    async def test_multimodal_plan_no_crash_invalid_destination(self):
        """Testet dass kein Absturz bei unbekanntem Ziel."""
        from src.swiss_road_mobility_mcp import multimodal

        # Nicht existierender Zielort – sollte Fehler graceful behandeln
        result = await multimodal.plan_multimodal_trip(
            start_latitude=ZURICH_HB["lat"],
            start_longitude=ZURICH_HB["lon"],
            destination="NichtExistierenderOrtXYZ123",
            park_rail_radius_km=5.0,
        )

        # Darf nicht abstürzen, muss ein dict zurückgeben
        assert isinstance(result, dict)


# ===========================================================================
# MCP Tool Integration Tests (via Server)
# ===========================================================================

class TestPhase3Tools:
    """End-to-End Tests für die Phase-3-MCP-Tools."""

    @pytest.mark.asyncio
    async def test_road_park_rail_tool(self):
        """Testet das road_park_rail Tool via Server."""
        import sys
        import os
        # Server importieren
        sys.path.insert(0, "src")

        from swiss_road_mobility_mcp.park_rail import find_nearby_park_rail

        result = await find_nearby_park_rail(
            latitude=47.3769,
            longitude=8.5417,
            radius_km=5.0,
            limit=5,
        )

        data = json.loads(json.dumps(result))
        assert "facilities" in data
        assert "found" in data

    @pytest.mark.asyncio
    async def test_mobility_snapshot_tool_complete(self):
        """Vollständiger Integration-Test des Mobility-Snapshots."""
        from src.swiss_road_mobility_mcp import multimodal

        snapshot = await multimodal.build_mobility_snapshot(
            latitude=BERN_HB["lat"],
            longitude=BERN_HB["lon"],
            radius_meters=500,
            radius_km_ev=1.0,
            radius_km_park=5.0,
            has_api_key=False,
        )

        # JSON-Serialisierbarkeit prüfen
        json_str = json.dumps(snapshot, ensure_ascii=False)
        assert len(json_str) > 100, "Snapshot muss substanzielle Daten enthalten"

        # Alle erwarteten Schlüssel prüfen
        parsed = json.loads(json_str)
        for key in ["snapshot_location", "nearest_station", "shared_mobility",
                    "ev_charging", "park_rail", "data_sources"]:
            assert key in parsed, f"Snapshot muss '{key}' enthalten"


# ===========================================================================
# Pytest Konfiguration
# ===========================================================================

if __name__ == "__main__":
    import asyncio

    async def run_quick_check():
        """Schneller Smoke-Test ohne pytest."""
        print("🧪 Phase 3 Quick Check...\n")

        from src.swiss_road_mobility_mcp import park_rail, multimodal

        print("1️⃣  Park & Rail (Zürich, 5km)...")
        pr = await park_rail.find_nearby_park_rail(47.3769, 8.5417, 5.0, 5)
        print(f"   ✅ Gefunden: {pr['found']} Anlagen")

        print("2️⃣  Nächster Bahnhof (Dietikon)...")
        station = await multimodal._find_nearest_station(47.4036, 8.4003)
        name = station["name"] if station else "❌ Nicht gefunden"
        print(f"   ✅ Nächster Bahnhof: {name}")

        print("3️⃣  Multimodaler Plan (Dietikon → Bern)...")
        plan = await multimodal.plan_multimodal_trip(47.4036, 8.4003, "Bern", 10.0)
        steps = len(plan.get("plan_steps", []))
        print(f"   ✅ Reiseplan: {steps} Schritte")

        print("\n🎉 Phase 3 funktioniert!")

    asyncio.run(run_quick_check())
