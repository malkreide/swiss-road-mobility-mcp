# Re-Audit Report — swiss-road-mobility-mcp

**Date:** 2026-06-03 · **Baseline:** [`../2026-06-03T115912-Z-swiss-road-mobility-mcp`](../2026-06-03T115912-Z-swiss-road-mobility-mcp/audit-report.md)
**Profile:** dual transport (stdio + SSE) · Python · Public Open Data · read-only · cloud-deployed (Render)

> **Update (post PR #19):** SEC-005 and SCALE-006 — previously listed as
> out-of-scope residuals — have since been resolved. Score and tables below
> reflect the updated state (40/44 pass, 4 remaining).

## Verdict

> **`production_ready: YES`** for the stated single-instance deployment model.

All **4 critical** and all **in-scope high/medium** findings from the baseline
audit are resolved and verified in `main`. The only remaining non-`pass`
findings (4) are explicitly **out of scope** for the current architecture — they
apply solely to a *multi-server gateway* or *horizontally-scaled* deployment,
neither of which is in use.

## Score: before → after

| | Baseline | Re-audit |
|---|---|---|
| **pass** | 15 / 44 | **40 / 44** |
| partial | 18 | 4 (all out-of-scope) |
| fail | 11 | 0 |
| **critical failures** | 4 | **0** |

29 findings were non-`pass` at baseline; **25 are now resolved**, 4 remain
out-of-scope.

## Resolved findings (25)

Evidence is `file:line` in current `main`; PR is the merge that delivered it.

| ID | Sev | Base → Now | Evidence | PR |
|---|---|---|---|---|
| SEC-016 | critical | fail → **pass** | `server.py:1640` `_in_container`; default `127.0.0.1` | #2 |
| ARCH-005 | critical | partial → **pass** | `.gitignore`, `.env.example:7`, `ci.yml:47` gitleaks | #2 |
| SEC-004 | critical | partial → **pass** | `egress.py:35` allow-list; metadata IP blocked per-hop | #7 |
| SEC-009 | critical | partial → **pass** | `security.py` Bearer auth + per-IP rate limit | #4 |
| SEC-007 | high | fail → **pass** | `Dockerfile:34` `USER 10001`, `:38` HEALTHCHECK | #2 |
| SDK-004 | high | fail → **pass** | `server.py:1731` `expose_headers=[Mcp-Session-Id]` | #2 |
| OPS-001 | high | fail → **pass** | `ci.yml:38` `pytest -m "not live"`; 68 mocked tests; `live` marker | #3 |
| OBS-001 | high | partial → **pass** | `errors.py` `{isError, error:{code,message}}` + error-path tests | #5 |
| OBS-002 | high | partial → **pass** | `api_infrastructure.py:201` body logged not surfaced; `errors.unexpected_error` masks | #5 |
| SDK-001 | high | partial → **pass** | `client_lifecycle.py:36` `managed_client`; `server.py:97` `lifespan=` | #8 |
| SEC-021 | high | partial → **pass** | `egress.py:35` frozenset allow-list + per-request hook | #7 |
| SEC-013 | high | partial → **pass** | `docs/SECURITY.md` credential model | #11 |
| SEC-018 | high | partial → **pass*** | `server.py:151` `strict=True` (*regex-whitelist on free-text = future enhancement) | #11 |
| SEC-022 | high | partial → **pass*** | `docs/ARCHITECTURE.md` namespacing; `road_` prefix + `roadmobility://` (*release-time tool-hash snapshot = open) | #11 |
| OPS-003 | high | partial → **pass** | `docs/ARCHITECTURE.md` phase declaration + roadmap | #11 |
| ARCH-002 | medium | partial → **pass** | `server.py:90` `<use_case>` tags | #11 |
| ARCH-008 | medium | fail → **pass** | `server.py:1589` `@mcp.resource`; `@mcp.prompt`; documented rationale | #11 |
| ARCH-012 | medium | partial → **pass** | `.github/dependabot.yml`; `pyproject.toml` major-pins | #11 |
| OBS-003 | medium | fail → **pass** | `logging_config.py:25` `JsonFormatter`, stderr | #5 |
| OBS-006 | medium | fail → **pass** | `tracing.py:46` `configure_tracing` (OTel, httpx + ASGI) | #6 |
| SCALE-004 | medium | fail → **pass** | `Dockerfile:5` multi-stage `AS builder` | #2 |
| SDK-002 | medium | fail → **pass** | `server.py:311` tools return `dict[str, Any]` → `outputSchema` + `structuredContent` | #10 |
| SDK-003 | medium | fail → **pass** | `server.py:431` `ctx: Context`; `report_progress` in multi-step tools | #9 |
| SEC-005 | high | partial → **pass** | `egress.py` `_assert_resolves_public` — rejects hosts resolving to non-public IPs (DNS-rebinding guard) | #19 |
| SCALE-006 | medium | fail → **pass** | `docker-compose.yml` mem/cpu/pids/nofile limits + restart; `docs/OPERATIONS.md` runbook | #19 |

\* Core control implemented; minor residual noted under "Residuals" and "Out of scope".

## Verification

- `ruff check src/ tests/` → clean.
- `pytest -m "not live"` → **86 passed, 27 deselected** (offline, respx-mocked +
  real in-memory MCP-session E2E tests for tools/resources/prompts; the egress
  resolver is stubbed in `tests/conftest.py` to keep the suite offline).
- All 15 tools expose `outputSchema` + `structuredContent`; 1 Resource + 1
  Prompt verified via session.
- No regressions in the 15 baseline-`pass` findings (spot-checked: OBS-004
  stderr logging, ARCH-011 README EN/DE parity).

## Out of scope (4 remaining non-pass)

These are **intentionally deferred** — they only become relevant under a
multi-server gateway or horizontal scaling, which the current single-instance
(stdio + single Render service) deployment does not use.

| ID | Sev | Status | Why out of scope |
|---|---|---|---|
| SEC-014 | medium | partial | **Gateway tool allow-list.** Only meaningful when this server sits behind a multi-server portfolio gateway. N/A for a single server. |
| SEC-015 | medium | partial | **Tool-poisoning detection.** Relevant only when aggregating *external* third-party MCP servers via a gateway. |
| SCALE-002 | high | partial | **Sticky-session / shared state.** Mitigated by single-instance deployment; only needed for horizontal scaling. |
| SCALE-003 | high | partial | **`Mcp-Session-Id` edge routing.** Same — only needed with multiple replicas behind a load balancer. |

## Residuals on otherwise-resolved findings

Non-blocking enhancements, safe to defer:

- **SEC-018** — `strict=True` is enforced; adding regex/pattern whitelists on
  free-text fields (`search_text`, `station_name`, `destination`) would tighten
  further.
- **SEC-022** — namespacing + dependency hash-pinning are documented; emitting a
  **tool-definition hash snapshot per release** and tracking tool changes in a
  CHANGELOG is a release-engineering follow-up.
- **OPS-003** — phase roadmap is documented; a formal DSG/ISDS processing-record
  reference could be linked if required by the operator.

## Conclusion

The remediation across Phases 1–5 plus the SEC-005/SCALE-006 follow-up (PR #19)
closed every blocking and in-scope finding. The server meets `production_ready`
for its declared deployment. The 4 remaining items are gateway-/scale-only and
are documented as out-of-scope in
[`docs/SECURITY.md`](../../docs/SECURITY.md#mcp-conformance-table-ch-004).
