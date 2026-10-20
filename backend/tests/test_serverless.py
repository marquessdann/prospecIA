"""Modo serverless (Vercel): ticks com prazo, cron autenticado, travas e URL do banco."""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, settings
from app.db import SessionLocal
from app.main import app
from app.models import Job, SearchUnit
from app.services import locks
from app.worker import _handle, run_tick
from tests.test_api_flow import H, SEARCH, fake_sources, register  # noqa: F401 - fixture reutilizada


@pytest.fixture
def request_mode(monkeypatch):
    monkeypatch.setattr(settings, "processing_mode", "request")
    monkeypatch.setattr(settings, "tick_budget_seconds", 10)


def test_ticks_pelo_navegador_concluem_a_pesquisa(request_mode, fake_sources):
    with TestClient(app) as c:
        register(c)
        s = c.post("/api/searches", json=SEARCH, headers=H).json()
        assert c.get("/api/worker/status").json()["pending_jobs"] == 1
        for _ in range(10):
            r = c.post("/api/worker/tick", headers=H).json()
            assert r["ran"]
            if r["pending_jobs"] == 0:
                break
        d = c.get(f"/api/searches/{s['id']}").json()
        assert d["status"] == "completed" and d["total_verified"] == 3


def test_tick_sem_login_e_bloqueado(request_mode):
    with TestClient(app) as c:
        assert c.post("/api/worker/tick", headers=H).status_code == 401


def test_cron_exige_segredo(request_mode, monkeypatch):
    with TestClient(app) as c:
        monkeypatch.setattr(settings, "cron_secret", None)
        assert c.get("/api/worker/cron").status_code == 401  # sem segredo configurado, nunca libera
        monkeypatch.setattr(settings, "cron_secret", "s3gredo")
        assert c.get("/api/worker/cron", headers={"Authorization": "Bearer errado"}).status_code == 401
        r = c.get("/api/worker/cron", headers={"Authorization": "Bearer s3gredo"})
        assert r.status_code == 200 and r.json()["ran"]


def test_pesquisa_continua_de_onde_parou_quando_o_tempo_acaba(request_mode, fake_sources):
    places, _ = fake_sources
    with TestClient(app) as c:
        register(c)
        s = c.post("/api/searches", json=SEARCH, headers=H).json()
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.kind == "run_search").one()
        job_id, payload = job.id, job.payload
        job.status, job.attempts = "running", 1
        db.commit()

    async def expired():
        import httpx
        async with httpx.AsyncClient() as client:
            await _handle(job_id, "run_search", payload, client, None, deadline=time.monotonic() - 1)
    asyncio.run(expired())
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        assert job.status == "queued" and job.attempts == 0  # adiada sem gastar tentativa
        assert db.query(SearchUnit).one().status == "pending"
    assert places.calls == 0
    asyncio.run(run_tick(budget_s=10))
    with TestClient(app) as c:
        c.post("/api/auth/login", json={"email": "ana@ex.com", "password": "senha-forte-1"})
        assert c.get(f"/api/searches/{s['id']}").json()["status"] == "completed"


def test_trava_impede_ticks_simultaneos():
    t = locks.acquire("x", 60)
    assert t and locks.acquire("x", 60) is None
    locks.release("x", t)
    assert locks.acquire("x", 60)
    r = asyncio.run(_tick_busy())
    assert r["ran"] is False


async def _tick_busy():
    locks.acquire("worker_tick", 60)
    return await run_tick(budget_s=5)


def test_url_do_neon_e_normalizada():
    s = Settings(database_url="postgres://u:p@ep-x-pooler.neon.tech/db?sslmode=require",
                 database_url_unpooled="postgresql://u:p@ep-x.neon.tech/db?sslmode=require")
    assert s.database_url.startswith("postgresql+psycopg://u:p@ep-x-pooler")
    assert s.database_url_unpooled.startswith("postgresql+psycopg://")


def test_painel_de_atividade_mostra_espera_de_nova_tentativa(request_mode, fake_sources):
    places, _ = fake_sources
    places.fail_times = 1
    with TestClient(app) as c:
        register(c)
        s = c.post("/api/searches", json=SEARCH, headers=H).json()
        assert c.get(f"/api/searches/{s['id']}").json()["activity"]["state"] == "queued"
        c.post("/api/worker/tick", headers=H)
        d = c.get(f"/api/searches/{s['id']}").json()
        a = d["activity"]
        assert a["state"] == "waiting_retry" and a["next_retry_at"] and "tentativa 2 de" in a["message"]
        assert any("Buscando 'barbearias'" in e["message"] for e in d["events"])
