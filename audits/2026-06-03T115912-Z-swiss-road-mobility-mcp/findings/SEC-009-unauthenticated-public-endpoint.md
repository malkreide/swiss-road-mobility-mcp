## Finding: SEC-009 — Session-ID Cryptographic Binding / Unauthentifizierter Endpoint

**Severity:** critical
**Status:** open
**Server:** swiss-road-mobility-mcp
**Check-Reference:** SEC-009
**PDF-Reference:** Sec 4.6

### Observed Behavior
Der Server hat kein Auth-Modell (`auth_model: none`) und wird gleichzeitig als öffentlicher SSE-Service auf Render deployed (`render.yaml`). Es gibt keine eigene Session-Validierung, kein User-Konzept und damit keine kryptografische Bindung Session↔User.

### Expected Behavior
Für netzwerk-exponierte Server fordert der Katalog Session-IDs mit ≥128 Bit Entropie, gebunden an eine **validierte** User-Identität, mit TTL und serverseitiger Invalidierung. Das setzt ein Auth-Modell voraus.

### Evidence
- `src/swiss_road_mobility_mcp/server.py:42-65` — FastMCP ohne Auth/Middleware
- `render.yaml` — öffentlicher SSE-Web-Service ohne vorgelagerte Authentifizierung

### Risk Description
Klassisches Session-Hijacking im engeren Sinn ist mangels User-Konzept nicht das Hauptproblem — das eigentliche Risiko ist der **vollständig unauthentifizierte, öffentlich erreichbare MCP-Endpoint**. Jede Entität im Internet kann `tools/list` + `tools/call` ausführen. Bei reinen Public-Open-Data-Read-Tools ist der Datenschaden begrenzt, aber: (a) der Server verbraucht für jeden anonymen Aufruf Upstream-API-Quote (DoS-/Quota-Exhaustion-Vektor, u.a. der gratis OPENTRANSPORTDATA-Key), (b) der Server wird zum offenen Proxy für die Upstream-APIs.

### Remediation
Entscheidung dokumentieren und eine der Optionen umsetzen:
1. **Lokal-only**: SSE-Deployment einstellen, nur stdio (eliminiert die Angriffsfläche vollständig — passt zu Public-Data-Demo).
2. **Auth vorlagern**: Reverse-Proxy / API-Gateway mit Token-Auth oder OAuth-Resource-Server vor den SSE-Endpoint; Session-ID an validierten `sub`-Claim binden, TTL + Invalidierung.
3. Mindestens Rate-Limiting pro Client-IP am Edge + Egress-Quota-Schutz.

### Effort Estimate
M (1-3d) — abhängig von gewählter Option (Option 1: S)
