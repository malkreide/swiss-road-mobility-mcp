# syntax=docker/dockerfile:1
# Multi-stage build (SCALE-004) + container hardening (SEC-007).

# ---- Build stage -----------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ src/

# Install into an isolated venv so the runtime image carries only the
# resolved dependencies, no build toolchain.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir .

# ---- Runtime stage ---------------------------------------------------------
FROM python:3.12-slim AS runtime

# SEC-007: dedicated non-root user (UID >= 10000).
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin mcp

COPY --from=builder /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    MCP_TRANSPORT=sse \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8001

# 0.0.0.0 is intentional here: inside the container the network is isolated
# by the platform. The application default is 127.0.0.1 (see SEC-016).

USER 10001
EXPOSE 8001

# SEC-007 / SCALE-004: liveness probe via TCP connect to the SSE port.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,socket; socket.create_connection(('127.0.0.1', int(os.environ.get('MCP_PORT','8001'))), timeout=3).close()" || exit 1

CMD ["swiss-road-mobility-mcp"]
