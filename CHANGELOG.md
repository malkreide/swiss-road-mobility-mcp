# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] - 2026-09-26

Erste Fassung, die Spec `2026-07-28` tatsächlich bedient — bis hierher war der
Server darauf gepinnt und dokumentiert, konnte die Revision über den
ausgelieferten Transport aber nicht sprechen. Enthält ausserdem zwei
Verschärfungen an der Browser-Schnittstelle, die vor dem Upgrade zu lesen sind.

> **Upgrade-Hinweis.** Zwei Punkte brechen bestehende Konfigurationen:
> `ALLOWED_ORIGINS` ist jetzt fail-closed — nicht gesetzt heisst **kein**
> Cross-Origin-Zugriff, wo vorher ungefragt jede Website durchkam (wer den
> alten Zustand will, setzt `ALLOWED_ORIGINS=*`; für claude.ai im Browser
> `ALLOWED_ORIGINS=https://claude.ai`). Und der empfohlene HTTP-Endpunkt ist
> neu `/mcp` statt `/sse`; die SSE-Routen bleiben erreichbar, die Container
> fahren aber `MCP_TRANSPORT=http`. stdio-Clients sind von beidem unberührt.

### Hinzugefügt

- **Streamable HTTP als Transport (`MCP_TRANSPORT=http`) — der Weg zu Spec
  `2026-07-28`.** Der Server bedient die moderne Revision jetzt auf dem Draht
  und nicht nur laut Konstante. Endpunkt `/mcp`; die SSE-Routen (`/sse`,
  `/messages/`) laufen **daneben** weiter, statt abgelöst zu werden, damit kein
  bestehender Client wegbricht. Dieselbe Härtung wie der SSE-Pfad: CORS →
  RateLimit → BearerAuth, jetzt aus der gemeinsamen Quelle `_harden` statt aus
  einer Kopie je Transport.

  `Dockerfile`, `docker-compose.yml` und `render.yaml` fahren `http`. `sse`
  bleibt wählbar und unverändert.

- **`tests/test_spec_2026_07_28.py`** — 13 Zusicherungen, die eine echte
  HTTP-Anfrage gegen die zusammengebaute App fahren, statt Konstanten zu lesen.

### Behoben

- **Der ausgelieferte Transport konnte `2026-07-28` gar nicht.** Beide READMEs
  sagten, der Server bediene «zwei Protokoll-Aeren über denselben Endpunkt».
  Das stimmte nicht, und nichts konnte es bemerken: die moderne
  Einzelaustausch-Zustellung (`mcp/server/_streamable_http_modern.py`) hängt an
  `StreamableHTTPSessionManager.handle_request` und ist nur über
  `streamable_http_app` erreichbar. Ausgeliefert wurde `sse_app`.

  Gemessen am 18.9.2026, derselbe `tools/list`-Umschlag mit
  `io.modelcontextprotocol/protocolVersion: 2026-07-28`:

  ```
  POST /messages/  (SSE)              -> HTTP 400  «session_id is required»
  POST /mcp        (Streamable HTTP)  -> HTTP 200  15 Tools, resultType=complete
  ```

  Die SSE-Antwort ist kein Konfigurationsfehler: eine moderne Anfrage ist
  sessionlos und in sich geschlossen, der Transport verlangt eine Session. Die
  Aera ist ihm strukturell nicht zugänglich.

- **Die `cache_hints` (SEP-2549) kamen nie beim Client an.** `ttlMs` und
  `cacheScope` sind Felder der *modernen* Antwort — konfiguriert waren sie seit
  je, erzeugen konnte sie der ausgelieferte Transport nicht.
  `tests/test_cache_hints.py` prüft die Konfiguration und konnte das deshalb
  nicht sehen. Jetzt auf dem Draht nachgewiesen (`ttlMs: 300000`,
  `cacheScope: public`), mit `resources/read` als Negativkontrolle: nicht
  konfiguriert heisst `ttlMs: 0` / `cacheScope: private`, also «sofort veraltet,
  nie geteilt» und eben nicht neutral.

