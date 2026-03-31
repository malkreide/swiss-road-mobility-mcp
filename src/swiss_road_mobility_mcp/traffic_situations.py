"""
Traffic Situations (DATEX II) – Phase 2 Modul.

Metapher: Wenn Shared Mobility (Phase 1) zeigt WO Fahrzeuge verfügbar sind,
dann zeigt Traffic Situations WARUM die Strasse gerade gesperrt ist.
Zusammen ergibt sich: «Gibt es einen Grund, heute das Velo statt das Auto zu nehmen?»

Datenquelle: ASTRA Verkehrsdaten-Plattform (opentransportdata.swiss)
Format: DATEX II v2.3 (SOAP + XML)
API-Key: Erforderlich (kostenlos: api-manager.opentransportdata.swiss)
Update: Echtzeit (VMZ-CH, Kantonspolizeien, ASTRA-Einheiten)
Kosten: Gratis nach Registrierung (Open Government Data)
"""

import logging
import time
import xml.etree.ElementTree as ET

import httpx

from .api_infrastructure import APIError

logger = logging.getLogger("swiss-road-mobility-mcp")

# ---------------------------------------------------------------------------
# DATEX II Namespace-Konstanten
# ---------------------------------------------------------------------------

_DX2 = "http://datex2.eu/schema/2/2_0"
_SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
_XSI = "http://www.w3.org/2001/XMLSchema-instance"

SITUATIONS_URL = (
    "https://api.opentransportdata.swiss/TDP/Soap_Datex2/TrafficSituations/Pull"
)
SITUATIONS_SOAP_ACTION = (
    "http://opentransportdata.swiss/TDP/Soap_Datex2/Pull/v1/pullTrafficMessages"
)

# ---------------------------------------------------------------------------
# SOAP Request Body (immer identisch – ASTRA-Vorgabe)
# ---------------------------------------------------------------------------

_SOAP_BODY = """\
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
        <subscription>
          <operatingMode>operatingMode1</operatingMode>
          <subscriptionStartTime>2025-01-01T00:00:00+00:00</subscriptionStartTime>
          <subscriptionState>active</subscriptionState>
          <updateMethod>singleElementUpdate</updateMethod>
          <target>
            <address></address>
            <protocol>http</protocol>
          </target>
        </subscription>
      </exchange>
    </d2LogicalModel>
  </soap:Body>
</soap:Envelope>"""

# ---------------------------------------------------------------------------
# Modul-Level Cache (2 Minuten TTL für Echtzeit-Meldungen)
# ---------------------------------------------------------------------------

_cache: dict = {}
_cache_ts: float = 0.0
_CACHE_TTL = 120.0  # 2 Minuten

# ---------------------------------------------------------------------------
# Ereignis-Typ-Mapping: DATEX II xsi:type → lesbare Kategorie
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, str] = {
    "Accident": "accident",
    "ConstructionWorks": "roadwork",
    "Roadworks": "roadwork",
    "MaintenanceWorks": "roadwork",
    "RoadOrCarriagewayOrLaneManagement": "road_management",
    "TrafficCongestion": "congestion",
    "AbnormalTraffic": "abnormal_traffic",
    "ObstructionOnRoad": "obstruction",
    "AnimalPresenceObstruction": "obstruction",
    "VehicleObstruction": "obstruction",
    "GeneralObstruction": "obstruction",
    "EnvironmentalObstruction": "environmental",
    "WeatherRelatedRoadConditions": "weather",
    "PoorRoadInfrastructure": "infrastructure",
    "PublicEvent": "public_event",
    "InfrastructureDamageObstruction": "infrastructure",
    "EquipmentOrSystemFault": "infrastructure",
    "ReroutingManagement": "road_management",
    "SpeedManagement": "road_management",
}

_SEVERITY_ORDER = {
    "highest": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "lowest": 1,
    "unknown": 0,
    "": 0,
}

# ---------------------------------------------------------------------------
# XML-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _t(tag: str) -> str:
    """DATEX II vollständiger Namespace-Tag."""
    return f"{{{_DX2}}}{tag}"


