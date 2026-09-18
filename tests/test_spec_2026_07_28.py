"""Der Server bedient Spec `2026-07-28` — gemessen auf dem Draht, nicht behauptet.

`tests/test_protocol_version.py` pinnt die beiden Revisionen gegen die
SDK-Konstanten und sagt selbst, wo es aufhoert: «dieses Repo baut keine
ASGI-App, durch die sich ein `initialize` schicken liesse». Genau diese Luecke
hat eine Zusicherung getragen, die nicht stimmte.

`mcp` 2.x bedient zwei Aeren, aber nicht ueber denselben Transport. Die moderne
Einzelaustausch-Zustellung liegt in `mcp/server/_streamable_http_modern.py` und
ist nur ueber `StreamableHTTPSessionManager.handle_request` erreichbar — also
ueber `streamable_http_app`. Ausgeliefert wurde bis zu diesem Stand `sse_app`:
`MCP_TRANSPORT=sse`, und Dockerfile, `docker-compose.yml` und `render.yaml`
setzten es alle drei. Sie fahren jetzt `http`; `sse` bleibt waehlbar.

Der Befund, der das sichtbar gemacht hat — derselbe `tools/list`-Umschlag mit
`io.modelcontextprotocol/protocolVersion: 2026-07-28`, gemessen am 18.9.2026:

    POST /messages/  (SSE)              -> HTTP 400  «session_id is required»
    POST /mcp        (Streamable HTTP)  -> HTTP 200  15 Tools, resultType=complete

Die SSE-Antwort ist kein Zufall und kein Konfigurationsfehler: eine moderne
Anfrage ist sessionlos und in sich geschlossen, der SSE-Transport verlangt eine
Session. Die Aera ist ihm strukturell nicht zugaenglich.

Damit lief auch die `cache_hints`-Arbeit des Servers (SEP-2549) ins Leere:
`ttlMs` und `cacheScope` sind Felder der modernen Antwort. Konfiguriert waren
sie, auf den Draht kamen sie nie — und `tests/test_cache_hints.py` konnte das
nicht bemerken, weil es die Konfiguration prueft und nicht die Antwort.

Jede Zusicherung hier faehrt deshalb eine echte HTTP-Anfrage gegen die
zusammengebaute App. Die Gegenprobe steht daneben: dieselbe Anfrage gegen SSE
muss scheitern, sonst misst der Test die Aera nicht, sondern nur, dass
irgendeine App irgendetwas antwortet.
"""

from __future__ import annotations

import warnings

import pytest
from starlette.testclient import TestClient

pytest.importorskip("mcp")

from mcp_types import (  # noqa: E402
    CLIENT_CAPABILITIES_META_KEY,
    HEADER_MISMATCH,
    PROTOCOL_VERSION_META_KEY,
)
from mcp_types.version import LATEST_MODERN_VERSION  # noqa: E402

from swiss_road_mobility_mcp import __version__  # noqa: E402
from swiss_road_mobility_mcp.server import (  # noqa: E402
    CACHE_HINTS,
    LIST_CACHE_TTL_MS,
    build_http_app,
    build_sse_app,
)

# `build_http_app()` ohne Argumente leitet die Host-Freigabeliste aus
# `127.0.0.1:8000` ab (siehe `build_transport_security`). Der TestClient meldet
# sich per Default als `testserver` und liefe in HTTP 421 — die Basis-URL ist
# hier also Teil des Aufbaus und keine Kosmetik.
BASE_URL = "http://127.0.0.1:8000"

MODERN_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def envelope(method: str) -> dict:
    """Ein vollstaendiger 2026-07-28-Umschlag.

    Die beiden `_meta`-Schluessel sind Pflicht: `classify_inbound_request`
    weist eine Anfrage ohne sie mit INVALID_PARAMS ab, bevor die Methode
    ueberhaupt geroutet wird.
    """
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": {
            "_meta": {
                PROTOCOL_VERSION_META_KEY: LATEST_MODERN_VERSION,
                CLIENT_CAPABILITIES_META_KEY: {},
            }
        },
    }


