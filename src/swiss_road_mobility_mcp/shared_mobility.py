"""
Shared Mobility Client – Zugriff auf sharedmobility.ch API.

Stell dir das vor wie eine Karte aller Sharing-Angebote der Schweiz:
Velos, E-Bikes, E-Trottis, Autos, Cargo-Bikes – alles an einem Ort.

Datenquelle: Bundesamt für Energie (BFE) via api.sharedmobility.ch
Format: REST/JSON (kein API-Key nötig!)
Aktualisierung: Echtzeit (~60 Sekunden)

Drei Hauptabfragen:
1. identify → "Was gibt es in meiner Nähe?" (Umkreissuche)
2. find → "Wo ist die Station X?" (Textsuche)
3. providers → "Welche Anbieter gibt es?" (Übersicht)
"""

import logging
from typing import Any

from .api_infrastructure import MobilityHTTPClient, APIError

logger = logging.getLogger("swiss-road-mobility-mcp")

# Basis-URL der sharedmobility.ch API
BASE_URL = "https://api.sharedmobility.ch/v1/sharedmobility"

# Bekannte Fahrzeugtypen im Schweizer Feed
VEHICLE_TYPES = [
    "Bicycle", "E-Bike", "E-Scooter", "E-Moped",
    "Car", "E-Car", "Cargo-Bicycle", "Other",
]

# Pickup-Typen
PICKUP_TYPES = ["free_floating", "station_based"]


def _format_vehicle(item: dict) -> dict:
    """
    Formatiert ein Fahrzeug/Station aus der API-Antwort
    in ein sauberes, LLM-freundliches Format.

    Metapher: Wie ein Gepäckband – die Rohdaten kommen
    in Koffern verschiedener Grösse, wir packen sie
    in einheitliche Taschen um.
    """
    attrs = item.get("attributes", {})
    geo = item.get("geometry", {})

    result = {
        "id": attrs.get("id", ""),
        "provider": attrs.get("provider_name", attrs.get("provider_id", "Unbekannt")),
        "vehicle_type": attrs.get("vehicle_type", []),
        "pickup_type": attrs.get("pickup_type", ""),
        "available": attrs.get("available", False),
        "latitude": geo.get("y"),
        "longitude": geo.get("x"),
    }

    # Station-basierte Systeme haben mehr Infos
    if attrs.get("station_name"):
        result["station_name"] = attrs["station_name"]
    if attrs.get("station_address"):
        result["station_address"] = attrs["station_address"]
    if attrs.get("station_postcode"):
        result["postcode"] = attrs["station_postcode"]

    # Verfügbare Fahrzeuge (bei Stationen)
    if attrs.get("num_bikes_available") is not None:
        result["bikes_available"] = attrs["num_bikes_available"]
    if attrs.get("num_docks_available") is not None:
        result["docks_available"] = attrs["num_docks_available"]

    # App-Links (für Buchung)
    ios_uri = attrs.get("provider_apps_ios_store_uri")
    android_uri = attrs.get("provider_apps_android_store_uri")
    if ios_uri or android_uri:
        result["app_links"] = {}
        if ios_uri:
            result["app_links"]["ios"] = ios_uri
        if android_uri:
            result["app_links"]["android"] = android_uri

    return result


async def find_nearby_vehicles(
    client: MobilityHTTPClient,
    longitude: float,
    latitude: float,
    radius_meters: int = 500,
    vehicle_type: str | None = None,
    pickup_type: str | None = None,
    only_available: bool = True,
) -> dict:
    """
    Sucht Shared-Mobility-Angebote im Umkreis einer Koordinate.

    Nutzt den 'identify'-Endpoint der API:
    → Räumliche Abfrage: «Was ist innerhalb von X Metern um Punkt Y?»

    Args:
        longitude: Längengrad (z. B. 8.5417 für Zürich HB)
        latitude: Breitengrad (z. B. 47.3769 für Zürich HB)
        radius_meters: Suchradius in Metern (50–5000)
        vehicle_type: Optional: «E-Bike», «E-Scooter», «Car», etc.
        pickup_type: Optional: «free_floating» oder «station_based»
        only_available: Nur verfügbare Fahrzeuge (Standard: ja)

    Hinweis Radius-Toleranz (Bug #5):
        Die sharedmobility.ch API interpretiert den 'Tolerance'-Parameter
        nicht als strenge Meterangabe. Fahrzeuge können um ~5–10 % ausserhalb
        des angegebenen Radius erscheinen (beobachtet: 53 m bei 50 m-Abfrage).
        Dies ist ein bekanntes Verhalten der API, kein Code-Fehler.
        Bei sehr kleinen Radien (< 100 m) sind die Ergebnisse entsprechend
        als Richtwert zu verstehen.
    """
    params: dict[str, Any] = {
        "Geometry": f"{longitude},{latitude}",
        "Tolerance": str(radius_meters),
        "offset": "0",
        "geometryFormat": "esrijson",
    }

    # Filter aufbauen
    filters = []
    if vehicle_type:
        filters.append(f"ch.bfe.sharedmobility.vehicle_type={vehicle_type}")
    if pickup_type:
        filters.append(f"ch.bfe.sharedmobility.pickup_type={pickup_type}")

    # httpx sendet gleiche Keys als Liste (filters=X&filters=Y)
    if filters:
        params["filters"] = filters

    try:
        raw = await client.get_json(
            f"{BASE_URL}/identify",
            params=params,
            cache_prefix="sharing_nearby",
            cache_ttl=60.0,  # 60s – Echtzeit-Daten
            limiter_name="sharedmobility",
        )
    except APIError:
        raise
    except Exception as e:
        raise APIError(f"Shared Mobility API nicht erreichbar: {e}")

    if not isinstance(raw, list):
        return {"count": 0, "vehicles": [], "hint": "Unerwartetes API-Format."}

    # Formatieren und optional filtern
    vehicles = [_format_vehicle(item) for item in raw]

    if only_available:
        vehicles = [v for v in vehicles if v.get("available")]

    # Nach Fahrzeugtyp gruppieren für Übersicht
    type_counts: dict[str, int] = {}
    for v in vehicles:
        for vt in v.get("vehicle_type", ["Unbekannt"]):
            type_counts[vt] = type_counts.get(vt, 0) + 1

    return {
        "search": {
            "latitude": latitude,
            "longitude": longitude,
            "radius_meters": radius_meters,
            "filters": {
                "vehicle_type": vehicle_type,
                "pickup_type": pickup_type,
                "only_available": only_available,
            },
        },
        "count": len(vehicles),
        "by_type": type_counts,
        "vehicles": vehicles[:50],  # Max 50 Ergebnisse für Token-Effizienz
        "hint": (
            "Ergebnisse zeigen Echtzeit-Verfügbarkeit. "
            "Nutze die App-Links zur direkten Buchung beim Anbieter."
        ),
    }


