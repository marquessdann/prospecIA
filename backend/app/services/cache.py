"""Cache persistente de respostas de API (somente onde a licença do provedor permite)."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta

from sqlalchemy import delete

from app.db import SessionLocal
from app.models import ApiCache, utcnow


def cache_key(provider: str, payload: dict) -> str:
    raw = json.dumps({"p": provider, **payload}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_get(key: str) -> dict | None:
    with SessionLocal() as db:
        row = db.get(ApiCache, key)
        if row is None:
            return None
        expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=utcnow().tzinfo)
        if expires < utcnow():
            return None
        return row.response


def cache_set(key: str, provider: str, response: dict, hours: int) -> None:
    if hours <= 0:
        return
    with SessionLocal() as db:
        row = db.get(ApiCache, key)
        now = utcnow()
        if row is None:
            row = ApiCache(key=key, provider=provider)
            db.add(row)
        row.response = response
        row.created_at = now
        row.expires_at = now + timedelta(hours=hours)
        db.commit()


def purge_expired() -> int:
    with SessionLocal() as db:
        res = db.execute(delete(ApiCache).where(ApiCache.expires_at < utcnow()))
        db.commit()
        return res.rowcount or 0
