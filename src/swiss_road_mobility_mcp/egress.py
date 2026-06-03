"""Outbound egress allow-listing (SEC-004, SEC-021).

The server only ever talks to a small, fixed set of official Swiss Open-Data
hosts. This module enforces that as defense-in-depth against SSRF:

  - A request **event hook** validates the target host on *every* outbound
    request — crucially including each hop of a redirect chain. So a malicious
    or compromised upstream that answers ``302 -> http://169.254.169.254/`` (a
    cloud metadata endpoint) is blocked, even though redirects stay enabled for
    legitimate (allow-listed) hosts.
  - ``async_client(...)`` is a drop-in ``httpx.AsyncClient`` factory that wires
    the hook in while preserving all caller kwargs (timeout, headers,
    follow_redirects, …), so it can replace ``httpx.AsyncClient(...)`` 1:1.

Although none of the tools build URLs from user input today (all base URLs are
constants), this guarantees that property holds even if a future change or a
redirect tries to reach somewhere it shouldn't.

Configuration:
  - ``MCP_EGRESS_EXTRA_HOSTS``       — comma-separated extra allowed hosts.
  - ``MCP_EGRESS_ALLOWLIST_DISABLED``— set truthy to disable enforcement
                                       (escape hatch; not recommended).
"""

from __future__ import annotations

import logging
import os

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


async def _enforce_request_host(request: httpx.Request) -> None:
    """httpx request event hook — runs per request, incl. redirect hops."""
    if not _enforcing():
        return
    host = request.url.host
    if not is_allowed(host):
        logger.warning("Egress blocked: non-allow-listed host %r (%s)", host, request.url)
        raise EgressBlockedError(f"Egress to non-allow-listed host blocked: {host}")


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
