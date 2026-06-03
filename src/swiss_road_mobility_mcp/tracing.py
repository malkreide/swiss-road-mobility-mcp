"""OpenTelemetry distributed tracing (OBS-006).

Optional and **off by default**. The server is cloud-deployable (SSE), where
tracing matters most: it is largely an upstream-API aggregator, so the dominant
latency/error source is the outbound HTTP calls.

Design:
  - Zero cost when unused: tracing only activates when explicitly requested via
    ``MCP_TRACING_ENABLED=true`` or by setting an OTLP endpoint
    (``OTEL_EXPORTER_OTLP_ENDPOINT``). Otherwise this module is a no-op.
  - Optional dependency: the ``opentelemetry-*`` packages live in the
    ``tracing`` extra. If they are not installed, tracing degrades gracefully
    (a warning, then normal operation) — it never breaks the server.
  - Maximum coverage, minimum intrusion: httpx auto-instrumentation traces
    every upstream API call without touching any tool or client code; the SSE
    app is wrapped with the ASGI middleware for server spans + W3C trace-context
    propagation.

Standard ``OTEL_*`` environment variables (endpoint, headers, service name,
sampling, …) are honoured by the OpenTelemetry SDK directly.
"""

from __future__ import annotations

import logging
import os

from . import __version__

logger = logging.getLogger("swiss-road-mobility-mcp")

_enabled = False


def tracing_requested() -> bool:
    """True if tracing should be activated (flag set, or an OTLP endpoint configured)."""
    if os.environ.get("MCP_TRACING_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip())


def is_enabled() -> bool:
    return _enabled


def configure_tracing(
    service_name: str = "swiss-road-mobility-mcp",
    *,
    force: bool = False,
    span_exporter=None,
) -> bool:
    """Set up the tracer provider and instrument httpx. Idempotent.

    Returns True if tracing is (now) active, False otherwise.

    ``span_exporter`` is a test seam: when provided, spans are exported through
    a ``SimpleSpanProcessor`` to that exporter instead of the OTLP/batch path.
    """
    global _enabled
    if _enabled and not force:
        return True
    if span_exporter is None and not tracing_requested():
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            SimpleSpanProcessor,
        )
    except ImportError:
        logger.warning(
            "Tracing was requested but OpenTelemetry is not installed. "
            "Install the 'tracing' extra (pip install 'swiss-road-mobility-mcp[tracing]'). "
            "Continuing without tracing."
        )
        return False

    resource = Resource.create({
        "service.name": service_name,
        "service.version": __version__,
    })
    provider = TracerProvider(resource=resource)

    if span_exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

    trace.set_tracer_provider(provider)
    # Auto-trace every outbound upstream call — no tool/client changes needed.
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)

    _enabled = True
    logger.info("OpenTelemetry tracing enabled (service=%s).", service_name)
    return True


def instrument_asgi(app):
    """Wrap an ASGI app with the OTel middleware (SSE server spans).

    Returns the app unchanged when tracing is disabled or the middleware is
    unavailable, so callers can wrap unconditionally.
    """
    if not _enabled:
        return app
    try:
        from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
    except ImportError:
        return app
    return OpenTelemetryMiddleware(app)
