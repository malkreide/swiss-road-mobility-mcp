"""Centralised tool error handling (OBS-001, OBS-002).

Two concerns are addressed here so every tool handles errors identically:

OBS-001 — *protocol vs. execution errors*: application errors (an upstream API
is down, rate-limited, …) are returned to the LLM as a structured result with
``isError: true`` and a stable, machine-readable ``code`` — never raised as a
transport/protocol error. That lets the model react (retry, refine, switch
tool) instead of assuming the connection broke.

OBS-002 — *mask error details*: unexpected exceptions are logged in full on the
server (stderr) but the LLM only sees a generic message. Raw exception strings,
stack traces and upstream response bodies must not leak into the model context
(information disclosure).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("swiss-road-mobility-mcp")

# Stable, machine-readable error codes surfaced to the client (OBS-001).
CODE_UPSTREAM = "UPSTREAM_ERROR"
CODE_RATE_LIMIT = "RATE_LIMIT_EXCEEDED"
CODE_EXECUTION = "EXECUTION_FAILED"


def error_envelope(code: str, message: str) -> dict[str, Any]:
    """Build a structured execution-error result (SDK-002).

    Shape:
        {"isError": true, "error": {"code": "<CODE>", "message": "<text>"}}

    Returned as a dict so FastMCP emits it as ``structuredContent`` (plus a
    JSON text rendering), consistent with the success path.
    """
    return {"isError": True, "error": {"code": code, "message": message}}


def upstream_error(exc: Exception) -> dict[str, Any]:
    """Surface an ``APIError`` to the LLM.

    ``APIError`` messages are curated and user-safe (the raw upstream response
    body is logged, not embedded — see ``api_infrastructure``), so the message
    is forwarded as-is, tagged with a code the model can branch on.
    """
    message = str(exc)
    lowered = message.lower()
    code = CODE_RATE_LIMIT if "rate limit" in lowered else CODE_UPSTREAM
    return error_envelope(code, message)


def unexpected_error(context: str | None = None) -> dict[str, Any]:
    """Handle an unexpected exception (OBS-002).

    Must be called from within an ``except`` block: the active exception is
    logged in full (stack trace included) to stderr, while the LLM receives a
    generic message with no internal detail.
    """
    logger.exception("Unhandled error in %s", context or "tool execution")
    return error_envelope(
        CODE_EXECUTION,
        "An internal error occurred while processing the request.",
    )
