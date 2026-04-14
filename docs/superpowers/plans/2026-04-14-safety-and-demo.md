# Safety & Limits + Demo SVG Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Safety & Limits section to both README files and create a dark-theme SVG demo asset showing a `road_mobility_snapshot` Claude interaction.

**Architecture:** Pure documentation changes — no source code modifications. Three files touched: `docs/assets/demo.svg` (new), `README.md` (two insertions), `README.de.md` (two insertions). Safety section replaces the existing thin `## Security & Privacy` / `## Sicherheit & Datenschutz` blocks.

**Tech Stack:** SVG (hand-authored XML), Markdown, Git

**Spec:** `docs/superpowers/specs/2026-04-14-safety-and-demo-design.md`

---

## Chunk 1: Demo SVG

### Task 1: Create docs/assets/demo.svg

**Files:**
- Create: `docs/assets/demo.svg`

- [ ] **Step 1: Create the SVG file**

Write the following content to `docs/assets/demo.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="860" height="520" viewBox="0 0 860 520" role="img" aria-label="Demo: Claude using road_mobility_snapshot at Zürich HB">
  <title>Demo: Claude using road_mobility_snapshot at Zürich HB</title>

  <!-- Background -->
  <rect width="860" height="520" rx="8" fill="#0d1117"/>

  <!-- Titlebar background (rx covers top corners; second rect squares off bottom) -->
  <rect width="860" height="40" rx="8" fill="#161b22"/>
  <rect y="20" width="860" height="20" fill="#161b22"/>
  <line x1="0" y1="40" x2="860" y2="40" stroke="#30363d" stroke-width="1"/>

  <!-- Traffic lights: cx=16,32,48 per spec -->
  <circle cx="16" cy="20" r="6" fill="#ff5f57"/>
  <circle cx="32" cy="20" r="6" fill="#ffbd2e"/>
  <circle cx="48" cy="20" r="6" fill="#28c940"/>

  <!-- Titlebar label -->
  <text x="430" y="20" dominant-baseline="middle" text-anchor="middle"
        fill="#8b949e" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="13">
    Claude — swiss-road-mobility-mcp
  </text>

  <!-- User message background -->
  <rect y="40" width="860" height="76" fill="#161b22"/>
  <line x1="0" y1="116" x2="860" y2="116" stroke="#30363d" stroke-width="1"/>

  <!-- User message text: y=72 per spec -->
  <text x="16" y="72" dominant-baseline="middle"
        fill="#e6edf3" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="14">
    &#x1F464;&#x2003;Zeig mir alles Mobilitätsrelevante am Zürich Hauptbahnhof.
  </text>

  <!-- Tool call box -->
  <rect x="16" y="128" width="828" height="88" rx="6"
        fill="#1c2128" stroke="#30363d" stroke-width="1"/>

  <!-- Tool call icon: x=32 y=144 per spec -->
  <text x="32" y="144" dominant-baseline="middle"
        fill="#8b949e" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="14">
    &#x1F527;
  </text>
  <!-- Tool name: x=52 y=144 per spec -->
  <text x="52" y="144" dominant-baseline="middle"
        fill="#79c0ff" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="14">
    road_mobility_snapshot
  </text>

  <!-- Tool params: y=168 per spec -->
  <text x="52" y="168" dominant-baseline="middle"
        fill="#8b949e" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="13">
    latitude: 47.3782  ·  longitude: 8.5403  ·  radius_km: 0.5
  </text>

  <!-- Response header: y=256 per spec -->
  <text x="16" y="256" dominant-baseline="middle"
        fill="#3fb950" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="14">
    ✓&#x2003;Mobilitäts-Lagebild · Zürich HB
  </text>
  <line x1="16" y1="268" x2="844" y2="268" stroke="#30363d" stroke-width="1"/>

  <!-- Response line 1: Sharing — label x=16, value x=120, y=304 per spec -->
  <text x="16" y="304" dominant-baseline="middle"
        fill="#8b949e" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="14">
    &#x1F6B2; Sharing
  </text>
  <text x="120" y="304" dominant-baseline="middle"
        fill="#e6edf3" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="14">
    PubliBike (3 Velos)  ·  Mobility (1 Auto)  ·  Tier (2 E-Trottis)
  </text>

  <!-- Response line 2: EV — y=344 per spec -->
  <text x="16" y="344" dominant-baseline="middle"
        fill="#8b949e" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="14">
    &#x26A1; E-Laden
  </text>
  <text x="120" y="344" dominant-baseline="middle"
        fill="#e6edf3" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="14">
    2 Stationen  ·  4 Stecker frei
  </text>

  <!-- Response line 3: Park+Rail — y=384 per spec -->
  <text x="16" y="384" dominant-baseline="middle"
        fill="#8b949e" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="14">
    &#x1F17F; Park+Rail
  </text>
  <text x="120" y="384" dominant-baseline="middle"
        fill="#e6edf3" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="14">
    Zürich HB Sihlquai  ·  312 Plätze
  </text>

  <!-- Response line 4: Bahnhof — y=424, format "(0.05 km)" per spec -->
  <text x="16" y="424" dominant-baseline="middle"
        fill="#8b949e" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="14">
    &#x1F689; Bahnhof
  </text>
  <text x="120" y="424" dominant-baseline="middle"
        fill="#e6edf3" font-family="'SF Mono','Fira Code','Consolas',monospace" font-size="14">
    Zürich HB (0.05 km)
  </text>
</svg>
```

