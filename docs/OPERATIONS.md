# Operations Runbook

Operational guidance for running the server with explicit resource bounds,
restart behaviour and health monitoring. Addresses audit finding **SCALE-006**.

## Resource limits (SCALE-006)

The process is small (an async HTTP aggregator with in-memory caches), but every
deployment should cap memory, CPU, file descriptors and PIDs so a bug or a load
spike cannot starve the host. Recommended baseline:

| Resource | Baseline | Why |
|---|---|---|
| Memory | 256 MB limit / 128 MB reservation | In-memory caches (EV GeoJSON ~ a few MB) + headroom. OOM-kill caps a leak. |
| CPU | 0.5 vCPU | I/O-bound; rarely CPU-bound. |
| File descriptors (`nofile`) | 1024 soft / 2048 hard | Bounds concurrent sockets to upstreams. |
| PIDs | 256 | Caps thread/process explosion. |

### Docker / Compose

`docker-compose.yml` ships these limits (plus `read_only`, `cap_drop: ALL`,
`no-new-privileges`, non-root user from the Dockerfile):

```bash
docker compose up --build
```

Or with `docker run`:

```bash
docker run --rm \
  --memory 256m --cpus 0.5 --pids-limit 256 \
  --ulimit nofile=1024:2048 \
  --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  -e MCP_AUTH_TOKEN=change-me \
  -p 127.0.0.1:8001:8001 \
  swiss-road-mobility-mcp:latest
```

### Kubernetes

```yaml
resources:
  requests: { memory: "128Mi", cpu: "100m" }
  limits:   { memory: "256Mi", cpu: "500m" }
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities: { drop: ["ALL"] }
```

### Render (managed)

Memory/CPU are fixed by the selected plan and Render **auto-restarts** the
service on crash/OOM — the platform owns these limits. Keep `render.yaml`'s plan
appropriate for the workload; the free plan suffices for light use.

## Restart policy & OOM behaviour

- **Docker/Compose:** `restart: unless-stopped` — the container is restarted on
  non-zero exit and OOM-kill, but stays down after an explicit `docker stop`.
- **Kubernetes:** default `restartPolicy: Always` for Deployments.
- **Render:** automatic restart on crash.
- On OOM-kill the process is terminated (SIGKILL); there is no in-process state
  to lose — caches are rebuilt lazily and the shared HTTP client is recreated by
  the lifespan (SDK-001).

## Health monitoring

- **Liveness:** TCP connect to `MCP_PORT` (shipped as Docker `HEALTHCHECK` and
  the Compose `healthcheck`).
- **Diagnostics:** the `road_check_status` tool probes every upstream and reports
  reachability without failing the tool call.
- **Logs:** stderr; set `MCP_LOG_FORMAT=json` for ingestion. See
  [`SECURITY.md`](./SECURITY.md) and [`ARCHITECTURE.md`](./ARCHITECTURE.md).
- **Tracing:** optional OpenTelemetry via `MCP_TRACING_ENABLED` (OBS-006).