def _text(el: ET.Element, *path: str) -> str:
    """
    Traversiert einen Pfad von DATEX II Kindelementen und gibt Text zurück.
    Gibt '' zurück wenn ein Schritt nicht gefunden wird.
    """
    cur = el
    for step in path:
        child = cur.find(_t(step))
        if child is None:
            return ""
        cur = child
    return (cur.text or "").strip()


def _multilang(el: ET.Element, prefer: tuple[str, ...] = ("de", "fr", "en")) -> dict[str, str]:
    """
    Extrahiert alle Sprachen aus DATEX II <values><value lang='xx'>-Struktur.
    Returns dict lang → text.
    """
    result: dict[str, str] = {}
    for v in el.iter(_t("value")):
        lang = v.get("lang", "xx")
        text = (v.text or "").strip()
        if text:
            result[lang] = text
    return result


def _best_text(texts: dict[str, str], prefer: tuple[str, ...] = ("de", "fr", "en")) -> str:
    """Gibt den besten verfügbaren Text zurück (bevorzugt Deutsch)."""
    for lang in prefer:
        if texts.get(lang):
            return texts[lang]
    return next(iter(texts.values()), "")


def _record_type(xsi_type: str) -> str:
    """DATEX II xsi:type → lesbare Kategorie."""
    bare = xsi_type.split(":")[-1] if ":" in xsi_type else xsi_type
    return _TYPE_MAP.get(bare, bare.lower())


def _parse_situation_record(rec_el: ET.Element) -> dict:
    """Parst ein einzelnes DATEX II <situationRecord>-Element."""
    raw_type = rec_el.get(f"{{{_XSI}}}type", "")
    category = _record_type(raw_type)

    # ── Validity ──────────────────────────────────────────────────────────
    validity_status = ""
    start_time = ""
    end_time = ""
    v_el = rec_el.find(_t("validity"))
    if v_el is not None:
        validity_status = _text(v_el, "validityStatus")
        ts_el = v_el.find(_t("validityTimeSpecification"))
        if ts_el is not None:
            start_time = _text(ts_el, "overallStartTime")
            end_time = _text(ts_el, "overallEndTime")

    # ── Description ───────────────────────────────────────────────────────
    # Priority: generalPublicComment > comment > cause
    descriptions: dict[str, str] = {}
    for comment_el in rec_el.findall(f".//{_t('comment')}"):
        descriptions.update(_multilang(comment_el))

    # generalPublicComment takes priority over generic comments
    gpc_el = rec_el.find(_t("generalPublicComment"))
    if gpc_el is not None:
        for c_el in gpc_el.findall(_t("comment")):
            descriptions.update(_multilang(c_el))

    description_de = _best_text(descriptions)

    # ── Road / Location hints ─────────────────────────────────────────────
    # AlertC codes are opaque without the topology table.
    # We extract any road name text we can find.
    road_refs: list[str] = []
    for road_el in rec_el.iter(_t("roadName")):
        txt = _best_text(_multilang(road_el))
        if txt:
            road_refs.append(txt)
    for loc_desc_el in rec_el.iter(_t("locationDescriptor")):
        txt = (loc_desc_el.text or "").strip()
        if txt:
            road_refs.append(txt)

    return {
        "category": category,
        "type_raw": raw_type.split(":")[-1],
        "validity_status": validity_status,
        "start_time": start_time,
        "end_time": end_time,
        "severity": _text(rec_el, "severity"),
        "creation_time": _text(rec_el, "situationRecordCreationTime"),
        "description": description_de,
        "description_multilang": descriptions,
        "road_references": list(dict.fromkeys(road_refs)),  # deduplicated
    }


def _parse_situation(sit_el: ET.Element) -> dict | None:
    """
    Parst ein DATEX II <situation>-Element.
    Returns None wenn keine Records vorhanden.
    """
    sit_id = sit_el.get("id", "unknown")
    records = [
        _parse_situation_record(rec_el)
        for rec_el in sit_el.findall(_t("situationRecord"))
    ]
    if not records:
        return None
    return {"id": sit_id, "records": records}


