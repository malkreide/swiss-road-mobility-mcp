# MCP-Server Audit-Report — `swiss-road-mobility-mcp`

**Audit-Datum:** 2026-06-03
**Run-ID:** `2026-06-03T115912-Z-swiss-road-mobility-mcp`
**Skill:** mcp-audit-skill v0.5.0
**Catalog-Hash:** `091f446b…093c0` (68 Checks, 8 Kategorien)
**Findings-Policy:** `fail-or-partial`

> Alle Zahlen stammen aus `summary.json` (Single Source of Truth).

---

## 1. Executive Summary

Der Server `swiss-road-mobility-mcp` (15 read-only Tools für Schweizer Strassen-/Mobilitätsdaten, FastMCP/Python, dual-transport, Public Open Data, Deployment lokal-stdio + Render-SSE) wurde gegen **44 anwendbare** von 68 Checks geprüft: **15 PASS, 18 PARTIAL, 11 FAIL** — insgesamt **29 Findings** (4 critical, 14 high, 11 medium).

**Production-ready: NEIN.** Blockierend (fail bei critical/high): **SEC-016, OPS-001, SEC-007, SDK-004**.

Architektur und Tool-Design sind solide (saubere Annotations, Input-Validierung, Aggregations-Tools, keine Command-Injection, keine hardcoded Secrets, korrekte Quellenangaben). Die Lücken liegen konzentriert bei **Cloud-/Netzwerk-Härtung** (0.0.0.0-Default, kein Auth am öffentlichen SSE-Endpoint, kein Container-Hardening, kein CORS), **Test-/CI-Disziplin** (Live-only-Tests, CI führt kein pytest aus) und **SDK-Reife** (keine strukturierten Returns, kein Context, kein Lifespan).

---

## 2. Profil-Snapshot

| Feld | Wert |
|---|---|
| Server-Name | `swiss-road-mobility-mcp` (v0.4.0) |
| Repo | github.com/malkreide/swiss-road-mobility-mcp |
| SDK / Sprache | Python / FastMCP |
| Transport | dual (Default stdio, SSE via `MCP_TRANSPORT`) |
| Auth-Modell | none |
| Datenklasse | Public Open Data |
| Schreibzugriff | read-only (alle 15 Tools `readOnlyHint:true`) |
| Deployment | local-stdio + Render (SSE, free plan) → `is_cloud_deployed: true` |
| Externe Requests | ja (sharedmobility.ch, ich-tanke-strom.ch, geo.admin.ch, data.sbb.ch, opentransportdata.swiss, transport.opendata.ch) |

---

## 3. Applicability (44 / 68 Checks anwendbar)

| Kategorie | Pass | Fail | Partial | Anwendbar |
|---|:-:|:-:|:-:|:-:|
| ARCH  | 7 | 1 | 3 | 11 |
| SDK   | 0 | 3 | 1 | 4 |
| SEC   | 4 | 2 | 9 | 15 |
| SCALE | 1 | 2 | 2 | 5 |
| OBS   | 1 | 2 | 2 | 5 |
| OPS   | 1 | 1 | 1 | 3 |
| CH    | 1 | 0 | 0 | 1 |
| HITL  | – | – | – | 0 (read-only, kein Sampling) |
| **Total** | **15** | **11** | **18** | **44** |

Nicht anwendbar (24): u.a. alle HITL (read-only), OAuth-/Confused-Deputy-Checks (auth_model none), Path-Traversal/Filesystem (kein FS-Tool), die meisten CH-Compliance (Public Open Data, kein PII), TypeScript-Checks.

**Findings nach Severity:** critical 4 · high 14 · medium 11 · low 0.

---

## 4. Findings-Übersicht (29)

### 🔴 Blockierend (critical/high mit Status `fail`)

