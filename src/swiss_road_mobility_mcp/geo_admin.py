"""
geo.admin.ch Integration – Strassenklassifikation & Amtliches Adressverzeichnis.

Datenquelle: api3.geo.admin.ch (swisstopo / Bundesamt für Landestopografie)
Keine Authentifizierung nötig – vollständig offene Bundesbehördendaten.

Metapher:
  Wenn das amtliche Strassenverzeichnis ein Personalausweis der Strasse ist,
  dann sagt dir dieses Modul:
    - «Wer ist diese Strasse?» (Klassifikation: Autobahn? Nebenstrasse?)
    - «Wo genau ist diese Adresse?» (Geocoding via amtl. Gebäudeadressverzeichnis)
    - «Wie lautet die offizielle Adresse an diesem Ort?» (Reverse Geocoding)

Layer:
  - ch.swisstopo.swisstlm3d-strassen            → Strassenklassifikation (swissTLM3D)
  - ch.swisstopo.amtliches-gebaeudeadressverzeichnis → Amtl. Adressverzeichnis (GWR)

Alle Koordinaten: WGS84 (SR=4326).
Keine Authentifizierung, keine API-Keys – Phase 1 kompatibel.
"""

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger("swiss-road-mobility-mcp")

# ---------------------------------------------------------------------------
# Basis-URLs
# ---------------------------------------------------------------------------

GEO_ADMIN_BASE = "https://api3.geo.admin.ch/rest/services"
SEARCH_URL = f"{GEO_ADMIN_BASE}/api/SearchServer"
IDENTIFY_URL = f"{GEO_ADMIN_BASE}/ech/MapServer/identify"

LAYER_ROADS = "ch.swisstopo.swisstlm3d-strassen"
LAYER_ADDRESSES = "ch.swisstopo.amtliches-gebaeudeadressverzeichnis"

TIMEOUT = 10.0

# ---------------------------------------------------------------------------
# Codierungstabellen – «Übersetzer» für numerische swissTLM3D-Codes
#
# Quelle: swisstopo TLM Produktinfo / Modelldokumentation
# Metapher: Wie ein Zolldokument mit Zahlen – erst die Tabelle macht
# «Objektart 8» zu «Nebenstrasse».
# ---------------------------------------------------------------------------

OBJEKTART: dict[int, dict] = {
    1:  {"de": "Autobahn",                  "en": "Motorway",                "emoji": "🛣️",  "importance": "national"},
    2:  {"de": "Autostrasse",               "en": "Motorway-like road",      "emoji": "🛤️",  "importance": "national"},
    3:  {"de": "Ausfahrt Autobahn",         "en": "Motorway exit/ramp",      "emoji": "↗️",  "importance": "national"},
    4:  {"de": "Anschluss Hauptverkehrsstr.","en": "Main road junction",      "emoji": "↗️",  "importance": "regional"},
    6:  {"de": "Hauptstrasse",              "en": "Main road",               "emoji": "🚗",  "importance": "regional"},
    8:  {"de": "Nebenstrasse",              "en": "Secondary road",          "emoji": "🏘️",  "importance": "local"},
    9:  {"de": "Strasse (Sonderzweck)",     "en": "Special-purpose road",    "emoji": "⚠️",  "importance": "local"},
    10: {"de": "Weg / sonstige Strasse",    "en": "Path / other road",       "emoji": "🚶",  "importance": "local"},
    11: {"de": "Zufahrtsstrasse",           "en": "Access road",             "emoji": "🏠",  "importance": "local"},
    12: {"de": "Karrenweg / Güterweg",      "en": "Track / farm road",       "emoji": "🌾",  "importance": "agricultural"},
    14: {"de": "Radweg",                    "en": "Cycle path",              "emoji": "🚲",  "importance": "local"},
    15: {"de": "Fussweg",                   "en": "Footpath",                "emoji": "🚶",  "importance": "local"},
    16: {"de": "Treppenweg",               "en": "Steps / stairway",        "emoji": "🪜",  "importance": "local"},
    20: {"de": "Flurweg",                   "en": "Field path",              "emoji": "🌿",  "importance": "agricultural"},
}

VERKEHRSBEDEUTUNG: dict[int, str] = {
    100:    "Kein Wert (unklassiert)",
    200:    "Zufahrtstrasse",
    300:    "Sammelstrasse",
    400:    "Verbindungsstrasse",
    500:    "Hauptverbindungsstrasse",
    600:    "Hauptstrasse",
    999997: "Keine Angabe",
    999998: "Kein Attributwert",
}

BELAGSART: dict[int, str] = {
    100:    "Hartbelag (Asphalt/Beton)",
    200:    "Weich- / Naturbelag",
    999998: "Unbekannt",
}

EIGENTUEMER: dict[int, str] = {
    100:    "Bund",
    200:    "Kanton",
    300:    "Gemeinde",
    400:    "Privat",
    999997: "Keine Angabe",
    999998: "Kein Attributwert",
}

