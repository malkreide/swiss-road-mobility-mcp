# Security Policy & Posture

[🇩🇪 Deutsche Version](SECURITY.de.md)

`swiss-road-mobility-mcp` was hardened against the internal MCP best-practice
audit catalogue. This document summarises the security posture and records the
**accepted-risk** decisions for controls that are deliberately handled at the
portfolio/gateway layer rather than inside this single server.

The full technical security model lives in [`docs/SECURITY.md`](docs/SECURITY.md)
(credential model, egress allow-list, MCP conformance table); the audit reports
are under [`audits/`](audits/).

## Reporting a vulnerability

Please open a private security advisory on the GitHub repository, or contact the
maintainer listed in `README.md`. Do not file public issues for exploitable
vulnerabilities.

## Posture summary

This is a **read-only**, **no-PII**, **public-open-data** MCP server. All 15
tools only issue HTTP GET requests to a fixed set of Swiss open-data providers.
Hardening already in place:

| Area | Control |
|---|---|
| Egress | HTTPS-enforced allow-list to the configured open-data hosts only (SEC-004/021) |
| SSRF | Resolved-IP guard rejecting hosts that resolve to private/internal IPs, incl. redirects (SEC-005) |
| Binding | Network transports default to `127.0.0.1` (`0.0.0.0` only in containers) (SEC-016) |
| Transport | SSE/HTTP with CORS exposing only `Mcp-Session-Id` (SDK-004) |
| Auth | Optional SSE Bearer token + per-IP rate limiting for public endpoints (SEC-009) |
| Input | Pydantic v2 strict validation (`extra="forbid"`, `strict=True`) + XML escaping (SEC-018) |
| Secrets | Env-vars only, `.gitignore` guards `.env`, gitleaks in CI, no hardcoded secrets (ARCH-005/SEC-013) |
| Errors | Upstream bodies logged to stderr, never forwarded to the model (OBS-002) |
| Stdout | Reserved for the JSON-RPC stream; logging pinned to stderr (OBS-004) |
| Container | Runs non-root with a healthcheck (SEC-007) |
| Tool surface | `road_` namespacing; tool definitions version-controlled, no dynamic registration (SEC-022/ARCH-002) |

See [`audits/`](audits/) for the full reports and `CHANGELOG.md` for the
hardening history.

## Accepted risks (portfolio-level controls)

The following audit checks are **not** implemented inside this server by design.
They are portfolio-wide concerns best enforced at an MCP gateway / host layer,
and the residual risk here is low because the server is read-only and only
reaches a small set of trusted public-data providers.

### SEC-014 — Tool allow-listing via an MCP gateway

**Status:** accepted risk (portfolio-level).
A per-tool allow-list belongs to the MCP host/gateway that aggregates multiple
servers, not to an individual server that exposes a fixed, read-only tool set.
If/when a central gateway is introduced for the portfolio, tool allow-listing
should be configured there. Until then, the risk is bounded: every tool is
read-only and constrained by the egress allow-list above.

### SEC-015 — Pre-flight tool-poisoning detection

**Status:** accepted risk (portfolio-level).
Tool-poisoning (malicious tool descriptions / rug-pulls) is a supply-chain and
host-side concern. This server's tool definitions are version-controlled and
shipped from this repository; there is no dynamic/remote tool registration.
Cross-server poisoning detection remains a gateway/host responsibility tracked
at the portfolio level.

## Re-evaluation triggers

These acceptances should be revisited if the server ever:

- gains **write** capability or starts processing **PII**, or
- registers tools **dynamically** / from remote sources, or
- is aggregated behind a shared MCP gateway (then implement SEC-014/015 there).
