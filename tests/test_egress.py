"""Unit tests for outbound egress allow-listing (SEC-004, SEC-021).

No real network: allowed hosts are respx-mocked; blocked hosts are rejected by
the request hook *before* any send, so no route is needed.
"""

import pytest
import respx

from swiss_road_mobility_mcp.egress import EgressBlockedError, async_client, is_allowed

ALLOWED = "https://api.sharedmobility.ch/v1/x"
METADATA = "http://169.254.169.254/latest/meta-data/"


class TestIsAllowed:
    def test_known_hosts_allowed(self):
        assert is_allowed("api.sharedmobility.ch")
        assert is_allowed("data.geo.admin.ch")
        assert is_allowed("transport.opendata.ch")

    def test_unknown_hosts_blocked(self):
        assert not is_allowed("169.254.169.254")
        assert not is_allowed("evil.example.com")
        assert not is_allowed(None)

    def test_case_insensitive(self):
        assert is_allowed("API.SharedMobility.CH")

    def test_env_extra_hosts(self, monkeypatch):
        monkeypatch.setenv("MCP_EGRESS_EXTRA_HOSTS", "extra.example.com, another.test")
        assert is_allowed("extra.example.com")
        assert is_allowed("another.test")


class TestEnforcement:
    @respx.mock
    async def test_allowed_host_passes(self):
        respx.get(ALLOWED).respond(200, json={"ok": True})
        async with async_client() as client:
            resp = await client.get(ALLOWED)
        assert resp.status_code == 200

    @respx.mock
    async def test_blocked_host_raises_before_send(self):
        # No respx route for the metadata host — the hook must reject it first.
        async with async_client() as client:
            with pytest.raises(EgressBlockedError):
                await client.get(METADATA)

    @respx.mock
    async def test_redirect_to_blocked_host_is_blocked(self):
        # SSRF via redirect: allowed host answers 302 -> cloud metadata IP.
        respx.get(ALLOWED).respond(302, headers={"location": METADATA})
        async with async_client(follow_redirects=True) as client:
            with pytest.raises(EgressBlockedError):
                await client.get(ALLOWED)

    @respx.mock
    async def test_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("MCP_EGRESS_ALLOWLIST_DISABLED", "true")
        # With enforcement off, the request proceeds to the (mocked) transport.
        respx.get(METADATA).respond(200, text="ok")
        async with async_client() as client:
            resp = await client.get(METADATA)
        assert resp.status_code == 200

    @respx.mock
    async def test_preserves_caller_event_hooks(self):
        seen = []

        async def my_hook(request):
            seen.append(request.url.host)

        respx.get(ALLOWED).respond(200, json={})
        async with async_client(event_hooks={"request": [my_hook]}) as client:
            await client.get(ALLOWED)
        # Caller's hook still ran alongside the egress hook.
        assert "api.sharedmobility.ch" in seen
