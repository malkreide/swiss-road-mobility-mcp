"""End-to-end tool tests through a real in-memory MCP session.

These import `server` (and therefore `mcp`) and drive a tool over a connected
client/server session, so Context injection, progress reporting and the full
FastMCP call path are exercised — with respx-mocked upstreams (offline).
"""

import json

import pytest
import respx

pytest.importorskip("mcp")

from mcp.shared.memory import (  # noqa: E402
    create_connected_server_and_client_session as connect,
)

from swiss_road_mobility_mcp import ev_charging, server  # noqa: E402

_GEO = {"features": [{"id": "st1", "geometry": {"coordinates": [8.5417, 47.3769]}, "properties": {}}]}
_STATUS = {"EVSEStatuses": [{"EVSEStatusRecord": [{"EvseID": "st1", "EVSEStatus": "Available"}]}]}


@respx.mock
async def test_find_charger_tool_via_session():
    """road_find_charger runs through a session (Context + progress) and returns data."""
    respx.get(ev_charging.GEOJSON_URL).respond(200, json=_GEO)
    respx.get(ev_charging.STATUS_URL).respond(200, json=_STATUS)

    async with connect(server.mcp._mcp_server) as client:
        result = await client.call_tool(
            "road_find_charger",
            {"params": {
                "latitude": 47.3769,
                "longitude": 8.5417,
                "radius_km": 2.0,
                "include_details": False,
                "only_available": False,
                "limit": 20,
            }},
        )

    assert result.isError is False
    # SDK-002: structured output is delivered alongside the JSON text.
    assert result.structuredContent is not None
    assert result.structuredContent["total_found"] >= 1
    # Backward-compatible text rendering is still present.
    data = json.loads(result.content[0].text)
    assert data["total_found"] >= 1
    assert data["stations"][0]["status"] == "Available"


@respx.mock
async def test_check_status_tool_via_session_is_resilient():
    """road_check_status uses Context and returns a result even when upstreams fail.

    No respx routes are registered, so every probe is intercepted and fails —
    proving the per-endpoint error handling keeps the tool itself successful
    (and offline-deterministic).
    """
    async with connect(server.mcp._mcp_server) as client:
        result = await client.call_tool("road_check_status", {})
    assert result.isError is False
    data = json.loads(result.content[0].text)
    assert "endpoints" in data


async def test_data_sources_resource_and_prompt_are_exposed():
    """ARCH-008: the server exposes a Resource and a Prompt (not tools-only)."""
    async with connect(server.mcp._mcp_server) as client:
        resources = await client.list_resources()
        assert "roadmobility://data-sources" in {str(r.uri) for r in resources.resources}

        read = await client.read_resource("roadmobility://data-sources")
        catalog = json.loads(read.contents[0].text)
        assert len(catalog["data_sources"]) == 6

        prompts = await client.list_prompts()
        assert "plan_trip" in {p.name for p in prompts.prompts}
        rendered = await client.get_prompt("plan_trip", {"start": "Dietikon", "destination": "Bern"})
        assert "Dietikon" in rendered.messages[0].content.text


async def test_strict_input_rejects_wrong_type():
    """SEC-018: strict=True rejects loosely-typed input (string for a float field)."""
    async with connect(server.mcp._mcp_server) as client:
        result = await client.call_tool(
            "road_find_sharing",
            {"params": {"latitude": "not-a-number", "longitude": 8.5417}},
        )
    assert result.isError is True
