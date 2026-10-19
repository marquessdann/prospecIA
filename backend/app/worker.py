"""Worker de tarefas em background.

Uso: `python -m app.worker` (ou RUN_WORKER_IN_API=true para rodar dentro da API em dev).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import time

import httpx

from app.config import settings
from app.db import SessionLocal
from app.models import Job
from app.services import queue
from app.services.cache import purge_expired
from app.providers.base import ProviderError
from app.services.search_runner import (
    Defer,
    RetryLater,
    mark_search_failed,
    mark_verification_failed,
    purge_retention,
    run_search,
    run_verification,
)
from app.verification.site_checker import SiteChecker

log = logging.getLogger("prospecia.worker")


async def _handle(job_id: int, kind: str, payload: dict, client: httpx.AsyncClient, checker: SiteChecker) -> None:
    error: str | None = None
    retryable = True
    deferred = False
    try:
        if kind == "run_search":
            await run_search(payload["search_id"], client)
        elif kind == "verify_business":
            await run_verification(payload, client, checker)
        else:
            raise ValueError(f"tipo de tarefa desconhecido: {kind}")
    except Defer:
        deferred = True
    except RetryLater as e:
        error = str(e)
    except ProviderError as e:
        error, retryable = str(e), e.retryable
    except Exception as e:  # noqa: BLE001 - registrar qualquer falha inesperada
        log.exception("falha na tarefa %s", job_id)
        error = f"{e.__class__.__name__}: {e}"
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        if deferred:
            queue.defer(db, job, 30)
            return
        if error is None:
            queue.complete(db, job)
            return
        will_retry = queue.fail(db, job, error, retryable)
        if not will_retry and kind == "verify_business":
            mark_verification_failed(payload, error)
        if not will_retry and kind == "run_search":
            mark_search_failed(payload["search_id"], error)
        log.warning("tarefa %s (%s) falhou: %s — %s", job_id, kind, error, "nova tentativa" if will_retry else "desistindo")


async def run_worker(stop: asyncio.Event, concurrency: int | None = None, idle_exit: bool = False) -> None:
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    concurrency = concurrency or settings.worker_concurrency
    running: set[asyncio.Task] = set()
    last_maintenance = 0.0
    async with httpx.AsyncClient(timeout=60, headers={"User-Agent": "ProspecIA/1.0"}) as client:
        checker = SiteChecker()
        try:
            while not stop.is_set():
                if time.monotonic() - last_maintenance > 300:
                    last_maintenance = time.monotonic()
                    with SessionLocal() as db:
                        if n := queue.recover_stale(db):
                            log.info("%s tarefas recuperadas para retomada", n)
                    purge_expired()
                    purge_retention()
                free = concurrency - len(running)
                claimed = []
                if free > 0:
                    with SessionLocal() as db:
                        claimed = [(j.id, j.kind, j.payload) for j in queue.claim(db, worker_id, free)]
                for job_id, kind, payload in claimed:
                    t = asyncio.create_task(_handle(job_id, kind, payload, client, checker))
                    running.add(t)
                    t.add_done_callback(running.discard)
                if not claimed:
                    if idle_exit and not running:
                        return
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_seconds)
                    except asyncio.TimeoutError:
                        pass
                else:
                    await asyncio.sleep(0)
            if running:
                await asyncio.wait(running, timeout=30)
        finally:
            await checker.aclose()


def main() -> None:
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stop = asyncio.Event()

    async def _main():
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        log.info("worker iniciado (concorrência=%s)", settings.worker_concurrency)
        await run_worker(stop)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
