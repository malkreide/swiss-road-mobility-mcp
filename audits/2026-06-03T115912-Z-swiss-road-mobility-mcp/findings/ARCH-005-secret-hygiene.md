## Finding: ARCH-005 — Keine Hardcoded Secrets (Secret-Hygiene)

**Severity:** critical
**Status:** open
**Server:** swiss-road-mobility-mcp
**Check-Reference:** ARCH-005
**PDF-Reference:** Sec 2.1

### Observed Behavior
Der kritische Kern ist erfüllt: **keine hardcoded Secrets im Code** (grep negativ), der einzige Key wird via `os.environ.get("OPENTRANSPORTDATA_API_KEY")` ohne Default-Realkey geladen (`server.py:97-99`). Es fehlen jedoch die Hygiene-Bausteine:
- **Keine `.gitignore`** im Repo → `.env`-Dateien wären nicht ignoriert.
- Keine `.env.example`.
- Kein CI-Secret-Scan (gitleaks/trufflehog).

### Expected Behavior
`.gitignore` mit `.env`/`.env.*` (ausser `.env.example`), eine `.env.example` mit Platzhaltern, ein Secret-Scan-Step im CI.

### Evidence
- Repo-Root: keine `.gitignore` vorhanden
- `.github/workflows/ci.yml` — kein gitleaks/trufflehog-Step
- `src/swiss_road_mobility_mcp/server.py:97-99` — sauberes Env-Loading (positiv)

### Risk Description
Da die Daten Public Open Data sind und der einzige Key ein gratis öffentlicher API-Key ist, ist das akute Leak-Risiko gering. Ohne `.gitignore` besteht aber die strukturelle Gefahr, dass künftig versehentlich eine `.env` committet wird.

### Remediation
1. `.gitignore` anlegen (mind. `.env`, `.env.*`, `__pycache__/`, `*.egg-info/`, `.venv/`).
2. `.env.example` mit `OPENTRANSPORTDATA_API_KEY=replace-with-key`.
3. CI-Step `gitleaks/gitleaks-action@v2` ergänzen.

### Effort Estimate
S (< 1d)