> **Note on emojis:** Emojis are encoded as XML numeric character references (`&#x1F464;` = 👤, `&#x1F527;` = 🔧, `&#x1F6B2;` = 🚲, `&#x26A1;` = ⚡, `&#x1F17F;` = 🅿, `&#x1F689;` = 🚉) for maximum compatibility across SVG renderers. `&#x2003;` is an em-space.

- [ ] **Step 2: Verify the SVG**

```bash
python -c "
import xml.etree.ElementTree as ET
tree = ET.parse('docs/assets/demo.svg')
svg = ET.tostring(tree.getroot(), encoding='unicode')
assert '860' in svg and '520' in svg, 'Wrong dimensions'
assert '#ff5f57' in svg, 'Missing red traffic light'
assert '#79c0ff' in svg, 'Missing tool name color'
assert 'road_mobility_snapshot' in svg, 'Missing tool name'
assert 'Zürich HB (0.05 km)' in svg, 'Missing Bahnhof line'
assert 'Mobilitäts-Lagebild' in svg, 'Missing response header'
print('SVG OK — dimensions, colors, and content verified')
"
```

Expected output: `SVG OK — dimensions, colors, and content verified`

- [ ] **Step 3: Commit**

```bash
git add docs/assets/demo.svg
git commit -m "feat: add dark-theme demo SVG for road_mobility_snapshot"
```

---

## Chunk 2: README Updates

### Task 2: Insert Demo section in README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Insert Demo block**

Using the Edit tool, match the following `old_string` and replace with `new_string`:

**old_string:**
```
[Deutsche Version](README.de.md)

---

## Overview
```

**new_string:**
```
[Deutsche Version](README.de.md)

---

## Demo

![Demo: Claude using road_mobility_snapshot at Zürich HB](docs/assets/demo.svg)

---

## Overview
```

- [ ] **Step 2: Verify insertion**

```bash
grep -n "## Demo" README.md
```

Expected: one match at roughly line 15.

### Task 3: Replace Security & Privacy in README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace the section**

**old_string:**
```
## Security & Privacy

- All data is public Open Government Data
- No personal data is processed
- Rate limiting protects APIs from overload
- Local caches minimise external requests
- DATEX II data contains no personal data
```

**new_string:**
```
## Safety & Limits

- **Read-only:** All tools perform HTTP GET requests only — no data is written, modified, or deleted on any upstream system.
- **No personal data:** Location coordinates passed as tool inputs are not stored, logged, or forwarded beyond the immediate API request. API responses contain no PII — only vehicle counts, charger availability, traffic events, and geographic metadata.
- **Rate limiting:** The server enforces client-side rate limits (Shared Mobility: 30 req/60s; EV Charging: 10 req/60s) to protect upstream APIs. The DATEX II key is subject to opentransportdata.swiss fair-use terms.
- **Caching:** Responses are cached in-process (Sharing: 60s · EV: 5 min · Park+Rail: 5 min · Traffic: 1–2 min). Real-time data reflects the cache age, not necessarily the current second.
- **Terms of service:** Data is subject to the ToS of each upstream source — [sharedmobility.ch](https://sharedmobility.ch), [ich-tanke-strom.ch](https://ich-tanke-strom.ch), [opentransportdata.swiss](https://opentransportdata.swiss), [data.sbb.ch](https://data.sbb.ch) (CC BY), [geo.admin.ch](https://www.geo.admin.ch/de/geo-dienstleistungen/geodienste/terms-of-use.html) (BGDI).
- **No guarantees:** This server is an independent community project, not affiliated with SBB, ASTRA, sharedmobility.ch, or any API provider. Availability depends on upstream services.
```

