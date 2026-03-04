# 🛣️ Swiss Road & Mobility MCP Server

**Shared Mobility + E-Ladestationen + DATEX II Verkehr + Park & Rail + Multimodal**

> 🇨🇭 *Wenn der Swiss Transport MCP das GA für die Schiene ist, dann ist dieser Server die Vignette + Park-&-Rail-Karte + Sharing-Abo für die Strasse – und zusammen zeichnen sie das vollständige multimodale Bild der Schweizer Mobilität.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)
[![Version](https://img.shields.io/badge/version-0.3.0-orange.svg)](pyproject.toml)

---

## 🎉 Phase 3 vollständig – 12 Tools, vollständig multimodal

Drei Phasen, ein Server:

| Phase | Tools | API-Key | Was es bringt |
|-------|-------|---------|---------------|
| **Phase 1** | 6 | ❌ Keiner | Shared Mobility + E-Ladestationen |
| **Phase 2** | 3 | ✅ Kostenlos | DATEX II Verkehr + Zählstellen |
| **Phase 3** | 3 | ❌ Keiner | Park & Rail + Snapshot + Multimodal |

**Metapher in drei Sätzen:**
- Phase 1 zeigt, welches Velo an der Ecke steht.
- Phase 2 erklärt, warum die Ecke gerade gesperrt ist.
- Phase 3 zeigt, wo du dein Auto parkierst, in den Zug steigst und ans Ziel kommst.

---

## 🧰 12 Tools

### Phase 1 – Sharing & Laden (kein API-Key)

| Tool | Beschreibung | Cache |
|------|-------------|-------|
| `road_find_sharing` | Shared Mobility in der Nähe (Velos, E-Trottis, Autos) | 60s |
| `road_search_sharing` | Sharing-Stationen nach Name suchen | 5min |
| `road_sharing_providers` | Alle Sharing-Anbieter der Schweiz | 1h |
| `road_find_charger` | E-Ladestationen in der Nähe | 5min |
| `road_charger_status` | Echtzeit-Verfügbarkeit von Ladestationen | 1min |
| `road_check_status` | Server- & API-Gesundheitsprüfung | – |

### Phase 2 – DATEX II Verkehr (🔑 kostenloser API-Key nötig)

| Tool | Beschreibung | Cache |
|------|-------------|-------|
| `road_traffic_situations` | Unfälle, Baustellen, Stau vom ASTRA/VMZ-CH | 2min |
| `road_traffic_counters` | Fahrzeuge/h + km/h an Zählstellen nahe Position | 1min |
| `road_counter_sites` | Messstellen in der Nähe auflisten | 24h |

### Phase 3 – Park & Rail + Multimodal (kein API-Key!)

| Tool | Beschreibung | Cache |
|------|-------------|-------|
| `road_park_rail` | SBB Park+Rail Anlagen in der Nähe finden | 5min |
| `road_mobility_snapshot` | Vollständiges Mobilitäts-Lagebild für einen Standort | – |
| `road_multimodal_plan` | Auto → Park+Rail → ÖV → Ziel planen | – |

---

## 🗺️ Phase 3 im Detail

### `road_park_rail`
Findet SBB Park & Rail Anlagen in einem Umkreis oder nach Bahnhofsname.
Datenquelle: **SBB Open Data Portal** (data.sbb.ch) – komplett offen, kein Key.

Gibt zurück: Name, Koordinaten, Gesamtplätze, Taritkategorie, Öffnungszeiten,
und wenn verfügbar: Echtzeit-Belegung und freie Plätze.

### `road_mobility_snapshot`
Der «Kontrollturm-Blick» auf einen Standort. Aggregiert **parallel**:
- Sharing-Fahrzeuge in der Nähe
- EV-Ladestationen
- Park & Rail Anlagen
- Nächster Bahnhof (transport.opendata.ch)
- Verkehrsmeldungen (optional, nur wenn Phase-2-Key vorhanden)

Perfekt für Demos: «Zeig mir alles Mobilitätsrelevante am Zürich HB.»

### `road_multimodal_plan`
Der multimodale Reiseplaner – das Herzstück von Phase 3.

**Workflow (parallel):**
1. Nächsten Bahnhof zur Startposition finden
2. Park & Rail Anlagen in der Nähe prüfen
3. ÖV-Verbindungen vom Bahnhof zum Ziel abfragen
4. Sharing-Optionen am Start für letzte Meile
5. Alles zu einem Schritt-für-Schritt-Plan zusammenführen

**Beispiel-Frage:** «Ich bin in Dietikon mit dem Auto. Ich muss nach Bern.
Wo kann ich parkieren? Welchen Zug soll ich nehmen?»

---

## 🚀 Quick Start

### Claude Desktop (stdio)

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

> Phase 1 und Phase 3 laufen auch **ohne** `OPENTRANSPORTDATA_API_KEY`.
> Der Key ist nur für Phase-2-Tools nötig.

### Lokale Installation

```bash
git clone https://github.com/your-org/swiss-road-mobility-mcp.git
cd swiss-road-mobility-mcp
pip install -e ".[dev]"

# Starten
swiss-road-mobility-mcp
# oder:
python -m swiss_road_mobility_mcp.server
```

### Remote / SSE (Render.com, Railway)

```bash
MCP_TRANSPORT=sse MCP_PORT=8001 swiss-road-mobility-mcp
```

---

## 🔑 API-Key für Phase 2

1. Registrierung: <https://api-manager.opentransportdata.swiss>
2. Neue Applikation erstellen → API «Strassenverkehr» abonnieren
3. Token kopieren

```bash
export OPENTRANSPORTDATA_API_KEY=<dein-token>
```

Ohne Key: Phase-2-Tools geben einen sprechenden Fehler mit dem genauen
Registrierungs-Link zurück – kein Absturz.

---

## 🏗️ Architektur

```
swiss_road_mobility_mcp/
├── server.py             # FastMCP Server, 12 Tools
├── api_infrastructure.py # RateLimiter, Cache, HTTP-Client, Geo-Hilfen
├── shared_mobility.py    # Phase 1: sharedmobility.ch
├── ev_charging.py        # Phase 1: ich-tanke-strom.ch
├── traffic_situations.py # Phase 2: DATEX II Verkehrsmeldungen (SOAP/XML)
├── traffic_counters.py   # Phase 2: DATEX II Zählstellen (SOAP/XML)
├── park_rail.py          # Phase 3: SBB Open Data Park & Rail
└── multimodal.py         # Phase 3: Snapshot + Reiseplaner (Cross-Source)
```

### Datenquellen

| Quelle | Was | Format | Key |
|--------|-----|--------|-----|
| sharedmobility.ch | Velos, E-Trottis, Autos | REST/JSON | ❌ |
| ich-tanke-strom.ch | E-Ladestationen | GeoJSON | ❌ |
| opentransportdata.swiss | Verkehr, Zähler | DATEX II / SOAP+XML | ✅ gratis |
| data.sbb.ch | Park & Rail | REST/JSON (Opendatasoft) | ❌ |
| transport.opendata.ch | ÖV-Verbindungen | REST/JSON | ❌ |

---

## 🧪 Tests

```bash
# Alle Tests
pytest tests/ -v

# Nur Phase 3
pytest tests/test_phase3.py -v

# Schnell-Check (ohne pytest)
python tests/test_phase3.py
```

---

## 🛡️ Sicherheit & Datenschutz

- Alle Daten sind öffentliche Open-Government-Data
- Keine persönlichen Daten werden verarbeitet
- Rate Limiting schützt die APIs vor Überlastung
- Lokale Caches minimieren externe Anfragen
- DATEX II-Daten enthalten keine Personendaten

---

## 📄 Lizenz

MIT License – siehe [LICENSE](LICENSE)

---

## 🤝 Verwandte Projekte

- **Swiss Transport MCP**: ÖV-Server (Züge, Busse, Tramverbindungen)
- **Zurich Open Data MCP**: 900+ Datensätze der Stadt Zürich