- **`serverInfo` meldete `version: ""` — bei jedem Aufruf.** Bei `2026-07-28`
  reitet `serverInfo` im `_meta` jeder Antwort, nicht mehr nur im
  `initialize`-Ergebnis. `MCPServer(version=...)` hat als SDK-Default den leeren
  String, und gesetzt wurde er nie. Jetzt `version=__version__` aus den
  Distributionsmetadaten — kein Literal, `scripts/check_version_sync.py` bleibt
  erfüllt.

- **SEP-2577: fünf Aufrufe einer abgekündigten Fähigkeit entfernt.**
  `2026-07-28` kündigt Logging, Sampling und Roots ab; der Server rief
  `ctx.info` fünfmal. Das war nicht nur ein Warnhinweis: bei dieser Revision ist
  die Zustellung ein Opt-in pro Anfrage
  (`io.modelcontextprotocol/logLevel`), und fehlt der Schlüssel, **darf** der
  Server nichts senden (`connection.py::allowed_log_levels`). Die Zeilen waren
  also wirkungslos und trugen die Meldung trotzdem. Ersetzt durch
  serverseitiges `logger.info` — die Zählwerte standen ohnehin im
  Werkzeugergebnis. `ctx.report_progress` bleibt: Server→Client-Progress ist
  **nicht** abgekündigt, nur der Client→Server-Weg.

### Geändert

- **`.env.example` behauptete weiter den Wildcard-Default.** Die Umstellung auf
  fail-closed korrigierte `README.md` und `README.de.md`, übersah aber diese
  dritte Kopie: dort stand weiterhin `Unset = wildcard "*"`, und die Zeile war
  auskommentiert. Wer die Datei kopierte, sperrte damit jeden Browser-Client
  aus und fand den Grund an der Stelle, an der er nachsah, falsch beschrieben.
  Die Variable ist jetzt gesetzt statt auskommentiert.

- **`test_wildcard_cors_default_is_not_copied` prüfte nichts mehr.** Die
  autouse-Fixture löscht `ALLOWED_ORIGINS`; seit dem leeren Default war die
  Liste damit leer und `"*" not in []` trivial wahr. Nachgemessen: den
  `if o != "*"`-Filter zu entfernen liess die Datei 13/13 grün. Der Test setzt
  die Wildcard jetzt selbst — und prüft mit einer zweiten Zusicherung, dass die
  echte Origin daneben durchkommt, sonst wäre er auch gegen einen Filter grün,
  der alles wegwirft.

### Geändert

- **BRECHEND: `allow_origins` las `allowed or ["*"]`.** Die Variable
  `ALLOWED_ORIGINS` nicht zu setzen hiess damit nicht «keine Browser-Clients»,
  sondern *jede* Website im Netz — ein Fallback ist kein Default, den jemand
  gewählt hat, sondern einer, den er ungefragt geerbt hat.

  Gemessen vorher am zusammengebauten ASGI-Stack: ein Preflight von
  `https://evil.example` bekam dasselbe `Access-Control-Allow-Origin: *` wie
  `https://client.example`. Danach ohne Konfiguration gar kein
  `Access-Control-Allow-Origin` mehr.

  Die Wildcard bleibt erreichbar, muss aber verlangt werden, und der Server
  protokolliert sie dann als Warnung; ein leerer Wert wird als `info` vermerkt.

  **Wer den bisherigen Zustand behalten will, setzt `ALLOWED_ORIGINS=*`;** für
  claude.ai im Browser `ALLOWED_ORIGINS=https://claude.ai`. stdio- und
  Nicht-Browser-Clients sind unberührt — CORS regelt ausschliesslich Browser.

  CORS-Schicht und Transportprüfung lesen die Origins jetzt aus derselben
  Funktion `configured_origins()`. Vorher waren es zwei getrennte
  `os.environ.get`-Aufrufe derselben Variablen, die auseinanderlaufen konnten,
  ohne dass etwas rot wird.

### Behoben

- **Browser-Clients scheiterten am Preflight.** Spec `2026-07-28` routet eine
  Anfrage über `Mcp-Method`, `Mcp-Name` und `Mcp-Protocol-Version`; die
  CORS-Freigabeliste nannte keinen davon, dafür mit `Mcp-Session-Id` den
  Session-Header, der für sich genommen keine Anfrage routet. Ein Browser darf
  einen nicht safelisteten Header nicht senden, wenn der Server ihn nicht
  nennt: die Anfrage starb vor dem ersten MCP-Byte, während stdio und Python
  weiterliefen. Deshalb war nichts rot.

