## Finding: SDK-004 — CORS Mcp-Session-Id Exposure

**Severity:** high
**Status:** open
**Server:** swiss-road-mobility-mcp
**Check-Reference:** SDK-004
**PDF-Reference:** Sec 3.1

### Observed Behavior
Der Server wird via SSE in der Cloud (Render) deployed (`render.yaml`: `MCP_TRANSPORT=sse`), hat aber **keine CORS-Middleware** konfiguriert (grep nach `CORS`/`expose_headers`/`allow_origins` negativ).

### Expected Behavior
Bei HTTP/SSE-Transport muss eine CORS-Middleware den `Mcp-Session-Id`-Header über `expose_headers` freigeben, damit Browser-Clients die Session-ID lesen und an Folge-Requests anhängen können.

### Evidence
- `src/swiss_road_mobility_mcp/server.py` — keine CORSMiddleware / `expose_headers`
- `render.yaml:8-12` — SSE-Deployment

### Risk Description
Browser-basierte MCP-Clients auf anderer Origin können den `Mcp-Session-Id`-Header nicht auslesen → Folge-Requests landen ohne Session → der Server behandelt jeden Request als neue Session → stateful-Verhalten/Konversation bricht. Symptom ist subtil: stdio- und Server-Side-curl-Tests funktionieren, nur echte Browser-Clients brechen.

### Remediation
CORSMiddleware in die Starlette/ASGI-App einhängen mit `expose_headers=["Mcp-Session-Id"]`, `allow_headers` inkl. `Mcp-Session-Id`, `allow_origins` aus `ALLOWED_ORIGINS`-Env (keine Wildcard in Production).

### Effort Estimate
S (< 1d)
