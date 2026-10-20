"""Dashboard, exportação, configurações, consumo e saúde."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.filters import BusinessFilters, apply_sort
from app.config import settings
from app.db import get_db
from app.models import ApiUsage, Business, Organization, Role, SearchStatus, SearchTask, User
from app.providers.registry import all_infos
from app.schemas import WeightsIn
from app.security import get_current_user, require_role
from app.services import quota
from app.services.costs import budget_status, month_start
from app.services.export import to_csv, to_xlsx
from app.services.scoring import CRITERIA_LABELS, compute_score, merge_weights
from app.verification.classifier import STATUS_LABELS

router = APIRouter(prefix="/api", tags=["misc"])


@router.get("/health")
def health():
    """Diagnóstico sem dados sensíveis: banco, migrações e modo de processamento."""
    from app import migrate
    from app.db import SessionLocal

    info: dict = {"env": settings.app_env, "processing_mode": settings.processing_mode,
                  "database_configured": not settings.database_url.startswith("postgresql+psycopg://prospec:prospec@localhost"),
                  "auto_migrate": settings.auto_migrate, "migration_error": migrate.last_error}
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            info["database"] = "ok"
            try:
                info["schema_version"] = db.scalar(text("SELECT version_num FROM alembic_version"))
            except Exception:  # noqa: BLE001
                info["schema_version"] = None
    except Exception as e:  # noqa: BLE001
        info["database"] = migrate.describe_error(e)
    info["status"] = "ok" if info.get("database") == "ok" and info.get("schema_version") else "erro"
    return info


@router.get("/dashboard")
def dashboard(fictitious: bool | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    base = [Business.org_id == user.org_id]
    if fictitious is not None:
        base.append(Business.is_fictitious.is_(fictitious))
    total = db.scalar(select(func.count(Business.id)).where(*base)) or 0
    by_status = dict(db.execute(select(Business.digital_status, func.count(Business.id)).where(*base)
                                .group_by(Business.digital_status)).all())
    by_city = [{"city": c or "(sem cidade)", "count": n} for c, n in db.execute(
        select(Business.city, func.count(Business.id)).where(*base).group_by(Business.city)
        .order_by(func.count(Business.id).desc()).limit(10)).all()]
    by_category = [{"category": c or "(sem categoria)", "count": n} for c, n in db.execute(
        select(Business.category, func.count(Business.id)).where(*base).group_by(Business.category)
        .order_by(func.count(Business.id).desc()).limit(10)).all()]
    by_lead = dict(db.execute(select(Business.lead_status, func.count(Business.id)).where(*base)
                              .group_by(Business.lead_status)).all())
    social_only = db.scalar(select(func.count(Business.id)).where(*base, Business.social_only.is_(True))) or 0
    pending = db.scalar(select(func.count(Business.id)).where(*base, Business.verification_state.in_(["queued", "pending"]))) or 0
    hot = db.scalar(select(func.count(Business.id)).where(*base, Business.lead_score >= 70)) or 0
    fictitious_count = db.scalar(select(func.count(Business.id)).where(Business.org_id == user.org_id,
                                                                       Business.is_fictitious.is_(True))) or 0
    active = db.scalar(select(func.count(SearchTask.id)).where(
        SearchTask.org_id == user.org_id,
        SearchTask.status.in_([SearchStatus.queued.value, SearchStatus.running.value]))) or 0
    return {
        "total": total,
        "by_status": {k: by_status.get(k, 0) for k in STATUS_LABELS},
        "status_labels": STATUS_LABELS,
        "awaiting_verification": pending,
        "social_only": social_only,
        "hot_leads": hot,
        "by_city": by_city,
        "by_category": by_category,
        "by_lead_status": by_lead,
        "active_searches": active,
        "fictitious_count": fictitious_count,
        "budget": budget_status(db, user),
        "free_tier_only": settings.free_tier_only,
        "quotas": quota.all_usage(),
    }


def _export_rows(db: Session, user: User, filters: BusinessFilters, sort: str | None, order: str | None,
                 exclude_do_not_contact: bool) -> list[Business]:
    stmt = filters.apply(select(Business), user.org_id)
    if exclude_do_not_contact:
        stmt = stmt.where(Business.lead_status != "nao_contatar")
    return list(db.scalars(apply_sort(stmt, sort, order).limit(50000)))


@router.get("/exports/businesses.csv")
def export_csv(filters: BusinessFilters = Depends(), sort: str | None = None, order: str | None = None,
               exclude_do_not_contact: bool = Query(True), user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    data = to_csv(_export_rows(db, user, filters, sort, order, exclude_do_not_contact))
    name = f"leads-{datetime.now():%Y%m%d-%H%M}.csv"
    return Response(data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/exports/businesses.xlsx")
def export_xlsx(filters: BusinessFilters = Depends(), sort: str | None = None, order: str | None = None,
                exclude_do_not_contact: bool = Query(True), user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    data = to_xlsx(_export_rows(db, user, filters, sort, order, exclude_do_not_contact))
    name = f"leads-{datetime.now():%Y%m%d-%H%M}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/settings")
def get_settings_info(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = db.get(Organization, user.org_id)
    return {
        "providers": [p.__dict__ for p in all_infos()],
        "ai": {"enabled": settings.ai_enabled, "provider": settings.ai_provider,
               "model": settings.ai_model if settings.ai_enabled else None},
        "domain_guessing": settings.enable_domain_guessing,
        "free_tier_only": settings.free_tier_only,
        "single_user_mode": settings.single_user_mode,
        "web_queries_per_business": settings.web_queries_per_business,
        "quotas": quota.all_usage(),
        "verification_ttl_days": settings.verification_ttl_days,
        "scoring": {"weights": merge_weights(org.scoring_weights if org else None), "labels": CRITERIA_LABELS},
        "limits": {"hard_max_results_per_search": settings.hard_max_results_per_search},
        "retention": {"google_places_days": settings.google_places_retention_days},
    }


@router.put("/settings/scoring")
def update_scoring(data: WeightsIn, user: User = Depends(require_role(Role.manager)), db: Session = Depends(get_db)):
    weights = merge_weights(data.weights)
    if sum(weights.values()) <= 0:
        raise HTTPException(422, "A soma dos pesos deve ser maior que zero")
    org = db.get(Organization, user.org_id)
    org.scoring_weights = weights
    # Recalcula a pontuação de toda a base da organização.
    for b in db.scalars(select(Business).where(Business.org_id == user.org_id)):
        b.lead_score, b.score_breakdown = compute_score(b, weights)
    db.commit()
    return {"weights": weights}


@router.get("/usage")
def usage(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(ApiUsage.provider, ApiUsage.operation, func.sum(ApiUsage.units), func.sum(ApiUsage.cost_usd),
                             func.count(ApiUsage.id))
                      .where(ApiUsage.org_id == user.org_id, ApiUsage.created_at >= month_start())
                      .group_by(ApiUsage.provider, ApiUsage.operation)).all()
    per_user = db.execute(select(User.name, func.coalesce(func.sum(ApiUsage.cost_usd), 0.0))
                          .join(ApiUsage, ApiUsage.user_id == User.id)
                          .where(User.org_id == user.org_id, ApiUsage.created_at >= month_start())
                          .group_by(User.name)).all()
    return {
        "month_start": month_start().isoformat(),
        "by_provider": [{"provider": p, "operation": o, "units": int(u or 0), "cost_usd": round(float(c or 0), 4),
                         "calls": n} for p, o, u, c, n in rows],
        "by_user": [{"user": n, "cost_usd": round(float(c), 4)} for n, c in per_user],
        "quotas": quota.all_usage(),
        "free_tier_only": settings.free_tier_only,
        "budget": budget_status(db, user),
    }