### Hinzugefügt

- **`build_sse_app()`**, herausgezogen aus `_run_sse`, damit die CORS-Schicht
  prüfbar ist. Die Middleware-Reihenfolge bleibt unverändert — CORS aussen,
  dann RateLimit, dann BearerAuth —, und ein Test misst sie nach, statt sie zu
  unterstellen. Der Fallback auf `mcp.run(transport="sse")` bei einem
  SDK-Bruch bleibt in `_run_sse`.

- **Frischehinweise auf den auflistenden Methoden** (SEP-2549, Spec
  `2026-07-28`): `tools/list`, `resources/list`, `resources/templates/list`,
  `prompts/list` und `server/discover` antworten mit `ttlMs` 300000 und
  `cacheScope` `public`. `resources/read` und `prompts/get` bleiben ohne
  Hinweis: das wäre eine Zusicherung über den Inhalt statt über das Verzeichnis.

- **Protokoll-Gate: beide Spec-Aeren gepinnt und geprueft**
  (`tests/test_protocol_version.py`). `mcp` 2.x bedient zwei Aeren ueber
  denselben Server — den `initialize`-Handshake, der bei `2025-11-25`
  deckelt, und den Pro-Request-Envelope, der `2026-07-28` erreicht.
  `LATEST_PROTOCOL_VERSION` ist ein Alias auf die **moderne** Aera; wer nur
  dagegen pinnt, laesst genau die Aera frei wandern, die heutige Clients
  aushandeln. Beide sind jetzt einzeln gepinnt, ein Dependabot-Bump von
  `mcp` kann keine davon still verschieben.

  Ohne gemessenen Teil: dieser Server baut keine ASGI-App, durch die sich ein
  `initialize` schicken liesse. Das Gate haengt deshalb an den SDK-Konstanten —
  die schwaechere Form, im Docstring benannt statt verschwiegen.

  Beide READMEs beschreiben die Aeren; ein Test haelt jede Sprache einzeln
  dagegen — im Portfolio sind EN und DE desselben Repos schon dreimal
  auseinandergelaufen, weil nur eine Fassung nachgezogen wurde.

- **`Mcp-Session-Id` ist weiterhin freigegeben — und das steht jetzt in einem
  Test statt in einem Satz.** Der Docstring von `tests/test_cors.py` nannte den
  Header die Spur einer Mechanik, die `2026-07-28` abgeschafft habe. Das stimmt
  nicht: `mcp` 2.x bedient beide Protokoll-Aeren, die Session gehoert zur
  Handshake-Aera, und der Server gibt den Header nicht ohne Grund auch in
  `expose_headers` frei.

  Nachgemessen statt aus Spec-Text geschlossen: `MCP_SESSION_ID_HEADER` steht
  unveraendert in `mcp/server/streamable_http.py`, und ein echter `initialize`
  durch den zusammengebauten ASGI-Stack bekommt eine Session-ID im
  Antwort-Header zurueck.

  `test_der_session_header_ist_weiterhin_freigegeben` haelt beides fest. Die
  Gegenprobe zeigt, dass es die Luecke wirklich gab: nimmt man den Header aus
  der Freigabeliste, faellt genau dieser eine Test, und die sieben bestehenden
  bleiben gruen.

### Behoben / Fixed

- **Die Pruefsummen im Fixture-Nachweis waren Zierde.** `PROVENANCE.md` fuehrt
  je Datei einen SHA-256 — um genau einen Fall zu fangen: eine Aufzeichnung,
  die nach dem Lauf von Hand nachgebessert wurde. Eine korrigierte Antwort ist
  wieder eine erfundene, und von aussen ist ihr das nicht anzusehen.
  Nachgerechnet hat sie kein Test. `test_die_pruefsumme_im_nachweis_stimmt`
  tut es jetzt, ueber die Bytes auf der Platte statt ueber den Loader — genau
  die hat der Recorder gehasht.

