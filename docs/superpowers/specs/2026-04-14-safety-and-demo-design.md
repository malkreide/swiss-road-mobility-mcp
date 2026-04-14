# Design Spec: Safety & Limits Section + Demo SVG

**Date:** 2026-04-14
**Repo:** swiss-road-mobility-mcp
**Status:** Approved by user

---

## 1. Context

The `swiss-road-mobility-mcp` repository provides 15 MCP tools across 6 Swiss road and mobility data sources. Two additions are needed to increase institutional acceptance and conversion on MCP directory pages:

1. A **Safety & Limits** section in both README files
2. A **Demo SVG** showing a real Claude interaction with `road_mobility_snapshot`

Reference repo: `malkreide/zurich-opendata-mcp` (lines 253–261 and `docs/assets/demo.svg`)

---

## 2. Safety & Limits Section

### Placement
- `README.md`: directly before the `## License` section
- `README.de.md`: same position, German translation

### Content (English)

```markdown
## Safety & Limits

- **Read-only:** All tools perform HTTP GET requests only — no data is written, modified, or deleted on any upstream system.
- **No personal data:** Location coordinates passed as tool inputs are not stored, logged, or forwarded beyond the immediate API request. API responses contain no PII — only vehicle counts, charger availability, traffic events, and geographic metadata.
- **Rate limiting:** The server enforces client-side rate limits (Shared Mobility: 30 req/60s; EV Charging: 10 req/60s) to protect upstream APIs. The DATEX II key is subject to opentransportdata.swiss fair-use terms.
- **Caching:** Responses are cached in-process (Sharing: 60s · EV: 5 min · Park+Rail: 5 min · Traffic: 1–2 min). Real-time data reflects the cache age, not necessarily the current second.
- **Terms of service:** Data is subject to the ToS of each upstream source — [sharedmobility.ch](https://sharedmobility.ch), [ich-tanke-strom.ch](https://ich-tanke-strom.ch), [opentransportdata.swiss](https://opentransportdata.swiss), [data.sbb.ch](https://data.sbb.ch) (CC BY), [geo.admin.ch](https://www.geo.admin.ch/de/geo-dienstleistungen/geodienste/terms-of-use.html) (BGDI).
- **No guarantees:** This server is an independent community project, not affiliated with SBB, ASTRA, sharedmobility.ch, or any API provider. Availability depends on upstream services.
```

### Content (German, for README.de.md)

```markdown
## Sicherheit & Grenzen

- **Nur lesend:** Alle Tools führen ausschliesslich HTTP-GET-Anfragen durch — es werden keine Daten geschrieben, verändert oder gelöscht.
- **Keine Personendaten:** Standortkoordinaten, die als Tool-Inputs übergeben werden, werden nicht gespeichert, protokolliert oder über die unmittelbare API-Anfrage hinaus weitergeleitet. API-Antworten enthalten keine personenbezogenen Daten — nur Fahrzeugzählungen, Ladestation-Verfügbarkeit, Verkehrsmeldungen und geografische Metadaten.
- **Rate Limiting:** Der Server erzwingt clientseitige Rate Limits (Shared Mobility: 30 Anfragen/60s; E-Laden: 10 Anfragen/60s) zum Schutz der vorgelagerten APIs. Der DATEX-II-Key unterliegt den Fair-Use-Bedingungen von opentransportdata.swiss.
- **Caching:** Antworten werden In-Process gecacht (Sharing: 60s · E-Laden: 5 Min. · Park & Rail: 5 Min. · Verkehr: 1–2 Min.). Echtzeit-Daten spiegeln das Cache-Alter wider, nicht zwingend die aktuelle Sekunde.
- **Nutzungsbedingungen:** Die Daten unterliegen den Nutzungsbedingungen der jeweiligen Quellen — [sharedmobility.ch](https://sharedmobility.ch), [ich-tanke-strom.ch](https://ich-tanke-strom.ch), [opentransportdata.swiss](https://opentransportdata.swiss), [data.sbb.ch](https://data.sbb.ch) (CC BY), [geo.admin.ch](https://www.geo.admin.ch/de/geo-dienstleistungen/geodienste/terms-of-use.html) (BGDI).
- **Keine Gewähr:** Dieser Server ist ein unabhängiges Community-Projekt, nicht verbunden mit SBB, ASTRA, sharedmobility.ch oder einem API-Anbieter. Die Verfügbarkeit hängt von den vorgelagerten Diensten ab.
```

---

## 3. Demo SVG

### File location
`docs/assets/demo.svg`

### README integration
Both `README.md` and `README.de.md`: insert a `## Demo` section directly after the introductory quote/tagline block and before the `## Overview` table.

```markdown
## Demo

![Demo: Claude using road_mobility_snapshot at Zürich HB](docs/assets/demo.svg)
```

### SVG Specification

**Dimensions:** 860 × 520 px
**Font:** monospace (system-ui fallback)
**Theme:** GitHub Dark

| Element | Color |
|---------|-------|
| Background | `#0d1117` |
| Titlebar | `#161b22` |
| User message bg | `#161b22` |
| User/content text | `#e6edf3` |
| Tool name | `#79c0ff` (cyan) |
| Tool params | `#8b949e` (grey) |
| Response header | `#3fb950` (green) |
| Dividers / borders | `#30363d` |

**Content blocks (top to bottom):**

1. **Titlebar** — macOS-style traffic lights (●●●) + label `"Claude — swiss-road-mobility-mcp"`
2. **User message** — `"Zeig mir alles Mobilitätsrelevante am Zürich Hauptbahnhof."`
3. **Tool call box** — tool name `road_mobility_snapshot` in cyan, params in grey:
   `latitude: 47.3782 · longitude: 8.5403 · radius_km: 0.5`
4. **Response header** — `"✓ Mobilitäts-Lagebild · Zürich HB"` in green
5. **Response content** — 4 lines with emoji icons:
   - `🚲 Sharing     PubliBike (3 Velos) · Mobility (1 Auto) · Tier (2 E-Trottis)`
   - `⚡ E-Laden     2 Stationen · 4 Stecker frei`
   - `🅿️ Park+Rail   Zürich HB Sihlquai · 312 Plätze`
   - `🚉 Bahnhof     Zürich HB (0.05 km)`

### Directory creation
`docs/assets/` directory must be created (currently does not exist).

---

## 4. Files Changed

| File | Change |
|------|--------|
| `README.md` | Add `## Demo` section after intro; add `## Safety & Limits` before License |
| `README.de.md` | Same structure, German content |
| `docs/assets/demo.svg` | New file — dark terminal-style SVG |

---

## 5. Out of Scope

- No changes to source code (`src/`)
- No changes to tests, CI, or pyproject.toml
- No new tools or API integrations
