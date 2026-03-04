"""
E-Ladestationen Client – Zugriff auf ich-tanke-strom.ch Daten.

Stell dir das vor wie eine Tankstellenkarte für Elektroautos:
Wo kann ich laden? Ist die Station frei? Welcher Stecker passt?

Datenquelle: Bundesamt für Energie (BFE) via data.geo.admin.ch
Format: GeoJSON + OICP-JSON (kein API-Key nötig!)
Aktualisierung: Echtzeit (Verfügbarkeit), kontinuierlich (Stammdaten)

Architektur-Entscheidung:
Die Stammdaten (~8000 Stationen als GeoJSON, ~2 MB) werden einmal
heruntergeladen und im Cache gehalten. Für die Umkreissuche filtern
wir lokal mit der Haversine-Formel. Das ist schneller und schonender
als bei jeder Anfrage den Bund-Server zu kontaktieren.

Metapher: Statt jedes Mal die Telefonzentrale anzurufen,
haben wir ein Telefonbuch im Schrank.
"""

import logging
from typing import Any

from .api_infrastructure import MobilityHTTPClient, APIError, haversine_km

logger = logging.getLogger("swiss-road-mobility-mcp")

# Endpunkte für ich-tanke-strom.ch Daten
GEOJSON_URL = (
    "https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet/"
    "data/ch.bfe.ladestellen-elektromobilitaet_de.json"
)
STATUS_URL = (
    "https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet/"
    "status/ch.bfe.ladestellen-elektromobilitaet.json"
)
EVSEDATA_URL = (
    "https://data.geo.admin.ch/ch.bfe.ladestellen-elektromobilitaet/"
    "data/ch.bfe.ladestellen-elektromobilitaet.json"
)

# Bekannte Stecker-Typen
PLUG_TYPES = [
    "CCS Combo 2 Plug (Cable Attached)",
    "CHAdeMO",
    "Type 2 Outlet",
    "Type 2 Connector (Cable Attached)",
    "Schuko (domestic)",
]

# Status-Mapping
STATUS_MAP = {
    "Available": "🟢 Frei",
    "Occupied": "🔴 Besetzt",
    "OutOfService": "⚫ Ausser Betrieb",
    "Unknown": "⚪ Status unbekannt",
}


async def _load_stations(client: MobilityHTTPClient) -> list[dict]:
    """
    Lädt alle Ladestationen als GeoJSON (gecacht).

    Die GeoJSON-Datei enthält ~8000 Features, jedes ein Ladepunkt.
    Wir cachen sie 30 Minuten – Standorte ändern sich nicht oft.
    """
    try:
        data = await client.get_json(
            GEOJSON_URL,
            cache_prefix="ev_geojson",
            cache_ttl=1800.0,  # 30 Min
            limiter_name="ev_charging",
        )
    except Exception as e:
        raise APIError(f"Ladestationen-Daten nicht abrufbar: {e}")

    features = data.get("features", [])
    if not features:
        raise APIError("Keine Ladestationen in den GeoJSON-Daten gefunden.")

    return features


async def _load_status(client: MobilityHTTPClient) -> dict[str, str]:
    """
    Lädt den Echtzeit-Status aller Ladepunkte.

    Returns: Dict von EvseID → Status ("Available", "Occupied", etc.)
    """
    try:
        data = await client.get_json(
            STATUS_URL,
            cache_prefix="ev_status",
            cache_ttl=120.0,  # 2 Min – Echtzeit-Daten
            limiter_name="ev_charging",
        )
    except Exception as e:
        logger.warning(f"Status-Daten nicht abrufbar: {e}")
        return {}

    status_map: dict[str, str] = {}
    evse_statuses = data.get("EVSEStatuses", [])

    if isinstance(evse_statuses, list):
        for operator in evse_statuses:
            records = operator.get("EVSEStatusRecord", [])
            if isinstance(records, list):
                for rec in records:
                    evse_id = rec.get("EvseID", "")
                    status = rec.get("EVSEStatus", "Unknown")
                    if evse_id:
                        status_map[evse_id] = status

    return status_map


