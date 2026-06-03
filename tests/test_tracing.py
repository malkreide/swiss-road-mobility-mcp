"""Unit tests for OpenTelemetry tracing (OBS-006).

No network (respx-mocked); skipped automatically if OpenTelemetry is not
installed. Otherwise runs in PR CI (`-m "not live"`).
"""

import httpx
import pytest
import respx

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

from swiss_road_mobility_mcp import tracing  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_tracing():
    """Keep global tracing/instrumentation state from leaking across tests."""
    yield
    tracing._enabled = False
    try:
        HTTPXClientInstrumentor().uninstrument()
    except Exception:
        pass


# ===========================================================================
# Gating logic — off by default
# ===========================================================================

class TestGating:
    def test_off_by_default(self, monkeypatch):
        monkeypatch.delenv("MCP_TRACING_ENABLED", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        assert tracing.tracing_requested() is False

    def test_enabled_by_flag(self, monkeypatch):
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        monkeypatch.setenv("MCP_TRACING_ENABLED", "true")
        assert tracing.tracing_requested() is True

    def test_enabled_by_otlp_endpoint(self, monkeypatch):
        monkeypatch.delenv("MCP_TRACING_ENABLED", raising=False)
        monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
        assert tracing.tracing_requested() is True

    def test_configure_is_noop_when_not_requested(self, monkeypatch):
        monkeypatch.delenv("MCP_TRACING_ENABLED", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        tracing._enabled = False
        assert tracing.configure_tracing() is False
        assert tracing.is_enabled() is False


# ===========================================================================
# instrument_asgi
# ===========================================================================

class TestInstrumentAsgi:
    def test_returns_app_unchanged_when_disabled(self):
        tracing._enabled = False
        sentinel = object()
        assert tracing.instrument_asgi(sentinel) is sentinel

    def test_wraps_app_when_enabled(self):
        exporter = InMemorySpanExporter()
        assert tracing.configure_tracing(force=True, span_exporter=exporter) is True
        sentinel = object()
        wrapped = tracing.instrument_asgi(sentinel)
        assert wrapped is not sentinel  # now wrapped by OpenTelemetryMiddleware


# ===========================================================================
# Real span creation — the core OBS-006 value: upstream calls are traced
# ===========================================================================

class TestHttpxTracing:
    @respx.mock
    async def test_outbound_httpx_call_creates_client_span(self):
        exporter = InMemorySpanExporter()
        assert tracing.configure_tracing(force=True, span_exporter=exporter) is True

        respx.get("https://example.test/ping").respond(200, json={"ok": True})
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://example.test/ping")
        assert resp.status_code == 200

        spans = exporter.get_finished_spans()
        assert len(spans) >= 1
        assert any(s.kind.name == "CLIENT" for s in spans)
