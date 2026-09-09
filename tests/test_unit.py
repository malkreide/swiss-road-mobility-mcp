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

from swiss_road_mobility_mcp import api_infrastructure, ev_charging, geo_admin, shared_mobility
from swiss_road_mobility_mcp.api_infrastructure import (
    APIError,
    MobilityHTTPClient,
    RateLimiter,
    SimpleCache,
    haversine_km,
)
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
        respx.get("https://data.geo.admin.ch/data").respond(500, text="boom")
        with pytest.raises(APIError):
            await client.get_json("https://data.geo.admin.ch/data")

    @respx.mock
    async def test_get_json_caches_second_call(self, client):
        route = respx.get("https://data.geo.admin.ch/data").respond(200, json={"ok": True})
        first = await client.get_json("https://data.geo.admin.ch/data", cache_prefix="t", cache_ttl=60)
        second = await client.get_json("https://data.geo.admin.ch/data", cache_prefix="t", cache_ttl=60)
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
        respx.get(f"{BASE_URL}/identify").respond(200, json=[_vehicle("v1", 8.54, 47.37), _vehicle("v2", 8.55, 47.38)])
        result = await shared_mobility.find_nearby_vehicles(client, longitude=8.54, latitude=47.37, radius_meters=500)
        assert result["count"] == 2
        assert result["by_type"] == {"E-Bike": 2}
        assert result["vehicles"][0]["provider"] == "PubliBike"

    @respx.mock
    async def test_find_nearby_only_available_filters(self, client):
        respx.get(f"{BASE_URL}/identify").respond(
            200, json=[_vehicle("v1", 8.54, 47.37, available=True), _vehicle("v2", 8.55, 47.38, available=False)]
        )
        result = await shared_mobility.find_nearby_vehicles(client, longitude=8.54, latitude=47.37, only_available=True)
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
            200,
            json=[
                {
                    "provider_id": "publibike",
                    "name": "PubliBike",
                    "vehicle_type": ["E-Bike", "Bicycle"],
                    "timezone": "Europe/Zurich",
                }
            ],
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
        respx.get(ev_charging.GEOJSON_URL).respond(
            200,
            json={
                "features": [
                    {"id": "st-near", "geometry": {"coordinates": [8.5417, 47.3769]}, "properties": {}},
                    {"id": "st-far", "geometry": {"coordinates": [6.1432, 46.2044]}, "properties": {}},  # Genf
                ]
            },
        )
        respx.get(ev_charging.STATUS_URL).respond(
            200, json={"EVSEStatuses": [{"EVSEStatusRecord": [{"EvseID": "st-near", "EVSEStatus": "Available"}]}]}
        )
        result = await ev_charging.find_nearby_chargers(
            client, longitude=8.5417, latitude=47.3769, radius_km=2.0, include_details=False
        )
        ids = [s["id"] for s in result["stations"]]
        assert "st-near" in ids and "st-far" not in ids
        near = next(s for s in result["stations"] if s["id"] == "st-near")
        assert near["status"] == "Available"

    @respx.mock
    async def test_get_charger_status_overall_statistics(self, client):
        respx.get(ev_charging.STATUS_URL).respond(
            200,
            json={
                "EVSEStatuses": [
                    {
                        "EVSEStatusRecord": [
                            {"EvseID": "a", "EVSEStatus": "Available"},
                            {"EvseID": "b", "EVSEStatus": "Occupied"},
                            {"EvseID": "c", "EVSEStatus": "Available"},
                        ]
                    }
                ]
            },
        )
        result = await ev_charging.get_charger_status(client, station_ids=None)
        assert result["total_charging_points"] == 3
        assert sum(result["status_distribution"].values()) == 3

    @respx.mock
    async def test_load_stations_empty_raises(self, client):
        respx.get(ev_charging.GEOJSON_URL).respond(200, json={"features": []})
        respx.get(ev_charging.STATUS_URL).respond(200, json={"EVSEStatuses": []})
        with pytest.raises(APIError):
            await ev_charging.find_nearby_chargers(client, longitude=8.54, latitude=47.37, include_details=False)


