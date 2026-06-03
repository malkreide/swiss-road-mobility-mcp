"""Progress-callback tests for find_nearby_chargers (SDK-003).

No `mcp` needed — the callback is exercised directly with respx-mocked
upstreams, so the progress *logic* is verified offline.
"""

import respx

from swiss_road_mobility_mcp import ev_charging
from swiss_road_mobility_mcp.api_infrastructure import MobilityHTTPClient

_GEO = {"features": [{"id": "st1", "geometry": {"coordinates": [8.54, 47.37]}, "properties": {}}]}
_STATUS = {"EVSEStatuses": [{"EVSEStatusRecord": [{"EvseID": "st1", "EVSEStatus": "Available"}]}]}


async def _run(on_progress, *, include_details):
    respx.get(ev_charging.GEOJSON_URL).respond(200, json=_GEO)
    respx.get(ev_charging.STATUS_URL).respond(200, json=_STATUS)
    respx.get(ev_charging.EVSEDATA_URL).respond(200, json={"EVSEData": []})
    client = MobilityHTTPClient()
    try:
        return await ev_charging.find_nearby_chargers(
            client, longitude=8.54, latitude=47.37, radius_km=2.0,
            include_details=include_details, on_progress=on_progress,
        )
    finally:
        await client.close()


class TestProgressCallback:
    @respx.mock
    async def test_two_steps_without_details(self):
        events = []

        async def rec(done, total, msg):
            events.append((done, total, msg))

        await _run(rec, include_details=False)
        assert [e[0] for e in events] == [1, 2]
        assert all(e[1] == 2.0 for e in events)
        assert all(isinstance(e[2], str) and e[2] for e in events)

    @respx.mock
    async def test_three_steps_with_details(self):
        events = []

        async def rec(done, total, msg):
            events.append((done, total, msg))

        await _run(rec, include_details=True)
        assert [e[0] for e in events] == [1, 2, 3]
        assert all(e[1] == 3.0 for e in events)

    @respx.mock
    async def test_no_callback_does_not_raise(self):
        result = await _run(None, include_details=False)
        assert result["total_found"] >= 1
