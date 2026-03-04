# 🛣️ Swiss Road & Mobility MCP Server

**Shared Mobility · E-Ladestationen · Verkehrsmeldungen · Park & Rail · Multimodal**

> 🇨🇭 *Wenn der Swiss Transport MCP das GA für die Schiene ist, dann ist dieser Server die Vignette + Park-&-Rail-Karte + Sharing-Abo für die Strasse – und zusammen zeichnen sie das vollständige multimodale Bild der Schweizer Mobilität.*
>
> 🇬🇧 *If the Swiss Transport MCP is the GA pass for rail, this server is the vignette + Park-&-Rail card + sharing subscription for the road – together they paint the complete multimodal picture of Swiss mobility.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)
[![Version](https://img.shields.io/badge/version-0.3.1-orange.svg)](pyproject.toml)

---

🇩🇪 [Deutsch](#-swiss-road--mobility-mcp-server-de) · 🇬🇧 [English](#-swiss-road--mobility-mcp-server-en)

---

## 🇩🇪 Swiss Road & Mobility MCP Server {#de}

### 🧰 12 Tools

#### Shared Mobility & E-Laden (kein API-Key)

| Tool | Beschreibung | Cache |
|------|-------------|-------|
| `road_find_sharing` | Shared Mobility in der Nähe (Velos, E-Trottis, Autos) | 60s |
| `road_search_sharing` | Sharing-Stationen nach Name suchen | 5min |
| `road_sharing_providers` | Alle Sharing-Anbieter der Schweiz | 1h |
| `road_find_charger` | E-Ladestationen in der Nähe | 5min |
| `road_charger_status` | Echtzeit-Verfügbarkeit von Ladestationen | 1min |
| `road_check_status` | Server- & API-Gesundheitsprüfung | – |

#### Verkehr (🔑 kostenloser API-Key nötig)

| Tool | Beschreibung | Cache |
|------|-------------|-------|
| `road_traffic_situations` | Unfälle, Baustellen, Stau vom ASTRA/VMZ-CH | 2min |
| `road_traffic_counters` | Fahrzeuge/h + km/h an Zählstellen nahe Position | 1min |
| `road_counter_sites` | Messstellen in der Nähe auflisten | 24h |

#### Park & Rail + Multimodal (kein API-Key)

| Tool | Beschreibung | Cache |
|------|-------------|-------|
| `road_park_rail` | SBB Park+Rail Anlagen in der Nähe finden | 5min |
| `road_mobility_snapshot` | Vollständiges Mobilitäts-Lagebild für einen Standort | – |
| `road_multimodal_plan` | Auto → Park+Rail → ÖV → Ziel planen | – |

---

### 🗺️ Tools im Detail

#### `road_park_rail`
Findet SBB Park & Rail Anlagen in einem Umkreis oder nach Bahnhofsname.
Datenquelle: **SBB Open Data Portal** (data.sbb.ch) – komplett offen, kein Key.

Gibt zurück: Name, Koordinaten, Gesamtplätze, Tarifkategorie, Öffnungszeiten,
und wenn verfügbar: Echtzeit-Belegung und freie Plätze.

#### `road_mobility_snapshot`
Der «Kontrollturm-Blick» auf einen Standort. Aggregiert **parallel**:
- Sharing-Fahrzeuge in der Nähe
- EV-Ladestationen
- Park & Rail Anlagen
- Nächster Bahnhof (transport.opendata.ch)
- Verkehrsmeldungen (optional, nur wenn DATEX-II-Key vorhanden)

Perfekt für Demos: «Zeig mir alles Mobilitätsrelevante am Zürich HB.»

#### `road_multimodal_plan`
Der multimodale Reiseplaner. Kombiniert Parkplatz, Bahn und Sharing zu einem
einzigen Schritt-für-Schritt-Plan.

**Workflow (parallel):**
1. Nächsten Bahnhof zur Startposition finden
2. Park & Rail Anlagen in der Nähe prüfen
3. ÖV-Verbindungen vom Bahnhof zum Ziel abfragen
4. Sharing-Optionen am Start für die letzte Meile
5. Alles zu einem Plan zusammenführen

**Beispiel:** «Ich bin in Dietikon mit dem Auto. Ich muss nach Bern.
Wo kann ich parkieren? Welchen Zug soll ich nehmen?»

---

### 🚀 Quick Start

#### Claude Desktop (stdio)

`claude_desktop_config.json`:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "swiss-road-mobility": {
      "command": "uvx",
      "args": ["swiss-road-mobility-mcp"],
      "env": {
        "OPENTRANSPORTDATA_API_KEY": "<dein-token>"
      }
    }
  }
}
```

> Shared Mobility, E-Laden, Park & Rail und der multimodale Planer laufen
> auch **ohne** `OPENTRANSPORTDATA_API_KEY`. Der Key ist ausschliesslich
> für die DATEX-II-Verkehrstools nötig.

#### Lokale Installation

```bash
git clone https://github.com/your-org/swiss-road-mobility-mcp.git
cd swiss-road-mobility-mcp
pip install -e ".[dev]"

# Starten
swiss-road-mobility-mcp
# oder:
python -m swiss_road_mobility_mcp.server
```

#### Remote / SSE (Render.com, Railway)

```bash
MCP_TRANSPORT=sse MCP_PORT=8001 swiss-road-mobility-mcp
```

---

### 🔑 API-Key für Verkehrstools

1. Registrierung: <https://api-manager.opentransportdata.swiss>
2. Neue Applikation erstellen → API «Strassenverkehr» abonnieren
3. Token kopieren

```bash
export OPENTRANSPORTDATA_API_KEY=<dein-token>
```

Ohne Key geben die Verkehrstools einen sprechenden Fehler mit dem genauen
Registrierungs-Link zurück – kein Absturz.

---

### 🏗️ Architektur

```
swiss_road_mobility_mcp/
├── server.py             # FastMCP Server, 12 Tools
├── api_infrastructure.py # RateLimiter, Cache, HTTP-Client, Geo-Hilfen
├── shared_mobility.py    # sharedmobility.ch
├── ev_charging.py        # ich-tanke-strom.ch
├── traffic_situations.py # DATEX II Verkehrsmeldungen (SOAP/XML)
├── traffic_counters.py   # DATEX II Zählstellen (SOAP/XML)
├── park_rail.py          # SBB Open Data Park & Rail
└── multimodal.py         # Snapshot + Reiseplaner (Cross-Source)
```

#### Datenquellen

| Quelle | Was | Format | Key |
|--------|-----|--------|-----|
| sharedmobility.ch | Velos, E-Trottis, Autos | REST/JSON | ❌ |
| ich-tanke-strom.ch | E-Ladestationen | GeoJSON | ❌ |
| opentransportdata.swiss | Verkehr, Zähler | DATEX II / SOAP+XML | ✅ gratis |
| data.sbb.ch | Park & Rail | REST/JSON (Opendatasoft) | ❌ |
| transport.opendata.ch | ÖV-Verbindungen | REST/JSON | ❌ |

---

### 🧪 Tests

```bash
# Alle Tests
pytest tests/ -v

# Schnell-Check (ohne pytest)
python tests/test_phase3.py
```

---

### 🛡️ Sicherheit & Datenschutz

- Alle Daten sind öffentliche Open-Government-Data
- Keine persönlichen Daten werden verarbeitet
- Rate Limiting schützt die APIs vor Überlastung
- Lokale Caches minimieren externe Anfragen
- DATEX-II-Daten enthalten keine Personendaten

---

### 📄 Lizenz

MIT License – siehe [LICENSE](LICENSE)

---

### 🤝 Verwandte Projekte

- **Swiss Transport MCP**: ÖV-Server (Züge, Busse, Tramverbindungen)
- **Zurich Open Data MCP**: 900+ Datensätze der Stadt Zürich

---
---

## 🇬🇧 Swiss Road & Mobility MCP Server {#en}

### 🧰 12 Tools

#### Shared Mobility & EV Charging (no API key required)

| Tool | Description | Cache |
|------|-------------|-------|
| `road_find_sharing` | Shared mobility nearby (bikes, e-scooters, cars) | 60s |
| `road_search_sharing` | Search sharing stations by name | 5min |
| `road_sharing_providers` | All sharing providers in Switzerland | 1h |
| `road_find_charger` | EV charging stations nearby | 5min |
| `road_charger_status` | Real-time availability of charging stations | 1min |
| `road_check_status` | Server & API health check | – |

#### Traffic (🔑 free API key required)

| Tool | Description | Cache |
|------|-------------|-------|
| `road_traffic_situations` | Accidents, roadworks, congestion from ASTRA/VMZ-CH | 2min |
| `road_traffic_counters` | Vehicles/h + km/h at counting stations near a position | 1min |
| `road_counter_sites` | List counting stations nearby | 24h |

#### Park & Rail + Multimodal (no API key required)

| Tool | Description | Cache |
|------|-------------|-------|
| `road_park_rail` | Find SBB Park+Rail facilities nearby | 5min |
| `road_mobility_snapshot` | Complete mobility overview for a location | – |
| `road_multimodal_plan` | Plan car → Park+Rail → public transport → destination | – |

---

### 🗺️ Tools in Detail

#### `road_park_rail`
Finds SBB Park & Rail facilities within a radius or by station name.
Data source: **SBB Open Data Portal** (data.sbb.ch) – fully open, no key required.

Returns: name, coordinates, total spaces, tariff category, opening hours,
and where available: real-time occupancy and free spaces.

#### `road_mobility_snapshot`
The "control tower view" of a location. Aggregates **in parallel**:
- Nearby sharing vehicles
- EV charging stations
- Park & Rail facilities
- Nearest station (transport.opendata.ch)
- Traffic alerts (optional, only if DATEX II key is present)

Perfect for demos: "Show me everything mobility-related at Zürich HB."

#### `road_multimodal_plan`
The multimodal trip planner. Combines parking, rail, and sharing into a
single step-by-step plan.

**Workflow (parallel):**
1. Find the nearest station to the starting position
2. Check Park & Rail facilities nearby
3. Query public transport connections from the station to the destination
4. Find sharing options at the start for the last mile
5. Merge everything into a single plan

**Example:** "I'm in Dietikon with my car. I need to get to Bern.
Where can I park? Which train should I take?"

---

### 🚀 Quick Start

#### Claude Desktop (stdio)

`claude_desktop_config.json`:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "swiss-road-mobility": {
      "command": "uvx",
      "args": ["swiss-road-mobility-mcp"],
      "env": {
        "OPENTRANSPORTDATA_API_KEY": "<your-token>"
      }
    }
  }
}
```

> Shared mobility, EV charging, Park & Rail, and the multimodal planner work
> **without** an `OPENTRANSPORTDATA_API_KEY`. The key is only required
> for the DATEX II traffic tools.

#### Local Installation

```bash
git clone https://github.com/your-org/swiss-road-mobility-mcp.git
cd swiss-road-mobility-mcp
pip install -e ".[dev]"

# Start
swiss-road-mobility-mcp
# or:
python -m swiss_road_mobility_mcp.server
```

#### Remote / SSE (Render.com, Railway)

```bash
MCP_TRANSPORT=sse MCP_PORT=8001 swiss-road-mobility-mcp
```

---

### 🔑 API Key for Traffic Tools

1. Register: <https://api-manager.opentransportdata.swiss>
2. Create a new application → subscribe to the «Strassenverkehr» API
3. Copy the token

```bash
export OPENTRANSPORTDATA_API_KEY=<your-token>
```

Without a key, the traffic tools return a descriptive error message including
the exact registration link – no crash.

---

### 🏗️ Architecture

```
swiss_road_mobility_mcp/
├── server.py             # FastMCP server, 12 tools
├── api_infrastructure.py # Rate limiter, cache, HTTP client, geo utilities
├── shared_mobility.py    # sharedmobility.ch
├── ev_charging.py        # ich-tanke-strom.ch
├── traffic_situations.py # DATEX II traffic alerts (SOAP/XML)
├── traffic_counters.py   # DATEX II counting stations (SOAP/XML)
├── park_rail.py          # SBB Open Data Park & Rail
└── multimodal.py         # Snapshot + trip planner (cross-source)
```

#### Data Sources

| Source | What | Format | Key |
|--------|------|--------|-----|
| sharedmobility.ch | Bikes, e-scooters, cars | REST/JSON | ❌ |
| ich-tanke-strom.ch | EV charging stations | GeoJSON | ❌ |
| opentransportdata.swiss | Traffic, counters | DATEX II / SOAP+XML | ✅ free |
| data.sbb.ch | Park & Rail | REST/JSON (Opendatasoft) | ❌ |
| transport.opendata.ch | Public transport connections | REST/JSON | ❌ |

---

### 🧪 Tests

```bash
# All tests
pytest tests/ -v

# Quick check (without pytest)
python tests/test_phase3.py
```

---

### 🛡️ Security & Privacy

- All data is public Open Government Data
- No personal data is processed
- Rate limiting protects APIs from overload
- Local caches minimise external requests
- DATEX II data contains no personal data

---

### 📄 License

MIT License – see [LICENSE](LICENSE)

---

### 🤝 Related Projects

- **Swiss Transport MCP**: Public transport server (trains, buses, trams)
- **Zurich Open Data MCP**: 900+ datasets from the City of Zurich
