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

from .api_infrastructure import APIError, MobilityHTTPClient, haversine_km

logger = logging.getLogger("swiss-road-mobility-mcp")

# Basis-URL der sharedmobility.ch API
BASE_URL = "https://api.sharedmobility.ch/v1/sharedmobility"

# Fahrzeugtypen, wie die Quelle sie schreibt — nicht, wie man sie erwarten
# wuerde. Gelesen am 4.10.2026 aus `/providers` (alle deklarierten Typen).
# Bis dahin stand hier «Bicycle» und «Cargo-Bicycle»: Werte, die die Quelle nicht
# kennt und auf die sie mit 200 und `[]` antwortet. Ein Filter darauf meldete
# «keine Velos» an Orten voller Velos.
VEHICLE_TYPES = [
    "Bike",
    "E-Bike",
    "E-Scooter",
    "E-Moped",
    "Car",
    "E-Car",
    "CargoBike",
    "E-CargoBike",
    "Other",
]

# Was sich einzeln abfragen laesst. «Other» fehlt: die Quelle antwortete am
# 4.10.2026 auf `vehicle_type=Other` an jedem gefragten Ort mit HTTP 500
# (gemeldet als SFOE/sharedmobility#46; seit dem 12.10.2026 antwortet sie
# darauf mit 200).
_EINZELN_ABFRAGBAR = tuple(t for t in VEHICLE_TYPES if t != "Other")

# Pickup-Typen
PICKUP_TYPES = ["free_floating", "station_based"]

# Der Hinweis zu einem gefuellten Ergebnis. Zu einem leeren gehoert er nicht:
# Dort las er sich wie eine Bestaetigung, dass die Leere echt sei.
_HINWEIS_ECHTZEIT = "Ergebnisse zeigen Echtzeit-Verfügbarkeit. Nutze die App-Links zur direkten Buchung beim Anbieter."

# Eine leere Antwort der Quelle ist entweder eine Auskunft oder eine Stoerung,
# und am Endpunkt selbst ist sie nicht zu unterscheiden. Gemessen am 3.11.2026:
# ein Unsinnswort in `/find`, der Piz Bernina in `/identify` und ein unbekannter
# Fahrzeugtyp antworten alle mit HTTP 200 und `[]` — byte-gleich mit dem, was
# die Quelle am 31.10. und 1.11.2026 auf JEDE Abfrage lieferte, auch auf
# `/providers`. Unterscheiden laesst es sich nur am Anbieterverzeichnis: Das ist
# nie berechtigt leer (am 3.11.2026: 46 Anbieter), waehrend der Stoerung war es
# das.
_STOERUNG = (
    "sharedmobility.ch antwortet, liefert aber keine Daten: Auch das Anbieterverzeichnis "
    "ist leer, das sonst alle Schweizer Sharing-Anbieter führt. Das ist eine Störung der "
    "Quelle und keine Auskunft — nicht als «keine Treffer» oder «keine Anbieter» "
    "weitergeben. Später erneut versuchen."
)

# Wie alt das Verzeichnis hoechstens sein darf, das ueber eine leere Antwort
# entscheidet. Nicht die Stunde von `list_providers`: Ein Verzeichnis, das vor
# 59 Minuten voll war, sagt nichts darueber, ob die Quelle JETZT liefert — so
# alt darf auch die Antwort von `/identify` nicht sein, die es einordnet.
_PRUEF_TTL = 60.0


def _formatfehler(endpunkt: str, raw: Any) -> APIError:
    """Eine Antwort, die keine Liste ist. Nicht «0 Treffer»: Das waere eine Auskunft.

    Bis zum 3.11.2026 wurde daraus still `count: 0` — von einer Quelle, die ihr
    Format geaendert hat, nicht zu unterscheiden von einem leeren Ort. Kein Rat,
    es spaeter erneut zu versuchen: Ein geaendertes Format bleibt geaendert, bis
    der Server angepasst ist.
    """
    return APIError(
        f"sharedmobility.ch {endpunkt} antwortete in einem unbekannten Format "
        f"({type(raw).__name__} statt Liste). Die Antwort ist nicht auswertbar — "
        "das ist keine Auskunft «keine Treffer»."
    )


async def _anbieterverzeichnis(client: MobilityHTTPClient, *, cache_prefix: str, cache_ttl: float) -> list:
    """`/providers`, roh. Eine leere Liste wird nie gecacht (siehe `_STOERUNG`)."""
    try:
        raw = await client.get_json(
            f"{BASE_URL}/providers",
            cache_prefix=cache_prefix,
            cache_ttl=cache_ttl,
            cache_empty=False,
            limiter_name="sharedmobility",
        )
    except APIError:
        raise
    except Exception as e:
        raise APIError(f"Shared Mobility Anbieterliste nicht abrufbar: {e}")
    if not isinstance(raw, list):
        raise _formatfehler("/providers", raw)
    return raw