async def _load_station_details(client: MobilityHTTPClient) -> dict[str, dict]:
    """
    Lädt die vollständigen Stammdaten aller Ladestationen (EVSEData).

    Dies ist die grosse Datei (~8-25 MB) mit allen Details.
    Wir cachen sie 1 Stunde.
    """
    try:
        data = await client.get_json(
            EVSEDATA_URL,
            cache_prefix="ev_details",
            cache_ttl=3600.0,  # 1h
            limiter_name="ev_charging",
        )
    except Exception as e:
        logger.warning(f"Detaildaten nicht abrufbar: {e}")
        return {}

    details: dict[str, dict] = {}
    evse_data = data.get("EVSEData", [])

    if isinstance(evse_data, list):
        for operator in evse_data:
            op_name = operator.get("OperatorName", "Unbekannt")
            records = operator.get("EVSEDataRecord", [])
            if isinstance(records, list):
                for rec in records:
                    station_id = rec.get("ChargingStationId", "")
                    if station_id:
                        # Bug #2 Fix: ChargingStationNames kommt je nach
                        # Betreiber als Liste [{"lang":…, "value":…}] ODER
                        # als einzelnes Dict {"lang":…, "value":…}.
                        # Normalisierung: immer als Liste behandeln.
                        names_raw = rec.get("ChargingStationNames", [])
                        if isinstance(names_raw, dict):
                            names_raw = [names_raw]
                        details[station_id] = {
                            "operator": op_name,
                            "address": rec.get("Address", {}),
                            "plugs": rec.get("Plugs", []),
                            "charging_facilities": rec.get("ChargingFacilities", []),
                            "is_open_24h": rec.get("IsOpen24Hours", False),
                            "accessibility": rec.get("Accessibility", ""),
                            "authentication": rec.get("AuthenticationModes", []),
                            "payment": rec.get("PaymentOptions", []),
                            "renewable_energy": rec.get("RenewableEnergy", False),
                            "hotline": rec.get("HotlinePhoneNumber", ""),
                            "names": [
                                n.get("value", "")
                                for n in names_raw
                                if isinstance(n, dict) and n.get("value")
                            ],
                        }

    return details


def _parse_geojson_feature(feature: dict, status_map: dict[str, str]) -> dict:
    """
    Wandelt ein GeoJSON-Feature in ein LLM-freundliches Format um.

    Die GeoJSON-Features enthalten leider HTML in 'description'.
    Wir extrahieren die Kerninfos stattdessen aus der ID und dem Status.
    """
    props = feature.get("properties", {})
    geo = feature.get("geometry", {})
    coords = geo.get("coordinates", [0, 0])

    station_id = feature.get("id", props.get("location_id", ""))
    status = status_map.get(station_id, "Unknown")

    return {
        "id": station_id,
        "latitude": coords[1] if len(coords) > 1 else None,
        "longitude": coords[0] if len(coords) > 0 else None,
        "status": status,
        "status_display": STATUS_MAP.get(status, f"⚪ {status}"),
    }


def _enrich_with_details(station: dict, details: dict[str, dict]) -> dict:
    """Reichert eine Station mit Detaildaten an (falls geladen)."""
    detail = details.get(station["id"])
    if not detail:
        return station

    enriched = {**station}

    if detail.get("names"):
        enriched["name"] = detail["names"][0]
    if detail.get("operator"):
        enriched["operator"] = detail["operator"]

    addr = detail.get("address", {})
    if addr:
        parts = [addr.get("Street", ""), addr.get("PostalCode", ""), addr.get("City", "")]
        enriched["address"] = " ".join(p for p in parts if p).strip()

    if detail.get("plugs"):
        enriched["plugs"] = detail["plugs"]

    facilities = detail.get("charging_facilities", [])
    if facilities:
        powers = []
        for f in facilities:
            power = f.get("power")
            ptype = f.get("powertype", "")
            if power:
                powers.append(f"{power} kW ({ptype})" if ptype else f"{power} kW")
        if powers:
            enriched["charging_power"] = powers

    enriched["is_open_24h"] = detail.get("is_open_24h", False)
    enriched["accessibility"] = detail.get("accessibility", "")

    if detail.get("renewable_energy"):
        enriched["renewable_energy"] = True

    return enriched