# ===========================================================================
# geo_admin (uses per-call httpx.AsyncClient — respx intercepts globally)
# ===========================================================================


class TestGeoAdmin:
    @respx.mock
    async def test_geocode_address_happy_path(self):
        respx.get(geo_admin.SEARCH_URL).respond(
            200,
            json={
                "results": [
                    {
                        "attrs": {
                            "label": "<b>Bahnhofstrasse 1</b> 8001 Zürich",
                            "lat": 47.3769,
                            "lon": 8.5417,
                            "featureId": "123",
                            "detail": "x",
                        }
                    }
                ]
            },
        )
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


# ===========================================================================
# Das Rate-Limit-Tor
#
# Bis hierher pruefte `test_rate_limiter_blocks_after_max` den Tuersteher als
# Objekt — `can_proceed()` und `wait_time()` —, nie aber, was der Client damit
# macht. Eine Messung zeigte die Zeilen des Tors in `get_json` als ungedeckt:
# **beide** Zweige der Entscheidung «warten oder absagen». Schreibbar waren sie
# vorher auch nicht, ausser durch echtes Warten: das Warten hatte keinen Namen,
# den ein Test uebernehmen kann, sondern lag direkt auf `asyncio.sleep`.
# ===========================================================================


class TestRateLimitTor:
    # Ein allow-gelisteter Host: der Egress-Guard (SEC-004) laesst nur die
    # echten Upstreams durch, und das gilt auch unter respx — der Guard haengt
    # als Request-Hook am Client, nicht am Transport.
    TOR_URL = f"{BASE_URL}/providers"

    @staticmethod
    def _erschoepft(client: MobilityHTTPClient, *, wartezeit: float) -> None:
        """Meldet den Limiter als voll, mit genau der gewuenschten Wartezeit.

        Nicht ueber echte Zeitstempel: die haengen an `time.monotonic()`, und
        die einzufrieren hiesse, die Uhr der Event-Loop anzuhalten.
        """
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.can_proceed = lambda: False
        limiter.wait_time = lambda: wartezeit
        client.register_limiter("test", limiter)

    @respx.mock
    async def test_ein_kurzes_warten_wird_abgewartet_und_die_anfrage_geht_raus(self, monkeypatch):
        """Unter der Grenze wartet der Client und fragt dann doch."""
        geschlafen: list[float] = []

        async def _kein_schlaf(sekunden: float) -> None:
            geschlafen.append(sekunden)

        monkeypatch.setattr(api_infrastructure, "_sleep", _kein_schlaf)
        route = respx.get(self.TOR_URL).respond(200, json={"ok": True})
        client = MobilityHTTPClient()
        self._erschoepft(client, wartezeit=api_infrastructure.MAX_RATE_LIMIT_WAIT - 1)

        ergebnis = await client.get_json(self.TOR_URL, limiter_name="test", use_cache=False)

        assert ergebnis == {"ok": True}
        assert route.call_count == 1, "nach dem Warten muss die Anfrage rausgehen"
        assert geschlafen == [api_infrastructure.MAX_RATE_LIMIT_WAIT - 1], (
            f"gewartet wurde {geschlafen}, nicht die vom Limiter genannte Zeit"
        )

    @respx.mock
    async def test_ein_langes_warten_wird_abgesagt_ohne_zu_warten(self, monkeypatch):
        """Ueber der Grenze wird abgesagt — und zwar *bevor* gewartet wird.

        Erst warten und dann absagen waere das Schlechteste aus beidem: der
        Anrufer haelt still, und am Ende bekommt er trotzdem einen Fehler.
        """
        geschlafen: list[float] = []

        async def _kein_schlaf(sekunden: float) -> None:
            geschlafen.append(sekunden)

        monkeypatch.setattr(api_infrastructure, "_sleep", _kein_schlaf)
        route = respx.get(self.TOR_URL).respond(200, json={"ok": True})
        client = MobilityHTTPClient()
        self._erschoepft(client, wartezeit=api_infrastructure.MAX_RATE_LIMIT_WAIT + 1)

        with pytest.raises(APIError) as fehler:
            await client.get_json(self.TOR_URL, limiter_name="test", use_cache=False)

        assert "Rate Limit" in str(fehler.value)
        assert geschlafen == [], "abgesagt wurde erst nach dem Warten"
        assert route.call_count == 0, "trotz Absage ging eine Anfrage raus"

    async def test_das_warten_traegt_einen_namen_dieses_moduls(self, monkeypatch):
        """Sonst liesse sich das Tor nur durch echtes Warten pruefen.

        `monkeypatch.setattr(api_infrastructure.asyncio, "sleep", ...)` loest
        `.asyncio` zum stdlib-Modul auf und ersetzt die Funktion im ganzen
        Prozess — httpx, respx, anyio und jeden anderen Test eingeschlossen.
        """
        import asyncio
        import inspect

        vorher = asyncio.sleep

        async def _nichts(_sekunden: float) -> None:
            return None

        monkeypatch.setattr(api_infrastructure, "_sleep", _nichts)
        assert api_infrastructure._sleep is _nichts, "die Naht wurde gar nicht uebernommen"
        assert asyncio.sleep is vorher, "asyncio.sleep wurde prozessweit ersetzt"

        quelle = inspect.getsource(MobilityHTTPClient.get_json)
        assert "await _sleep(" in quelle, "das Tor wartet nicht mehr ueber den Alias"
        assert "asyncio.sleep" not in quelle, "zurueck auf der stdlib-Funktion"


