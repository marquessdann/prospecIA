from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.filters import BusinessFilters, apply_sort
from app.db import get_db
from app.models import Business, Interaction, Organization, Role, User
from app.schemas import (
    BulkUpdate,
    BusinessDetail,
    BusinessOut,
    BusinessUpdate,
    InteractionIn,
    InteractionOut,
    Page,
)
from app.security import ROLE_RANK, get_current_user, require_role
from app.services.scoring import compute_score
from app.services.search_runner import schedule_verification
from app.verification.normalize import normalize_name, normalize_phone

router = APIRouter(prefix="/api/businesses", tags=["businesses"])

LEAD_STATUS_LABELS = {
    "novo": "Novo lead", "revisado": "Lead revisado", "contato_realizado": "Contato realizado",
    "aguardando_resposta": "Aguardando resposta", "interessado": "Interessado",
    "proposta_enviada": "Proposta enviada", "convertido": "Cliente convertido",
    "sem_interesse": "Sem interesse", "nao_contatar": "Não contatar",
}


def _get(db: Session, user: User, business_id: int) -> Business:
    b = db.get(Business, business_id)
    if not b or b.org_id != user.org_id:
        raise HTTPException(404, "Empresa não encontrada")
    return b


@router.get("", response_model=Page)
def list_businesses(
    filters: BusinessFilters = Depends(),
    sort: str | None = "lead_score",
    order: str | None = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    base = filters.apply(select(Business), user.org_id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    stmt = apply_sort(base, sort, order).offset((page - 1) * page_size).limit(page_size)
    return Page(items=list(db.scalars(stmt)), total=total, page=page, page_size=page_size)


@router.get("/map")
def map_points(filters: BusinessFilters = Depends(), limit: int = Query(2000, le=5000),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = filters.apply(select(Business.id, Business.name, Business.lat, Business.lng, Business.digital_status,
                                Business.lead_score, Business.category, Business.city, Business.is_fictitious),
                         user.org_id).where(Business.lat.is_not(None)).limit(limit)
    return [dict(r._mapping) for r in db.execute(stmt)]


@router.get("/{business_id}", response_model=BusinessDetail)
def get_business(business_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = db.scalar(select(Business).where(Business.id == business_id, Business.org_id == user.org_id)
                  .options(selectinload(Business.source_records), selectinload(Business.verifications),
                           selectinload(Business.interactions).selectinload(Interaction.user)))
    if not b:
        raise HTTPException(404, "Empresa não encontrada")
    detail = BusinessDetail.model_validate(b)
    for i, it in enumerate(b.interactions):
        detail.interactions[i].user_name = it.user.name if it.user else None
    return detail


@router.patch("/{business_id}", response_model=BusinessOut)
def update_business(business_id: int, data: BusinessUpdate, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    b = _get(db, user, business_id)
    changes = data.model_dump(exclude_unset=True)
    if "digital_status" in changes and ROLE_RANK.get(user.role, 0) < ROLE_RANK[Role.manager.value]:
        raise HTTPException(403, "Somente gestores podem corrigir manualmente a classificação")
    old_status = b.lead_status
    for k, v in changes.items():
        setattr(b, k, v.value if hasattr(v, "value") else v)
    if "name" in changes:
        b.normalized_name = normalize_name(b.name)
    if "phone" in changes:
        b.phone_normalized = normalize_phone(b.phone)
    if "digital_status" in changes:
        b.classification_reason = f"Classificação corrigida manualmente por {user.name}."
        b.confidence = 100
    if "lead_status" in changes and changes["lead_status"] != old_status:
        db.add(Interaction(business_id=b.id, user_id=user.id, kind="status_change",
                           content=f"Status: {LEAD_STATUS_LABELS.get(old_status, old_status)} → "
                                   f"{LEAD_STATUS_LABELS.get(b.lead_status, b.lead_status)}"))
    org = db.get(Organization, user.org_id)
    b.lead_score, b.score_breakdown = compute_score(b, org.scoring_weights if org else None)
    db.commit()
    return b


@router.delete("/{business_id}", status_code=204)
def delete_business(business_id: int, user: User = Depends(require_role(Role.manager)), db: Session = Depends(get_db)):
    """Exclusão definitiva do registro e do histórico (atende pedidos de eliminação — LGPD)."""
    b = _get(db, user, business_id)
    db.delete(b)
    db.commit()


@router.post("/{business_id}/verify")
def reverify(business_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = _get(db, user, business_id)
    # Verificação avulsa usa as opções padrão e é contabilizada para o usuário.
    if not schedule_verification(db, b, None, force=True, user_id=user.id):
        return {"queued": False, "detail": "Verificação já está na fila"}
    db.commit()
    return {"queued": True}


@router.post("/{business_id}/interactions", response_model=InteractionOut, status_code=201)
def add_interaction(business_id: int, data: InteractionIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    b = _get(db, user, business_id)
    it = Interaction(business_id=b.id, user_id=user.id, kind=data.kind, content=data.content)
    db.add(it)
    db.commit()
    out = InteractionOut.model_validate(it)
    out.user_name = user.name
    return out


@router.post("/bulk")
def bulk_update(data: BulkUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = list(db.scalars(select(Business).where(Business.org_id == user.org_id, Business.id.in_(data.ids))))
    for b in items:
        if data.lead_status and b.lead_status != data.lead_status.value:
            db.add(Interaction(business_id=b.id, user_id=user.id, kind="status_change",
                               content=f"Status: {LEAD_STATUS_LABELS.get(b.lead_status)} → {LEAD_STATUS_LABELS.get(data.lead_status.value)} (em lote)"))
            b.lead_status = data.lead_status.value
        if data.assignee_id is not None:
            b.assignee_id = data.assignee_id or None
    db.commit()
    return {"updated": len(items)}


@router.post("/bulk-verify")
def bulk_verify(data: BulkUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = list(db.scalars(select(Business).where(Business.org_id == user.org_id, Business.id.in_(data.ids),
                                                   Business.is_fictitious.is_(False))))
    queued = sum(1 for b in items if schedule_verification(db, b, None, force=True, user_id=user.id))
    db.commit()
    return {"queued": queued}
