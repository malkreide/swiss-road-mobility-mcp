# Design Spec: Safety & Limits Section + Demo SVG

**Date:** 2026-04-14
**Repo:** swiss-road-mobility-mcp
**Status:** Approved by user

---

## 1. Context

The `swiss-road-mobility-mcp` repository provides 15 MCP tools across 6 Swiss road and mobility data sources. Two additions are needed to increase institutional acceptance and conversion on MCP directory pages:

1. A **Safety & Limits** section in both README files (replaces the existing thin `## Security & Privacy` section)
2. A **Demo SVG** showing a real Claude interaction with `road_mobility_snapshot`

Reference repo: `malkreide/zurich-opendata-mcp` (lines 253–261 and `docs/assets/demo.svg`)

---

## 2. Safety & Limits Section

### Existing section to replace

Both READMEs currently contain a thin `## Security & Privacy` / `## Sicherheit & Datenschutz` section (line 291) with 5 short bullets. This section is **replaced in full** by the new richer `## Safety & Limits` / `## Sicherheit & Grenzen` section. The old content is a strict subset of the new content.

### Placement

- `README.md`: replace the `## Security & Privacy` block (lines 291–298) with the new section
- `README.de.md`: replace the `## Sicherheit & Datenschutz` block (lines 291–298) with the new section

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
`docs/assets/demo.svg` (directory does not yet exist — create it)

### README integration — exact insertion point

In both `README.md` and `README.de.md`, insert a `## Demo` section between the `---` divider on **line 15** and the `## Overview` heading on **line 17**. The surrounding context to match:

```
---
                          ← insert here
## Overview
```

**English (README.md):**
```markdown
## Demo

![Demo: Claude using road_mobility_snapshot at Zürich HB](docs/assets/demo.svg)

---
```

**German (README.de.md):**
```markdown
## Demo

![Demo: Claude nutzt road_mobility_snapshot am Zürich HB](docs/assets/demo.svg)

---
```

### SVG Specification

**Dimensions:** 860 × 520 px
**Font:** `'SF Mono', 'Fira Code', 'Consolas', monospace`
**Font size:** 14px
**Line height:** 24px
**Theme:** GitHub Dark

#### Color palette

| Element | Color |
|---------|-------|
| Page background | `#0d1117` |
| Titlebar background | `#161b22` |
| Titlebar border | `#30363d` |
| Traffic light — red | `#ff5f57` |
| Traffic light — yellow | `#ffbd2e` |
| Traffic light — green | `#28c940` |
| User message background | `#161b22` |
| User/content text | `#e6edf3` |
| Tool name (cyan) | `#79c0ff` |
| Tool params (grey) | `#8b949e` |
| Tool call box background | `#1c2128` |
| Tool call box border | `#30363d` |
| Response header (green) | `#3fb950` |
| Dividers | `#30363d` |

#### Vertical layout (y-coordinates)

| Block | y-start | height | Notes |
|-------|---------|--------|-------|
| Titlebar | 0 | 40 | Full width, border-bottom 1px `#30363d` |
| User message block | 40 | 76 | Background `#161b22`, padding 16px, text at y=72 |
| Gap | 116 | 12 | |
| Tool call box | 128 | 88 | Background `#1c2128`, border 1px `#30363d`, rounded corners r=6 |
| Gap | 216 | 16 | |
| Response header line | 232 | 40 | Color `#3fb950` |
| Response line 1 | 288 | 40 | 🚲 Sharing |
| Response line 2 | 328 | 40 | ⚡ E-Laden |
| Response line 3 | 368 | 40 | 🅿️ Park+Rail |
| Response line 4 | 408 | 40 | 🚉 Bahnhof |
| Bottom padding | 448 | 72 | |

#### Content per block

**Titlebar** (y=20, vertically centered):
- Three circles at x=16,32,48, r=6: colors `#ff5f57`, `#ffbd2e`, `#28c940`
- Label at x=430, text-anchor=middle: `"Claude — swiss-road-mobility-mcp"` in `#8b949e`

**User message** (x=16, y=72):
- Icon: `👤` + text: `"Zeig mir alles Mobilitätsrelevante am Zürich Hauptbahnhof."` in `#e6edf3`

**Tool call box** (x=16, y=144 for tool name; y=168 for params):
- `"🔧 "` + `"road_mobility_snapshot"` in `#79c0ff`
- `"   latitude: 47.3782 · longitude: 8.5403 · radius_km: 0.5"` in `#8b949e`
- Left margin: x=32 inside box

**Response header** (x=16, y=256):
- `"✓  Mobilitäts-Lagebild · Zürich HB"` in `#3fb950`

**Response lines** (x=16, left-pad label to x=120 for value column):
- y=304: `"🚲 Sharing"` `"PubliBike (3 Velos) · Mobility (1 Auto) · Tier (2 E-Trottis)"`
- y=344: `"⚡ E-Laden"` `"2 Stationen · 4 Stecker frei"`
- y=384: `"🅿️ Park+Rail"` `"Zürich HB Sihlquai · 312 Plätze"`
- y=424: `"🚉 Bahnhof"` `"Zürich HB (0.05 km)"`

Labels in `#8b949e`, values in `#e6edf3`.

---

## 4. Files Changed

| File | Change |
|------|--------|
| `README.md` | (a) Insert `## Demo` section between line 15 `---` and line 17 `## Overview`; (b) Replace `## Security & Privacy` (lines 291–298) with `## Safety & Limits` |
| `README.de.md` | Same structure, German content |
| `docs/assets/demo.svg` | New file — dark terminal-style SVG, 860×520px |

---

## 5. Out of Scope

- No changes to source code (`src/`)
- No changes to tests, CI, or pyproject.toml
- No new tools or API integrations
