# Security Model

Security posture and the rationale behind each control. Addresses audit findings
**SEC-013**, **SEC-022** and the **CH-004** conformance table, and summarises the
controls shipped during the post-audit hardening track.

## Credentials & secrets (SEC-013)

This server brokers **public open data**. Of the 15 tools, only the three
Phase-2 traffic tools need a credential:

- **`OPENTRANSPORTDATA_API_KEY`** — a *free* key from
  [api-manager.opentransportdata.swiss](https://api-manager.opentransportdata.swiss).
- It is read from a **plain environment variable** (`server._get_api_key`). This
  is acceptable here because:
  - the key only unlocks **read access to public traffic data** (no PII, no
    write, no billing exposure);
  - there are no other secrets, sessions, or user data to protect;
  - env-var injection is the standard, audited delivery path for MCP hosts
    (Claude Desktop `env` block, Render/host secret store).
- **Never commit the key.** `.env` is git-ignored and `.env.example` documents
  the variable. A gitleaks CI step (ARCH-005) scans every push.
- **Rotation:** revoke/reissue in the opentransportdata portal and update the
  host's environment; no code change required.
- The key is **never logged** and **never returned to the LLM**; upstream error
  bodies are logged server-side only (OBS-002).

If a future phase introduces a higher-value secret, migrate to a secret manager
(env-var injection from a vault) rather than embedding it.

## Supply-chain & dependency integrity (SEC-022)

- Direct dependencies are **major-pinned** in `pyproject.toml`
  (`mcp[cli]>=1.0.0,<2.0.0`, `httpx<1.0.0`, `pydantic<3.0.0`) so a breaking
  upstream release cannot silently enter (ARCH-012).
- **Dependabot** (`.github/dependabot.yml`) proposes weekly updates for both pip
  and GitHub Actions; CI gates every bump.
- **Hash-pinning** for fully reproducible installs is recommended for production
  deployments: generate a hashed lockfile (e.g. `pip-compile --generate-hashes`
  or `uv pip compile`) and install with `--require-hashes`. The library ships
  with version ranges; the deploying environment owns the lockfile.

## Network controls (summary)

| Control | Finding | Where |
|---|---|---|
| Default bind `127.0.0.1` (0.0.0.0 only in containers) | SEC-016 | `server._in_container` / `_run_sse` |
| Outbound egress **allow-list** (per request, incl. redirects) | SEC-004 / SEC-021 | `egress.py` |
| **Resolved-IP guard** (reject hosts resolving to private/internal IPs) | SEC-005 | `egress.py` (`_assert_resolves_public`) |
| SSE **Bearer auth** (optional) + per-IP **rate limiting** | SEC-009 | `security.py` |
| CORS with explicit `expose_headers=[Mcp-Session-Id]` | SDK-004 | `server._run_sse` |
| Container runs **non-root** + healthcheck | SEC-007 | `Dockerfile` |
| Input validation: `extra="forbid"` + `strict=True` | SEC-018 | tool input models |
| Errors masked; no `str(e)`/upstream body to the LLM | OBS-002 | `errors.py`, `api_infrastructure.py` |

## MCP conformance table (CH-004)

Status of the server against the MCP build/security checklist. ✅ = addressed,
⚪ = intentionally out of scope (documented).

| # | Item | Status | Reference |
|---|---|---|---|
| 1 | Localhost-default bind | ✅ | SEC-016 |
| 2 | Authn/throttle before public transport | ✅ | SEC-009 (`security.py`) |
| 3 | Secret hygiene (`.gitignore`, `.env.example`, gitleaks) | ✅ | ARCH-005 |
| 4 | Container non-root + healthcheck + multi-stage | ✅ | SEC-007 / SCALE-004 |
| 5 | CORS exposes `Mcp-Session-Id` | ✅ | SDK-004 |
| 6 | SSRF egress allow-list | ✅ | SEC-004 / SEC-021 (`egress.py`) |
| 7 | Mocked unit tests + `live` split + CI | ✅ | OPS-001 |
| 8 | Structured errors (`isError` + codes) | ✅ | OBS-001 (`errors.py`) |
| 9 | Error masking | ✅ | OBS-002 |
| 10 | Structured / JSON logging to stderr | ✅ | OBS-003 (`logging_config.py`) |
| 11 | Distributed tracing (optional) | ✅ | OBS-006 (`tracing.py`) |
| 12 | Lifespan-managed shared client | ✅ | SDK-001 (`client_lifecycle.py`) |
| 13 | `Context` + progress for long tools | ✅ | SDK-003 |
| 14 | Structured tool outputs + `outputSchema` | ✅ | SDK-002 |
| 15 | Strict input validation | ✅ | SEC-018 |
| 16 | Tool namespacing (`road_` prefix) | ✅ | SEC-022 / ARCH-002 |
| 17 | Resources/Prompts audited | ✅ | ARCH-008 ([ARCHITECTURE.md](./ARCHITECTURE.md)) |
| 18 | Dependency pinning + Dependabot | ✅ | ARCH-012 |
| 19 | Phase declaration / roadmap | ✅ | OPS-003 ([ARCHITECTURE.md](./ARCHITECTURE.md)) |
| 20 | Resolved-IP / DNS-rebinding guard | ✅ | SEC-005 (`egress.py`) |
| 21 | Resource/CPU/FD/PID limits + restart policy | ✅ | SCALE-006 (`docker-compose.yml`, [OPERATIONS.md](./OPERATIONS.md)) |
| 22 | Gateway allow-list / tool-poisoning detection | ⚪ | SEC-014/015 — only relevant behind a multi-server gateway |
| 23 | Sticky-session / shared state | ⚪ | SCALE-002/003 — only for horizontal scaling |

## Reporting

Found a vulnerability? Open a private security advisory on the GitHub repository
rather than a public issue.
