"""Outbound egress allow-listing (SEC-004, SEC-021, SEC-005).

The server only ever talks to a small, fixed set of official Swiss Open-Data
hosts. This module enforces that as defense-in-depth against SSRF:

  - A request **event hook** validates the target host on *every* outbound
    request — crucially including each hop of a redirect chain. So a malicious
    or compromised upstream that answers ``302 -> http://169.254.169.254/`` (a
    cloud metadata endpoint) is blocked, even though redirects stay enabled for
    legitimate (allow-listed) hosts.
  - The same hook then resolves the host and **rejects any that map to a
    non-public IP** (SEC-005), closing the DNS-rebinding gap where an
    allow-listed name is pointed at an internal/RFC1918/link-local address.
  - ``async_client(...)`` is a drop-in ``httpx.AsyncClient`` factory that wires
    the hook in while preserving all caller kwargs (timeout, headers,
    follow_redirects, …), so it can replace ``httpx.AsyncClient(...)`` 1:1.

Although none of the tools build URLs from user input today (all base URLs are
constants), this guarantees that property holds even if a future change or a
redirect tries to reach somewhere it shouldn't.

Configuration:
  - ``MCP_EGRESS_EXTRA_HOSTS``        — comma-separated extra allowed hosts.
  - ``MCP_EGRESS_ALLOWLIST_DISABLED`` — set truthy to disable host enforcement
                                        (escape hatch; not recommended).
  - ``MCP_EGRESS_DNS_GUARD_DISABLED`` — set truthy to disable the resolved-IP
                                        guard only (e.g. constrained networks).
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import socket

import httpx

logger = logging.getLogger("swiss-road-mobility-mcp")

# The official upstreams this server is allowed to reach.
ALLOWED_HOSTS: frozenset[str] = frozenset({
    "api.sharedmobility.ch",          # shared mobility (BFE)
    "data.geo.admin.ch",              # EV charging GeoJSON/status (swisstopo)
    "api3.geo.admin.ch",              # geocoding / road classification
    "data.sbb.ch",                    # SBB Park & Rail open data
    "transport.opendata.ch",          # public-transport journey planner
    "api.opentransportdata.swiss",    # DATEX II traffic (Phase 2)
    "api-manager.opentransportdata.swiss",
})


class EgressBlockedError(Exception):
    """Raised when an outbound request targets a non-allow-listed host."""


def _enforcing() -> bool:
    return os.environ.get("MCP_EGRESS_ALLOWLIST_DISABLED", "").strip().lower() not in (
        "1", "true", "yes", "on",
    )


def _extra_hosts() -> set[str]:
    raw = os.environ.get("MCP_EGRESS_EXTRA_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def is_allowed(host: str | None) -> bool:
    """True if ``host`` may be contacted (allow-list + env extras)."""
    host = (host or "").lower()
    return host in ALLOWED_HOSTS or host in _extra_hosts()


# --- SEC-005: DNS / resolved-IP guard --------------------------------------

def is_public_ip(ip_str: str) -> bool:
    """True only for routable, public IPs (rejects private/loopback/link-local/…)."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _dns_guard_enabled() -> bool:
    return os.environ.get("MCP_EGRESS_DNS_GUARD_DISABLED", "").strip().lower() not in (
        "1", "true", "yes", "on",
    )


async def _resolver(host: str, port: int) -> list[str]:
    """Resolve ``host`` to IP strings (async, non-blocking).

    Defined at module level so tests can substitute a deterministic, offline
    resolver (see tests/conftest.py).
    """
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


async def _assert_resolves_public(host: str, port: int) -> None:
    """Block a host that resolves to a non-public IP (DNS-rebinding / SSRF, SEC-005).

    Even an allow-listed hostname must not point at an internal address (e.g. a
    rebinding attack or a misconfigured record aimed at 169.254.169.254 / RFC1918).
    """
    try:
        ips = await _resolver(host, port)
    except OSError as exc:
        logger.warning("Egress blocked: DNS resolution failed for %s: %s", host, exc)
        raise EgressBlockedError(f"DNS resolution failed for host: {host}")
    if not ips or not all(is_public_ip(ip) for ip in ips):
        logger.warning("Egress blocked: %s resolves to non-public IP(s): %s", host, ips)
        raise EgressBlockedError(f"Host resolves to a non-public address: {host}")


async def _enforce_request_host(request: httpx.Request) -> None:
    """httpx request event hook — runs per request, incl. redirect hops."""
    if not _enforcing():
        return
    host = request.url.host
    if not is_allowed(host):
        logger.warning("Egress blocked: non-allow-listed host %r (%s)", host, request.url)
        raise EgressBlockedError(f"Egress to non-allow-listed host blocked: {host}")
    if _dns_guard_enabled():
        port = request.url.port or (443 if request.url.scheme == "https" else 80)
        await _assert_resolves_public(host, port)


def async_client(**kwargs) -> httpx.AsyncClient:
    """Create an ``httpx.AsyncClient`` with the egress allow-list hook installed.

    Drop-in replacement for ``httpx.AsyncClient(...)``: caller kwargs (timeout,
    headers, follow_redirects, …) are preserved; the egress hook is appended to
    any existing ``request`` event hooks.
    """
    event_hooks = dict(kwargs.pop("event_hooks", None) or {})
    request_hooks = list(event_hooks.get("request", []))
    request_hooks.append(_enforce_request_host)
    event_hooks["request"] = request_hooks
    return httpx.AsyncClient(event_hooks=event_hooks, **kwargs)
