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

import hashlib
import json
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger("swiss-road-mobility-mcp")


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
        self._client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "swiss-road-mobility-mcp/0.1.0",
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
                if wait > 10:
                    raise APIError(
                        f"Rate Limit für '{limiter_name}' erreicht. "
                        f"Nächste Abfrage in {wait:.0f}s möglich."
                    )
                import asyncio
                await asyncio.sleep(wait)
            limiter.record()

        # 3. Request
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise APIError(
                f"HTTP {e.response.status_code} von {url}: "
                f"{e.response.text[:200]}"
            )
        except httpx.TimeoutException:
            raise APIError(f"Timeout nach 30s für {url}")
        except httpx.ConnectError:
            raise APIError(f"Verbindung zu {url} fehlgeschlagen.")

        # 4. Parse & Cache
        result = response.json()
        self._cache.set(cache_prefix, cache_params, result, cache_ttl)
        return result

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
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# =============================================================================
# Fehlerklassen
# =============================================================================

class APIError(Exception):
    """Allgemeiner API-Fehler."""
    pass