def _is_active(validity_status: str) -> bool:
    """True wenn ein Record noch aktiv ist (nicht widerrufen/archiviert)."""
    return validity_status.lower() not in ("revoked", "cancelled", "archived")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_situations(
    api_key: str,
    filter_type: str | None = None,
    active_only: bool = True,
    limit: int = 50,
) -> dict:
    """
    Holt aktuelle Verkehrsmeldungen von der ASTRA DATEX II API.

    Args:
        api_key: Bearer Token von api-manager.opentransportdata.swiss
        filter_type: Kategorie-Filter ('accident', 'roadwork', 'congestion',
                     'obstruction', 'weather', 'all'). Default: 'all'
        active_only: Nur aktive Meldungen (nicht widerrufene)
        limit: Maximale Anzahl Resultate (1–200)

    Returns:
        dict mit publication_time, total, situations-Liste
    """
    global _cache, _cache_ts

    # ── Cache-Prüfung ──────────────────────────────────────────────────────
    cache_key = f"{filter_type or 'all'}_{active_only}_{limit}"
    now = time.monotonic()
    if _cache and (now - _cache_ts) < _CACHE_TTL:
        if cache_key in _cache:
            logger.debug("Cache HIT: traffic_situations")
            return _cache[cache_key]

    # ── SOAP POST Request ──────────────────────────────────────────────────
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": SITUATIONS_SOAP_ACTION,
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "swiss-road-mobility-mcp/0.2.0",
        "Accept-Encoding": "gzip, deflate",
    }

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.post(
                SITUATIONS_URL,
                content=_SOAP_BODY.encode("utf-8"),
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            sc = e.response.status_code
            if sc in (401, 403):
                raise APIError(
                    f"HTTP {sc}: API-Key fehlt oder ungültig. "
                    "Kostenlose Registrierung: api-manager.opentransportdata.swiss. "
                    "Umgebungsvariable OPENTRANSPORTDATA_API_KEY setzen."
                )
            raise APIError(
                f"HTTP {sc} von TrafficSituations-API: {e.response.text[:300]}"
            )
        except httpx.TimeoutException:
            raise APIError("Timeout (30s) bei TrafficSituations-API.")
        except httpx.ConnectError as e:
            raise APIError(f"Verbindungsfehler zur TrafficSituations-API: {e}")

    # ── XML Parsing ────────────────────────────────────────────────────────
    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as e:
        raise APIError(f"DATEX II XML-Parsing-Fehler: {e}")

    body_el = root.find(f"{{{_SOAP_ENV}}}Body")
    if body_el is None:
        raise APIError("SOAP-Body nicht gefunden in Response.")

    d2_el = body_el.find(_t("d2LogicalModel"))
    if d2_el is None:
        # Sometimes d2LogicalModel is directly the body child without namespace
        d2_el = next(iter(body_el), None)
        if d2_el is None:
            raise APIError("d2LogicalModel nicht gefunden in SOAP-Body.")

    pub_el = d2_el.find(_t("payloadPublication"))
    if pub_el is None:
        raise APIError("payloadPublication nicht gefunden in d2LogicalModel.")

    pub_time = _text(pub_el, "publicationTime")

    # ── Parse und Filter ───────────────────────────────────────────────────
    situations: list[dict] = []
    total_in_feed = 0

    for sit_el in pub_el.findall(_t("situation")):
        total_in_feed += 1
        parsed = _parse_situation(sit_el)
        if parsed is None:
            continue

        records = parsed["records"]

        if active_only:
            records = [
                r for r in records if _is_active(r.get("validity_status", ""))
            ]
            if not records:
                continue

        if filter_type and filter_type != "all":
            records = [r for r in records if r.get("category") == filter_type]
            if not records:
                continue

        parsed["records"] = records

        # Sort records by severity (highest first)
        parsed["records"].sort(
            key=lambda r: _SEVERITY_ORDER.get(r.get("severity", ""), 0),
            reverse=True,
        )

        situations.append(parsed)
        if len(situations) >= limit:
            break

    # ── Cache + Rückgabe ───────────────────────────────────────────────────
    result = {
        "publication_time": pub_time,
        "total_in_feed": total_in_feed,
        "returned": len(situations),
        "filter": {
            "type": filter_type or "all",
            "active_only": active_only,
            "limit": limit,
        },
        "data_source": "ASTRA VMZ-CH via opentransportdata.swiss (DATEX II)",
        "situations": situations,
    }

    if not _cache:
        _cache = {}
    _cache[cache_key] = result
    _cache_ts = now

    return result