| ID | Sev | Status | Kurzbefund |
|---|---|---|---|
| SEC-016 | critical | fail | Code-Default `MCP_HOST=0.0.0.0` → NeighborJack bei lokalem SSE |
| OPS-001 | high | fail | Live-only-Tests, kein Mocking; CI führt `pytest` nicht aus |
| SEC-007 | high | fail | Container läuft als root, kein USER/HEALTHCHECK/Hardening |
| SDK-004 | high | fail | Keine CORS-Middleware → `Mcp-Session-Id` für Browser nicht exponiert |

### 🟠 Kritisch, aber `partial` (Kernrisiko abwesend, Härtung fehlt)

| ID | Sev | Status | Kurzbefund |
|---|---|---|---|
| ARCH-005 | critical | partial | Keine hardcoded Secrets ✓, aber keine `.gitignore`/`.env.example`/CI-Scan |
| SEC-004 | critical | partial | Keine User-URLs ✓, aber `follow_redirects=True`, kein HTTPS/IP-Guard |
| SEC-009 | critical | partial | Öffentlicher SSE-Endpoint **ohne jegliche Authentifizierung** |

### 🟡 High (`partial`)

| ID | Status | Kurzbefund |
|---|---|---|
| OBS-001 | partial | Fehler als `{error:…}`-JSON statt MCP `isError`/Codes |
| OBS-002 | partial | `str(e)` + Upstream-Body[:200] ans LLM; kein `mask_error_details` |
| OPS-003 | partial | De-facto Phase 1, aber keine Phasendeklaration/roadmap |
| SCALE-002 | partial | Kein Sticky-Session/Shared-State (Single-Instance mitigiert) |
| SCALE-003 | partial | Kein Mcp-Session-Id-Edge-Routing |
| SDK-001 | partial | Kein Lifespan; per-Call `httpx.AsyncClient` in 5 Modulen |
| SEC-005 | partial | Kein DNS-Pinning |
| SEC-013 | partial | Plain-Env-Key (für Public Data ok, aber undokumentiert) |
| SEC-018 | partial | Pydantic+extra=forbid ✓, aber kein `strict=True`/Regex-Whitelist |
| SEC-021 | partial | Hosts hardcoded ✓, aber keine frozenset-Allow-List/Network-Policy |
| SEC-022 | partial | `road_`-Prefix ✓, aber kein Server-Namespace/Hash-Pinning |

### ⚪ Medium

| ID | Status | Kurzbefund |
|---|---|---|
| ARCH-002 | partial | Use-Cases in Prosa, keine `<use_case>`-Tags |
| ARCH-008 | fail | Nur Tools, keine Resources/Prompts, keine Begründung |
| ARCH-012 | partial | Keine `protocol_version`-Pinnung, kein Dependabot |
| OBS-003 | fail | Kein structlog/JSON-Logging, keine correlation-id |
| OBS-006 | fail | Kein OpenTelemetry-Tracing (cloud-deployed) |
| SCALE-004 | fail | Single-Stage-Dockerfile, kein non-root/Healthcheck |
| SCALE-006 | fail | Keine Memory/CPU/FD-Limits |
| SDK-002 | fail | Tool-Returns `-> str`, kein strukturierter Output-Type |
| SDK-003 | fail | Kein `ctx: Context`, kein Progress bei langen Tools |
| SEC-014 | partial | Keine Tool-Allow-List (geringe Relevanz, Single-Server) |
| SEC-015 | partial | Keine Tool-Poisoning-Detection (Relevanz erst bei Gateway) |

---

## 5. Detail-Findings (blockierend + critical)

Vollständige Finding-Dokumente mit Code-Diffs unter [`findings/`](./findings/):

