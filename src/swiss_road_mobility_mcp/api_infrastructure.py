"""
Gemeinsame Infrastruktur für die Strassen- & Mobilitäts-APIs.

Metapher: Wenn der ÖV-Server die SBB-Schalterhalle ist (Tickets nötig),
dann ist dieser Server der offene Bahnhofsplatz – jeder darf rein,
aber wir passen trotzdem auf, dass niemand die Eingänge verstopft.

Beide APIs (sharedmobility.ch und ich-tanke-strom.ch) sind:
✅ Komplett offen – kein API-Key nötig!
✅ JSON-basiert – kein XML-Parsing nötig!
✅ Rate Limits trotzdem respektieren – wir sind gute Gäste.
"""

import asyncio
import hashlib
import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from . import USER_AGENT
from .egress import async_client

logger = logging.getLogger("swiss-road-mobility-mcp")

# Wie lange am Tuersteher gewartet wird, bevor abgesagt wird. Darueber ist
# Warten ein Warten fuer niemanden: der Anrufer hat sein eigenes Timeout, und
# eine Antwort nach seiner Frist kostet die Quelle eine Anfrage und bringt
# nichts. Stand vorher als nackte 10 in der Bedingung — ein Test darueber
# haette die Zahl ein zweites Mal hinschreiben muessen und damit sich selbst
# zugestimmt.
MAX_RATE_LIMIT_WAIT = 10.0

# Das Warten unter einem Namen dieses Moduls. Ein Test, der stattdessen
# `api_infrastructure.asyncio.sleep` uebernimmt, greift ins stdlib-Modul —
# `.asyncio` *ist* `asyncio` — und ersetzt die Funktion im ganzen Prozess statt
# nur hier. Ohne diesen Namen liess sich das Tor unten gar nicht pruefen, ausser
# durch echtes Warten; es war denn auch ungeprueft, beide Zweige.
_sleep = asyncio.sleep

# Das Timeout des HTTP-Clients, an genau einer Stelle. Es stand doppelt da:
# einmal als Argument im Konstruktor, einmal als "30s" im Text der
# Timeout-Meldung. Wer das eine anhebt und das andere vergisst, laesst den
# Server eine Frist nennen, die er gar nicht faehrt.
REQUEST_TIMEOUT = 30.0

# Wie oft ein Versuch wiederholt wird, der die Quelle gar nicht erreicht hat.
#
# Die Trennlinie ist nicht der Statuscode, sondern ob die Quelle ueberhaupt
# geantwortet hat. Ein Statuscode ist eine Auskunft und faellt beim zweiten
# Mal gleich aus — ihn zu wiederholen kostet die Quelle eine Anfrage und
# bringt nichts. Ein abgerissener Verbindungsaufbau ist keine Auskunft und
# faellt womoeglich anders aus.
#
# Genau daran starb der naechtliche Live-Lauf vom 7.9.2026: ein
# httpx.ConnectError auf data.geo.admin.ch, waehrend drei andere Tests
# desselben Laufs dieselbe URL erfolgreich luden. Die Quelle war da, dieser
# eine Aufbau nicht — und dasselbe traf produktiv jeden Anrufer, der zufaellig
# in denselben Zappler lief.
MAX_TRANSIENT_RETRIES = 2
RETRY_BACKOFF_SECONDS = 0.5

# Wiederholt wird nur, was schnell scheitert. Ein ConnectTimeout oder
# ReadTimeout hat die Uhr vollaufen lassen; ihn zu wiederholen verdreifacht
# die Wartezeit des Anrufers, ohne dass sich an der Ursache etwas geaendert
# haette — der Anrufer hat sein eigenes Timeout und ist dann laengst weg.
# Diese hier brechen binnen Millisekunden ab, ein zweiter Versuch ist billig.
# (In httpx erben die Timeout-Klassen von TimeoutException, die Klassen hier
# von NetworkError bzw. ProtocolError; sie ueberschneiden sich nicht.)
TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
)


# =============================================================================
# Rate Limiter – Der Türsteher
# =============================================================================