- **Das Rate-Limit-Tor war ungeprüft — beide Zweige.** `test_unit.py` prüfte
  den `RateLimiter` als Objekt (`can_proceed()`, `wait_time()`), nie aber, was
  `MobilityHTTPClient.get_json` damit macht. Eine Coverage-Messung wies die
  Zeilen der Entscheidung «warten oder absagen» als nicht durchlaufen aus:
  weder das Warten unter der Grenze noch die Absage darüber.

  Schreibbar waren die Tests vorher auch nicht. Das Warten lag als
  `import asyncio; await asyncio.sleep(wait)` direkt in der Funktion — ohne
  Namen, den ein Test übernehmen kann. Wer es doch versuchte, hätte
  `api_infrastructure.asyncio.sleep` gesetzt und damit `asyncio.sleep` im
  ganzen Prozess ersetzt (`.asyncio` **ist** das stdlib-Modul), oder er hätte
  bis zu zehn Sekunden echt gewartet. Das Warten heisst jetzt `_sleep` — die
  Portfolio-Konvention aus `CLAUDE.md` Teil 1 —, und der Import steht oben
  statt in der Schleife.

  Die Grenze heisst jetzt `MAX_RATE_LIMIT_WAIT` statt einer nackten `10` in der
  Bedingung: ein Test darüber hätte die Zahl sonst ein zweites Mal hinschreiben
  müssen und damit sich selbst zugestimmt.

  Drei neue Tests. Der über die Absage prüft, dass sie **vor** dem Warten
  fällt — erst warten und dann absagen wäre das Schlechteste aus beidem, und
  eine Prüfung, die nur `APIError` erwartet, kann die Reihenfolge nicht sehen.
  Deckung von `api_infrastructure.py`: 87 % → 91 %.

- **Der Fixture-Nachweis wies jede gekürzte Aufzeichnung als vollständig aus.**
  `_kuerze` gab seine Zähler als `return vorher, nachher, geh(daten)` zurück.
  Python wertet von links nach rechts aus und liest die beiden Zahlen, **bevor**
  `geh` sie hochzählt — sie waren immer `(0, 0)`. Über jeder gekürzten Datei
  stand «ungekuerzt»; sieben der zehn Aufzeichnungen sind es, die grösste stammt
  aus 26 MB Rohantwort und trägt davon 95 Einträge. Die Fixtures sind neu
  aufgezeichnet, damit die Zahlen aus einem echten Lauf stammen, und
  `test_der_nachweis_meldet_was_gekuerzt_wurde` fällt, wenn die Zähler wieder
  blind werden.

### Hinzugefügt / Added

- **Aufgezeichnete Fixtures** in `tests/fixtures/` — zehn echte Antworten, eine
  je Abfrageform (acht Hosts, aber mehr Abfrageformen als Hosts). Herkunft,
  Datum, Auswahlregel und SHA-256 je Datei in `tests/fixtures/PROVENANCE.md`,
  neu aufzeichnen mit `scripts/record_fixtures.py`, geladen über
  `tests/fixture_data.py`. Portfolio-Konvention, gleich wie in `meteoswiss-mcp`
  und `swiss-statistics-mcp`.

  Zugeordnet wird beim Abspielen nach der **Anfrage** und nicht nach der
  Reihenfolge: `road_mobility_snapshot` fragt mehrere Quellen in einem Aufruf
  ab. Die Anbieterliste bleibt ungekürzt — das Werkzeug listet den Markt,
  gekürzt log es.

  **Zwei Nahtstellen, nicht eine.** Die Sharing- und Ladewerkzeuge nehmen den
  gepoolten `MobilityHTTPClient`; `geo_admin`, `multimodal` und die
  Verkehrsmodule bauen sich ihren eigenen Client über `egress.async_client()`.
  Wer beim Aufzeichnen nur `build_client` abfängt, bekommt für die zweite
  Hälfte «hat keine Anfrage abgeschickt» statt einer Aufzeichnung — genau so
  ist es beim ersten Lauf passiert. Der Recorder fängt jetzt beide ab, und
  `test_die_geokodierung_geht_an_die_andere_nahtstelle` hält das fest.

### Bekannt / Known

