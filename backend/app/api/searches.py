from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import (
    Business,
    Job,
    JobStatus,
    SearchEvent,
    SearchResult,
    SearchStatus,
    SearchTask,
    SearchUnit,
    User,
    utcnow,
)
from app.providers.registry import place_provider
from app.schemas import SearchConfig, SearchDetail, SearchOut
from app.security import get_current_user
from app.services import queue
from app.services.costs import budget_status, estimate

router = APIRouter(prefix="/api/searches", tags=["searches"])


def _get(db: Session, user: User, search_id: int) -> SearchTask:
    s = db.get(SearchTask, search_id)
    if not s or s.org_id != user.org_id:
        raise HTTPException(404, "Pesquisa não encontrada")
    return s


def _validate(cfg: SearchConfig, user: User) -> dict:
    for s in cfg.sources:
        if place_provider(s) is None:
            raise HTTPException(422, f"Fonte desconhecida: {s}")
    data = cfg.model_dump()
    data["max_results"] = min(cfg.max_results, user.max_results_per_search, settings.hard_max_results_per_search)
    return data


@router.post("/estimate")
def estimate_search(cfg: SearchConfig, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Estimativa de custo antes de iniciar a pesquisa, com o saldo do limite mensal do usuário."""
    data = _validate(cfg, user)
    est = estimate(data)
    budget = budget_status(db, user)
    warnings = []
    unavailable = [l["provider"] for l in est["lines"] if not l.get("available")]
    if unavailable:
        warnings.append(f"Sem credenciais/indisponível: {', '.join(unavailable)}.")
    if est["total_usd"] > budget["remaining_usd"]:
        warnings.append("A estimativa máxima excede o saldo do seu limite mensal; a pesquisa será pausada ao atingir o limite.")
    warnings.extend(est.get("quota_warnings", []))
    if data["max_results"] < cfg.max_results:
        warnings.append(f"Limite de empresas ajustado para {data['max_results']} conforme seu perfil.")
    return {**est, "budget": budget, "warnings": warnings, "max_results": data["max_results"]}


@router.post("", response_model=SearchOut, status_code=201)
def create_search(cfg: SearchConfig, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = _validate(cfg, user)
    if budget_status(db, user)["level"] == "exceeded":
        raise HTTPException(402, "Limite mensal de consumo atingido. Solicite aumento ao administrador.")
    est = estimate(data)
    first_loc = data["locations"][0]
    name = cfg.name or f"{', '.join(data['categories'][:2])} — {first_loc.get('neighborhood') or first_loc.get('city') or first_loc.get('state') or 'região'}"
    s = SearchTask(org_id=user.org_id, created_by=user.id, name=name[:300], config=data,
                   estimated_cost_usd=est["total_usd"], status=SearchStatus.queued.value)
    db.add(s)
    db.flush()
    queue.enqueue(db, "run_search", {"search_id": s.id}, dedup_key=f"search:{s.id}")
    db.commit()
    return s


@router.get("", response_model=list[SearchOut])
def list_searches(limit: int = 50, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(SearchTask).where(SearchTask.org_id == user.org_id).order_by(SearchTask.id.desc()).limit(min(limit, 200))
    return list(db.scalars(q))


@router.get("/{search_id}", response_model=SearchDetail)
def get_search(search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get(db, user, search_id)
    events = list(db.scalars(select(SearchEvent).where(SearchEvent.search_id == s.id)
                             .order_by(SearchEvent.id.desc()).limit(100)))
    counts = dict(db.execute(
        select(Business.digital_status, func.count(Business.id))
        .join(SearchResult, SearchResult.business_id == Business.id)
        .where(SearchResult.search_id == s.id).group_by(Business.digital_status)).all())
    units = list(db.scalars(select(SearchUnit).where(SearchUnit.search_id == s.id).order_by(SearchUnit.id)))
    return SearchDetail.model_validate({**SearchOut.model_validate(s).model_dump(), "units": units,
                                        "events": events, "status_counts": counts,
                                        "activity": _activity(db, s, units)})


def _activity(db: Session, s: SearchTask, units: list[SearchUnit]) -> dict:
    done = sum(1 for u in units if u.status in ("done", "skipped")
               or (u.status == "error" and u.attempts >= settings.job_max_attempts))
    total = len(units)
    base = {"units_done": done, "units_total": total, "server_time": utcnow()}
    if s.status == SearchStatus.paused.value:
        return {**base, "state": "paused", "message": s.error_message or "Pesquisa pausada. Clique em Retomar para continuar."}
    if s.status == SearchStatus.cancelled.value:
        return {**base, "state": "cancelled", "message": "Pesquisa cancelada."}
    if s.status == SearchStatus.completed.value:
        return {**base, "state": "done", "message": f"Concluída: {s.total_found} empresas encontradas e {s.total_verified} verificadas."}
    if s.status == SearchStatus.failed.value:
        return {**base, "state": "failed", "message": s.error_message or "A pesquisa falhou. Use Retomar para tentar de novo."}
    job = db.scalar(select(Job).where(Job.dedup_key == f"search:{s.id}").order_by(Job.id.desc()))
    running = next((u for u in units if u.status == "running"), None)
    if job is not None and job.status == JobStatus.running.value:
        if running is not None:
            loc = ", ".join(x for x in [running.location.get("neighborhood"), running.location.get("city")] if x) or "região"
            return {**base, "state": "searching",
                    "message": f"Buscando '{running.category}' em {loc} — lote {min(done + 1, total)} de {total}."}
        return {**base, "state": "searching", "message": f"Buscando empresas — lote {min(done + 1, total)} de {total}."}
    if job is not None and job.status == JobStatus.queued.value:
        run_after = job.run_after if job.run_after.tzinfo else job.run_after.replace(tzinfo=utcnow().tzinfo)
        if run_after > utcnow() and job.attempts > 0:
            return {**base, "state": "waiting_retry", "next_retry_at": run_after,
                    "message": f"Servidor da fonte ocupado. Nova tentativa automática agendada "
                               f"(tentativa {job.attempts + 1} de {job.max_attempts})."}
        return {**base, "state": "queued", "message": "Na fila — começa em instantes."}
    if s.total_verified < s.total_to_verify:
        return {**base, "state": "verifying",
                "message": f"Verificando a presença digital: {s.total_verified} de {s.total_to_verify} empresas."}
    return {**base, "state": "queued", "message": "Finalizando…"}


@router.post("/{search_id}/pause", response_model=SearchOut)
def pause(search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get(db, user, search_id)
    if s.status in (SearchStatus.queued.value, SearchStatus.running.value):
        s.status = SearchStatus.paused.value
        db.add(SearchEvent(search_id=s.id, message="Pesquisa pausada pelo usuário."))
        db.commit()
    return s


@router.post("/{search_id}/resume", response_model=SearchOut)
def resume(search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retoma uma pesquisa pausada, interrompida ou com falhas a partir do último checkpoint."""
    s = _get(db, user, search_id)
    if s.status == SearchStatus.cancelled.value:
        raise HTTPException(409, "Pesquisa cancelada não pode ser retomada; use 'executar novamente'.")
    if budget_status(db, user)["level"] == "exceeded":
        raise HTTPException(402, "Limite mensal de consumo atingido.")
    for u in s.units:
        if u.status in ("error", "running"):
            u.status, u.attempts = "pending", 0
    s.status = SearchStatus.queued.value
    s.error_message = None
    queue.enqueue(db, "run_search", {"search_id": s.id}, dedup_key=f"search:{s.id}")
    db.add(SearchEvent(search_id=s.id, message="Pesquisa retomada a partir do último checkpoint."))
    db.commit()
    return s


@router.post("/{search_id}/cancel", response_model=SearchOut)
def cancel(search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = _get(db, user, search_id)
    if s.status not in (SearchStatus.completed.value, SearchStatus.cancelled.value):
        s.status = SearchStatus.cancelled.value
        db.add(SearchEvent(search_id=s.id, message="Pesquisa cancelada pelo usuário."))
        db.commit()
    return s


@router.post("/{search_id}/rerun", response_model=SearchOut, status_code=201)
def rerun(search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Cria uma nova execução com a mesma configuração (tarefas recorrentes por cidade/segmento)."""
    s = _get(db, user, search_id)
    return create_search(SearchConfig(**{**s.config, "name": s.name}), user, db)


@router.delete("/{search_id}", status_code=204)
def delete_search(search_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Remove a pesquisa e seu histórico (as empresas permanecem na base)."""
    s = _get(db, user, search_id)
    for j in db.scalars(select(Job).where(Job.status == JobStatus.queued.value, Job.kind == "run_search")):
        if j.payload.get("search_id") == s.id:
            db.delete(j)
    db.delete(s)
    db.commit()