async def search_stations(
    client: MobilityHTTPClient,
    search_text: str,
    search_field: str = "ch.bfe.sharedmobility.station.name",
    provider_id: str | None = None,
    limit: int = 20,
) -> dict:
    """
    Volltextsuche nach Sharing-Stationen.

    Nutzt den 'find'-Endpoint:
    → "Zeig mir alle Stationen mit 'Bahnhof' im Namen"

    Args:
        search_text: Suchbegriff (z. B. "Bahnhof", "ETH")
        search_field: Suchfeld (Standard: Stationsname)
        provider_id: Optional: Nur Stationen eines Anbieters
        limit: Max. Ergebnisse
    """
    params: dict[str, Any] = {
        "searchText": search_text,
        "searchField": search_field,
        "offset": "0",
        "geometryFormat": "esrijson",
    }

    if provider_id:
        params["filters"] = f"ch.bfe.sharedmobility.provider.id={provider_id}"

    try:
        raw = await client.get_json(
            f"{BASE_URL}/find",
            params=params,
            cache_prefix="sharing_search",
            cache_ttl=120.0,  # 2 Min – Stationsnamen ändern sich selten
            limiter_name="sharedmobility",
        )
    except APIError:
        raise
    except Exception as e:
        raise APIError(f"Shared Mobility Suche fehlgeschlagen: {e}")

    if not isinstance(raw, list):
        return {"count": 0, "stations": []}

    stations = [_format_vehicle(item) for item in raw[:limit]]

    return {
        "search_text": search_text,
        "count": len(stations),
        "stations": stations,
    }


async def list_providers(client: MobilityHTTPClient) -> dict:
    """
    Listet alle Shared-Mobility-Anbieter in der Schweiz auf.

    Metapher: Wie das Verzeichnis an der Infotafel –
    wer bietet was an, und welche Fahrzeugtypen gibt es?
    """
    try:
        raw = await client.get_json(
            f"{BASE_URL}/providers",
            cache_prefix="sharing_providers",
            cache_ttl=3600.0,  # 1h – Anbieter ändern sich kaum
            limiter_name="sharedmobility",
        )
    except APIError:
        raise
    except Exception as e:
        raise APIError(f"Shared Mobility Anbieterliste nicht abrufbar: {e}")

    if not isinstance(raw, list):
        return {"count": 0, "providers": []}

    providers = []
    for p in raw:
        entry = {
            "id": p.get("provider_id", ""),
            "name": p.get("name", ""),
            "vehicle_types": p.get("vehicle_type", []),
            "timezone": p.get("timezone", ""),
        }
        # App-Links
        apps = p.get("rental_apps", {})
        if apps:
            entry["app_links"] = {}
            if apps.get("ios", {}).get("store_uri"):
                entry["app_links"]["ios"] = apps["ios"]["store_uri"]
            if apps.get("android", {}).get("store_uri"):
                entry["app_links"]["android"] = apps["android"]["store_uri"]
        if p.get("phone_number"):
            entry["phone"] = p["phone_number"]

        providers.append(entry)

    # Statistik
    all_types: dict[str, int] = {}
    for p in providers:
        for vt in p.get("vehicle_types", []):
            all_types[vt] = all_types.get(vt, 0) + 1

    return {
        "count": len(providers),
        "vehicle_type_summary": all_types,
        "providers": providers,
        "source": "sharedmobility.ch (Bundesamt für Energie BFE)",
    }
