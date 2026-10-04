"""Zugriff auf die aufgezeichneten Antworten in `tests/fixtures/`.

Ein Loader statt `open()` an jeder Stelle: so gibt es genau einen Ort, der weiss,
wo die Aufzeichnungen liegen, und die Tests koennen ueber sie iterieren, statt
eine Liste von Hand zu pflegen, die zurueckbleibt.

Die Zuordnung Anfrage → Datei kommt aus `PROVENANCE.md`. Das ist Absicht: der
Nachweis ist damit nicht bloss Prosa neben den Dateien, sondern traegt den
Abspielbetrieb. Steht dort ein falscher Schluessel, faellt ein Test, statt dass
jemand ihn Jahre spaeter beim Lesen bemerkt.

Neu aufzeichnen mit `PYTHONPATH=src python scripts/record_fixtures.py`.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

WURZEL = Path(__file__).resolve().parent.parent
FIXTURES = WURZEL / "tests" / "fixtures"


@lru_cache(maxsize=1)
def recorder() -> Any:
    """Laedt `scripts/record_fixtures.py` als Modul, ohne `main()` zu rufen.

    Damit ist nebenbei geprueft, dass das Skript ueberhaupt laedt: im Betrieb
    ruft es niemand auf, und ruff kaeme einem Fehler darin nicht bei.
    """
    pfad = WURZEL / "scripts" / "record_fixtures.py"
    name = "record_fixtures_probe"
    spec = importlib.util.spec_from_file_location(name, pfad)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"{pfad} laesst sich nicht als Modul laden")
    modul = importlib.util.module_from_spec(spec)
    # Vor dem Ausfuehren registrieren: `@dataclass` schlaegt das eigene Modul in
    # `sys.modules` nach, um Annotationen aufzuloesen, und faellt sonst um.
    sys.modules[name] = modul
    try:
        spec.loader.exec_module(modul)
    finally:
        del sys.modules[name]
    return modul


@lru_cache(maxsize=1)
def schluesselverzeichnis() -> dict[str, str]:
    """Schluessel (die angefragte URL) → Dateiname, gelesen aus PROVENANCE.md."""
    verzeichnis: dict[str, str] = {}
    datei: str | None = None
    for zeile in provenance().splitlines():
        kopf = re.match(r"## `([^`]+)`", zeile)
        if kopf:
            datei = kopf.group(1)
            continue
        eintrag = re.match(r"- \*\*Schluessel:\*\* `(.+)`$", zeile)
        if eintrag and datei:
            verzeichnis[eintrag.group(1)] = datei
    return verzeichnis


@lru_cache(maxsize=1)
def statusverzeichnis() -> dict[str, int]:
    """Dateiname → HTTP-Status, gelesen aus PROVENANCE.md; ohne Angabe 200."""
    verzeichnis: dict[str, int] = {}
    datei: str | None = None
    for zeile in provenance().splitlines():
        kopf = re.match(r"## `([^`]+)`", zeile)
        if kopf:
            datei = kopf.group(1)
            verzeichnis[datei] = 200
            continue
        eintrag = re.match(r"- \*\*Status:\*\* (\d{3})$", zeile)
        if eintrag and datei:
            verzeichnis[datei] = int(eintrag.group(1))
    return verzeichnis


def fixture_text(name: str) -> str:
    """Die Aufzeichnung als Text — so, wie sie ueber die Leitung kaeme."""
    pfad = FIXTURES / name
    if not pfad.is_file():
        raise FileNotFoundError(f"keine Aufzeichnung {name} in {FIXTURES}")
    return pfad.read_text(encoding="utf-8")


def fixture_json(name: str) -> Any:
    """Die Aufzeichnung geparst."""
    return json.loads(fixture_text(name))


@lru_cache(maxsize=1)
def recorded_names() -> tuple[str, ...]:
    """Alle Aufzeichnungen im Ordner — nicht die, die ein Test erwartet.

    Der Unterschied ist der Punkt: eine Datei, die niemand erwartet, faellt
    sonst niemandem auf.
    """
    return tuple(sorted(p.name for p in FIXTURES.iterdir() if p.name != "PROVENANCE.md"))


def provenance() -> str:
    return (FIXTURES / "PROVENANCE.md").read_text(encoding="utf-8")
