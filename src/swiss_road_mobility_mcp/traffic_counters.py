"""
Traffic Counters (DATEX II) – Phase 2 Modul.

Metapher: Während Verkehrsmeldungen zeigen «Was ist passiert?»,
zeigen Traffic Counters «Wie viele Fahrzeuge fahren gerade pro Stunde?»
Das ist die digitale Strichliste am Strassenrand – nur präziser,
minütlich aktualisiert und unterscheidet Leicht- von Schwerverkehr.

Datenquelle: ASTRA Verkehrsdaten-Plattform (opentransportdata.swiss)
Format: DATEX II v2.3 (SOAP + XML), FEDRO-Profil
API-Key: Erforderlich (kostenlos: api-manager.opentransportdata.swiss)
Update: Minütlich (dynamisch) / Selten (statische Messstellen-Tabelle)

Zwei SOAP-Operationen:
  1. pullMeasurementSiteTable  → statische Metadaten (Standorte, IDs)
  2. pullMeasuredData          → Echtzeit-Messungen (Fahrzeuge/h, km/h)
"""

import logging
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import httpx

from .api_infrastructure import APIError, haversine_km

logger = logging.getLogger("swiss-road-mobility-mcp")

# ---------------------------------------------------------------------------
# Namespace-Konstanten
# ---------------------------------------------------------------------------

_DX2 = "http://datex2.eu/schema/2/2_0"
_SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
_XSI = "http://www.w3.org/2001/XMLSchema-instance"

COUNTERS_URL = (
    "https://api.opentransportdata.swiss/TDP/Soap_Datex2/TrafficCounters/Pull"
)
SOAP_ACTION_SITES = (
    "http://opentransportdata.swiss/TDP/Soap_Datex2/Pull/v1/pullMeasurementSiteTable"
)
SOAP_ACTION_DATA = (
    "http://opentransportdata.swiss/TDP/Soap_Datex2/Pull/v1/pullMeasuredData"
)

# ---------------------------------------------------------------------------
# Cache-Konfiguration
# ---------------------------------------------------------------------------

# Statische Messstellentabelle: lange gültig (ändert sich selten)
_sites_cache: dict[str, dict] | None = None
_sites_cache_ts: float = 0.0
_SITES_TTL = 86_400.0  # 24 Stunden

# Dynamische Messdaten: minutengenau
_data_cache: dict[str, list] = {}
_data_cache_ts: dict[str, float] = {}
_DATA_TTL = 60.0  # 1 Minute

# ---------------------------------------------------------------------------
# SOAP Request Bodies
# ---------------------------------------------------------------------------

_SOAP_BODY_SITES = """\
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <d2LogicalModel xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                    modelBaseVersion="2"
                    xmlns="http://datex2.eu/schema/2/2_0">
      <exchange>
        <supplierIdentification>
          <country>ch</country>
          <nationalIdentifier>swiss-road-mobility-mcp</nationalIdentifier>
        </supplierIdentification>
      </exchange>
    </d2LogicalModel>
  </soap:Body>
</soap:Envelope>"""


def _make_data_body(site_ids: list[str]) -> str:
    """
    Erstellt den SOAP-Body für pullMeasuredData mit optionalem ID-Filter.

    Mit Filter: Nur Messdaten für die gewünschten Stationen.
    Ohne Filter wäre die Response sehr gross (alle Schweizer Zählstellen).
    """
    site_refs = "\n".join(
        f'            <measurementSiteReference id="{sid}"/>'
        for sid in site_ids[:50]  # Safety-Limit: max 50 Sites pro Anfrage
    )

    # Aktueller Zeitstempel für publicationTime
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")

    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <d2LogicalModel xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                    modelBaseVersion="2"
                    xmlns="http://datex2.eu/schema/2/2_0">
      <exchange>
        <supplierIdentification>
          <country>ch</country>
          <nationalIdentifier>swiss-road-mobility-mcp</nationalIdentifier>
        </supplierIdentification>
      </exchange>
      <payloadPublication xsi:type="GenericPublication" lang="de">
        <publicationTime>{now_iso}</publicationTime>
        <publicationCreator>
          <country>ch</country>
          <nationalIdentifier>swiss-road-mobility-mcp</nationalIdentifier>
        </publicationCreator>
        <genericPublicationName>MeasuredDataFilter</genericPublicationName>
        <genericPublicationExtension>
          <measuredDataFilter>
            <measurementSiteTableReference targetClass="MeasurementSiteTable"
                                           id="OTD:TrafficData"
                                           version="0"/>
{site_refs}
          </measuredDataFilter>
        </genericPublicationExtension>
      </payloadPublication>
    </d2LogicalModel>
  </soap:Body>