@dataclass
class RateLimiter:
    """
    Sliding-Window Rate Limiter.

    Auch wenn die APIs offen sind, bombardieren wir sie nicht.
    Metapher: Wie ein Zebrastreifen – man DARF rüber,
    aber rennt trotzdem nicht blindlings los.
    """

    max_requests: int
    window_seconds: float
    _timestamps: list = field(default_factory=list)

    def _clean_old(self):
        cutoff = time.monotonic() - self.window_seconds
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    def can_proceed(self) -> bool:
        self._clean_old()
        return len(self._timestamps) < self.max_requests

    def record(self):
        self._timestamps.append(time.monotonic())

    def wait_time(self) -> float:
        self._clean_old()
        if self.can_proceed():
            return 0.0
        oldest = self._timestamps[0]
        return (oldest + self.window_seconds) - time.monotonic()


# =============================================================================
# Cache – Die Wandtafel
# =============================================================================


@dataclass
class CacheEntry:
    data: Any
    created_at: float
    ttl: float

    @property
    def is_expired(self) -> bool:
        return (time.monotonic() - self.created_at) > self.ttl


class SimpleCache:
    """
    In-Memory Cache mit TTL.

    Warum? E-Ladestationen bewegen sich nicht. Shared-Mobility-Daten
    ändern sich alle ~60 Sekunden. Wir cachen aggressiv.

    Metapher: Wie ein Veloständer-Plan an der Wand –
    stimmt nicht sekundengenau, aber reicht für die Planung.
    """

    def __init__(self, max_entries: int = 200):
        self._store: dict[str, CacheEntry] = {}
        self._max_entries = max_entries

    def _make_key(self, prefix: str, params: dict) -> str:
        raw = f"{prefix}:{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, prefix: str, params: dict) -> Any | None:
        key = self._make_key(prefix, params)
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired:
            del self._store[key]
            return None
        logger.debug(f"Cache HIT für {prefix}")
        return entry.data

    def set(self, prefix: str, params: dict, data: Any, ttl: float):
        if len(self._store) >= self._max_entries:
            self._evict_expired()
        key = self._make_key(prefix, params)
        self._store[key] = CacheEntry(data=data, created_at=time.monotonic(), ttl=ttl)

    def _evict_expired(self):
        expired = [k for k, v in self._store.items() if v.is_expired]
        for k in expired:
            del self._store[k]

    def clear(self):
        self._store.clear()


# =============================================================================
# HTTP Client – Offen, aber höflich
# =============================================================================