async def _leere_antwort_einordnen(client: MobilityHTTPClient) -> str:
    """Auskunft oder Stoerung? Wirft bei Stoerung, sonst der Hinweis zum leeren Ergebnis.

    Kostet nur etwas, wenn die Antwort leer war: Ein gefuelltes Ergebnis braucht
    keine Pruefung, und der Normalfall fragt das Verzeichnis nie.
    """
    try:
        anbieter = await _anbieterverzeichnis(client, cache_prefix="sharing_providers_probe", cache_ttl=_PRUEF_TTL)
    except APIError as e:
        # Nicht pruefbar ist nicht dasselbe wie gestoert: Das leere Ergebnis
        # bleibt stehen, aber ausdruecklich unbestaetigt. Genannt wird nur der
        # Status, nicht der Text: `_anbieterverzeichnis` verpackt jede Exception
        # samt Rohtext, und der landete hier in einem ERFOLGREICHEN Ergebnis.
        grund = f"HTTP {e.status_code}" if e.status_code else "nicht abrufbar"
        return (
            f"Keine Treffer. Ob die Quelle gerade Daten führt, liess sich nicht prüfen "
            f"(Anbieterverzeichnis: {grund}). Die leere Antwort ist deshalb unbestätigt — "
            "nicht als «hier gibt es nichts» weitergeben."
        )
    if not anbieter:
        raise APIError(_STOERUNG)
    return (
        f"Keine Treffer. Geprüft: Die Quelle ist erreichbar und führt derzeit {len(anbieter)} "
        "Anbieter. Eine Störung der ganzen Quelle ist damit ausgeschlossen; die leere Antwort "
        "gilt als ihre Auskunft."
    )


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

    vollstaendigkeit: dict | None = None
    try:
        raw = await _identify(client, params, filters)
    except APIError as e:
        # Nur der Fall, der gemessen ist: ohne Fahrzeugtyp und mit HTTP 500.
        # Ein 502/503/504 meldet eine Quelle, die gerade nicht da ist — sie mit
        # acht weiteren Abfragen zu bedraengen, aendert daran nichts.
        if vehicle_type or e.status_code != 500:
            raise
        raw, vollstaendigkeit = await _identify_je_typ(client, params, filters, ausloeser=e)

    if not isinstance(raw, list):
        raise _formatfehler("/identify", raw)

    # Geprueft wird die ROHE Antwort, vor `only_available`: Sind Fahrzeuge
    # gemeldet, aber keines frei, hat die Quelle geliefert — das ist eine
    # Auskunft und braucht keine Pruefung.
    hinweis = await _leere_antwort_einordnen(client) if not raw else _HINWEIS_ECHTZEIT

    # Formatieren und optional filtern
    vehicles = [_format_vehicle(item) for item in raw]

    if vollstaendigkeit is not None:
        # Acht Teillisten hintereinander gehaengt zeigten unter `[:50]` nur die
        # ersten Typen. Nach Distanz geordnet zeigen sie das Naechste.
        vehicles.sort(key=lambda v: _distanz_km(latitude, longitude, v))

    if only_available:
        vehicles = [v for v in vehicles if v.get("available")]

    # Nach Fahrzeugtyp gruppieren für Übersicht
    type_counts: dict[str, int] = {}
    for v in vehicles:
        for vt in v.get("vehicle_type", ["Unbekannt"]):
            type_counts[vt] = type_counts.get(vt, 0) + 1

    ergebnis: dict[str, Any] = {
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
        "hint": hinweis,
    }
    if vollstaendigkeit is not None:
        ergebnis["completeness"] = vollstaendigkeit
        fehlend = [
            *vollstaendigkeit["not_queryable_vehicle_types"],
            *vollstaendigkeit.get("failed_vehicle_types", {}),
        ]
        ergebnis["hint"] = (
            "UNVOLLSTÄNDIG: Die Quelle scheitert an der Umkreissuche ohne Fahrzeugtyp, "
            "deshalb wurde je Typ einzeln gefragt. Es fehlen Fahrzeuge der Typen: "
            + ", ".join(fehlend)
            + ". Details unter 'completeness'. "
            + ergebnis["hint"]
        )
    return ergebnis


async def _identify(client: MobilityHTTPClient, params: dict[str, Any], filters: list[str]) -> Any:
    """Eine Abfrage an `/identify`, mit den gegebenen Filtern."""
    anfrage = dict(params)
    # httpx sendet gleiche Keys als Liste (filters=X&filters=Y)
    if filters:
        anfrage["filters"] = filters
    try:
        return await client.get_json(
            f"{BASE_URL}/identify",
            params=anfrage,
            cache_prefix="sharing_nearby",
            cache_ttl=60.0,  # 60s – Echtzeit-Daten
            limiter_name="sharedmobility",
        )
    except APIError:
        raise
    except Exception as e:
        raise APIError(f"Shared Mobility API nicht erreichbar: {e}")


