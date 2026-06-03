"""Unit tests for outbound egress allow-listing (SEC-004, SEC-021).

No real network: allowed hosts are respx-mocked; blocked hosts are rejected by
the request hook *before* any send, so no route is needed.
"""

import pytest
import respx

from swiss_road_mobility_mcp import egress
from swiss_road_mobility_mcp.egress import (
    EgressBlockedError,
    async_client,
    is_allowed,
    is_public_ip,
)

ALLOWED = "https://api.sharedmobility.ch/v1/x"
METADATA = "http://169.254.169.254/latest/meta-data/"


def _set_resolver(monkeypatch, ips):
    async def _fake(host, port):
        if isinstance(ips, Exception):
            raise ips
        return list(ips)
    monkeypatch.setattr(egress, "_resolver", _fake)


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


# ===========================================================================
# SEC-005 — resolved-IP guard (DNS rebinding / SSRF to internal addresses)
# ===========================================================================

class TestIsPublicIp:
    @pytest.mark.parametrize("ip", ["8.8.8.8", "93.184.216.34", "2606:2800:220:1::1"])
    def test_public(self, ip):
        assert is_public_ip(ip)

    @pytest.mark.parametrize("ip", [
        "127.0.0.1", "10.0.0.1", "192.168.1.5", "172.16.0.1",
        "169.254.169.254", "0.0.0.0", "::1", "fc00::1", "fe80::1", "not-an-ip",
    ])
    def test_not_public(self, ip):
        assert not is_public_ip(ip)


class TestDnsGuard:
    @respx.mock
    async def test_allowed_host_with_public_ip_passes(self, monkeypatch):
        _set_resolver(monkeypatch, ["93.184.216.34"])
        respx.get(ALLOWED).respond(200, json={"ok": True})
        async with async_client() as client:
            assert (await client.get(ALLOWED)).status_code == 200

    @respx.mock
    async def test_allowed_host_resolving_to_private_ip_blocked(self, monkeypatch):
        # DNS-rebinding: an allow-listed name now points at an internal address.
        _set_resolver(monkeypatch, ["10.0.0.5"])
        async with async_client() as client:
            with pytest.raises(EgressBlockedError):
                await client.get(ALLOWED)

    @respx.mock
    async def test_mixed_public_and_private_blocked(self, monkeypatch):
        _set_resolver(monkeypatch, ["93.184.216.34", "169.254.169.254"])
        async with async_client() as client:
            with pytest.raises(EgressBlockedError):
                await client.get(ALLOWED)

    @respx.mock
    async def test_resolution_failure_blocked(self, monkeypatch):
        _set_resolver(monkeypatch, OSError("dns down"))
        async with async_client() as client:
            with pytest.raises(EgressBlockedError):
                await client.get(ALLOWED)

    @respx.mock
    async def test_dns_guard_can_be_disabled(self, monkeypatch):
        monkeypatch.setenv("MCP_EGRESS_DNS_GUARD_DISABLED", "true")
        _set_resolver(monkeypatch, ["10.0.0.5"])  # would be blocked if guard ran
        respx.get(ALLOWED).respond(200, text="ok")
        async with async_client() as client:
            assert (await client.get(ALLOWED)).status_code == 200
