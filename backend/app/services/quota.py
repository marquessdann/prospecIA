"""Cotas gratuitas por provedor.

Cada requisição cobrável reserva uma unidade de forma atômica (UPDATE ... WHERE count < limite),
então mesmo com vários workers em paralelo o limite nunca é ultrapassado. A contagem considera
apenas as requisições feitas por este sistema: se a mesma chave for usada em outro lugar, configure
também um limite no painel do provedor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.db import SessionLocal
from app.models import ProviderQuotaUsage


@dataclass
class QuotaRule:
    provider: str
    label: str
    limit: int
    period: str  # month | day


def rules() -> dict[str, QuotaRule]:
    return {
        "google_places": QuotaRule("google_places", "Google Places (Text Search)", settings.google_places_free_monthly_requests, "month"),
        "brave_search": QuotaRule("brave_search", "Brave Search", settings.brave_search_free_monthly_requests, "month"),
        "google_cse": QuotaRule("google_cse", "Google Programmable Search", settings.google_cse_free_daily_requests, "day"),
    }


def period_key(period: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m") if period == "month" else now.strftime("%Y-%m-%d")


def effective_limit(rule: QuotaRule) -> int:
    return int(rule.limit * settings.free_tier_safety_percent / 100)


def _ensure_row(db, provider: str, period: str) -> None:
    if db.scalar(select(ProviderQuotaUsage.id).where(ProviderQuotaUsage.provider == provider,
                                                     ProviderQuotaUsage.period == period)) is None:
        try:
            db.add(ProviderQuotaUsage(provider=provider, period=period, count=0))
            db.commit()
        except IntegrityError:  # criado em paralelo por outro worker
            db.rollback()


def reserve(provider: str) -> tuple[bool, int, int]:
    """Reserva uma requisição. Retorna (permitido, usados, limite efetivo).

    Sem regra de cota (ex.: OpenStreetMap) sempre permite. Fora do modo gratuito, apenas conta.
    """
    rule = rules().get(provider)
    if rule is None:
        return True, 0, 0
    period = period_key(rule.period)
    limit = effective_limit(rule)
    with SessionLocal() as db:
        _ensure_row(db, provider, period)
        cond = [ProviderQuotaUsage.provider == provider, ProviderQuotaUsage.period == period]
        if settings.free_tier_only:
            cond.append(ProviderQuotaUsage.count < limit)
        res = db.execute(update(ProviderQuotaUsage).where(*cond).values(count=ProviderQuotaUsage.count + 1))
        db.commit()
        used = db.scalar(select(ProviderQuotaUsage.count).where(ProviderQuotaUsage.provider == provider,
                                                                ProviderQuotaUsage.period == period)) or 0
        return res.rowcount == 1, used, limit


def release(provider: str) -> None:
    """Devolve uma reserva quando a requisição nem chegou ao provedor (erro de rede)."""
    rule = rules().get(provider)
    if rule is None:
        return
    with SessionLocal() as db:
        db.execute(update(ProviderQuotaUsage)
                   .where(ProviderQuotaUsage.provider == provider, ProviderQuotaUsage.period == period_key(rule.period),
                          ProviderQuotaUsage.count > 0)
                   .values(count=ProviderQuotaUsage.count - 1))
        db.commit()


def usage(provider: str) -> dict | None:
    rule = rules().get(provider)
    if rule is None:
        return None
    period = period_key(rule.period)
    with SessionLocal() as db:
        used = db.scalar(select(ProviderQuotaUsage.count).where(ProviderQuotaUsage.provider == provider,
                                                                ProviderQuotaUsage.period == period)) or 0
    limit = effective_limit(rule)
    return {"provider": provider, "label": rule.label, "period": rule.period, "period_key": period,
            "used": used, "free_limit": rule.limit, "effective_limit": limit,
            "remaining": max(0, limit - used), "enforced": settings.free_tier_only}


def all_usage() -> list[dict]:
    return [u for p in rules() if (u := usage(p))]
