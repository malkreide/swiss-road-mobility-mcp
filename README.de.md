[English Version](README.md)

> **Teil des [Swiss Public Data MCP Portfolios](https://github.com/malkreide)**

# Swiss Road & Mobility MCP Server

![Version](https://img.shields.io/badge/version-0.4.0-blue)
[![Lizenz: MIT](https://img.shields.io/badge/Lizenz-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-purple)](https://modelcontextprotocol.io/)
![CI](https://github.com/malkreide/swiss-road-mobility-mcp/actions/workflows/ci.yml/badge.svg)

> MCP-Server für Schweizer Strassenmobilität — Sharing-Fahrzeuge, E-Ladestationen, Verkehrsmeldungen, Park & Rail und multimodale Reiseplanung

---

## Übersicht

`swiss-road-mobility-mcp` ermöglicht KI-Assistenten den direkten Zugang zu Schweizer Strassen- und Mobilitätsdaten:

| Quelle | Daten | API | Auth |
|--------|-------|-----|------|
| **sharedmobility.ch** | Velos, E-Trottis, Autos (GBFS) | REST/JSON | Keine |
| **ich-tanke-strom.ch** | E-Ladestationen | GeoJSON | Keine |
| **opentransportdata.swiss** | Verkehrsmeldungen, Zählstellen | DATEX II / SOAP+XML | Gratis-Key |
| **data.sbb.ch** | Park & Rail Anlagen | REST/JSON (Opendatasoft) | Keine |
| **transport.opendata.ch** | ÖV-Verbindungen | REST/JSON | Keine |
| **geo.admin.ch** | Adress-Geokodierung, Strassenklassifikation | REST/JSON | Keine |

Wenn der Swiss Transport MCP das GA für die Schiene ist, dann ist dieser Server die Vignette + Park-&-Rail-Karte + Sharing-Abo für die Strasse — zusammen zeichnen sie das vollständige multimodale Bild der Schweizer Mobilität.

**Anker-Demo-Abfrage:** *«Ich bin in Dietikon mit dem Auto. Ich muss nach Bern. Wo kann ich parkieren? Welchen Zug soll ich nehmen?»*

---

## Funktionen

- **15 Tools** über sechs Datenquellen (Phase 1–4)
- **`road_mobility_snapshot`** — aggregiertes Mobilitäts-Lagebild für jeden Standort
- **`road_multimodal_plan`** — Auto + Park & Rail + ÖV in einem Plan
- Kein API-Key erforderlich für 12 von 15 Tools
- Dualer Transport — stdio (Claude Desktop) + SSE (Cloud)
- Rate Limiting + Caching für alle Endpunkte

---

## Voraussetzungen

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (empfohlen) oder pip

---

## Installation

```bash
# Repository klonen
git clone https://github.com/malkreide/swiss-road-mobility-mcp.git
cd swiss-road-mobility-mcp

# Installieren
pip install -e .
# oder mit uv:
uv pip install -e .
```

Oder mit `uvx` (ohne dauerhafte Installation):

```bash
uvx swiss-road-mobility-mcp
```

---

## Schnellstart

```bash
# stdio (für Claude Desktop)
swiss-road-mobility-mcp
# oder:
python -m swiss_road_mobility_mcp.server

# SSE (für Cloud / Render.com)
MCP_TRANSPORT=sse MCP_PORT=8001 swiss-road-mobility-mcp
```

Sofort in Claude Desktop ausprobieren:

> *«Zeig mir alles Mobilitätsrelevante am Zürich HB.»*
> *«Finde Sharing-Velos in der Nähe vom Bern Bahnhof.»*
> *«Wo kann ich mein E-Auto in der Nähe von Luzern laden?»*

---

## Konfiguration

### Claude Desktop

Editiere `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) bzw. `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

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

Oder mit `python`:

```json
{
  "mcpServers": {
    "swiss-road-mobility": {
      "command": "python",
      "args": ["-m", "swiss_road_mobility_mcp.server"],
      "env": {
        "OPENTRANSPORTDATA_API_KEY": "<dein-token>"
      }
    }
  }
}
```

> Shared Mobility, E-Laden, Park & Rail und der multimodale Planer laufen **ohne** `OPENTRANSPORTDATA_API_KEY`. Der Key ist ausschliesslich für die DATEX-II-Verkehrstools nötig.

**Pfad zur Konfigurationsdatei:**
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### Cloud-Deployment (SSE für Browser-Zugriff)

Für den Einsatz via **claude.ai im Browser** (z.B. auf verwalteten Arbeitsplätzen ohne lokale Software):

**Render.com (empfohlen):**
1. Repository auf GitHub pushen/forken
2. Auf [render.com](https://render.com): New Web Service -> GitHub-Repo verbinden
3. Start-Befehl setzen: `MCP_TRANSPORT=sse MCP_PORT=8001 swiss-road-mobility-mcp`
4. In claude.ai unter Settings -> MCP Servers eintragen: `https://your-app.onrender.com/sse`

---

## Verfügbare Tools

### Shared Mobility & E-Laden (kein API-Key)

| Tool | Beschreibung | Cache |
|------|-------------|-------|
| `road_find_sharing` | Shared Mobility in der Nähe (Velos, E-Trottis, Autos) | 60s |
| `road_search_sharing` | Sharing-Stationen nach Name suchen | 5min |
| `road_sharing_providers` | Alle Sharing-Anbieter der Schweiz | 1h |
| `road_find_charger` | E-Ladestationen in der Nähe | 5min |
| `road_charger_status` | Echtzeit-Verfügbarkeit von Ladestationen | 1min |
| `road_check_status` | Server- & API-Gesundheitsprüfung | – |

### Verkehr (kostenloser API-Key nötig)

| Tool | Beschreibung | Cache |
|------|-------------|-------|
| `road_traffic_situations` | Unfälle, Baustellen, Stau vom ASTRA/VMZ-CH | 2min |
| `road_traffic_counters` | Fahrzeuge/h + km/h an Zählstellen nahe Position | 1min |
| `road_counter_sites` | Messstellen in der Nähe auflisten | 24h |

### Park & Rail + Multimodal (kein API-Key)

| Tool | Beschreibung | Cache |
|------|-------------|-------|
| `road_park_rail` | SBB Park+Rail Anlagen in der Nähe finden | 5min |
| `road_mobility_snapshot` | Vollständiges Mobilitäts-Lagebild für einen Standort | – |
| `road_multimodal_plan` | Auto -> Park+Rail -> ÖV -> Ziel planen | – |

### Geografie & Adressen — Phase 4 (kein API-Key)

| Tool | Beschreibung | Cache |
|------|-------------|-------|
| `road_geocode_address` | Schweizer Adresse -> GPS (amtl. Gebäudeadressverzeichnis) | – |
| `road_reverse_geocode` | GPS -> amtliche Adresse mit EGID/EGAID (GWR) | – |
| `road_classify_road` | Strassenklassifikation via swissTLM3D | – |

### Beispiel-Abfragen

| Abfrage | Tool |
|---------|------|
| *«Finde Sharing-Velos beim Zürich HB»* | `road_find_sharing` |
| *«Wo kann ich mein E-Auto bei Bern laden?»* | `road_find_charger` |
| *«Gibt es Verkehrsstörungen auf der A1?»* | `road_traffic_situations` |
| *«Wo kann ich beim Bahnhof Winterthur parkieren?»* | `road_park_rail` |
| *«Plane meine Reise von Dietikon nach Bern mit Auto + Zug»* | `road_multimodal_plan` |

---

## API-Key für Verkehrstools

1. Registrierung: <https://api-manager.opentransportdata.swiss>
2. Neue Applikation erstellen -> API «Strassenverkehr» abonnieren
3. Token kopieren

```bash
export OPENTRANSPORTDATA_API_KEY=<dein-token>
```

Ohne Key geben die Verkehrstools einen sprechenden Fehler mit dem genauen Registrierungs-Link zurück — kein Absturz.

---

## Architektur

```
swiss_road_mobility_mcp/
├── server.py             # FastMCP Server, 15 Tools
├── api_infrastructure.py # RateLimiter, Cache, HTTP-Client, Geo-Hilfen
├── shared_mobility.py    # sharedmobility.ch
├── ev_charging.py        # ich-tanke-strom.ch
├── traffic_situations.py # DATEX II Verkehrsmeldungen (SOAP/XML)
├── traffic_counters.py   # DATEX II Zählstellen (SOAP/XML)
├── park_rail.py          # SBB Open Data Park & Rail
├── multimodal.py         # Snapshot + Reiseplaner (Cross-Source)
└── geo_admin.py          # geo.admin.ch Geokodierung + Strassenklassifikation
```

### Datenquellen-Übersicht

| Quelle | Protokoll | Umfang | Auth |
|--------|-----------|--------|------|
| sharedmobility.ch | REST/JSON (GBFS) | Alle CH-Sharing-Anbieter | Keine |
| ich-tanke-strom.ch | GeoJSON | Alle öffentlichen E-Ladestationen | Keine |
| opentransportdata.swiss | DATEX II / SOAP+XML | ASTRA-Verkehrsdaten | Gratis-Key |
| data.sbb.ch | REST/JSON (Opendatasoft) | SBB Park & Rail | Keine |
| transport.opendata.ch | REST/JSON | ÖV-Fahrpläne | Keine |
| geo.admin.ch | REST/JSON | Amtliche Adressen, Strassen | Keine |

---

## Projektstruktur

```
swiss-road-mobility-mcp/
├── src/swiss_road_mobility_mcp/
│   ├── __init__.py              # Package
│   ├── server.py                # FastMCP Server, 15 Tools
│   ├── api_infrastructure.py    # RateLimiter, Cache, HTTP-Client
│   ├── shared_mobility.py       # Sharing-Fahrzeuge
│   ├── ev_charging.py           # E-Ladestationen
│   ├── traffic_situations.py    # Verkehrsmeldungen
│   ├── traffic_counters.py      # Fahrzeugzählung
│   ├── park_rail.py             # Park & Rail
│   ├── multimodal.py            # Snapshot + Reiseplanung
│   └── geo_admin.py             # Geokodierung + Strassen
├── tests/
│   ├── test_integration.py      # Live-API-Tests
│   └── test_phase3.py           # Park & Rail + Multimodal Tests
├── .github/workflows/ci.yml     # GitHub Actions (Python 3.11/3.12/3.13)
├── pyproject.toml
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md                    # Englische Hauptversion
└── README.de.md                 # Diese Datei (Deutsch)
```

---

## Bekannte Einschränkungen

- **Shared Mobility:** Die `sharedmobility.ch`-API erzwingt kein striktes Radius-Filtering; Fahrzeuge leicht ausserhalb des Radius können erscheinen
- **E-Laden:** Namenskonventionen für Stationen variieren je nach Betreiber
- **Verkehr (DATEX II):** Benötigt einen kostenlosen API-Key; ohne Key geben die Tools hilfreiche Fehlermeldungen zurück
- **Park & Rail:** SBB benennt gelegentlich Endpunkte um; der Server enthält eine Fallback-Kette
- **Multimodaler Planer:** Antwortzeit hängt von der langsamsten der abgefragten Quellen ab

---

## Tests

```bash
# Alle Tests
pytest tests/ -v

# Schnell-Check (ohne pytest)
python tests/test_phase3.py
```

---

## Sicherheit & Datenschutz

- Alle Daten sind öffentliche Open-Government-Data
- Keine persönlichen Daten werden verarbeitet
- Rate Limiting schützt die APIs vor Überlastung
- Lokale Caches minimieren externe Anfragen
- DATEX-II-Daten enthalten keine Personendaten

---

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md)

---

## Mitwirken

Siehe [CONTRIBUTING.md](CONTRIBUTING.md)

---

## Lizenz

MIT-Lizenz — siehe [LICENSE](LICENSE)

---

## Autor

Hayal Oezkan · [malkreide](https://github.com/malkreide)

---

## Credits & Verwandte Projekte

- **sharedmobility.ch:** [sharedmobility.ch](https://sharedmobility.ch/) — Schweizer Sharing-Plattform
- **ich-tanke-strom.ch:** [ich-tanke-strom.ch](https://ich-tanke-strom.ch/) — Schweizer E-Ladenetzwerk
- **ASTRA / opentransportdata.swiss:** [opentransportdata.swiss](https://opentransportdata.swiss/) — Strassenverkehrsdaten Bund
- **SBB Open Data:** [data.sbb.ch](https://data.sbb.ch/) — Schweizerische Bundesbahnen
- **geo.admin.ch:** [geo.admin.ch](https://api3.geo.admin.ch/) — Geodienste des Bundes
- **Protokoll:** [Model Context Protocol](https://modelcontextprotocol.io/) — Anthropic / Linux Foundation
- **Verwandt:** [swiss-transport-mcp](https://github.com/malkreide/swiss-transport-mcp) — ÖV-Server (Züge, Busse, Trams)
- **Verwandt:** [zurich-opendata-mcp](https://github.com/malkreide/zurich-opendata-mcp) — 900+ Datensätze der Stadt Zürich
- **Portfolio:** [Swiss Public Data MCP Portfolio](https://github.com/malkreide)
