"""Unit tests for observability hardening (OBS-001, OBS-002, OBS-003).

No `mcp` import, no network (respx-mocked) — runs in PR CI (`-m "not live"`).
"""

import json
import logging
import sys

import pytest
import respx

from swiss_road_mobility_mcp.api_infrastructure import APIError, MobilityHTTPClient
from swiss_road_mobility_mcp.errors import (
    CODE_EXECUTION,
    CODE_RATE_LIMIT,
    CODE_UPSTREAM,
    error_envelope,
    unexpected_error,
    upstream_error,
)
from swiss_road_mobility_mcp.logging_config import JsonFormatter, configure_logging

# ===========================================================================
# OBS-001 — structured execution errors with stable codes
# ===========================================================================

class TestErrorEnvelope:
    def test_envelope_shape(self):
        data = json.loads(error_envelope(CODE_UPSTREAM, "boom"))
        assert data["isError"] is True
        assert data["error"] == {"code": CODE_UPSTREAM, "message": "boom"}

    def test_upstream_error_preserves_curated_message(self):
        data = json.loads(upstream_error(APIError("Datenquelle nicht erreichbar.")))
        assert data["error"]["code"] == CODE_UPSTREAM
        assert data["error"]["message"] == "Datenquelle nicht erreichbar."

    def test_upstream_error_detects_rate_limit(self):
        data = json.loads(upstream_error(APIError("Rate Limit für 'x' erreicht.")))
        assert data["error"]["code"] == CODE_RATE_LIMIT


# ===========================================================================
# OBS-002 — mask details, log server-side
# ===========================================================================

class TestMasking:
    def test_unexpected_error_masks_and_logs(self, caplog):
        caplog.set_level(logging.ERROR, logger="swiss-road-mobility-mcp")
        try:
            raise ValueError("SECRET internal detail 0xCAFE")
        except Exception:
            out = unexpected_error("road_demo")
        data = json.loads(out)
        assert data["isError"] is True
        assert data["error"]["code"] == CODE_EXECUTION
        # The raw exception text must NOT reach the client.
        assert "SECRET" not in out
        assert "0xCAFE" not in out
        # But it IS logged server-side (with the tool context + traceback).
        assert any("road_demo" in r.getMessage() for r in caplog.records)
        assert any(r.exc_info for r in caplog.records)

    @respx.mock
    async def test_apierror_does_not_leak_upstream_body(self):
        client = MobilityHTTPClient()
        try:
            respx.get("https://data.geo.admin.ch/x").respond(500, text="DB STACKTRACE SECRET")
            with pytest.raises(APIError) as exc:
                await client.get_json("https://data.geo.admin.ch/x")
            msg = str(exc.value)
            assert "SECRET" not in msg and "STACKTRACE" not in msg
            assert "500" in msg
        finally:
            await client.close()


# ===========================================================================
# OBS-003 — structured (JSON) logging
# ===========================================================================

class TestJsonFormatter:
    def test_basic_record(self):
        rec = logging.LogRecord("svc", logging.INFO, "p", 1, "hello %s", ("world",), None)
        data = json.loads(JsonFormatter().format(rec))
        assert data["level"] == "INFO"
        assert data["logger"] == "svc"
        assert data["message"] == "hello world"
        assert "timestamp" in data

    def test_includes_structured_extra(self):
        rec = logging.LogRecord("svc", logging.INFO, "p", 1, "m", (), None)
        rec.tool = "road_find_sharing"
        rec.session_id = "abc"
        data = json.loads(JsonFormatter().format(rec))
        assert data["tool"] == "road_find_sharing"
        assert data["session_id"] == "abc"

    def test_renders_exception(self):
        try:
            raise ValueError("boom")
        except Exception:
            rec = logging.LogRecord("svc", logging.ERROR, "p", 1, "m", (), sys.exc_info())
        data = json.loads(JsonFormatter().format(rec))
        assert "exc_info" in data
        assert "ValueError" in data["exc_info"]


class TestConfigureLogging:
    @staticmethod
    def _restore(saved_handlers, saved_level):
        root = logging.getLogger()
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)

    def test_json_format_installs_json_formatter(self, monkeypatch):
        root = logging.getLogger()
        saved_handlers, saved_level = root.handlers[:], root.level
        try:
            monkeypatch.setenv("MCP_LOG_FORMAT", "json")
            configure_logging()
            assert any(isinstance(getattr(h, "formatter", None), JsonFormatter)
                       for h in root.handlers)
            assert all(getattr(h, "stream", sys.stderr) is sys.stderr
                       for h in root.handlers if isinstance(h, logging.StreamHandler))
        finally:
            self._restore(saved_handlers, saved_level)

    def test_text_format_default(self, monkeypatch):
        root = logging.getLogger()
        saved_handlers, saved_level = root.handlers[:], root.level
        try:
            monkeypatch.delenv("MCP_LOG_FORMAT", raising=False)
            configure_logging()
            assert not any(isinstance(getattr(h, "formatter", None), JsonFormatter)
                           for h in root.handlers)
        finally:
            self._restore(saved_handlers, saved_level)
