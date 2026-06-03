"""Shared test fixtures.

The egress layer (SEC-005) resolves each outbound host and rejects non-public
IPs. To keep the suite fully offline and deterministic, we replace the resolver
with a stub that returns a fixed public IP for every host. Tests that exercise
the DNS guard itself override this within the test body.
"""

import pytest

from swiss_road_mobility_mcp import egress

_PUBLIC_IP = "93.184.216.34"  # example.net — a stable public address


@pytest.fixture(autouse=True)
def offline_dns_resolver(monkeypatch):
    async def _fake_resolver(host: str, port: int) -> list[str]:
        return [_PUBLIC_IP]

    monkeypatch.setattr(egress, "_resolver", _fake_resolver)