- **Zwei Werkzeuge haben keine Aufzeichnung, und beide Gründe stehen im
  Nachweis.** `road_traffic_situations` verlangt `OPENTRANSPORTDATA_API_KEY`.
  Und `data.opentransportdata.swiss` — die Quelle von `road_park_rail` —
  antwortet diesem Anschluss auf **jede** Anfrage mit einem nginx-403, auch auf
  `/api/3/action/site_read`. Das ist eine Sperre gegen Rechenzentrums-IPs und
  **kein Befund über das Werkzeug**; ohne Verifikation von einem normalen
  Anschluss aus wird darauf nichts gebaut, weder eine Fixture noch eine
  Behauptung. `test_die_luecken_stehen_im_nachweis` sorgt dafür, dass die Lücke
  sichtbar bleibt statt zu verschwinden.


## [0.5.4] - 2026-07-31

### Fixed

- **Der gehärtete SSE-Pfad wies unter jedem echten Hostnamen mit 421 ab
  (SEC-005).** `_run_sse()` baute die App mit `mcp.sse_app()` ohne `host`. Unter
  mcp 2.x ist das kein neutraler Default: das SDK leitet daraus seine
  Host-Allow-List ab und aktiviert bei loopback-artigem Wert automatisch
  `127.0.0.1:*`. Da der Default `127.0.0.1` ist, traf das genau das
  `MCP_HOST=0.0.0.0`-Deployment aus Dockerfile und render.yaml.

  Der Server hat **zwei** SSE-Pfade, und nur einer war betroffen: der
  Fallback `mcp.run(transport="sse", host=…)` gibt den Bind weiter, dort sah das
  SDK die echte Adresse. Betroffen war der gehärtete Pfad — also der, der
  ausgeliefert wird.

  Der Bind reist jetzt mit, und eine echte Allow-List entsteht aus dem neuen
  `MCP_ALLOWED_HOSTS`. Ohne diese Variable bleibt der Schutz auf einem
  Nicht-Loopback-Bind bewusst aus und der Aufrufer warnt.

  Das ist unabhängig von `MCP_AUTH_TOKEN`: die Bearer-Prüfung sagt, *wer* fragt,
  die Host-Prüfung, *unter welchem Namen* der Server angesprochen wird. Ein
  Rebinding-Angriff bringt ein gültiges Token per Konstruktion mit.

- **Der `except Exception`-Fallback ist jetzt im Test sichtbar.** Er verwirft
  bei jedem Fehler im gehärteten Aufbau still Auth, Rate-Limit *und*
  Allow-List. Ein Test hält fest, dass der gehärtete Pfad wirklich genommen
  wird; eine Fixture patcht `mcp.run`, damit ein Fallback im Test nicht einen
  echten Server startet. Ohne das liess ein Mutationstest die Suite *hängen*
  statt sie scheitern zu lassen — nachgemessen und behoben.

  13 neue Tests, darunter der tragende Fall „richtiger Hostname, falscher Port".
  Der Positivfall wird bewusst an der Verdrahtung geprüft statt end-to-end: ein
  erlaubter Host öffnet einen endlosen Event-Stream, auf den der TestClient
  wartet. Mutationsgetestet in beide Richtungen.

  Geprüft mit den wörtlichen CI-Kommandos: 102 passed / 27 deselected,
  `ruff check src/` clean, Versions-Sync OK.


### Fixed
- **User-Agent no longer reports a stale version.** `__version__` was a
  hand-maintained literal in `__init__.py` that nothing forced anyone to bump.
  It sat at `0.5.0` while the package had moved on to `0.5.3`, so every outbound
  request advertised a version three patch releases old to GBFS operators, the
  EV charging feeds and DATEX II. It is now read from the installed
  distribution metadata (`importlib.metadata`), which is generated from
  `pyproject.toml` — a value nobody has to remember to bump cannot go stale.
  Running from a bare source checkout yields `0.0.0+source` rather than a
  plausible-looking wrong number. Guarded by `tests/test_version.py`.

## [0.5.0] - 2026-06-03

Security-, observability- and SDK-maturity hardening release implementing the
full remediation of the 2026-06-03 audit (29 non-pass findings → 25 resolved,
4 documented out-of-scope; **`production_ready: YES`**). Tool inputs/outputs stay
backward compatible — JSON text is preserved, structured output is added.

