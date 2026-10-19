"""Limitadores de taxa por provedor.

Com REDIS_URL configurado o limite é compartilhado entre todos os workers/processos;
sem Redis, usa um limitador em memória por processo.
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.config import settings

log = logging.getLogger(__name__)


class MemoryRateLimiter:
    def __init__(self, rps: float):
        self.interval = 1.0 / rps if rps > 0 else 0.0
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self.interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = self._next - now
            self._next = max(now, self._next) + self.interval
        if wait > 0:
            await asyncio.sleep(wait)


class RedisRateLimiter:
    """Reserva "fatias" de tempo com SET NX PX: no máximo `rps` requisições/s no cluster."""

    def __init__(self, name: str, rps: float, redis_client):
        self.key = f"prospecia:rl:{name}"
        self.interval_ms = max(1, int(1000 / rps)) if rps > 0 else 0
        self.redis = redis_client

    async def acquire(self) -> None:
        if self.interval_ms <= 0:
            return
        for _ in range(600):
            ok = await self.redis.set(self.key, "1", nx=True, px=self.interval_ms)
            if ok:
                return
            ttl = await self.redis.pttl(self.key)
            await asyncio.sleep(max(ttl, 5) / 1000)
        raise TimeoutError(f"rate limiter {self.key} indisponível")


_limiters: dict[str, object] = {}
_redis = None


def _redis_client():
    global _redis
    if _redis is None and settings.redis_url:
        try:
            import redis.asyncio as aioredis

            _redis = aioredis.from_url(settings.redis_url)
        except Exception as e:  # pragma: no cover - depende do ambiente
            log.warning("Redis indisponível para rate limit (%s); usando memória", e)
    return _redis


def get_limiter(name: str, rps: float):
    key = f"{name}:{asyncio.get_running_loop().__hash__()}"
    if key not in _limiters:
        client = _redis_client()
        _limiters[key] = RedisRateLimiter(name, rps, client) if client else MemoryRateLimiter(rps)
    return _limiters[key]
