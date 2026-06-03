"""Unit tests for the SSE security middleware (SEC-009).

These exercise the pure-ASGI middlewares in isolation via Starlette's
TestClient — no `mcp` import, no network, so they run in PR CI
(`pytest -m "not live"`).
"""

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from swiss_road_mobility_mcp.security import (
    BearerAuthMiddleware,
    MiddlewareConfig,
    RateLimitMiddleware,
    middleware_config,
)


def _make_app(middleware):
    async def ok(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/x", ok, methods=["GET", "POST", "OPTIONS"])])
    for cls, kwargs in middleware:
        app.add_middleware(cls, **kwargs)
    return TestClient(app)


# ===========================================================================
# BearerAuthMiddleware
# ===========================================================================

class TestBearerAuth:
    def test_no_token_configured_is_passthrough(self):
        client = _make_app([(BearerAuthMiddleware, {"token": None})])
        assert client.get("/x").status_code == 200

    def test_missing_header_is_rejected(self):
        client = _make_app([(BearerAuthMiddleware, {"token": "s3cr3t"})])
        r = client.get("/x")
        assert r.status_code == 401
        assert "Bearer token" in r.json()["error"]

    def test_correct_token_passes(self):
        client = _make_app([(BearerAuthMiddleware, {"token": "s3cr3t"})])
        r = client.get("/x", headers={"Authorization": "Bearer s3cr3t"})
        assert r.status_code == 200
        assert r.text == "ok"

    def test_wrong_token_rejected(self):
        client = _make_app([(BearerAuthMiddleware, {"token": "s3cr3t"})])
        assert client.get("/x", headers={"Authorization": "Bearer nope"}).status_code == 401

    def test_options_preflight_bypasses_auth(self):
        client = _make_app([(BearerAuthMiddleware, {"token": "s3cr3t"})])
        # No auth header, but OPTIONS must pass through (CORS preflight).
        assert client.options("/x").status_code == 200


# ===========================================================================
# RateLimitMiddleware
# ===========================================================================

class TestRateLimit:
    def test_under_limit_passes(self):
        client = _make_app([(RateLimitMiddleware, {"max_requests": 3, "window_seconds": 60})])
        for _ in range(3):
            assert client.get("/x").status_code == 200

    def test_over_limit_returns_429_with_retry_after(self):
        client = _make_app([(RateLimitMiddleware, {"max_requests": 2, "window_seconds": 60})])
        assert client.get("/x").status_code == 200
        assert client.get("/x").status_code == 200
        r = client.get("/x")
        assert r.status_code == 429
        assert "Retry-After" in r.headers
        assert int(r.headers["Retry-After"]) >= 1

    def test_zero_disables_limiter(self):
        client = _make_app([(RateLimitMiddleware, {"max_requests": 0, "window_seconds": 60})])
        for _ in range(10):
            assert client.get("/x").status_code == 200

    def test_distinct_ips_are_independent(self):
        client = _make_app([(RateLimitMiddleware, {"max_requests": 1, "window_seconds": 60})])
        h_a = {"X-Forwarded-For": "10.0.0.1"}
        h_b = {"X-Forwarded-For": "10.0.0.2"}
        assert client.get("/x", headers=h_a).status_code == 200
        assert client.get("/x", headers=h_a).status_code == 429  # IP A exhausted
        assert client.get("/x", headers=h_b).status_code == 200  # IP B fresh

    def test_options_bypasses_limiter(self):
        client = _make_app([(RateLimitMiddleware, {"max_requests": 1, "window_seconds": 60})])
        assert client.get("/x").status_code == 200
        # OPTIONS must not be throttled (preflight).
        assert client.options("/x").status_code == 200


# ===========================================================================
# Layered: CORS-equivalent order (RateLimit outer, Auth inner)
# ===========================================================================

class TestLayered:
    def test_rate_limit_runs_before_auth(self):
        # RateLimit added last => outermost. An unauthenticated flood should be
        # throttled (429) rather than every request hitting auth (401).
        client = _make_app([
            (BearerAuthMiddleware, {"token": "s3cr3t"}),          # innermost
            (RateLimitMiddleware, {"max_requests": 1, "window_seconds": 60}),  # outermost
        ])
        assert client.get("/x").status_code == 401  # auth fails, but counts a hit
        assert client.get("/x").status_code == 429  # second request throttled first


# ===========================================================================
# middleware_config (env parsing)
# ===========================================================================

class TestConfig:
    def test_defaults(self, monkeypatch):
        for k in ("MCP_AUTH_TOKEN", "MCP_RATE_LIMIT", "MCP_RATE_WINDOW"):
            monkeypatch.delenv(k, raising=False)
        cfg = middleware_config()
        assert isinstance(cfg, MiddlewareConfig)
        assert cfg.auth_token is None
        assert cfg.rate_limit_max == 60
        assert cfg.rate_limit_window == 60.0

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MCP_AUTH_TOKEN", "tok")
        monkeypatch.setenv("MCP_RATE_LIMIT", "10")
        monkeypatch.setenv("MCP_RATE_WINDOW", "30")
        cfg = middleware_config()
        assert cfg.auth_token == "tok"
        assert cfg.rate_limit_max == 10
        assert cfg.rate_limit_window == 30.0

    def test_malformed_values_fall_back(self, monkeypatch):
        monkeypatch.setenv("MCP_RATE_LIMIT", "not-a-number")
        monkeypatch.setenv("MCP_RATE_WINDOW", "nope")
        cfg = middleware_config()
        assert cfg.rate_limit_max == 60
        assert cfg.rate_limit_window == 60.0