### Added
- **SSE authentication & rate limiting** (SEC-009): optional `MCP_AUTH_TOKEN` Bearer gate + per-IP sliding-window limiter (`security.py`).
- **Outbound egress allow-list** (SEC-004/021) enforced per request incl. redirect hops, plus a **resolved-IP guard** rejecting non-public IPs (SEC-005) (`egress.py`).
- **Structured logging** with optional JSON formatter to stderr (OBS-003/004) via `MCP_LOG_FORMAT` / `MCP_LOG_LEVEL`.
- **OpenTelemetry tracing** (OBS-006, optional `tracing` extra): httpx auto-instrumentation + SSE ASGI spans.
- **Lifespan-managed shared HTTP client** (SDK-001); **`Context` progress/logging** in multi-step tools (SDK-003).
- **Structured tool outputs**: tools return `dict` → `outputSchema` + `structuredContent` (SDK-002).
- **MCP Resource** `roadmobility://data-sources` + **Prompt** `plan_trip` (ARCH-008); `<use_case>` tags (ARCH-002).
- **Tests + CI**: respx-mocked offline unit tests, `live` marker, in-memory MCP-session E2E tests; CI runs `pytest -m "not live"` (OPS-001); nightly live-test workflow.
- **Docs**: `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/OPERATIONS.md`; `docker-compose.yml` with resource limits (SCALE-006); `.github/dependabot.yml` (ARCH-012); `.env.example`.

### Changed
- **Default SSE bind is now `127.0.0.1`** (was `0.0.0.0`; `0.0.0.0` only inside a container) (SEC-016).
- **CORS** exposes `Mcp-Session-Id` for browser clients (SDK-004).
- **Input validation** hardened with Pydantic `strict=True` + `extra="forbid"` (SEC-018).
- **Error handling**: structured `{isError, error:{code, message}}` envelopes (OBS-001); exception/upstream details logged server-side only, never surfaced to the LLM (OBS-002).
- **Dockerfile**: multi-stage build, non-root user, healthcheck (SEC-007 / SCALE-004).
- **Dependencies** major-pinned: `mcp`, `httpx`, `pydantic` (ARCH-012).
- **Versioning unified** to a single source of truth in `__init__.py`; `User-Agent` and `road_check_status` derive from it (previously drifted across 0.1.0/0.2.0/0.3.1/0.4.0).

### Security
- Closes all critical/high audit findings. See [`docs/SECURITY.md`](docs/SECURITY.md) and the re-audit verdict in [`audits/2026-06-03-re-audit/`](audits/2026-06-03-re-audit/) (40/44 pass).

## [0.4.0] - 2026-03-15

### Added
- **Phase 4 — Geography & Addresses** (geo.admin.ch, no API key):
  - `road_geocode_address`: Swiss address to GPS coordinates (official building register)
  - `road_reverse_geocode`: GPS to official address with EGID/EGAID (GWR)
  - `road_classify_road`: Road classification via swissTLM3D

## [0.3.1] - 2026-03-04

### Fixed
- `park_rail.py`: SBB renamed dataset `park-and-rail` causing HTTP 404. Added fallback chain across 3 candidate endpoints with clear error message linking to data.sbb.ch
- `ev_charging.py`: `ChargingStationNames` arrives as `dict` or `list` depending on operator. Fixed with `isinstance` normalization
- `multimodal.py`: `transport.opendata.ch` returns `duration` as string `'HH:MM:SS'`, not integer. Fixed with robust string-to-seconds conversion
- `multimodal.py`: `build_mobility_snapshot()` crashed with `NoneType has no attribute 'get'` when Park+Rail query returned `None`. Added `or {}` guard with fallback empty facilities list
- `server.py`: `road_check_status()` used `HEAD` request for sharedmobility API which only supports `GET`. Fixed to use `GET` for sharedmobility, `HEAD` for others
- `shared_mobility.py`: Documented that `sharedmobility.ch` does not enforce strict radius filtering (API behaviour, no code fix needed)

## [0.3.0] - 2026-03-01

### Added
- **Phase 3 — Park & Rail + Multimodal** (no API key):
  - `road_park_rail`: SBB Park+Rail facilities nearby
  - `road_mobility_snapshot`: Aggregated mobility overview for a location
  - `road_multimodal_plan`: Car to Park+Rail to public transport trip planning
