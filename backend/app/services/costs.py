"""Estimativa de custos e controle de consumo por usuário."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ApiUsage, User
from app.providers.registry import place_provider, web_provider
from app.services import quota

# Premissas da estimativa (ajuste conforme seu histórico real).
AI_INPUT_TOKENS_PER_CALL = 1800
AI_OUTPUT_TOKENS_PER_CALL = 350
AI_CALL_RATE = 0.35  # fração das empresas que chegam a casos ambíguos e acionam a IA


def _quota_note(provider: str, requests: int, warnings: list[str]) -> dict:
    """Anexa a situação da cota gratuita à linha da estimativa e gera avisos."""
    u = quota.usage(provider)
    if not u:
        return {}
    per = "mês" if u["period"] == "month" else "dia"
    note = f"cota grátis: {u['used']}/{u['effective_limit']} usadas no {per}, restam {u['remaining']}"
    if requests > u["remaining"]:
        if settings.free_tier_only:
            warnings.append(f"{u['label']}: a pesquisa pode precisar de ~{requests} requisições, mas restam {u['remaining']} "
                            f"grátis no {per}. Ela vai parar sozinha ao atingir a cota — sem cobrança.")
        else:
            warnings.append(f"{u['label']}: ~{requests} requisições excedem as {u['remaining']} grátis restantes; o excedente será cobrado.")
    return {"note": note, "quota": u}


def estimate(config: dict) -> dict:
    locations = config.get("locations") or []
    categories = config.get("categories") or []
    sources = config.get("sources") or []
    max_results = int(config.get("max_results") or settings.default_max_results_per_search)
    units = max(1, len(locations)) * max(1, len(categories))
    lines = []
    warnings: list[str] = []
    total = 0.0
    free = settings.free_tier_only
    expected_businesses = 0
    for s in sources:
        p = place_provider(s)
        if not p:
            continue
        per_unit = min(max_results, p.max_results_per_query or max_results)
        expected_businesses += per_unit * units
        if p.name == "google_places":
            requests = units * math.ceil(per_unit / 20)
        else:
            requests = units * 2  # geocodificação + consulta
        cost = requests * p.billable_cost()
        total += cost
        lines.append({"provider": p.label, "requests": requests, "unit_cost_usd": p.billable_cost(),
                      "cost_usd": round(cost, 4), "available": p.available(), **_quota_note(p.name, requests, warnings)})
    expected_businesses = min(expected_businesses, max_results * units)
    if config.get("web_verification", True):
        w = web_provider(config.get("web_provider"))
        if w:
            per_business = int(config.get("web_queries_per_business") or settings.web_queries_per_business)
            q = expected_businesses * per_business
            cost = q * w.billable_cost()
            total += cost
            lines.append({"provider": w.label, "requests": q, "unit_cost_usd": w.billable_cost(),
                          "cost_usd": round(cost, 4), "available": True, **_quota_note(w.name, q, warnings)})
        else:
            lines.append({"provider": "Busca web", "requests": 0, "unit_cost_usd": 0, "cost_usd": 0,
                          "available": False, "note": "Nenhum provedor configurado: empresas sem site no cadastro ficarão como 'Site não informado no Maps'."})
    if config.get("use_ai", True) and settings.ai_enabled:
        calls = int(expected_businesses * AI_CALL_RATE)
        per_call = (AI_INPUT_TOKENS_PER_CALL * settings.ai_input_price_per_mtok
                    + AI_OUTPUT_TOKENS_PER_CALL * settings.ai_output_price_per_mtok) / 1_000_000
        total += calls * per_call
        lines.append({"provider": f"IA ({settings.ai_model})", "requests": calls, "unit_cost_usd": round(per_call, 5),
                      "cost_usd": round(calls * per_call, 4), "available": True})
    return {
        "units": units,
        "expected_businesses_max": expected_businesses,
        "lines": lines,
        "total_usd": round(total, 4),
        "free_tier_only": free,
        "quota_warnings": warnings,
        "disclaimer": ("Modo somente gratuito: nenhuma requisição além da cota grátis é feita, então o custo é zero. "
                       if free else "") + ("Estimativa máxima baseada nos preços configurados (USD). Créditos gratuitos mensais dos "
                       "provedores, cache e resultados menores que o limite reduzem o custo real."),
    }


def month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def user_month_spend(db: Session, user_id: int) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(ApiUsage.cost_usd), 0.0))
                           .where(ApiUsage.user_id == user_id, ApiUsage.created_at >= month_start())) or 0.0)


def budget_status(db: Session, user: User) -> dict:
    spent = user_month_spend(db, user.id)
    remaining = max(0.0, user.monthly_budget_usd - spent)
    pct = (spent / user.monthly_budget_usd * 100) if user.monthly_budget_usd else 100.0
    level = "ok" if pct < 80 else ("warning" if pct < 100 else "exceeded")
    return {"monthly_budget_usd": user.monthly_budget_usd, "spent_usd": round(spent, 4),
            "remaining_usd": round(remaining, 4), "percent": round(pct, 1), "level": level}


def record_usage(db: Session, *, org_id: int, user_id: int | None, search_id: int | None, provider: str,
                 operation: str, units: int, cost: float, cached: bool = False) -> None:
    db.add(ApiUsage(org_id=org_id, user_id=user_id, search_id=search_id, provider=provider, operation=operation,
                    units=units, cost_usd=cost, cached=cached))
