## Finding: SEC-016 — 0.0.0.0-Binding-Prevention (NeighborJack)

**Severity:** critical
**Status:** open
**Server:** swiss-road-mobility-mcp
**Check-Reference:** SEC-016
**PDF-Reference:** Sec 4 (Empirie 2025)

### Observed Behavior
Der Code-Default für den SSE-Listen-Host ist `0.0.0.0`:
```python
# src/swiss_road_mobility_mcp/server.py:1614
host = os.environ.get("MCP_HOST", "0.0.0.0")
```
Wird der Server lokal mit `MCP_TRANSPORT=sse` gestartet (ohne `MCP_HOST` zu setzen), bindet er an alle Interfaces.

### Expected Behavior
Der Code-Default muss `127.0.0.1` sein. Das Binden an `0.0.0.0` gehört ausschliesslich in den Container-Kontext (Dockerfile / render.yaml — dort bereits korrekt via `ENV MCP_HOST=0.0.0.0` gesetzt).

### Evidence
- File: `src/swiss_road_mobility_mcp/server.py:1614` — `os.environ.get("MCP_HOST", "0.0.0.0")`
- Dockerfile:10 + render.yaml:11 setzen `MCP_HOST=0.0.0.0` bereits explizit → Code-Default ist redundant und gefährlich.

### Risk Description
Startet ein:e Entwickler:in den SSE-Modus lokal (z.B. zum Testen) in einem öffentlichen WLAN / Co-Working-Space, ist der Server für alle Geräte im Subnetz erreichbar (NeighborJack). Da der Server mit User-Privilegien läuft und 15 Tools exponiert, kann ein Angreifer im selben Netz `tools/list` abrufen und sämtliche Tools aufrufen.

### Remediation
```diff
-         host = os.environ.get("MCP_HOST", "0.0.0.0")
+         host = os.environ.get("MCP_HOST", "127.0.0.1")
```
Container-Override bleibt im Dockerfile/render.yaml (`ENV MCP_HOST=0.0.0.0`). Optional: Warn-Log bei `0.0.0.0`-Bind ausserhalb Container-Kontext (Heuristik via `/.dockerenv` / `RENDER`-Env). README-Sektion „Network Binding" ergänzen.

### Effort Estimate
S (< 1d)
