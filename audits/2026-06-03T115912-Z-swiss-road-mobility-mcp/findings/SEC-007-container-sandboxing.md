## Finding: SEC-007 — Container-Sandboxing

**Severity:** high
**Status:** open
**Server:** swiss-road-mobility-mcp
**Check-Reference:** SEC-007
**PDF-Reference:** Sec 4.5

### Observed Behavior
Das Dockerfile führt den Server als `root` aus, ohne Privileg-Reduktion:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .
ENV MCP_TRANSPORT=sse ...
CMD ["swiss-road-mobility-mcp"]
```
Kein `USER`, kein `HEALTHCHECK`, kein read-only-Filesystem, keine Capability-Drops.

### Expected Behavior
Non-root-User (UID ≥ 10000), `HEALTHCHECK`, bei K8s zusätzlich `runAsNonRoot`, `readOnlyRootFilesystem`, `capabilities.drop: ["ALL"]`, `seccompProfile: RuntimeDefault`.

### Evidence
- File: `Dockerfile:1-12` — kein `USER`, kein `HEALTHCHECK`

### Risk Description
Wird der Server-Code kompromittiert (Supply-Chain, Bug), läuft der Angreifer-Code als root im Container — Container-Escape und Privileg-Eskalation werden erleichtert. Für einen öffentlich erreichbaren Render-Service ist das eine relevante Defense-in-Depth-Lücke.

### Remediation
```diff
+ RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin mcp \
+     && chown -R mcp:mcp /app
+ USER 10001
+ HEALTHCHECK CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"MCP_PORT\",\"8001\")}/')" || exit 1
```
Optional Multi-Stage-Build (siehe SCALE-004) für kleinere Angriffsfläche.

### Effort Estimate
S (< 1d)
