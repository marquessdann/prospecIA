"""Travas com prazo no banco, seguras para funções serverless e poolers em modo transação."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import AppLock, utcnow


def acquire(name: str, seconds: float) -> str | None:
    """Tenta obter a trava por `seconds`. Retorna um token do dono ou None se já estiver em uso."""
    token = uuid.uuid4().hex
    until = utcnow() + timedelta(seconds=seconds)
    with SessionLocal() as db:
        if db.scalar(select(AppLock.name).where(AppLock.name == name)) is None:
            try:
                db.add(AppLock(name=name, locked_until=until, holder=token))
                db.commit()
                return token
            except IntegrityError:
                db.rollback()
        res = db.execute(update(AppLock).where(AppLock.name == name, AppLock.locked_until < utcnow())
                         .values(locked_until=until, holder=token))
        db.commit()
        return token if res.rowcount == 1 else None


def release(name: str, token: str) -> None:
    with SessionLocal() as db:
        db.execute(delete(AppLock).where(AppLock.name == name, AppLock.holder == token))
        db.commit()