</soap:Envelope>"""

# ---------------------------------------------------------------------------
# XML-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _t(tag: str) -> str:
    return f"{{{_DX2}}}{tag}"


def _text(el: ET.Element, *path: str) -> str:
    cur = el
    for step in path:
        child = cur.find(_t(step))
        if child is None:
            return ""
        cur = child
    return (cur.text or "").strip()


def _best_lang(el: ET.Element, prefer: tuple[str, ...] = ("de", "fr", "en")) -> str:
    """Beste verfügbare Sprache aus DATEX II <values><value lang='xx'>."""
    texts: dict[str, str] = {}
    for v in el.iter(_t("value")):
        lang = v.get("lang", "xx")
        t = (v.text or "").strip()
        if t:
            texts[lang] = t
    for lang in prefer:
        if texts.get(lang):
            return texts[lang]
    return next(iter(texts.values()), "")


async def _soap_post(api_key: str, soap_action: str, body: str) -> ET.Element:
    """
    Gemeinsamer SOAP-POST-Helper für alle DATEX II Counters-Requests.
    Returns das d2LogicalModel-Element (Wurzel des DATEX II Inhalts).
    """
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": soap_action,
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "swiss-road-mobility-mcp/0.2.0",
        "Accept-Encoding": "gzip, deflate",
    }

    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        try:
            resp = await client.post(
                COUNTERS_URL,
                content=body.encode("utf-8"),
                headers=headers,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            sc = e.response.status_code
            if sc in (401, 403):
                raise APIError(
                    f"HTTP {sc}: API-Key fehlt oder ungültig. "
                    "Kostenlose Registrierung auf api-manager.opentransportdata.swiss. "
                    "Dann OPENTRANSPORTDATA_API_KEY als Umgebungsvariable setzen."
                )
            raise APIError(
                f"HTTP {sc} von TrafficCounters-API: {e.response.text[:300]}"
            )
        except httpx.TimeoutException:
            raise APIError("Timeout (45s) bei TrafficCounters-API. "
                           "Die Messstellentabelle ist gross – bitte erneut versuchen.")
        except httpx.ConnectError as e:
            raise APIError(f"Verbindungsfehler zur TrafficCounters-API: {e}")

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        raise APIError(f"DATEX II XML-Parsing-Fehler: {e}")

    body_el = root.find(f"{{{_SOAP_ENV}}}Body")
    if body_el is None:
        raise APIError("SOAP-Body nicht gefunden in Response.")

    d2_el = body_el.find(_t("d2LogicalModel"))
    if d2_el is None:
        d2_el = next(iter(body_el), None)
    if d2_el is None:
        raise APIError("d2LogicalModel nicht gefunden in SOAP-Body.")

    return d2_el


# ---------------------------------------------------------------------------
# Statische Messstellentabelle
# ---------------------------------------------------------------------------

async def fetch_measurement_sites(api_key: str) -> dict[str, dict]:
    """
    Holt die statische Messstellentabelle (MeasurementSiteTable).

    Gecached für 24h – ändert sich selten.
    Returns: dict site_id → {id, name, latitude, longitude, supplier}
    """
    global _sites_cache, _sites_cache_ts

    now = time.monotonic()
    if _sites_cache is not None and (now - _sites_cache_ts) < _SITES_TTL:
        logger.debug("Cache HIT: measurement_sites")
        return _sites_cache

    logger.info("Fetching MeasurementSiteTable (statisch, 24h Cache)...")
    d2_el = await _soap_post(api_key, SOAP_ACTION_SITES, _SOAP_BODY_SITES)

    pub_el = d2_el.find(_t("payloadPublication"))
    if pub_el is None:
        raise APIError("payloadPublication nicht gefunden in MeasurementSiteTable.")

    sites: dict[str, dict] = {}

    for table_el in pub_el.findall(_t("measurementSiteTable")):
        for site_el in table_el.findall(_t("measurementSiteRecord")):
            site_id = site_el.get("id", "")
            if not site_id:
                continue

            # Name
            name_el = site_el.find(_t("measurementSiteName"))
            name = _best_lang(name_el) if name_el is not None else site_id

            # Koordinaten: DATEX II nutzt WGS84 (oder ETRS89 ≈ WGS84)
            lat: float | None = None
            lon: float | None = None

            loc_el = site_el.find(_t("measurementSiteLocation"))
            if loc_el is not None:
                # Suche nach PointByCoordinates oder LocationByCoordinates
                for lat_el in loc_el.iter(_t("latitude")):
                    try:
                        lat = float(lat_el.text or "")
                        break
                    except (ValueError, TypeError):
                        pass
                for lon_el in loc_el.iter(_t("longitude")):
                    try:
                        lon = float(lon_el.text or "")
                        break
                    except (ValueError, TypeError):
                        pass

            if lat is None or lon is None:
                # Ohne Koordinaten können wir keine Geo-Suche machen
                continue

            # Supplier aus ID ableiten (Format: "CH:xxx" oder "ZH:xxx")
            supplier_code = site_id.split(":")[0] if ":" in site_id else "UNKNOWN"
            supplier_names = {
                "CH": "ASTRA (Bund)",
                "ZH": "Kanton Zürich",
                "BE": "Kanton Bern",
                "VD": "Kanton Waadt",
                "GE": "Kanton Genf",
                "BS": "Kanton Basel-Stadt",
                "SG": "Kanton St. Gallen",
            }
            supplier = supplier_names.get(supplier_code, supplier_code)

            sites[site_id] = {
                "id": site_id,
                "name": name,
                "latitude": lat,
                "longitude": lon,
                "supplier": supplier,
            }

    _sites_cache = sites
    _sites_cache_ts = now
    logger.info(f"MeasurementSiteTable geladen: {len(sites)} Messstellen mit Koordinaten.")
    return sites


# ---------------------------------------------------------------------------
# Dynamische Messdaten
# ---------------------------------------------------------------------------

async def fetch_measured_data(
    api_key: str,
    site_ids: list[str],
) -> list[dict]:
    """
    Holt Echtzeit-Verkehrsdaten für spezifische Messstellen (pullMeasuredData).

    Gecached für 60s – Daten werden minütlich aktualisiert.

    DATEX II Index-Konvention (FEDRO-Profil):
      Indices 1–9:   Leichtfahrzeuge (Klasse 1–7: Autos, Motorräder, Busse)
      Indices 11–19: Schwerverkehr (Klasse 8–10: LKW, Sattelzüge)
      Index 21+:     Sonderkategorien (Unklassifiziert, Ungültige Geschwindigkeit)

    Args:
        api_key: Bearer Token
        site_ids: Liste von Messstellen-IDs (max 50)

    Returns:
        Liste von Messdatensätzen pro Messstelle
    """
    if not site_ids:
        return []

    # Cache-Key aus sortierten Site-IDs
    cache_key = ",".join(sorted(site_ids[:50]))
    now = time.monotonic()

    if cache_key in _data_cache and (now - _data_cache_ts.get(cache_key, 0.0)) < _DATA_TTL:
        logger.debug(f"Cache HIT: traffic_data ({len(site_ids)} sites)")
        return _data_cache[cache_key]

    body = _make_data_body(site_ids)
    d2_el = await _soap_post(api_key, SOAP_ACTION_DATA, body)

    pub_el = d2_el.find(_t("payloadPublication"))
    if pub_el is None:
        raise APIError("payloadPublication nicht gefunden in MeasuredDataPublication.")

    measurements: list[dict] = []

    for sm_el in pub_el.findall(_t("siteMeasurements")):
        site_ref_el = sm_el.find(_t("measurementSiteReference"))
        if site_ref_el is None:
            continue
        site_id = site_ref_el.get("id", "")

        meas_time = _text(sm_el, "measurementTimeDefault")

        # Gesammelte Werte nach Fahrzeugklasse
        flow: dict[str, float | None] = {"light": None, "heavy": None}
        speed: dict[str, float | None] = {"light": None, "heavy": None}
        unclassified_flow: float | None = None

        for mv_outer in sm_el.findall(_t("measuredValue")):
            idx = int(mv_outer.get("index", "-1"))
            mv_inner = mv_outer.find(_t("measuredValue"))
            if mv_inner is None:
                continue
            basic_el = mv_inner.find(_t("basicData"))
            if basic_el is None:
                continue

            basic_type = basic_el.get(f"{{{_XSI}}}type", "")

            # Fahrzeugklasse aus Index ableiten (FEDRO-Konvention)
            vehicle_class: str | None = None
            if 1 <= idx <= 9:
                vehicle_class = "light"
            elif 11 <= idx <= 19:
                vehicle_class = "heavy"
            elif idx == 21:
                vehicle_class = "unclassified"

            if "TrafficFlow" in basic_type:
                vf_el = basic_el.find(_t("vehicleFlow"))
                if vf_el is not None:
                    vfr_el = vf_el.find(_t("vehicleFlowRate"))
                    if vfr_el is not None:
                        try:
                            rate = float(vfr_el.text or "")
                            if vehicle_class == "light":
                                flow["light"] = rate
                            elif vehicle_class == "heavy":
                                flow["heavy"] = rate
                            elif vehicle_class == "unclassified":
                                unclassified_flow = rate
                        except (ValueError, TypeError):
                            pass

            elif "TrafficSpeed" in basic_type:
                avs_el = basic_el.find(_t("averageVehicleSpeed"))
                if avs_el is not None:
                    s_el = avs_el.find(_t("speed"))
                    if s_el is not None:
                        try:
                            spd = float(s_el.text or "")
                            if vehicle_class == "light":
                                speed["light"] = spd
                            elif vehicle_class == "heavy":
                                speed["heavy"] = spd
                        except (ValueError, TypeError):
                            pass

        # Ergebnis aufbauen
        m: dict = {
            "site_id": site_id,
            "measurement_time": meas_time,
        }

        if flow["light"] is not None:
            m["flow_light_vehicles_per_hour"] = round(flow["light"])
        if flow["heavy"] is not None:
            m["flow_heavy_vehicles_per_hour"] = round(flow["heavy"])
        if unclassified_flow is not None:
            m["flow_unclassified_per_hour"] = round(unclassified_flow)

        # Gesamtverkehr (wenn Leicht + Schwer bekannt)
        if flow["light"] is not None and flow["heavy"] is not None:
            m["flow_total_per_hour"] = round(flow["light"] + flow["heavy"])

        if speed["light"] is not None:
            m["avg_speed_light_kmh"] = round(speed["light"], 1)
        if speed["heavy"] is not None:
            m["avg_speed_heavy_kmh"] = round(speed["heavy"], 1)

        # Nur Einträge mit Daten hinzufügen
        if any(k.startswith("flow_") for k in m):
            measurements.append(m)

    _data_cache[cache_key] = measurements
    _data_cache_ts[cache_key] = now

    return measurements


# ---------------------------------------------------------------------------
# Geo-Suche in der Messstellentabelle
# ---------------------------------------------------------------------------

def find_nearby_sites(
    sites: dict[str, dict],
    latitude: float,
    longitude: float,
    radius_km: float,
    limit: int = 20,
) -> list[dict]:
    """
    Findet Messstellen in einem Umkreis via Haversine.

    Args:
        sites: Messstellentabelle (von fetch_measurement_sites)
        latitude, longitude: Suchzentrum
        radius_km: Suchradius in km
        limit: Maximale Anzahl Resultate

    Returns:
        Liste von Messstellen, sortiert nach Distanz
    """
    results: list[tuple[float, dict]] = []

    for site in sites.values():
        dist_km = haversine_km(
            latitude, longitude,
            site["latitude"], site["longitude"],
        )
        if dist_km <= radius_km:
            enriched = {**site, "distance_km": round(dist_km, 3)}
            results.append((dist_km, enriched))

    results.sort(key=lambda x: x[0])
    return [r[1] for r in results[:limit]]
