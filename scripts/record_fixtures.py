#!/usr/bin/env python3
"""Zeichnet je eine echte Antwort pro Abfrage auf.

Warum nicht von Hand geschrieben: eine handgeschriebene Erfolgs-Antwort stimmt
mit dem ueberein, was ihr Autor annahm, und kann die Quelle deshalb nicht
widerlegen. Aufgezeichnet wird darum an demselben Ort, an dem der Server die
Antwort entgegennimmt — ueber einen httpx-Response-Hook auf dem Client aus
`client_lifecycle.build_client()`. Damit tragen Aufzeichnung und Betrieb
denselben User-Agent, dasselbe Timeout und dieselbe Egress-Allow-List.

Acht Hosts, aber mehr Abfrageformen als Hosts: Sharing-Suche nach Ort und nach
Text, Ladestationen, Park+Rail, Geocoding vorwaerts und rueckwaerts,
Strassenklassierung, und die Aggregate, die mehrere davon in einem Aufruf
verbinden. Die Portfolio-Regel «eine Antwort je externem Endpunkt» waere mit
acht Dateien erfuellt und truege fast nichts.

Zugeordnet wird beim Abspielen nach der Anfrage und nicht nach der Reihenfolge:
`road_mobility_snapshot` und `road_multimodal_plan` fragen mehrere Quellen in
einem Aufruf ab.

## Was einen Schluessel braucht

Die Verkehrsmeldungen (Phase 2, `opentransportdata.swiss`) verlangen
`OPENTRANSPORTDATA_API_KEY`. Ohne ihn laesst sich dafuer nichts aufzeichnen;
`SCHLUESSELPFLICHTIG` unten nennt die betroffenen Werkzeuge, und der Nachweis
sagt es ebenfalls. Das ist eine Luecke im Ordner, keine stille.

## Aufruf

    PYTHONPATH=src python scripts/record_fixtures.py

Schreibt nach `tests/fixtures/` und erzeugt `tests/fixtures/PROVENANCE.md` neu.
Dateien, die kein Plan-Eintrag mehr erzeugt, werden geloescht — sonst waechst
der Ordner und der Nachweis bleibt zurueck.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "src"))

from swiss_road_mobility_mcp import (  # noqa: E402
    api_infrastructure,
    client_lifecycle,
    egress,
    geo_admin,
    multimodal,
    server,
    traffic_counters,
)

# Module, die sich ihren Client selbst bauen statt den gepoolten zu nehmen.
_MODULE_MIT_EIGENEM_CLIENT = (
    api_infrastructure,
    geo_admin,
    multimodal,
    server,
    traffic_counters,
)

FIXTURES = WURZEL / "tests" / "fixtures"

VERSUCHE = 4

# Wie viele Eintraege einer Trefferliste bleiben. Die Form einer Zeile belegen
# drei genauso gut wie hundert; die Zahl steht je Datei im Nachweis.
ZEILEN = 3

# Bern, Hauptbahnhof — ein Ort quer durch alle Werkzeuge, damit die
# Aufzeichnungen zueinander passen und ein Test sie gegeneinander halten kann.
BERN = {"latitude": 46.9490, "longitude": 7.4396}

# Werkzeuge, die ohne `OPENTRANSPORTDATA_API_KEY` nichts liefern koennen.
SCHLUESSELPFLICHTIG = ("road_traffic_situations",)

# Werkzeuge, die sich von *hier* nicht aufzeichnen lassen — und warum.
#
# `data.opentransportdata.swiss` antwortet diesem Anschluss auf **jede**
# Anfrage mit einem nginx-403, auch auf `/api/3/action/site_read`. Das ist eine
# Sperre gegen Rechenzentrums-IPs und **kein Beleg dafuer, dass das Werkzeug
# kaputt ist** — dieselbe Lage wie bei `admin.ch` aus der CI. Ohne Verifikation
# von einem normalen Anschluss aus wird darauf nichts gebaut, weder eine
# Fixture noch eine Behauptung.
NICHT_VON_HIER = {
    "road_park_rail": "data.opentransportdata.swiss antwortet mit HTTP 403 (nginx, "
    "auch auf site_read) — Sperre gegen diesen Anschluss, kein Befund ueber das Werkzeug",
}


@dataclass(frozen=True)
class Aufruf:
    """Ein Werkzeugaufruf, der Anfragen ausloesen soll."""

    name: str
    werkzeug: str
    klasse: str | None
    eingabe: dict[str, Any]
    braucht_ctx: bool = False
    # Kuerzen ist nur dort harmlos, wo der Server die Liste ganz liest. Filtert
    # oder zaehlt er *in* ihr, schneidet ein Schnitt womoeglich genau die Zeile
    # weg, die er sucht.
    kuerzen: bool = True
    notiz: str = ""


PLAN: list[Aufruf] = [
    Aufruf("sharing_nearby", "road_find_sharing", "FindSharingInput", dict(BERN)),
    Aufruf(
        "sharing_search",
        "road_search_sharing",
        "SearchSharingInput",
        {"search_text": "Bern"},
    ),
    Aufruf(
        "sharing_providers",
        "road_sharing_providers",
        None,
        {},
        kuerzen=False,
        notiz="Ungekuerzt: das Werkzeug listet die Anbieter vollstaendig. "
        "Gekuerzt behauptete es einen kleineren Markt.",
    ),
    Aufruf("charger", "road_find_charger", "FindChargerInput", dict(BERN), braucht_ctx=True),
    Aufruf(
        "geocode",
        "road_geocode_address",
        "GeocodeAddressInput",
        {"search_text": "Bundesplatz 3, Bern"},
    ),
    Aufruf("reverse_geocode", "road_reverse_geocode", "ReverseGeocodeInput", dict(BERN)),
    Aufruf("classify_road", "road_classify_road", "ClassifyRoadInput", dict(BERN)),
    Aufruf(
        "snapshot",
        "road_mobility_snapshot",
        "MobilitySnapshotInput",
        dict(BERN),
        braucht_ctx=True,
        notiz="Mehrere Quellen in einem Aufruf — der Grund, warum nach Anfrage "
        "und nicht nach Reihenfolge zugeordnet wird.",
    ),
]


@dataclass
class Antwort:
    """Eine gesehene Antwort samt der Anfrage, die sie ausgeloest hat."""

    url: str
    text: str
    # Der Status gehoert zur Antwort. Ohne ihn spielte der Test einen
    # aufgezeichneten 500 als 200 ab — und zeigte einen Pfad, den die Quelle
    # gar nicht genommen hat.
    status: int = 200
    werkzeuge: list[str] = field(default_factory=list)
    darf_kuerzen: bool = True
    dateiname: str = ""
    original_bytes: int = 0
    gekuerzt_von: int = 0
    behalten: int = 0
    leer: bool = False
    sha256: str = ""
    bytes: int = 0

    @property
    def schluessel(self) -> str:
        """Woran eine Anfrage beim Abspielen wiedererkannt wird."""
        return self.url


def _endung(text: str) -> str:
    """`.json`, wenn die Antwort JSON ist — sonst `.txt`."""
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return ".txt"
    return ".json"


def _hook_fuer(gesehen: list[Antwort]) -> Callable[[httpx.Response], Awaitable[None]]:
    """Baut den Response-Hook fuer einen Versuch.

    Eigene Funktion, damit die Liste als Argument gebunden ist und nicht als
    Schleifenvariable aus dem umgebenden Namensraum (ruff B023).
    """

    async def hook(response: httpx.Response) -> None:
        await response.aread()
        if response.is_redirect:
            return
        gesehen.append(Antwort(url=str(response.request.url), text=response.text, status=response.status_code))

    return hook


class _StillerKontext:
    """Der `ctx`, den MCPServer sonst reicht — hier ohne Ausgabe."""

    async def info(self, *a: object, **kw: object) -> None: ...

    async def warning(self, *a: object, **kw: object) -> None: ...

    async def error(self, *a: object, **kw: object) -> None: ...

    async def debug(self, *a: object, **kw: object) -> None: ...

    async def report_progress(self, *a: object, **kw: object) -> None: ...


async def _fahre(a: Aufruf) -> list[Antwort]:
    """Ruft ein Werkzeug und gibt die dabei gesehenen Antworten zurueck."""
    fn = getattr(server, a.werkzeug)
    letzter: Exception | None = None

    for versuch in range(VERSUCHE):
        if versuch:
            await asyncio.sleep(2**versuch)
        gesehen: list[Antwort] = []
        hook = _hook_fuer(gesehen)

        # Zwei Nahtstellen, nicht eine. Die Sharing- und Ladewerkzeuge nehmen
        # den gepoolten `MobilityHTTPClient`, `geo_admin` und die
        # Verkehrsmodule bauen sich ihren eigenen Client ueber
        # `egress.async_client()`. Wer nur die erste patcht, zeichnet die
        # Haelfte nicht auf — und sieht das als «hat keine Anfrage
        # abgeschickt», nicht als Luecke.
        original_build = client_lifecycle.build_client
        original_async = egress.async_client

        def gehookt() -> Any:
            klient = original_build()
            klient._client.event_hooks.setdefault("response", []).append(hook)
            return klient

        def gehookter_client(*args: Any, **kwargs: Any) -> Any:
            klient = original_async(*args, **kwargs)
            klient.event_hooks.setdefault("response", []).append(hook)
            return klient

        client_lifecycle.build_client = gehookt
        server.build_client = gehookt  # falls direkt importiert
        for modul in _MODULE_MIT_EIGENEM_CLIENT:
            modul.async_client = gehookter_client
        # `_get_client()` merkt sich den Client prozessweit. Ohne Reset baute
        # nur der erste Aufruf einen gehookten — alle weiteren liefen an der
        # Aufzeichnung vorbei und saehen aus, als haetten sie nichts gefragt.
        server._client = None
        try:
            if a.klasse:
                modell = getattr(server, a.klasse)(**a.eingabe)
                ergebnis = await fn(modell, _StillerKontext()) if a.braucht_ctx else await fn(modell)
            else:
                ergebnis = await (fn(_StillerKontext()) if a.braucht_ctx else fn())
        except Exception as e:  # noqa: BLE001 — jeder Fehler ist hier ein Retry-Grund
            letzter = e
            continue
        finally:
            client_lifecycle.build_client = original_build
            server.build_client = original_build
            for modul in _MODULE_MIT_EIGENEM_CLIENT:
                modul.async_client = original_async
            server._client = None

        if isinstance(ergebnis, dict) and ergebnis.get("error"):
            letzter = RuntimeError(f"{a.werkzeug} meldet: {str(ergebnis['error'])[:200]}")
            continue
        if not gesehen:
            letzter = RuntimeError(f"{a.werkzeug} hat keine Anfrage abgeschickt")
            continue
        # Je URL die letzte Antwort: nach einem Wiederholungsversuch ist das
        # die, mit der das Werkzeug weitergearbeitet hat. Ein 500, auf den ein
        # 200 folgte, als *die* Antwort aufzuzeichnen, behauptete einen
        # Ausfall, den es so nicht gab.
        letzte: dict[str, Antwort] = {}
        for antwort in gesehen:
            letzte.pop(antwort.url, None)
            letzte[antwort.url] = antwort
        for antwort in letzte.values():
            antwort.werkzeuge.append(a.werkzeug)
            antwort.darf_kuerzen = a.kuerzen
        return list(letzte.values())

    raise RuntimeError(f"{a.name} nach {VERSUCHE} Versuchen nicht aufgezeichnet: {letzter}")


def _kuerze(daten: Any) -> tuple[int, int, Any]:
    """Kuerzt jede Liste im Baum auf `ZEILEN`; gibt (vorher, nachher, Daten).

    Nur die Zahl der Eintraege, nie ein Feld. Zaehlfelder daneben bleiben
    stehen: die Quelle meint damit die Gesamtzahl der Treffer und nicht die
    Zahl der gelieferten Zeilen, und genau die liest der Server aus.
    """
    vorher = nachher = 0

    def geh(knoten: Any) -> Any:
        nonlocal vorher, nachher
        if isinstance(knoten, dict):
            return {k: geh(v) for k, v in knoten.items()}
        if isinstance(knoten, list):
            vorher += len(knoten)
            gekuerzt = knoten[:ZEILEN]
            nachher += len(gekuerzt)
            return [geh(v) for v in gekuerzt]
        return knoten

    # Erst laufen lassen, dann die Zaehler lesen. `return vorher, nachher,
    # geh(daten)` wertet von links nach rechts aus und lieferte deshalb immer
    # (0, 0) — der Nachweis schrieb «ungekuerzt» ueber jede gekuerzte Datei.
    ergebnis = geh(daten)
    return vorher, nachher, ergebnis


async def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    heute = datetime.now(UTC).date().isoformat()
    nach_schluessel: dict[str, Antwort] = {}
    zaehler: dict[str, int] = {}

    for a in PLAN:
        print(f"… {a.werkzeug} ({a.name})", file=sys.stderr)
        for antwort in await _fahre(a):
            if antwort.schluessel in nach_schluessel:
                vorhanden = nach_schluessel[antwort.schluessel]
                if a.werkzeug not in vorhanden.werkzeuge:
                    vorhanden.werkzeuge.append(a.werkzeug)
                continue
            zaehler[a.name] = zaehler.get(a.name, 0) + 1
            antwort.dateiname = f"{a.name}_{zaehler[a.name]}{_endung(antwort.text)}"
            nach_schluessel[antwort.schluessel] = antwort

    for antwort in nach_schluessel.values():
        antwort.original_bytes = len(antwort.text.encode("utf-8"))
        try:
            daten = json.loads(antwort.text)
        except json.JSONDecodeError:
            (FIXTURES / antwort.dateiname).write_text(antwort.text, encoding="utf-8")
        else:
            antwort.leer = daten == []
            if antwort.darf_kuerzen:
                antwort.gekuerzt_von, antwort.behalten, daten = _kuerze(daten)
            # Neu eingerueckt geschrieben: eine Zeile JSON waere kleiner, aber
            # im Diff nicht lesbar, und ein Fixture will gelesen werden.
            (FIXTURES / antwort.dateiname).write_text(
                json.dumps(daten, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        roh = (FIXTURES / antwort.dateiname).read_bytes()
        antwort.sha256 = hashlib.sha256(roh).hexdigest()
        antwort.bytes = len(roh)

    antworten = sorted(nach_schluessel.values(), key=lambda x: x.dateiname)
    _schreibe_provenance(antworten, heute)

    # Aufraeumen: was kein Plan-Eintrag mehr erzeugt, hat auch keinen Nachweis.
    geschrieben = {a.dateiname for a in antworten} | {"PROVENANCE.md"}
    for pfad in sorted(FIXTURES.iterdir()):
        if pfad.name not in geschrieben:
            print(f"– entferne veraltet: {pfad.name}", file=sys.stderr)
            pfad.unlink()

    print(f"{len(antworten)} Aufzeichnungen in {FIXTURES}", file=sys.stderr)
    return 0


def _schreibe_provenance(antworten: list[Antwort], heute: str) -> None:
    hat_schluessel = bool(os.environ.get("OPENTRANSPORTDATA_API_KEY"))
    zeilen = [
        "# Herkunft der Fixtures",
        "",
        f"Aufgezeichnet am **{heute}** mit `PYTHONPATH=src python scripts/record_fixtures.py`.",
        "",
        "Eine Antwort je **Abfrage**, nicht je Endpunkt: acht Hosts, aber mehr",
        "Abfrageformen als Hosts. Acht Dateien wuerden die Portfolio-Regel erfuellen",
        "und fast nichts belegen.",
        "",
        "Der **Schluessel** unten ist die angefragte URL; danach ordnet der Test zu und",
        "nicht nach Reihenfolge. `road_mobility_snapshot` fragt mehrere Quellen in einem",
        "Aufruf ab, und eine Zuordnung nach Reihenfolge waere im gruenen Fall bloss",
        "zufaellig richtig.",
        "",
        "Die Antworten stammen aus dem Client von `client_lifecycle.build_client()`",
        "(gleicher User-Agent, gleiches Timeout, gleiche Egress-Allow-List wie im",
        "Betrieb), abgegriffen ueber einen httpx-Response-Hook. Ausgeloest hat sie",
        "jeweils das Werkzeug selbst — so belegt die Aufzeichnung auch, dass das",
        "Werkzeug genau diese Anfrage schickt.",
        "",
        "## Was hier fehlt, und warum",
        "",
        *[f"- `{w}`: {grund}" for w, grund in NICHT_VON_HIER.items()],
        "",
        "Die Verkehrsmeldungen (Phase 2, `opentransportdata.swiss`) verlangen",
        "`OPENTRANSPORTDATA_API_KEY`. Beim Aufzeichnen war "
        + ("er gesetzt." if hat_schluessel else "**kein Schluessel gesetzt**,")
        + (
            ""
            if hat_schluessel
            else " deshalb gibt es fuer "
            + ", ".join(f"`{w}`" for w in SCHLUESSELPFLICHTIG)
            + " keine Aufzeichnung. Das ist eine Luecke im Ordner — und sie steht hier,"
            " statt still zu bleiben."
        ),
        "",
        "Neu gesetzt ist die Einrueckung; gekuerzt ist allein die **Zahl** der",
        "Listeneintraege. Kein Feld eines behaltenen Eintrags ist angetastet, und",
        "Zaehlfelder daneben stehen wie geliefert.",
        "",
        "Die Fehlerpfade — Timeout, 5xx, leere Trefferliste — bleiben handgeschrieben.",
        "Sie lassen sich nicht auf Zuruf aufzeichnen und sind als Erfindung in Ordnung.",
        "Ausnahme: Liefert die Quelle beim Aufzeichnen *von sich aus* einen Fehler, auf",
        "den das Werkzeug weiterarbeitet, steht er hier mit seinem **Status** — und wird",
        "mit diesem Status abgespielt.",
        "",
    ]
    for a in antworten:
        zeilen += [
            f"## `{a.dateiname}`",
            "",
            f"- **Werkzeuge:** {', '.join(f'`{w}`' for w in sorted(a.werkzeuge))}",
            f"- **Schluessel:** `{a.schluessel}`",
        ]
        if a.status != 200:
            zeilen.append(f"- **Status:** {a.status}")
        if a.leer:
            # Ein `[]` ist eine Aussage der Quelle: an diesem Ort steht nichts.
            # Aufgezeichnet wird es, weil das Werkzeug genau so fragt — und
            # ausgewiesen, damit der Waechter gegen leere Fixtures es nicht
            # fuer eine misslungene Aufnahme halten muss.
            zeilen.append("- **Auswahl:** leer, wie geliefert — die Quelle meldet hier keinen Treffer")
        elif a.gekuerzt_von > a.behalten:
            zeilen.append(
                f"- **Auswahl:** {a.behalten} von {a.gekuerzt_von} Listeneintraegen "
                f"(je Liste die ersten {ZEILEN}), aus {a.original_bytes} Bytes Rohantwort"
            )
        elif not a.darf_kuerzen:
            zeilen.append(
                "- **Auswahl:** ungekuerzt — der Server liest diese Liste ganz, "
                "ein Schnitt behauptete einen kleineren Bestand"
            )
        else:
            zeilen.append("- **Auswahl:** ungekuerzt")
        zeilen += [
            f"- **Groesse:** {a.bytes} Bytes",
            f"- **SHA-256:** `{a.sha256}`",
            "",
        ]
    (FIXTURES / "PROVENANCE.md").write_text("\n".join(zeilen), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
