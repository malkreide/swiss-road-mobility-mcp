"""Unit tests for the shared-client lifecycle (SDK-001).

No `mcp` import, no network — runs in PR CI (`-m "not live"`).
"""

from swiss_road_mobility_mcp.api_infrastructure import MobilityHTTPClient
from swiss_road_mobility_mcp.client_lifecycle import build_client, managed_client


class TestBuildClient:
    async def test_returns_client_with_limiters(self):
        client = build_client()
        try:
            assert isinstance(client, MobilityHTTPClient)
            assert "sharedmobility" in client._rate_limiters
            assert "ev_charging" in client._rate_limiters
        finally:
            await client.close()


class TestManagedClient:
    async def test_yields_open_client_and_closes_on_exit(self):
        async with managed_client() as client:
            assert isinstance(client, MobilityHTTPClient)
            assert client._client.is_closed is False
        # After the context exits the underlying httpx client is closed.
        assert client._client.is_closed is True

    async def test_closes_even_on_exception(self):
        captured = None
        try:
            async with managed_client() as client:
                captured = client
                raise ValueError("boom")
        except ValueError:
            pass
        assert captured is not None
        assert captured._client.is_closed is True
