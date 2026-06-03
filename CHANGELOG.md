# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-06-03

Security-, observability- and SDK-maturity hardening release implementing the
full remediation of the 2026-06-03 audit (29 non-pass findings → 25 resolved,
4 documented out-of-scope; **`production_ready: YES`**). Tool inputs/outputs stay
backward compatible — JSON text is preserved, structured output is added.

### Added
- **SSE authentication & rate limiting** (SEC-009): optional `MCP_AUTH_TOKEN` Bearer gate + per-IP sliding-window limiter (`security.py`).
- **Outbound egress allow-list** (SEC-004/021) enforced per request incl. redirect hops, plus a **resolved-IP guard** rejecting non-public IPs (SEC-005) (`egress.py`).
- **Structured logging** with optional JSON formatter to stderr (OBS-003/004) via `MCP_LOG_FORMAT` / `MCP_LOG_LEVEL`.
- **OpenTelemetry tracing** (OBS-006, optional `tracing` extra): httpx auto-instrumentation + SSE ASGI spans.
- **Lifespan-managed shared HTTP client** (SDK-001); **`Context` progress/logging** in multi-step tools (SDK-003).
- **Structured tool outputs**: tools return `dict` → `outputSchema` + `structuredContent` (SDK-002).
- **MCP Resource** `roadmobility://data-sources` + **Prompt** `plan_trip` (ARCH-008); `<use_case>` tags (ARCH-002).
- **Tests + CI**: respx-mocked offline unit tests, `live` marker, in-memory MCP-session E2E tests; CI runs `pytest -m "not live"` (OPS-001); nightly live-test workflow.
- **Docs**: `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/OPERATIONS.md`; `docker-compose.yml` with resource limits (SCALE-006); `.github/dependabot.yml` (ARCH-012); `.env.example`.

### Changed
- **Default SSE bind is now `127.0.0.1`** (was `0.0.0.0`; `0.0.0.0` only inside a container) (SEC-016).
- **CORS** exposes `Mcp-Session-Id` for browser clients (SDK-004).
- **Input validation** hardened with Pydantic `strict=True` + `extra="forbid"` (SEC-018).
- **Error handling**: structured `{isError, error:{code, message}}` envelopes (OBS-001); exception/upstream details logged server-side only, never surfaced to the LLM (OBS-002).
- **Dockerfile**: multi-stage build, non-root user, healthcheck (SEC-007 / SCALE-004).
- **Dependencies** major-pinned: `mcp`, `httpx`, `pydantic` (ARCH-012).
- **Versioning unified** to a single source of truth in `__init__.py`; `User-Agent` and `road_check_status` derive from it (previously drifted across 0.1.0/0.2.0/0.3.1/0.4.0).

### Security
- Closes all critical/high audit findings. See [`docs/SECURITY.md`](docs/SECURITY.md) and the re-audit verdict in [`audits/2026-06-03-re-audit/`](audits/2026-06-03-re-audit/) (40/44 pass).

## [0.4.0] - 2026-03-15

### Added
- **Phase 4 — Geography & Addresses** (geo.admin.ch, no API key):
  - `road_geocode_address`: Swiss address to GPS coordinates (official building register)
  - `road_reverse_geocode`: GPS to official address with EGID/EGAID (GWR)
  - `road_classify_road`: Road classification via swissTLM3D

## [0.3.1] - 2026-03-04

### Fixed
- `park_rail.py`: SBB renamed dataset `park-and-rail` causing HTTP 404. Added fallback chain across 3 candidate endpoints with clear error message linking to data.sbb.ch
- `ev_charging.py`: `ChargingStationNames` arrives as `dict` or `list` depending on operator. Fixed with `isinstance` normalization
- `multimodal.py`: `transport.opendata.ch` returns `duration` as string `'HH:MM:SS'`, not integer. Fixed with robust string-to-seconds conversion
- `multimodal.py`: `build_mobility_snapshot()` crashed with `NoneType has no attribute 'get'` when Park+Rail query returned `None`. Added `or {}` guard with fallback empty facilities list
- `server.py`: `road_check_status()` used `HEAD` request for sharedmobility API which only supports `GET`. Fixed to use `GET` for sharedmobility, `HEAD` for others
- `shared_mobility.py`: Documented that `sharedmobility.ch` does not enforce strict radius filtering (API behaviour, no code fix needed)

## [0.3.0] - 2026-03-01

### Added
- **Phase 3 — Park & Rail + Multimodal** (no API key):
  - `road_park_rail`: SBB Park+Rail facilities nearby
  - `road_mobility_snapshot`: Aggregated mobility overview for a location
  - `road_multimodal_plan`: Car to Park+Rail to public transport trip planning