VERKEHRSBESCHRAENKUNG: dict[int, str] = {
    100:    "Keine Beschränkung",
    200:    "Fahrzeuge mit Bewilligung",
    300:    "Forst- und Landwirtschaft",
    400:    "Grundstückbesitzer",
    500:    "Einsatzkräfte (Feuerwehr/Ambulanz/Polizei)",
    900:    "Kein öffentlicher Verkehr",
    1000:   "Baufahrzeuge",
    1100:   "Busse und Taxis",
    1200:   "Zweiräder erlaubt",
    1900:   "Fussgänger und Radfahrer",
    999998: "Kein Attributwert",
}

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _decode_road_properties(props: dict) -> dict:
    """
    Übersetzt rohe swissTLM3D-Attribute in lesbare Texte und Metadaten.
    """
    raw_obj = props.get("objektart")
    raw_vb  = props.get("verkehrsbedeutung")
    raw_ba  = props.get("belagsart")
    raw_eig = props.get("eigentuemer")
    raw_vbs = props.get("verkehrsbeschraenkung")

    obj_info = OBJEKTART.get(raw_obj, {
        "de": f"Unbekannt (Code {raw_obj})",
        "en": f"Unknown (code {raw_obj})",
        "emoji": "❓",
        "importance": "unknown",
    })

    return {
        "road_name":       props.get("strassenname"),
        "road_type": {
            "code":               raw_obj,
            "label_de":           obj_info["de"],
            "label_en":           obj_info["en"],
            "emoji":              obj_info["emoji"],
            "network_importance": obj_info["importance"],
        },
        "surface":            BELAGSART.get(raw_ba,  f"Code {raw_ba}"),
        "functional_class":   VERKEHRSBEDEUTUNG.get(raw_vb,  f"Code {raw_vb}"),
        "ownership":          EIGENTUEMER.get(raw_eig, f"Code {raw_eig}"),
        "access_restriction": VERKEHRSBESCHRAENKUNG.get(raw_vbs, f"Code {raw_vbs}"),
    }


def _clean_label(label: str) -> str:
    """Entfernt HTML-Tags aus geo.admin.ch Labels (z.B. <b>Zürich</b> → Zürich)."""
    return re.sub(r"<[^>]+>", "", label).strip()


def _build_mapextent(lon: float, lat: float, delta: float = 0.02) -> str:
    """Erstellt den Karten-Extent-String für den identify-Endpoint."""
    return f"{lon - delta},{lat - delta},{lon + delta},{lat + delta}"


# ---------------------------------------------------------------------------
# Öffentliche API-Funktionen
# ---------------------------------------------------------------------------