# ===========================================================================
# Der abgerissene Verbindungsaufbau
#
# Der naechtliche Live-Lauf vom 7.9.2026 (Run 96) war rot, weil ein einziger
# Aufbau zu data.geo.admin.ch mit `httpx.ConnectError` scheiterte. Die
# Positivkontrolle steckte im selben Lauf: drei weitere Tests luden dieselbe
# URL erfolgreich, und der Lauf der Folgenacht war wieder gruen. Die Quelle
# war also da — nur dieser eine Aufbau nicht.
#
# Ungeprueft war bis hierher die Unterscheidung, an der alles haengt: ob die
# Quelle *geantwortet* hat. Ein Statuscode ist eine Auskunft und wiederholt
# sich; ein abgerissener Aufbau ist keine. Die Tests unten fahren beide
# Richtungen, weil ein Retry, der auch ueber Statuscodes laeuft, dieselbe
# Absage dreimal einholt und die Quelle dafuer dreimal fragt.
# ===========================================================================


class TestVerbindungsabbruchWirdWiederholt:
    # Allow-gelistet (SEC-004) und zugleich der Host aus dem Vorfall.
    URL = "https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet/data/x.json"

    @staticmethod
    def _ohne_warten(monkeypatch) -> list[float]:
        """Nimmt dem Backoff die Zeit ab und schreibt mit, wie lange er wollte.

        Ueber den Modul-Alias `_sleep`, nicht ueber `api_infrastructure.asyncio`:
        letzteres *ist* das stdlib-Modul und entschaerfte das Warten im ganzen
        Prozess.
        """
        geschlafen: list[float] = []

        async def _kein_schlaf(sekunden: float) -> None:
            geschlafen.append(sekunden)

        monkeypatch.setattr(api_infrastructure, "_sleep", _kein_schlaf)
        return geschlafen

    @respx.mock
    async def test_ein_abgerissener_aufbau_wird_wiederholt_und_die_daten_kommen(self, monkeypatch, client):
        """Der Fall vom 7.9.2026: erster Aufbau weg, zweiter traegt."""
        self._ohne_warten(monkeypatch)
        route = respx.get(self.URL).mock(
            side_effect=[httpx.ConnectError("kein Aufbau"), httpx.Response(200, json={"features": [1]})]
        )

        ergebnis = await client.get_json(self.URL, use_cache=False)

        assert ergebnis == {"features": [1]}
        assert route.call_count == 2, "der zweite Versuch fand gar nicht statt"

    @respx.mock
    async def test_nach_dem_letzten_versuch_wird_abgesagt(self, monkeypatch, client):
        """Wiederholt wird begrenzt — sonst haengt der Anrufer an einer toten Leitung."""
        self._ohne_warten(monkeypatch)
        route = respx.get(self.URL).mock(side_effect=httpx.ConnectError("kein Aufbau"))

        with pytest.raises(APIError) as fehler:
            await client.get_json(self.URL, use_cache=False)

        versuche = api_infrastructure.MAX_TRANSIENT_RETRIES + 1
        assert route.call_count == versuche, f"{route.call_count} Versuche statt {versuche}"
        assert str(versuche) in str(fehler.value), f"die Absage nennt die Zahl der Versuche nicht: {fehler.value}"

    @respx.mock
    async def test_die_pause_waechst_und_steht_vor_dem_versuch(self, monkeypatch, client):
        """Zwischen die Versuche gehoert Abstand, und nach den letzten keiner.

        Ein Backoff hinter dem letzten Fehlschlag liesse den Anrufer warten,
        ohne dass danach noch etwas passiert.
        """
        geschlafen = self._ohne_warten(monkeypatch)
        respx.get(self.URL).mock(side_effect=httpx.ConnectError("kein Aufbau"))

        with pytest.raises(APIError):
            await client.get_json(self.URL, use_cache=False)

        erwartet = [
            api_infrastructure.RETRY_BACKOFF_SECONDS * 2**i for i in range(api_infrastructure.MAX_TRANSIENT_RETRIES)
        ]
        assert geschlafen == erwartet, f"gewartet wurde {geschlafen}, erwartet war {erwartet}"

    @respx.mock
    async def test_ein_statuscode_wird_nicht_wiederholt(self, monkeypatch, client):
        """Gegenprobe: Die Quelle hat geantwortet — dreimal fragen aendert daran nichts.

        Faellt dieser Test, laeuft der Retry ueber Antworten statt ueber ihr
        Ausbleiben und holt jede Absage dreifach ein.
        """
        self._ohne_warten(monkeypatch)
        route = respx.get(self.URL).respond(500, text="boom")

        with pytest.raises(APIError) as fehler:
            await client.get_json(self.URL, use_cache=False)

        assert route.call_count == 1, f"ein HTTP 500 wurde {route.call_count}-mal abgeholt"
        assert "500" in str(fehler.value)

    @respx.mock
    async def test_ein_timeout_wird_nicht_wiederholt(self, monkeypatch, client):
        """Gegenprobe: Wer die Uhr hat vollaufen lassen, laesst sie zweimal vollaufen.

        Wiederholt wird nur, was schnell scheitert. Ein ReadTimeout nach der
        vollen Frist zu wiederholen, verdreifacht die Wartezeit des Anrufers —
        der dann laengst sein eigenes Timeout gezogen hat.
        """
        self._ohne_warten(monkeypatch)
        route = respx.get(self.URL).mock(side_effect=httpx.ReadTimeout("Uhr voll"))

        with pytest.raises(APIError) as fehler:
            await client.get_json(self.URL, use_cache=False)

        assert route.call_count == 1, f"ein Timeout wurde {route.call_count}-mal abgewartet"
        assert "Timeout" in str(fehler.value)

    @respx.mock
    async def test_die_frist_steht_nur_an_einer_stelle(self):
        """Die 30s im Konstruktor und die 30s in der Meldung waren zwei Zahlen.

        Wer die eine anhebt und die andere vergisst, laesst den Server eine
        Frist nennen, die er gar nicht faehrt — und es faellt niemandem auf,
        weil die Meldung ja plausibel aussieht. Geprueft wird deshalb nicht
        der Quelltext, sondern beide Enden gegen denselben verstellten Wert.
        """
        monkeypatch = pytest.MonkeyPatch()
        try:
            monkeypatch.setattr(api_infrastructure, "REQUEST_TIMEOUT", 7.0)
            respx.get(self.URL).mock(side_effect=httpx.ReadTimeout("Uhr voll"))
            client = MobilityHTTPClient()

            assert client._client.timeout.read == 7.0, "der Client faehrt nicht die Konstante"

            with pytest.raises(APIError) as fehler:
                await client.get_json(self.URL, use_cache=False)

            assert "7s" in str(fehler.value), (
                f"die Meldung nennt eine andere Frist als der Client faehrt: {fehler.value}"
            )
            await client.close()
        finally:
            monkeypatch.undo()
