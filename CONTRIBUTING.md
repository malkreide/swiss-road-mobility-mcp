# Contributing

[🇩🇪 Deutsche Version](CONTRIBUTING.de.md)

Thank you for your interest in this project! Contributions are welcome. This
server is part of the [Swiss Public Data MCP Portfolio](https://github.com/malkreide/swiss-public-data-mcp).

## How can I contribute?

**Report bugs:** Create an [Issue](../../issues) with a clear description,
reproduction steps, and expected vs. actual output. Please include your Python
version and OS.

**Suggest features:** Describe the use case, ideally with a reference to Swiss
road and mobility context (shared mobility, EV charging, traffic, Park & Rail,
multimodal trips, etc.).

**Contribute code:**

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Write tests for your changes
5. Run linter: `ruff check src/ tests/`
6. Ensure all tests pass: `pytest tests/ -v`
7. Commit with a clear message (see [Conventional Commits](https://www.conventionalcommits.org/)): `git commit -m "feat: add new tool"`
8. Create a Pull Request against `main`

## Code Standards

- Python 3.11+, Ruff for linting and formatting
- Type hints required for all public functions
- Docstrings in English (for international compatibility)
- Comments and error messages may be in German or English
- All MCP tools must set `readOnlyHint: True` (read-only access)
- Pydantic v2 models for all tool inputs
- Follow the existing FastMCP patterns in the source modules

## Data Sources

This server uses Swiss road and mobility APIs — most without authentication:

| Source | Documentation |
|--------|--------------|
| sharedmobility.ch | [sharedmobility.ch](https://sharedmobility.ch/) |
| ich-tanke-strom.ch | [ich-tanke-strom.ch](https://ich-tanke-strom.ch/) |
| opentransportdata.swiss | [opentransportdata.swiss](https://opentransportdata.swiss/) |
| SBB Open Data | [data.sbb.ch](https://data.sbb.ch/) |
| geo.admin.ch | [api3.geo.admin.ch](https://api3.geo.admin.ch/) |

When adding new data sources, follow the **No-Auth-First** principle: open,
authentication-free endpoints first; authenticated APIs are introduced with
graceful degradation.

## API Keys

Integration tests for the traffic tools require a free API key from
[api-manager.opentransportdata.swiss](https://api-manager.opentransportdata.swiss/).
**Never** commit API keys.

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
