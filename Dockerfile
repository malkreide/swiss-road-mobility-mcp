FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir .

ENV MCP_TRANSPORT=sse
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8001

EXPOSE 8001
CMD ["swiss-road-mobility-mcp"]