class MobilityHTTPClient:
    """
    Zentraler HTTP-Client für offene Mobilitäts-APIs.

    Im Gegensatz zum Transport-Server brauchen wir hier:
    - KEINEN API-Key (alles Open Data!)
    - Rate Limiting (Höflichkeit)
    - Caching (Effizienz)
    - Gzip-Support (die EV-Daten sind gross)
    """

    def __init__(self):
        self._cache = SimpleCache()
        self._rate_limiters: dict[str, RateLimiter] = {}
        self._client = async_client(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Encoding": "gzip, deflate",
            },
        )

    def register_limiter(self, name: str, limiter: RateLimiter):
        self._rate_limiters[name] = limiter

    async def get_json(
        self,
        url: str,
        params: dict | None = None,
        cache_prefix: str = "default",
        cache_ttl: float = 60.0,
        use_cache: bool = True,
        limiter_name: str | None = None,
    ) -> Any:
        """
        GET-Request mit Cache und Rate Limiting.

        Ablauf:
        1. Cache prüfen → Treffer? Sofort zurück.
        2. Rate Limit prüfen → Warten falls nötig.
        3. Request senden → JSON parsen.
        4. Cache befüllen → Für nächste Anfrage.
        """
        params = params or {}
        cache_params = {"url": url, **params}

        # 1. Cache
        if use_cache:
            cached = self._cache.get(cache_prefix, cache_params)
            if cached is not None:
                return cached

        # 2. Rate Limit
        if limiter_name and limiter_name in self._rate_limiters:
            limiter = self._rate_limiters[limiter_name]
            if not limiter.can_proceed():
                wait = limiter.wait_time()
                if wait > MAX_RATE_LIMIT_WAIT:
                    raise APIError(f"Rate Limit für '{limiter_name}' erreicht. Nächste Abfrage in {wait:.0f}s möglich.")
                await _sleep(wait)
            limiter.record()

        # 3. Request
        response = await self._get_with_retries(url, params)

        # 4. Parse & Cache
        result = response.json()
        self._cache.set(cache_prefix, cache_params, result, cache_ttl)
        return result

    async def _get_with_retries(self, url: str, params: dict) -> httpx.Response:
        """
        GET mit Wiederholung genau der Fehler, bei denen die Quelle schweigt.

        Metapher: Beim Anrufen gibt ein Besetztzeichen keine Auskunft ueber den
        Anschluss — man waehlt noch einmal. Eine Absage der Person am anderen
        Ende dagegen wiederholt sich, wenn man sie wiederholt.

        Der Tuersteher zaehlt den Aufruf einmal, nicht je Versuch: gezaehlt
        wird, was die Quelle Arbeit kostet, und ein Aufbau, der nie zustande
        kam, kostet sie keine. Wiederholt werden ohnehin nur Fehlschlaege —
        eine Antwort beendet die Schleife.

        Ein von der Egress-Allowlist blockierter Host (`EgressBlockedError`,
        SEC-004/005) faellt hier nicht hinein: die Sperre ist keine
        httpx-Exception und keine Aussage ueber die Erreichbarkeit. Sie
        durchlaeuft die Schleife ungefangen, wie sie soll.
        """
        letzter: Exception | None = None

        for versuch in range(MAX_TRANSIENT_RETRIES + 1):
            # Die Pause steht vor dem Versuch, nicht hinter dem Fehlschlag:
            # so gibt es keinen Zweig, der nach dem letzten Versuch noch
            # wartet, ohne dass jemand auf das Ergebnis dieses Wartens wartet.
            if versuch:
                await _sleep(RETRY_BACKOFF_SECONDS * 2 ** (versuch - 1))

            try:
                response = await self._client.get(url, params=params)
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                # OBS-002: log the raw upstream body server-side, but never
                # surface it to the caller/LLM (information disclosure). The
                # client sees a generic, status-only message.
                logger.warning(
                    "Upstream HTTP %s from %s: %s",
                    e.response.status_code,
                    url,
                    e.response.text[:200],
                )
                raise APIError(f"Die Datenquelle antwortete mit HTTP {e.response.status_code}.") from e
            except httpx.TimeoutException as e:
                raise APIError(f"Timeout nach {REQUEST_TIMEOUT:.0f}s für {url}") from e
            except TRANSIENT_ERRORS as e:
                letzter = e
                logger.warning(
                    "Verbindungsversuch %s/%s zu %s gescheitert (%s).",
                    versuch + 1,
                    MAX_TRANSIENT_RETRIES + 1,
                    url,
                    type(e).__name__,
                )

        # Die Zahl gehoert in die Meldung: "fehlgeschlagen" allein liest sich
        # wie ein einmaliger Zufall und laedt zum Nachfassen ein. Nach drei
        # Aufbauversuchen ist das Nachfassen schon geschehen.
        versuche = MAX_TRANSIENT_RETRIES + 1
        raise APIError(f"Verbindung zu {url} fehlgeschlagen (nach {versuche} Versuchen).") from letzter

    async def close(self):
        await self._client.aclose()


# =============================================================================
# Geo-Hilfsfunktionen
# =============================================================================


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Distanz zwischen zwei GPS-Koordinaten in Kilometern.

    Metapher: Wie eine Schnur auf dem Globus spannen –
    misst die Luftlinie, nicht den Strassenverlauf.
    """
    R = 6371.0  # Erdradius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# =============================================================================
# Fehlerklassen
# =============================================================================


class APIError(Exception):
    """Allgemeiner API-Fehler."""

    pass
