"""ASGI security middleware for the SSE transport (SEC-009).

The public SSE endpoint is otherwise unauthenticated, which exposes two risks
even for a read-only Public-Open-Data server: (1) anyone on the internet can
drive the server's upstream API quota (the free OPENTRANSPORTDATA key, the
shared-mobility endpoints, …), and (2) there is no way to attribute or throttle
abuse.

This module provides two **pure ASGI** middlewares (deliberately NOT Starlette
`BaseHTTPMiddleware`, which buffers responses and would break SSE streaming):

  - ``BearerAuthMiddleware``  — optional shared-secret Bearer-token gate.
  - ``RateLimitMiddleware``   — per-client-IP sliding-window limiter.

Both are configured from the environment (see ``middleware_config``) and are
wired into the SSE app by ``server._run_sse``. They are independently unit
tested with Starlette's ``TestClient`` (no ``mcp`` import required).
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass

logger = logging.getLogger("swiss-road-mobility-mcp")

# Methods that must never be gated/throttled: CORS preflight carries no auth
# header and must reach the CORS layer.
_BYPASS_METHODS = frozenset({"OPTIONS"})


def _client_ip(scope) -> str:
    """Best-effort client IP.

    Behind a reverse proxy / PaaS (Render, Railway, …) the TCP peer is the
    proxy, so the real client sits in ``X-Forwarded-For``. We take the
    left-most entry. Note: ``X-Forwarded-For`` is spoofable when the server is
    NOT behind a trusted proxy — acceptable here because the limiter is a
    courtesy/abuse-dampener, not an authorization boundary (that is auth's job).
    """
    headers = dict(scope.get("headers") or [])
    xff = headers.get(b"x-forwarded-for")
    if xff:
        first = xff.decode(errors="replace").split(",")[0].strip()
        if first:
            return first
    client = scope.get("client")
    return client[0] if client else "unknown"


async def _send_json(send, status: int, message: str, extra_headers=()) -> None:
    body = json.dumps({"error": message}).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
    ]
    headers.extend(extra_headers)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class BearerAuthMiddleware:
    """Require ``Authorization: Bearer <token>`` when a token is configured.

    If ``token`` is falsy the middleware is a no-op pass-through (the server
    logs a prominent warning at startup so unauthenticated mode is a conscious
    choice, not an accident).
    """

    def __init__(self, app, token: str | None):
        self.app = app
        self.token = token or None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.token:
            await self.app(scope, receive, send)
            return
        if scope.get("method") in _BYPASS_METHODS:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        provided = headers.get(b"authorization", b"").decode(errors="replace")
        expected = f"Bearer {self.token}"
        # Constant-time comparison to avoid leaking the token via timing.
        if provided and hmac.compare_digest(provided, expected):
            await self.app(scope, receive, send)
            return

        await _send_json(send, 401, "Unauthorized: a valid Bearer token is required.")


class RateLimitMiddleware:
    """Per-client-IP sliding-window rate limiter.

    ``max_requests`` <= 0 disables the limiter. On limit breach it returns
    HTTP 429 with a ``Retry-After`` header.
    """

    def __init__(self, app, max_requests: int, window_seconds: float):
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = float(window_seconds)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _purge_idle(self, now: float) -> None:
        # Opportunistic memory hygiene: drop IP buckets with no recent hits.
        if len(self._hits) <= 4096:
            return
        cutoff = now - self.window_seconds
        for ip in [ip for ip, dq in self._hits.items() if not dq or dq[-1] <= cutoff]:
            del self._hits[ip]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self.max_requests <= 0:
            await self.app(scope, receive, send)
            return
        if scope.get("method") in _BYPASS_METHODS:
            await self.app(scope, receive, send)
            return

        ip = _client_ip(scope)
        now = time.monotonic()
        dq = self._hits[ip]
        cutoff = now - self.window_seconds
        while dq and dq[0] <= cutoff:
            dq.popleft()

        if len(dq) >= self.max_requests:
            retry_after = max(1, int(dq[0] + self.window_seconds - now) + 1)
            await _send_json(
                send,
                429,
                f"Rate limit exceeded ({self.max_requests} requests / "
                f"{int(self.window_seconds)}s). Retry in {retry_after}s.",
                extra_headers=[(b"retry-after", str(retry_after).encode())],
            )
            return

        dq.append(now)
        self._purge_idle(now)
        await self.app(scope, receive, send)


@dataclass(frozen=True)
class MiddlewareConfig:
    auth_token: str | None
    rate_limit_max: int
    rate_limit_window: float


def middleware_config() -> MiddlewareConfig:
    """Build the SSE middleware configuration from environment variables.

    - ``MCP_AUTH_TOKEN``   — shared secret; if unset, SSE stays unauthenticated.
    - ``MCP_RATE_LIMIT``   — max requests per window per IP (default 60; 0 = off).
    - ``MCP_RATE_WINDOW``  — window length in seconds (default 60).
    """
    token = os.environ.get("MCP_AUTH_TOKEN") or None
    try:
        max_req = int(os.environ.get("MCP_RATE_LIMIT", "60"))
    except ValueError:
        max_req = 60
    try:
        window = float(os.environ.get("MCP_RATE_WINDOW", "60"))
    except ValueError:
        window = 60.0
    return MiddlewareConfig(auth_token=token, rate_limit_max=max_req, rate_limit_window=window)
