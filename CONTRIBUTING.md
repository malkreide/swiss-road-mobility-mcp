# Contributing to swiss-road-mobility-mcp

Thank you for your interest in contributing! This server is part of the [Swiss Public Data MCP Portfolio](https://github.com/malkreide).

---

## Reporting Issues

Use [GitHub Issues](https://github.com/malkreide/swiss-road-mobility-mcp/issues) to report bugs or request features.

Please include:
- Python version and OS
- Full error message or description of unexpected behaviour
- Steps to reproduce

---

## Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Make your changes and add tests
4. Ensure all tests pass: `pytest tests/ -v`
5. Commit using [Conventional Commits](https://www.conventionalcommits.org/): `feat: add new tool`
6. Push and open a Pull Request against `main`

---

## Code Style

- Python 3.11+
- [Ruff](https://github.com/astral-sh/ruff) for linting and formatting
- Type hints required for all public functions
- Tests required for new tools
- Follow the existing FastMCP / Pydantic v2 patterns in the source modules

---

## Data Sources

This server uses Swiss road and mobility APIs — most without authentication:

| Source | Documentation |
|--------|--------------|
| sharedmobility.ch | [sharedmobility.ch](https://sharedmobility.ch/) |
| ich-tanke-strom.ch | [ich-tanke-strom.ch](https://ich-tanke-strom.ch/) |
| opentransportdata.swiss | [opentransportdata.swiss](https://opentransportdata.swiss/) |
| SBB Open Data | [data.sbb.ch](https://data.sbb.ch/) |
| geo.admin.ch | [api3.geo.admin.ch](https://api3.geo.admin.ch/) |

When adding new data sources, follow the **No-Auth-First** principle: Phase 1 uses only open, authentication-free endpoints. Authenticated APIs are introduced in later phases with graceful degradation.

---

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
