"""Processamento da fila em modo serverless (Vercel): ticks curtos disparados pelo navegador ou por cron."""

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.models import User
from app.security import get_current_user
from app.worker import queue_status, run_tick

router = APIRouter(prefix="/api/worker", tags=["worker"])


@router.get("/status")
def status(user: User = Depends(get_current_user)):
    return {"processing_mode": settings.processing_mode, **queue_status()}


@router.post("/tick")
async def tick(user: User = Depends(get_current_user)):
    """Chamado pelo navegador enquanto houver tarefas pendentes."""
    if settings.processing_mode != "request":
        return {"ran": False, "reason": "worker dedicado em uso (PROCESSING_MODE=worker)", **queue_status()}
    return await run_tick()


@router.get("/cron")
async def cron(request: Request):
    """Chamado pelo cron da Vercel (ou cron-job.org) com Authorization: Bearer <CRON_SECRET>."""
    expected = f"Bearer {settings.cron_secret}" if settings.cron_secret else None
    got = request.headers.get("authorization", "")
    if not expected or not hmac.compare_digest(got, expected):
        raise HTTPException(401, "Não autorizado")
    return await run_tick()