DATA_SOURCES_URI = "roadmobility://data-sources"


def resource_envelope() -> dict:
    """Ein `resources/read`-Umschlag auf die statische Quellenliste.

    Bewusst diese Ressource: sie wird im Prozess erzeugt und fasst kein Netz
    an, der Test bleibt also offline-deterministisch.
    """
    body = envelope("resources/read")
    body["params"]["uri"] = DATA_SOURCES_URI
    return body


def read_resource(client: TestClient):
    return client.post(
        "/mcp",
        json=resource_envelope(),
        headers={
            **MODERN_HEADERS,
            "Mcp-Protocol-Version": LATEST_MODERN_VERSION,
            "Mcp-Method": "resources/read",
            "Mcp-Name": DATA_SOURCES_URI,
        },
    )


def post_modern(client: TestClient, method: str, path: str = "/mcp"):
    return client.post(
        path,
        json=envelope(method),
        headers={
            **MODERN_HEADERS,
            "Mcp-Protocol-Version": LATEST_MODERN_VERSION,
            "Mcp-Method": method,
        },
    )


@pytest.fixture
def http_client(monkeypatch: pytest.MonkeyPatch):
    """Die gehaertete Streamable-HTTP-App, mit laufender Lifespan.

    Der `with`-Block ist nicht optional: die Lifespan startet den
    StreamableHTTP-Session-Manager. Ohne ihn antwortet `/mcp` nicht.
    """
    for var in ("MCP_ALLOWED_HOSTS", "ALLOWED_ORIGINS", "MCP_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    with TestClient(build_http_app(), base_url=BASE_URL) as client:
        yield client


# ── Die Aera selbst ────────────────────────────────────────────────────────


def test_die_moderne_revision_wird_ueber_streamable_http_bedient(http_client: TestClient) -> None:
    """Der lasttragende Test: eine 2026-07-28-Anfrage bekommt eine Antwort."""
    resp = post_modern(http_client, "tools/list")
    assert resp.status_code == 200, resp.text
    result = resp.json()["result"]
    assert len(result["tools"]) == 15


def test_der_sse_transport_kann_die_moderne_revision_nicht(monkeypatch: pytest.MonkeyPatch) -> None:
    """Die Gegenprobe zum Test darueber.

    Ohne sie waere der Test oben auch dann gruen, wenn beide Transporte die
    Anfrage bedienten — er koennte dann nicht zeigen, dass der Wechsel auf
    Streamable HTTP ueberhaupt etwas bewirkt hat.

    Gemessen wird der Statuscode, nicht der Text: dass die Ablehnung heute
    «session_id is required» lautet, ist eine Formulierung des SDK und keine
    Zusicherung, an die sich dieser Test binden sollte.
    """
    for var in ("MCP_ALLOWED_HOSTS", "ALLOWED_ORIGINS", "MCP_AUTH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    with TestClient(build_sse_app(), base_url=BASE_URL) as client:
        resp = post_modern(client, "tools/list", path="/messages/")
    assert resp.status_code != 200, "SSE beantwortet eine moderne Anfrage — die Aufteilung oben stimmt nicht mehr"


def test_die_antwort_traegt_den_pflicht_resultType(http_client: TestClient) -> None:
    """`Result.resultType` ist bei 2026-07-28 Pflicht (SDK: `runner.py`).

    Das SDK setzt es selbst; der Test haelt fest, dass es auf dem Draht
    ankommt — und faellt, wenn der Server je auf einen Transport zurueckfaellt,
    der die moderne Antwortform nicht erzeugt.
    """
    assert post_modern(http_client, "tools/list").json()["result"]["resultType"] == "complete"


# ── SEP-2549: die Cache-Hinweise, jetzt nachweisbar ────────────────────────


@pytest.mark.parametrize("method", ["tools/list", "prompts/list", "resources/list"])
def test_die_cache_hints_stehen_auf_dem_draht(http_client: TestClient, method: str) -> None:
    """Was `test_cache_hints.py` nur konfiguriert sehen konnte.

    Dort wird `CACHE_HINTS` gelesen. Hier wird gemessen, was der Client
    bekommt. Der Unterschied war genau der Fehler: die Konfiguration war die
    ganze Zeit richtig und kam nie an.
    """
    result = post_modern(http_client, method).json()["result"]
    assert result["ttlMs"] == LIST_CACHE_TTL_MS
    assert result["cacheScope"] == CACHE_HINTS[method].scope == "public"


def test_eine_nicht_cachebare_methode_bekommt_den_strengen_default(http_client: TestClient) -> None:
    """Negativkontrolle zum Test darueber.

    Ohne sie waeren die Zusicherungen oben auch gegen einen Server gruen, der
    jeder Antwort dieselben Felder anhaengt — dann pruefte der Test einen
    Default und nicht die Konfiguration.

    `resources/read` steht bewusst nicht in `CACHE_HINTS`: ein Hinweis dort
    waere eine Zusicherung ueber den INHALT statt ueber das Verzeichnis. Die
    Antwort belegt zugleich, was der Kommentar an `CACHE_HINTS` behauptet —
    ohne Konfiguration ist der Default `ttlMs: 0` / `cacheScope: private`,
    also «sofort veraltet, nie geteilt» und eben nicht neutral.
    """
    assert "resources/read" not in CACHE_HINTS
    result = read_resource(http_client).json()["result"]
    assert result["ttlMs"] == 0
    assert result["cacheScope"] == "private"


def test_ein_falscher_routing_header_wird_abgewiesen(http_client: TestClient) -> None:
    """`Mcp-Name` ist bei 2026-07-28 nicht dekorativ.

    `mcp.shared.inbound.NAME_BEARING_METHODS` bindet `resources/read` an den
    `uri`-Parameter: weicht der Header vom Rumpf ab, endet die Anfrage mit
    HEADER_MISMATCH, bevor irgendein Handler laeuft.

    `test_cors.py` zeigt, dass der Header den Preflight passiert. Hier steht
    daneben, warum das zaehlt — ein Browser, der ihn nicht senden darf, kommt
    an dieser Pruefung nicht vorbei.
    """
    resp = http_client.post(
        "/mcp",
        json=resource_envelope(),
        headers={
            **MODERN_HEADERS,
            "Mcp-Protocol-Version": LATEST_MODERN_VERSION,
            "Mcp-Method": "resources/read",
            "Mcp-Name": "roadmobility://etwas-anderes",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == HEADER_MISMATCH


# ── serverInfo ─────────────────────────────────────────────────────────────


def test_serverinfo_nennt_die_paketversion(http_client: TestClient) -> None:
    """Bei 2026-07-28 reitet `serverInfo` im `_meta` JEDER Antwort.

    Der SDK-Default fuer `MCPServer(version=...)` ist der leere String. Gemessen
    am 18.9.2026 meldete der Server `version: ""` — bei jedem Aufruf, nicht nur
    im Handshake. Der leere String ist hier die eigentliche Zusicherung: ein
    Vergleich allein gegen `__version__` waere auch dann gruen, wenn beide
    Seiten leer waeren.
    """
    meta = post_modern(http_client, "tools/list").json()["result"]["_meta"]
    info = meta["io.modelcontextprotocol/serverInfo"]
    assert info["version"] == __version__
    assert info["version"] != ""
    assert info["name"] == "swiss_road_mobility_mcp"


# ── Die Alt-Aera bricht nicht weg ──────────────────────────────────────────


def test_die_alt_aera_routen_laufen_daneben_weiter(http_client: TestClient) -> None:
    """Der neue Transport loest den alten nicht ab, er tritt daneben.

    Ein bestehender SSE-Client soll nicht deshalb wegbrechen, weil der Server
    die neue Revision zusaetzlich kann. Geprueft an den Routen der
    zusammengesetzten App.
    """
    pfade = {r.path for r in http_client.app.router.routes if hasattr(r, "path")}
    assert {"/mcp", "/sse", "/messages"} <= pfade, pfade


# ── Haertung gilt auch fuer den neuen Endpunkt ─────────────────────────────


def test_der_neue_endpunkt_steht_hinter_der_bearer_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ein neuer Transport darf die Auth-Schicht nicht umgehen.

    Der gefaehrliche Ausgang eines solchen Umbaus ist nicht ein roter Test,
    sondern ein zweiter, offener Endpunkt neben einem geschuetzten. `_harden`
    ist die gemeinsame Quelle; dieser Test haelt fest, dass der HTTP-Pfad sie
    wirklich durchlaeuft.
    """
    monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("MCP_AUTH_TOKEN", "geheim")
    with TestClient(build_http_app(), base_url=BASE_URL) as client:
        assert post_modern(client, "tools/list").status_code == 401
        mit_token = client.post(
            "/mcp",
            json=envelope("tools/list"),
            headers={
                **MODERN_HEADERS,
                "Mcp-Protocol-Version": LATEST_MODERN_VERSION,
                "Mcp-Method": "tools/list",
                "Authorization": "Bearer geheim",
            },
        )
    assert mit_token.status_code == 200, mit_token.text


def test_die_middleware_reihenfolge_gilt_auch_hier(http_client: TestClient) -> None:
    """Dieselbe Reihenfolge wie im SSE-Pfad: CORS -> RateLimit -> BearerAuth."""
    namen = [m.cls.__name__ for m in http_client.app.user_middleware]
    assert namen[:3] == ["CORSMiddleware", "RateLimitMiddleware", "BearerAuthMiddleware"], namen


# ── SEP-2577: keine abgekuendigte Faehigkeit mehr ──────────────────────────


async def test_kein_werkzeug_ruft_eine_abgekuendigte_faehigkeit() -> None:
    """`2026-07-28` kuendigt Logging, Sampling und Roots ab (SEP-2577).

    Der Server rief `ctx.info` — fuenfmal. Das ist nicht nur ein Warnhinweis:
    bei 2026-07-28 ist die Zustellung ein Opt-in pro Anfrage
    (`io.modelcontextprotocol/logLevel`), und fehlt der Schluessel, DARF der
    Server nichts senden (`mcp/server/connection.py::allowed_log_levels`). Die
    Zeilen waren dort also wirkungslos und trugen die Meldung trotzdem.

    Gemessen an einem echten Werkzeugaufruf durch eine Session, nicht am
    Quelltext: ein `grep` nach `ctx.info` wuerde einen Aufruf ueber einen Alias
    oder aus einem Hilfsmodul nicht sehen.
    """
    import respx
    from mcp.client import Client as connect
    from mcp.shared.exceptions import MCPDeprecationWarning

    from swiss_road_mobility_mcp import ev_charging, server

    with warnings.catch_warnings(record=True) as gesammelt:
        warnings.simplefilter("always")
        with respx.mock:
            respx.get(ev_charging.GEOJSON_URL).respond(
                200, json={"features": [{"id": "st1", "geometry": {"coordinates": [8.54, 47.37]}, "properties": {}}]}
            )
            respx.get(ev_charging.STATUS_URL).respond(
                200, json={"EVSEStatuses": [{"EVSEStatusRecord": [{"EvseID": "st1", "EVSEStatus": "Available"}]}]}
            )
            async with connect(server.mcp) as client:
                await client.call_tool(
                    "road_find_charger",
                    {"params": {"latitude": 47.37, "longitude": 8.54, "radius_km": 2.0}},
                )
                await client.call_tool("road_check_status", {})

    abgekuendigt = [str(w.message) for w in gesammelt if issubclass(w.category, MCPDeprecationWarning)]
    assert not abgekuendigt, abgekuendigt
