"""Aplicação FastAPI. Documentação interativa em /docs (OpenAPI)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, businesses, misc, searches
from app.config import settings

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("prospecia")

if settings.app_env == "production" and settings.secret_key == "change-me-in-production":
    raise RuntimeError("Defina SECRET_KEY em produção")


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = asyncio.Event()
    task = None
    if settings.run_worker_in_api:
        from app.worker import run_worker

        task = asyncio.create_task(run_worker(stop))
        log.info("worker embutido iniciado (RUN_WORKER_IN_API=true)")
    yield
    stop.set()
    if task:
        await task


app = FastAPI(
    title="ProspecIA API",
    version="1.0.0",
    description="Prospecção B2B: descoberta de empresas em fontes autorizadas e classificação da presença digital.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("erro não tratado em %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Erro interno. Consulte os logs do servidor."})


app.include_router(auth.router)
app.include_router(searches.router)
app.include_router(businesses.router)
app.include_router(misc.router)