async def _identify_je_typ(
    client: MobilityHTTPClient,
    params: dict[str, Any],
    filters: list[str],
    ausloeser: APIError,
) -> tuple[list, dict]:
    """
    Die Umkreissuche ohne Fahrzeugtyp, zusammengesetzt aus einer je Typ.

    Gemessen am 4.10.2026: `/identify` ohne `vehicle_type` antwortete in
    Zuerich, Bern, Winterthur, Lausanne und Basel mit HTTP 500, ebenso mit
    `pickup_type=free_floating` allein. Die Quelle scheitert an einzelnen
    Datensaetzen, und eine Abfrage traegt, sobald der Filter sie ausschliesst.
    Je Anbieter eingegrenzt: in Zuerich brach allein `velospot`, in Bern
    `velospot` und `voiscooters.com`. Dort scheiterte darum auch
    `vehicle_type=E-Scooter`, in Zuerich nicht; `vehicle_type=Other` scheiterte
    ueberall. Welcher Typ bricht, haengt also am Ort — er wird deshalb nicht
    vorab ausgelassen, sondern versucht und im Ergebnis genannt, wenn er
    scheitert.

    Das Ergebnis ist deshalb ausdruecklich unvollstaendig und sagt es: ein
    stilles Zusammensetzen saehe aus wie die ganze Antwort und waere es nicht.

    Gemeldet als https://github.com/SFOE/sharedmobility/issues/46, behoben
    am 12.10.2026 (der Hostname zeigte noch auf einen alten Server). Der Umweg
    bleibt fuer einen Rueckfall stehen; er greift nur bei einem 500 und kostet
    sonst nichts. Ob die Quelle traegt, prueft der Live-Test
    `test_umkreissuche_ohne_typ_traegt_wieder` jede Nacht.

    Kosten: bis zu acht Abfragen statt einer, sequentiell — gegen eine Quelle,
    die gerade stolpert, und gegen den Tuersteher (30/min), der jede einzeln
    zaehlt.
    """
    gesammelt: list = []
    gesehen: set[str] = set()
    abgefragt: list[str] = []
    gescheitert: dict[str, str] = {}

    for typ in _EINZELN_ABFRAGBAR:
        try:
            teil = await _identify(client, params, [f"ch.bfe.sharedmobility.vehicle_type={typ}", *filters])
        except APIError as e:
            gescheitert[typ] = str(e)
            continue
        if not isinstance(teil, list):
            gescheitert[typ] = "Unerwartetes API-Format."
            continue
        abgefragt.append(typ)
        for item in teil:
            # Eine Station mit E-Bikes und Velos kommt unter beiden Typen.
            vid = (item.get("attributes") or {}).get("id")
            if vid:
                if vid in gesehen:
                    continue
                gesehen.add(vid)
            gesammelt.append(item)

    if not abgefragt:
        # Keine Teilabfrage hat getragen: dann ist nichts zusammengesetzt, und
        # der urspruengliche Befund ist die ehrlichste Auskunft.
        raise ausloeser

    vollstaendigkeit = {
        "complete": False,
        "reason": (
            "Die Quelle antwortete auf die Umkreissuche ohne Fahrzeugtyp mit HTTP 500. "
            "Abgefragt wurde je Fahrzeugtyp einzeln."
        ),
        "queried_vehicle_types": abgefragt,
        "not_queryable_vehicle_types": [t for t in VEHICLE_TYPES if t not in _EINZELN_ABFRAGBAR],
    }
    if gescheitert:
        vollstaendigkeit["failed_vehicle_types"] = gescheitert
    return gesammelt, vollstaendigkeit


def _distanz_km(latitude: float, longitude: float, fahrzeug: dict) -> float:
    """Distanz zum Suchpunkt; ohne Koordinaten ganz nach hinten."""
    lat, lon = fahrzeug.get("latitude"), fahrzeug.get("longitude")
    if lat is None or lon is None:
        return float("inf")
    return haversine_km(latitude, longitude, lat, lon)


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
        raise _formatfehler("/find", raw)

    stations = [_format_vehicle(item) for item in raw[:limit]]

    ergebnis: dict[str, Any] = {
        "search_text": search_text,
        "count": len(stations),
        "stations": stations,
    }
    if not raw:
        ergebnis["hint"] = await _leere_antwort_einordnen(client)
    return ergebnis


async def list_providers(client: MobilityHTTPClient) -> dict:
    """
    Listet alle Shared-Mobility-Anbieter in der Schweiz auf.

    Metapher: Wie das Verzeichnis an der Infotafel –
    wer bietet was an, und welche Fahrzeugtypen gibt es?
    """
    # 1h – Anbieter ändern sich kaum. Eine leere Liste bleibt draussen.
    raw = await _anbieterverzeichnis(client, cache_prefix="sharing_providers", cache_ttl=3600.0)
    if not raw:
        # Am 31.10. und 1.11.2026 hiess das `count: 0` samt Quelle BFE — eine
        # belegte Auskunft, die falsch war.
        raise APIError(_STOERUNG)

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
