## Finding: OPS-001 — Test-Strategie (Unit mocked + Live markiert)

**Severity:** high
**Status:** open
**Server:** swiss-road-mobility-mcp
**Check-Reference:** OPS-001
**PDF-Reference:** Anhang C1

### Observed Behavior
- 27 Tests in `tests/test_integration.py` + `tests/test_phase3.py`, jedoch **Live-Tests gegen echte APIs** ohne Mocking (siehe `tests/test_phase3.py:9-10`: „Echte Netzwerk-Abfragen werden durchgeführt (Live-Tests gegen offene APIs)").
- Kein `@pytest.mark.live`-Marker, kein Marker in `pyproject.toml` registriert.
- **CI (`.github/workflows/ci.yml`) führt `pytest` gar nicht aus** — nur `ruff check`, `py_compile` und einen Import-Test.

### Expected Behavior
Trennung in `respx`-gemockte Unit-Tests (laufen in CI bei jedem PR) und mit `@pytest.mark.live` markierte Live-Tests (nightly / manuell). CI führt `pytest -m "not live"` aus.

### Evidence
- File: `tests/test_phase3.py:9-10` — Live-Test-Hinweis
- File: `.github/workflows/ci.yml` — kein `pytest`-Step
- `pyproject.toml` — keine `[tool.pytest.ini_options] markers`-Registrierung

### Risk Description
Keine Regressions-Detection im CI: Refactorings können Tools brechen, ohne dass CI es bemerkt. Live-only-Tests brechen bei API-Outages der Datenquellen und sind in CI unbrauchbar — was vermutlich der Grund ist, weshalb `pytest` aus CI entfernt wurde. Schema-Drift der Upstream-APIs bleibt unentdeckt.

### Remediation
1. `respx` als Dev-Dependency; pro Tool ≥3 Unit-Tests (Happy-Path, 4xx/5xx, Edge-Case) mit gemockten HTTP-Antworten.
2. Live-Tests mit `@pytest.mark.live` markieren, Marker in `pyproject.toml` registrieren.
3. CI: `pytest -m "not live" --cov=src` als Step ergänzen.
4. Separater nightly-Workflow `pytest -m live`.

### Effort Estimate
M (1-3d)
