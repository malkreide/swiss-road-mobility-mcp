"""Swiss Road & Mobility MCP Server.

Shared mobility, EV charging, traffic alerts, Park & Rail, multimodal trip
planning and geo.admin.ch geocoding for Swiss road infrastructure.
"""

__version__ = "0.5.0"

# Single source of truth for the outbound User-Agent (used by every HTTP client).
USER_AGENT = f"swiss-road-mobility-mcp/{__version__}"
