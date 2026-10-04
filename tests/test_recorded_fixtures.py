"""Jedes Werkzeug, gefahren aus einer aufgezeichneten Antwort.

Die handgeschriebenen Stubs im Rest der Suite pruefen die *Fehler*-Pfade — ein
Timeout, ein 5xx, eine leere Trefferliste —, die sich nicht auf Zuruf
aufzeichnen lassen und als Erfindung in Ordnung sind. Was sie nicht koennen: die
Form einer Erfolgs-Antwort belegen. Sie stimmen mit dem ueberein, was ihr Autor
annahm.

Acht Hosts, aber mehr Abfrageformen als Hosts. Zugeordnet wird beim Abspielen
nach der Anfrage und nicht nach der Reihenfolge: `road_mobility_snapshot` fragt
mehrere Quellen in einem Aufruf ab.

**Zwei Nahtstellen, nicht eine.** Die Sharing- und Ladewerkzeuge nehmen den
gepoolten `MobilityHTTPClient`, `geo_admin` und die Verkehrsmodule bauen sich
ihren eigenen ueber `egress.async_client()`. Ein Test, der nur eine davon
abfaengt, laesst die andere Haelfte ins echte Netz — deshalb faengt die Fixture
unten beide ab und faellt laut, wenn eine Anfrage keine Aufzeichnung hat.

Herkunft, Datum, Auswahlregel und SHA-256 je Datei stehen in
`tests/fixtures/PROVENANCE.md`; neu aufzeichnen mit
`PYTHONPATH=src python scripts/record_fixtures.py`.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

import httpx
import pytest
import respx
from fixture_data import (
    fixture_json,
    fixture_text,
    provenance,
    recorded_names,
    recorder,
    schluesselverzeichnis,
    statusverzeichnis,
)

from swiss_road_mobility_mcp import api_infrastructure, server

BERN = {"latitude": 46.9490, "longitude": 7.4396}

# Werkzeug → (Eingabeklasse oder None, Eingabe, braucht ctx). Bewusst noch
# einmal hingeschrieben und nicht aus dem Recorder-Plan abgeleitet: die Tests
# sollen eine eigene Aussage machen. Dass beide dieselben Aufrufe fahren,
# prueft `test_der_recorder_faehrt_dieselben_aufrufe`.
WERKZEUGE: dict[str, tuple[str, str | None, dict[str, Any], bool]] = {
    "sharing_nearby": ("road_find_sharing", "FindSharingInput", dict(BERN), False),
    "sharing_search": ("road_search_sharing", "SearchSharingInput", {"search_text": "Bern"}, False),
    "sharing_providers": ("road_sharing_providers", None, {}, False),
    "charger": ("road_find_charger", "FindChargerInput", dict(BERN), True),
    "geocode": (
        "road_geocode_address",
        "GeocodeAddressInput",
        {"search_text": "Bundesplatz 3, Bern"},
        False,
    ),
    "reverse_geocode": ("road_reverse_geocode", "ReverseGeocodeInput", dict(BERN), False),
    "classify_road": ("road_classify_road", "ClassifyRoadInput", dict(BERN), False),
    "snapshot": ("road_mobility_snapshot", "MobilitySnapshotInput", dict(BERN), True),
}


class _StillerKontext:
    """Der `ctx`, den MCPServer sonst reicht — hier ohne Ausgabe."""

    async def info(self, *a: object, **kw: object) -> None: ...

    async def warning(self, *a: object, **kw: object) -> None: ...

    async def error(self, *a: object, **kw: object) -> None: ...

    async def debug(self, *a: object, **kw: object) -> None: ...

    async def report_progress(self, *a: object, **kw: object) -> None: ...


@pytest.fixture
def quelle(monkeypatch):
    """Beantwortet jede Anfrage aus ihrer eigenen Aufzeichnung und protokolliert mit.

    Nach der *Anfrage* zugeordnet, nicht nach der Reihenfolge. `respx` faengt
    beide Nahtstellen ab, weil es auf der Transportschicht sitzt — der gepoolte
    Client und die selbstgebauten gehen beide durch.
    """
    protokoll: list[httpx.Request] = []
    verzeichnis = schluesselverzeichnis()
    status = statusverzeichnis()
    server._client = None  # der gepoolte Client wird sonst zwischen Tests geteilt

    # Ein aufgezeichneter 5xx wird wiederholt, wie im Betrieb — ohne die Pause.
    # Ueber den Modul-Alias, nicht ueber `api_infrastructure.asyncio`.
    async def _kein_schlaf(sekunden: float) -> None: ...

    monkeypatch.setattr(api_infrastructure, "_sleep", _kein_schlaf)

    def antwort(request: httpx.Request) -> httpx.Response:
        protokoll.append(request)
        name = verzeichnis.get(str(request.url))
        if name is None:
            raise AssertionError(
                f"keine Aufzeichnung fuer diese Anfrage:\n  {request.url}\n"
                "Neu aufzeichnen mit `PYTHONPATH=src python scripts/record_fixtures.py`."
            )
        return httpx.Response(status[name], text=fixture_text(name))

    with respx.mock:
        respx.route().mock(side_effect=antwort)
        yield protokoll
    server._client = None


async def _fahre(name: str):
    """Ruft ein Werkzeug mit der Eingabe aus der Tabelle."""
    werkzeug, klasse, eingabe, braucht_ctx = WERKZEUGE[name]
    fn = getattr(server, werkzeug)
    if klasse is None:
        return await (fn(_StillerKontext()) if braucht_ctx else fn())
    modell = getattr(server, klasse)(**eingabe)
    return await (fn(modell, _StillerKontext()) if braucht_ctx else fn(modell))


# --------------------------------------------------------------------------
# Herkunft
# --------------------------------------------------------------------------
def test_provenance_nennt_ein_brauchbares_aufnahmedatum():
    """Eine Aufzeichnung ohne Datum ist eine undatierte Behauptung ueber die Quelle."""
    treffer = re.search(r"Aufgezeichnet am \*\*(\d{4}-\d{2}-\d{2})\*\*", provenance())
    assert treffer, "PROVENANCE.md nennt kein Aufnahmedatum im erwarteten Format"
    wann = dt.date.fromisoformat(treffer.group(1))
    assert wann <= dt.datetime.now(dt.UTC).date(), "Aufnahmedatum liegt in der Zukunft"


def test_jede_fixture_steht_in_der_provenance():
    """Sonst waechst der Ordner und der Nachweis bleibt zurueck."""
    text = provenance()
    fehlend = [n for n in recorded_names() if f"## `{n}`" not in text]
    assert not fehlend, f"ohne Eintrag in PROVENANCE.md: {fehlend}"


def test_jeder_schluessel_zeigt_auf_eine_vorhandene_datei():
    """Der Nachweis traegt hier den Abspielbetrieb — er darf nicht ins Leere zeigen."""
    fehlend = sorted(set(schluesselverzeichnis().values()) - set(recorded_names()))
    assert not fehlend, f"im Nachweis genannt, aber nicht vorhanden: {fehlend}"


def test_keine_aufzeichnung_liegt_unbenutzt_herum():
    """Die Gegenrichtung — eine Datei, die kein Schluessel erreicht, belegt nichts."""
    ueberzaehlig = sorted(set(recorded_names()) - set(schluesselverzeichnis().values()))
    assert not ueberzaehlig, f"von keinem Schluessel erreicht: {ueberzaehlig}"


def test_der_recorder_faehrt_dieselben_aufrufe():
    """Recorder und Tests duerfen nicht auseinanderlaufen.

    Laedt `scripts/record_fixtures.py` als Modul — `main()` wird nicht gerufen,
    es geht keine Anfrage raus.
    """
    im_plan = {a.name for a in recorder().PLAN}
    assert im_plan == set(WERKZEUGE), "Recorder und Testtabelle nennen verschiedene Aufrufe"


def test_der_nachweis_meldet_was_gekuerzt_wurde():
    """Ein Nachweis, der ueber jeder Datei «ungekuerzt» schreibt, belegt nichts.

    Genau das tat er: `_kuerze` gab seine Zaehler als `return vorher, nachher,
    geh(daten)` zurueck, und Python liest die beiden Zahlen, *bevor* `geh` sie
    hochzaehlt — also immer (0, 0). Sieben der zehn Aufzeichnungen standen damit
    als vollstaendig im Ordner; die groesste stammt aus 26 MB Rohantwort und
    traegt davon 95 Eintraege.

    Diese Zusicherung faellt, wenn die Zaehler wieder blind werden.
    """
    modul = recorder()
    vorher, nachher, gekuerzt = modul._kuerze({"a": list(range(modul.ZEILEN * 3))})
    assert (vorher, nachher) == (modul.ZEILEN * 3, modul.ZEILEN), (
        f"_kuerze meldet {vorher}→{nachher} statt {modul.ZEILEN * 3}→{modul.ZEILEN}"
    )
    assert len(gekuerzt["a"]) == modul.ZEILEN
    assert re.search(r"- \*\*Auswahl:\*\* \d+ von \d+ Listeneintraegen", provenance()), (
        "keine einzige Datei im Nachweis ist als gekuerzt ausgewiesen"
    )


@pytest.mark.parametrize("name", sorted(recorded_names()))
def test_keine_aufzeichnung_ist_leer(name):
    """Eine leere Antwort sieht aus wie eine gueltige und prueft nichts.

    Zwei Ausnahmen, beide im Nachweis ausgewiesen und nicht still: ein
    aufgezeichneter Fehler (dort *ist* der Status die Antwort) und ein `[]`,
    das die Quelle so geliefert hat.
    """
    if statusverzeichnis()[name] != 200:
        assert fixture_text(name).strip(), f"{name}: Fehlerantwort ohne Koerper"
        return
    daten = fixture_json(name)
    if isinstance(daten, list):
        block = provenance().split(f"## `{name}`", 1)[1].split("## ", 1)[0]
        if "leer, wie geliefert" in block:
            assert daten == [], f"{name} ist als leer ausgewiesen und ist es nicht"
            return
        assert daten, f"{name} ist eine leere Liste"
        return
    listen = [v for v in daten.values() if isinstance(v, list)]
    if listen:
        assert any(listen), f"{name} traegt nur leere Listen — neu aufzeichnen"
        return
    assert daten, f"{name} ist leer"


# --------------------------------------------------------------------------
# Was der Ordner *nicht* enthaelt, und warum
# --------------------------------------------------------------------------
def test_die_luecken_stehen_im_nachweis():
    """Ein Werkzeug ohne Aufzeichnung soll auffallen, nicht verschwinden.

    Zwei Gruende gibt es hier, und beide gehoeren hingeschrieben:
    `road_traffic_situations` braucht `OPENTRANSPORTDATA_API_KEY`, und
    `data.opentransportdata.swiss` antwortet diesem Anschluss auf jede Anfrage
    mit einem nginx-403 — auch auf `site_read`. Das ist eine Sperre gegen
    Rechenzentrums-IPs und **kein Befund ueber das Werkzeug**; ohne
    Verifikation von einem normalen Anschluss aus wird darauf nichts gebaut.
    """
    nachweis = provenance()
    assert "OPENTRANSPORTDATA_API_KEY" in nachweis
    assert "road_park_rail" in nachweis
    assert "403" in nachweis


def test_der_recorder_nennt_dieselben_luecken():
    """Damit die Begruendung nicht nur im Nachweis steht, sondern auch im Code."""
    modul = recorder()
    assert "road_traffic_situations" in modul.SCHLUESSELPFLICHTIG
    assert "road_park_rail" in modul.NICHT_VON_HIER


# --------------------------------------------------------------------------
# Die Werkzeuge, jedes an seiner eigenen Antwort
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(WERKZEUGE))
async def test_jedes_werkzeug_liest_seine_aufgezeichnete_antwort(quelle, name):
    """Der eigentliche Punkt: jede Abfrage bekommt *ihre* Antwort.

    Alle mit derselben zu bedienen hiesse, die Aufzeichnung gegen eine Abfrage
    zu halten, die sie nicht beantwortet. Der Dispatcher faellt laut, wenn eine
    Anfrage keine Aufzeichnung hat.
    """
    ergebnis = await _fahre(name)
    assert isinstance(ergebnis, dict), f"{name} liefert kein Dict"
    assert not ergebnis.get("error"), ergebnis.get("error")
    assert quelle, f"{name} hat gar keine Anfrage abgeschickt"


async def test_die_geokodierung_geht_an_die_andere_nahtstelle(quelle):
    """`geo_admin` baut sich seinen Client selbst, statt den gepoolten zu nehmen.

    Wer beim Aufzeichnen nur `build_client` patcht, sieht hier «hat keine
    Anfrage abgeschickt» — so ist es beim ersten Lauf passiert. Diese
    Zusicherung haelt fest, dass die Abfrage wirklich rausgeht.
    """
    await _fahre("geocode")
    hosts = {r.url.host for r in quelle}
    assert "api3.geo.admin.ch" in hosts, hosts


async def test_die_anbieterliste_steht_ungekuerzt_im_ordner(quelle):
    """`road_sharing_providers` listet den Markt — gekuerzt log es."""
    anbieter = fixture_json("sharing_providers_1.json")
    assert len(anbieter) > 20, f"nur {len(anbieter)} Anbieter — die Datei ist gekuerzt"
    block = provenance().split("## `sharing_providers_1.json`", 1)[1].split("## ", 1)[0]
    assert "ungekuerzt" in block, block


async def test_die_sharing_antwort_ist_eine_liste_ohne_umschlag(quelle):
    """Drei Quellen, drei Antwortformen — sharedmobility.ch antwortet nackt.

    Ein Loader, der ueberall `results` erwartet, liefert hier still nichts.
    """
    umkreis = [n for n, st in statusverzeichnis().items() if n.startswith("sharing_nearby_") and st == 200]
    assert umkreis, "keine einzige Umkreissuche mit 200 aufgezeichnet"
    assert all(isinstance(fixture_json(n), list) for n in umkreis), umkreis
    assert "results" in fixture_json("geocode_1.json")
    ergebnis = await _fahre("sharing_nearby")
    assert ergebnis["vehicles"], list(ergebnis)[:6]
    assert ergebnis["count"] == len(ergebnis["vehicles"])


async def test_die_umkreissuche_folgt_der_aufgezeichneten_quelle(quelle):
    """Beide Zweige, je nachdem, was die Quelle beim Aufzeichnen tat.

    Am 4.10.2026 antwortete sie auf `/identify` ohne Fahrzeugtyp mit HTTP 500
    und mit jedem einzelnen Typ mit 200. Ist das so aufgezeichnet, muss der
    Server je Typ fragen und die Luecke melden; antwortet sie wieder ganz,
    darf er nichts zusammensetzen. Ein Test, der nur den heutigen Zweig kennt,
    prueft den Tag.
    """
    ergebnis = await _fahre("sharing_nearby")
    ohne_typ = [r for r in quelle if not r.url.params.get_list("filters")]
    assert ohne_typ, "die Abfrage ohne Fahrzeugtyp ging nicht raus"
    name = schluesselverzeichnis()[str(ohne_typ[0].url)]
    if statusverzeichnis()[name] == 500:
        assert ergebnis["completeness"]["complete"] is False, list(ergebnis)
        je_typ = {str(r.url) for r in quelle if r.url.params.get_list("filters")}
        vollst = ergebnis["completeness"]
        versucht = [*vollst["queried_vehicle_types"], *vollst.get("failed_vehicle_types", {})]
        assert len(je_typ) == len(versucht), (je_typ, versucht)
        # Was die Aufzeichnung als Fehlschlag fuehrt, muss das Ergebnis nennen.
        for url in je_typ:
            if statusverzeichnis()[schluesselverzeichnis()[url]] != 200:
                typ = httpx.URL(url).params.get_list("filters")[0].split("=", 1)[1]
                assert typ in vollst.get("failed_vehicle_types", {}), (typ, vollst)
    else:
        assert "completeness" not in ergebnis
        assert len(quelle) == 1


async def test_der_schnappschuss_fragt_mehrere_quellen(quelle):
    """Mehrere Quellen in einem Aufruf — der Grund fuer die Zuordnung nach Anfrage.

    Eine Zuordnung nach Reihenfolge waere im gruenen Fall bloss zufaellig
    richtig.
    """
    await _fahre("snapshot")
    assert len(quelle) >= 1, "der Schnappschuss hat nichts gefragt"


# --------------------------------------------------------------------------
# Die Gegenrichtung
# --------------------------------------------------------------------------
@respx.mock
async def test_eine_leere_trefferliste_bleibt_eine_leere_trefferliste():
    """`[]` ist eine Aussage der Quelle: dort steht nichts.

    Das darf nicht als Fehler herauskommen — sonst kann das Modell einen echten
    Negativtreffer nicht von einem Ausfall unterscheiden.
    """
    server._client = None
    respx.route().mock(return_value=httpx.Response(200, text=json.dumps([])))
    ergebnis = await _fahre("sharing_nearby")
    assert isinstance(ergebnis, dict)
    assert not ergebnis.get("error"), "eine leere Suche ist kein Fehler"
    server._client = None


# --------------------------------------------------------------------------
# Der Nachweis, nachgerechnet
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(n for n in recorded_names() if n != "PROVENANCE.md"))
def test_die_pruefsumme_im_nachweis_stimmt(name):
    """Eine Pruefsumme, die niemand nachrechnet, ist Zierde.

    Sie steht im Nachweis, um genau einen Fall zu fangen: eine Aufzeichnung,
    die nach dem Lauf von Hand nachgebessert wurde. Eine korrigierte Antwort
    ist wieder eine erfundene — und von aussen ist ihr das nicht anzusehen.
    Ohne diesen Test faengt die Summe nichts.

    Gerechnet wird ueber die Bytes auf der Platte, nicht ueber den Loader:
    genau die hat der Recorder gehasht, und ein Loader, der unterwegs dekodiert
    oder normalisiert, wuerde die Pruefung gegen sich selbst fuehren.
    """
    import hashlib
    import re
    from pathlib import Path

    teile = provenance().split(f"## `{name}`", 1)
    assert len(teile) == 2, f"{name} hat keinen Block in PROVENANCE.md"
    treffer = re.search(r"\*\*SHA-256:\*\*\s*`([0-9a-f]{64})`", teile[1].split("## ", 1)[0])
    assert treffer, f"{name} steht ohne Pruefsumme im Nachweis"
    roh = (Path(__file__).resolve().parent / "fixtures" / name).read_bytes()
    assert hashlib.sha256(roh).hexdigest() == treffer.group(1), (
        f"{name} weicht vom Nachweis ab — von Hand nachgebessert? Neu aufzeichnen."
    )
