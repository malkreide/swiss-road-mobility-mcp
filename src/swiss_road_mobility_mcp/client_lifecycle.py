"""Shared HTTP client construction and lifecycle (SDK-001).

Previously the shared ``MobilityHTTPClient`` was created by an ad-hoc lazy
global and never closed — the underlying httpx connection pool leaked at
shutdown. The construction logic lives here (no ``mcp`` import, so it is unit
testable) and is driven by the FastMCP *lifespan* in ``server.py``: the client
is built at startup and deterministically closed at shutdown.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .api_infrastructure import MobilityHTTPClient, RateLimiter

logger = logging.getLogger("swiss-road-mobility-mcp")


def build_client() -> MobilityHTTPClient:
    """Create the shared client with the standard (polite) rate limiters."""
    client = MobilityHTTPClient()
    client.register_limiter(
        "sharedmobility",
        RateLimiter(max_requests=30, window_seconds=60),
    )
    client.register_limiter(
        "ev_charging",
        RateLimiter(max_requests=10, window_seconds=60),
    )
    return client


@asynccontextmanager
async def managed_client() -> AsyncIterator[MobilityHTTPClient]:
    """Async context manager: build the client, close it on exit (always)."""
    client = build_client()
    logger.info("Shared HTTP client initialised.")
    try:
        yield client
    finally:
        await client.close()
        logger.info("Shared HTTP client closed.")
