"""Logging configuration (OBS-003, OBS-004).

OBS-004: all log output goes to **stderr** explicitly. For a stdio MCP server
stdout is reserved for the JSON-RPC stream; any log line on stdout corrupts it.

OBS-003: structured (JSON) logging is available via ``MCP_LOG_FORMAT=json`` so
logs can be ingested by Datadog/Loki/Splunk without regex parsing. The default
stays human-readable text for local development.

Environment variables:
  - ``MCP_LOG_LEVEL``  : DEBUG | INFO | WARNING | ERROR  (default INFO)
  - ``MCP_LOG_FORMAT`` : text | json                     (default text)
"""

from __future__ import annotations

import json
import logging
import os
import sys

_TEXT_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"


class JsonFormatter(logging.Formatter):
    """Minimal structured JSON formatter (no third-party dependency).

    Emits one JSON object per line with stable keys, plus any extra attributes
    attached via ``logger.info(..., extra={...})``. Exception info is rendered
    into an ``exc_info`` string so stack traces stay on stderr, never silently
    dropped.
    """

    _RESERVED = frozenset(
        vars(logging.makeLogRecord({})).keys()
    ) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Surface structured extras (e.g. tool=, session_id=).
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Install a single stderr handler with the configured format/level."""
    level_name = os.environ.get("MCP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stderr)  # OBS-004: never stdout
    if os.environ.get("MCP_LOG_FORMAT", "text").lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_TEXT_FORMAT))

    # force=True replaces any handlers a dependency may have installed.
    logging.basicConfig(level=level, handlers=[handler], force=True)