- [ ] **Step 2: Verify replacement**

```bash
grep -n "## Safety\|## Security" README.md
```

Expected: one match `## Safety & Limits`, zero matches for `## Security & Privacy`.

- [ ] **Step 3: Commit README.md changes**

```bash
git add README.md
git commit -m "docs(readme): add Demo section and expand Safety & Limits"
```

---

### Task 4: Update README.de.md

**Files:**
- Modify: `README.de.md`

- [ ] **Step 1: Insert Demo block**

**old_string:**
```
> MCP-Server für Schweizer Strassenmobilität — Sharing-Fahrzeuge, E-Ladestationen, Verkehrsmeldungen, Park & Rail und multimodale Reiseplanung

---

## Übersicht
```

**new_string:**
```
> MCP-Server für Schweizer Strassenmobilität — Sharing-Fahrzeuge, E-Ladestationen, Verkehrsmeldungen, Park & Rail und multimodale Reiseplanung

---

## Demo

![Demo: Claude nutzt road_mobility_snapshot am Zürich HB](docs/assets/demo.svg)

---

## Übersicht
```

- [ ] **Step 2: Replace Sicherheit & Datenschutz section**

**old_string:**
```
## Sicherheit & Datenschutz

- Alle Daten sind öffentliche Open-Government-Data
- Keine persönlichen Daten werden verarbeitet
- Rate Limiting schützt die APIs vor Überlastung
- Lokale Caches minimieren externe Anfragen
- DATEX-II-Daten enthalten keine Personendaten
```

**new_string:**
```
## Sicherheit & Grenzen

- **Nur lesend:** Alle Tools führen ausschliesslich HTTP-GET-Anfragen durch — es werden keine Daten geschrieben, verändert oder gelöscht.
- **Keine Personendaten:** Standortkoordinaten, die als Tool-Inputs übergeben werden, werden nicht gespeichert, protokolliert oder über die unmittelbare API-Anfrage hinaus weitergeleitet. API-Antworten enthalten keine personenbezogenen Daten — nur Fahrzeugzählungen, Ladestation-Verfügbarkeit, Verkehrsmeldungen und geografische Metadaten.
- **Rate Limiting:** Der Server erzwingt clientseitige Rate Limits (Shared Mobility: 30 Anfragen/60s; E-Laden: 10 Anfragen/60s) zum Schutz der vorgelagerten APIs. Der DATEX-II-Key unterliegt den Fair-Use-Bedingungen von opentransportdata.swiss.
- **Caching:** Antworten werden In-Process gecacht (Sharing: 60s · E-Laden: 5 Min. · Park & Rail: 5 Min. · Verkehr: 1–2 Min.). Echtzeit-Daten spiegeln das Cache-Alter wider, nicht zwingend die aktuelle Sekunde.
- **Nutzungsbedingungen:** Die Daten unterliegen den Nutzungsbedingungen der jeweiligen Quellen — [sharedmobility.ch](https://sharedmobility.ch), [ich-tanke-strom.ch](https://ich-tanke-strom.ch), [opentransportdata.swiss](https://opentransportdata.swiss), [data.sbb.ch](https://data.sbb.ch) (CC BY), [geo.admin.ch](https://www.geo.admin.ch/de/geo-dienstleistungen/geodienste/terms-of-use.html) (BGDI).
- **Keine Gewähr:** Dieser Server ist ein unabhängiges Community-Projekt, nicht verbunden mit SBB, ASTRA, sharedmobility.ch oder einem API-Anbieter. Die Verfügbarkeit hängt von den vorgelagerten Diensten ab.
```

- [ ] **Step 3: Verify both changes**

```bash
grep -n "## Demo\|## Sicherheit" README.de.md
```

Expected: `## Demo` at ~line 15, `## Sicherheit & Grenzen` later (no `## Sicherheit & Datenschutz`).

- [ ] **Step 4: Commit README.de.md changes**

```bash
git add README.de.md
git commit -m "docs(readme-de): add Demo section and expand Sicherheit & Grenzen"
```

---

### Task 5: Push to main

- [ ] **Step 1: Push all commits**

```bash
git push origin main
```

Expected: three new commits pushed (SVG, README.md, README.de.md).

- [ ] **Step 2: Verify on GitHub**

Open `https://github.com/malkreide/swiss-road-mobility-mcp` in a browser and confirm:
- The SVG renders below the intro quote in the README
- The `## Safety & Limits` section appears before the License block