async def geocode_address(
    search_text: str,
    limit: int = 5,
) -> dict[str, Any]:
    """
    Geocodiert eine Schweizer Adresse zu GPS-Koordinaten.

    Verwendet das amtliche Gebäudeadressverzeichnis (GWR-basiert)
    von swisstopo über die geo.admin.ch SearchServer-API.

    Metapher: Das amtliche «Telefonbuch» der Schweizer Adressen –
    du gibst den Namen, es liefert die exakte Haustür-Koordinate.

    Rückgabe enthält pro Treffer:
      - address:  Bereinigte Adresszeile
      - latitude / longitude: WGS84-Koordinaten
      - feature_id: ID im amtl. Gebäudeadressverzeichnis
      - source: Datenebene (Layer-ID)
    """
    params = {
        "searchText": search_text,
        "type":       "locations",
        "origins":    "address",
        "returnGeometry": "true",
        "limit":      str(limit),
        "lang":       "de",
        "sr":         "4326",
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(SEARCH_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    results = []
    for hit in data.get("results", []):
        attrs = hit.get("attrs", {})
        results.append({
            "address":     _clean_label(attrs.get("label", "")),
            "detail":      attrs.get("detail", ""),
            "latitude":    attrs.get("lat"),
            "longitude":   attrs.get("lon"),
            "feature_id":  attrs.get("featureId"),
            "source":      LAYER_ADDRESSES,
        })

    return {
        "query":       search_text,
        "found":       len(results),
        "data_source": "swisstopo amtliches Gebäudeadressverzeichnis (geo.admin.ch)",
        "results":     results,
    }


async def reverse_geocode(
    latitude: float,
    longitude: float,
    limit: int = 3,
) -> dict[str, Any]:
    """
    Findet die nächstgelegenen offiziellen Adressen für GPS-Koordinaten.

    Verwendet den identify-Endpoint mit dem amtlichen Gebäudeadressverzeichnis.
    Liefert EGID (Gebäudeidentifikator) und EGAID (Adressidentifikator)
    aus dem Eidgenössischen Gebäude- und Wohnungsregister (GWR).

    Metapher: Du stehst irgendwo auf der Strasse und fragst:
    «Was ist die offizielle Adresse an diesem Ort?»

    Rückgabe enthält pro Adresse:
      - address:   «Strassenname Hausnummer» (z.B. «Bahnhofplatz 1»)
      - zip_municipality: PLZ + Ort
      - egid / egaid: GWR-Identifikatoren (für Folgeabfragen)
      - official_address: true wenn amtlich registriert
    """
    params = {
        "geometry":       f"{longitude},{latitude}",
        "geometryFormat": "geojson",
        "geometryType":   "esriGeometryPoint",
        "imageDisplay":   "500,500,96",
        "mapExtent":      _build_mapextent(longitude, latitude, delta=0.005),
        "tolerance":      "30",
        "layers":         f"all:{LAYER_ADDRESSES}",
        "sr":             "4326",
        "lang":           "de",
        "returnGeometry": "false",
        "limit":          str(min(limit, 10)),
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(IDENTIFY_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    addresses = []
    for feature in data.get("results", [])[:limit]:
        p = feature.get("properties", {})
        addresses.append({
            "address":            f"{p.get('stn_label', '')} {p.get('adr_number', '')}".strip(),
            "street":             p.get("stn_label"),
            "house_number":       p.get("adr_number"),
            "zip_municipality":   p.get("zip_label"),
            "municipality":       p.get("com_name"),
            "municipality_number": p.get("com_fosnr"),
            "egid":               p.get("bdg_egid"),    # Eidg. Gebäudeidentifikator
            "egaid":              p.get("adr_egaid"),   # Eidg. Adressidentifikator
            "building_category":  p.get("bdg_category"),
            "official_address":   p.get("adr_official"),
            "status":             p.get("adr_status"),
            "last_modified":      p.get("adr_modified"),
            "source":             LAYER_ADDRESSES,
        })

    return {
        "query":       {"latitude": latitude, "longitude": longitude},
        "found":       len(addresses),
        "data_source": "swisstopo amtliches Gebäudeadressverzeichnis (geo.admin.ch / GWR)",
        "addresses":   addresses,
    }


async def classify_road(
    latitude: float,
    longitude: float,
    tolerance: int = 50,
    limit: int = 5,
) -> dict[str, Any]:
    """
    Klassifiziert Strassen an einem Standort via swissTLM3D.

    Ruft den identify-Endpoint für ch.swisstopo.swisstlm3d-strassen ab
    und übersetzt die numerischen Codes in lesbare Klassifikationen.

    Das swissTLM3D ist das offizielle topografische Landschaftsmodell
    der Schweiz – die «amtliche Karte» der Landesgeografie im Digitalformat.

    Metapher: Wie ein Strasseninspektor, der alle Strassen im Umkreis
    katalogisiert und dir ihren «amtlichen Ausweis» zeigt:
    Autobahn, Hauptstrasse, Nebenstrasse, Güterweg – jede hat ihren Status.

    Klassifizierung nach:
      - objektart: Strassentyp (Autobahn, Hauptstrasse, Nebenstrasse, Weg …)
      - verkehrsbedeutung: Funktionale Klasse im Netz
      - belagsart: Strassenbelag (Hart- vs. Naturbelag)
      - eigentuemer: Bund / Kanton / Gemeinde / Privat
      - verkehrsbeschraenkung: Zugangsbeschränkungen

    Parameter:
        tolerance: Suchtoleranz in Pixeln bei 1000×1000px Render
                   (je nach Zoom ca. 5–200m; Default 50 ≈ ~25m)
    """
    params = {
        "geometry":       f"{longitude},{latitude}",
        "geometryFormat": "geojson",
        "geometryType":   "esriGeometryPoint",
        "imageDisplay":   "1000,1000,96",
        "mapExtent":      _build_mapextent(longitude, latitude, delta=0.01),
        "tolerance":      str(tolerance),
        "layers":         f"all:{LAYER_ROADS}",
        "sr":             "4326",
        "lang":           "de",
        "returnGeometry": "false",
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(IDENTIFY_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    roads = []
    seen_ids: set = set()

    for feature in data.get("results", []):
        fid = feature.get("featureId")
        if fid in seen_ids:
            continue
        seen_ids.add(fid)

        props = feature.get("properties", {})
        decoded = _decode_road_properties(props)
        roads.append({"feature_id": fid, **decoded})

        if len(roads) >= limit:
            break

    # Übersicht: welche Strassentypen wurden gefunden?
    type_summary: dict[str, int] = {}
    for r in roads:
        label = r["road_type"]["label_de"]
        type_summary[label] = type_summary.get(label, 0) + 1

    return {
        "query": {
            "latitude":     latitude,
            "longitude":    longitude,
            "tolerance_px": tolerance,
        },
        "found":        len(roads),
        "type_summary": type_summary,
        "data_source":  "swisstopo swissTLM3D Strassen (geo.admin.ch)",
        "roads":        roads,
    }