- [`SEC-016`](./findings/SEC-016-default-bind-0000.md) — 0.0.0.0-Binding (NeighborJack) · **S**
- [`OPS-001`](./findings/OPS-001-test-strategy.md) — Test-Strategie / CI · **M**
- [`SEC-007`](./findings/SEC-007-container-sandboxing.md) — Container-Sandboxing · **S**
- [`SDK-004`](./findings/SDK-004-cors-session-id.md) — CORS `Mcp-Session-Id` · **S**
- [`SEC-009`](./findings/SEC-009-unauthenticated-public-endpoint.md) — Unauthentifizierter SSE-Endpoint · **M**
- [`SEC-004`](./findings/SEC-004-ssrf-redirects.md) — SSRF / `follow_redirects` · **M**
- [`ARCH-005`](./findings/ARCH-005-secret-hygiene.md) — Secret-Hygiene (`.gitignore`) · **S**

Evidenz und Gaps **aller** 29 Findings (mit `datei:zeile`) in [`verification-results.json`](./verification-results.json).

---

## 6. Remediation-Plan (empfohlene Reihenfolge)

**Sprint 1 — Blocker & kritische Netzwerk-Härtung (≈ 3–5 Tage)**
1. **SEC-016** (S) — Code-Default auf `127.0.0.1`. *Einzeiler, höchste Hebelwirkung.*
2. **SEC-009** (S–M) — Grundsatzentscheid: SSE-Deployment einstellen (nur stdio) **oder** Auth/Rate-Limit vor den Endpoint. *Wichtigste Architekturfrage.*
3. **ARCH-005** (S) — `.gitignore` + `.env.example` + gitleaks-CI-Step.
4. **SEC-007** (S) — Dockerfile non-root USER + HEALTHCHECK.
5. **SDK-004** (S) — CORS-Middleware mit `expose_headers=["Mcp-Session-Id"]`.
6. **SEC-004 / SEC-005** (M) — zentraler `safe_fetch` (HTTPS+IP-Guard+DNS-Pinning), `follow_redirects=False`.

**Sprint 2 — Test/CI & Observability (≈ 3–4 Tage)**
7. **OPS-001** (M) — respx-Unit-Tests + `live`-Marker + `pytest -m "not live"` im CI.
8. **OBS-002** (S) — `mask_error_details`, keine `str(e)`/Upstream-Body-Leaks.
9. **OBS-001** (M) — `isError`-Pattern + standardisierte Codes.
10. **OBS-003** (S) — structlog/JSON-Logging.

**Sprint 3 — SDK-Reife & Doku (≈ 3–4 Tage)**
11. **SDK-002** (S) — Pydantic-Return-Modelle (source/provenance/count-Envelope).
12. **SDK-001** (S) — FastMCP-Lifespan + geteilter httpx-Client.
13. **SDK-003** (S) — `ctx: Context` + Progress in Aggregations-Tools.
14. **SCALE-004/006** (S) — Multi-Stage-Build + Resource-Limits.
15. **ARCH-012** (S) — `protocol_version` pinnen + Dependabot.
16. **ARCH-008 / ARCH-002 / SEC-021/022 / SEC-013/018 / OPS-003 / CH-004-Tabelle** — Resources-Audit, Use-Case-Tags, Egress-Allow-List, strict-Mode, Phasendoku.

**Sprint 4 — nur bei Multi-Server-Gateway**
17. SEC-014, SEC-015 (Gateway-Allow-List, Tool-Poisoning-Detection), SCALE-002/003 (Sticky/Shared-State) — erst bei horizontaler Skalierung / Portfolio-Gateway.

---

## 7. Audit-Metadata

| Feld | Wert |
|---|---|
| Run-ID | `2026-06-03T115912-Z-swiss-road-mobility-mcp` |
| Skill-Version | 0.5.0 |
| Catalog-Hash | `091f446b27965044ce658a1d5f4b2cabe2b0ab5661dcc1a53b6be8f1f2e093c0` |
| Anwendbare Checks | 44 / 68 |
| Findings (fail+partial) | 29 |
| Production-ready | false |
| Methodik | mcp-audit-skill (Profil → Applicability → Check-Execution → Findings → Report) |