async def find_nearby_chargers(
    client: MobilityHTTPClient,
    longitude: float,
    latitude: float,
    radius_km: float = 2.0,
    only_available: bool = False,
    include_details: bool = True,
    limit: int = 20,
) -> dict:
    """
    Sucht E-Ladestationen im Umkreis einer Koordinate.

    Strategie: GeoJSON laden (gecacht), dann lokal mit
    Haversine-Formel filtern. Schneller und API-schonender
    als bei jeder Suche den Bund-Server zu kontaktieren.

    Args:
        longitude: Längengrad (z. B. 8.5417 für Zürich HB)
        latitude: Breitengrad (z. B. 47.3769 für Zürich HB)
        radius_km: Suchradius in km (0.1–50)
        only_available: Nur freie Stationen zeigen
        include_details: Stammdaten anreichern (Stecker, Betreiber etc.)
        limit: Max. Ergebnisse
    """
    # 1. Stationen und Status laden
    features = await _load_stations(client)
    status_map = await _load_status(client)

    # 2. Details laden (optional, grosse Datei)
    details: dict[str, dict] = {}
    if include_details:
        try:
            details = await _load_station_details(client)
        except Exception as e:
            logger.warning(f"Details konnten nicht geladen werden: {e}")

    # 3. Filtern nach Distanz
    results = []
    for feature in features:
        geo = feature.get("geometry", {})
        coords = geo.get("coordinates", [])
        if len(coords) < 2:
            continue

        flon, flat = coords[0], coords[1]
        dist = haversine_km(latitude, longitude, flat, flon)

        if dist <= radius_km:
            station = _parse_geojson_feature(feature, status_map)
            station["distance_km"] = round(dist, 2)

            if include_details:
                station = _enrich_with_details(station, details)

            results.append(station)

    # 4. Sortieren nach Distanz
    results.sort(key=lambda x: x.get("distance_km", 999))

    # 5. Filtern nach Verfügbarkeit
    if only_available:
        results = [r for r in results if r.get("status") == "Available"]

    # Statistik
    status_counts: dict[str, int] = {}
    for r in results:
        s = r.get("status", "Unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    total = len(results)
    results = results[:limit]

    return {
        "search": {
            "latitude": latitude,
            "longitude": longitude,
            "radius_km": radius_km,
            "only_available": only_available,
        },
        "total_found": total,
        "returned": len(results),
        "status_summary": {
            STATUS_MAP.get(k, k): v for k, v in status_counts.items()
        },
        "stations": results,
        "source": "ich-tanke-strom.ch (Bundesamt für Energie BFE)",
        "hint": (
            "Status-Daten sind Echtzeit. 'Frei' bedeutet, der Ladepunkt "
            "ist aktuell nicht belegt. Detaillierte Infos (Stecker, Leistung) "
            "kommen aus den Stammdaten."
        ),
    }


async def get_charger_status(
    client: MobilityHTTPClient,
    station_ids: list[str] | None = None,
) -> dict:
    """
    Prüft den Echtzeit-Status von Ladestationen.

    Args:
        station_ids: Liste von Station-IDs (z. B. ["CH*SWI*E10382"]).
                     Wenn leer: Gesamtstatistik über alle Stationen.
    """
    status_map = await _load_status(client)

    if station_ids:
        results = {}
        for sid in station_ids:
            status = status_map.get(sid, "Not found")
            results[sid] = {
                "status": status,
                "display": STATUS_MAP.get(status, f"⚪ {status}"),
            }
        return {
            "requested": len(station_ids),
            "stations": results,
        }

    # Gesamtstatistik
    counts: dict[str, int] = {}
    for status in status_map.values():
        counts[status] = counts.get(status, 0) + 1

    return {
        "total_charging_points": len(status_map),
        "status_distribution": {
            STATUS_MAP.get(k, k): v for k, v in sorted(counts.items())
        },
        "source": "ich-tanke-strom.ch (Echtzeit)",
    }
