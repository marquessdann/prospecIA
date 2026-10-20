"""Execução das pesquisas (descoberta em lotes) e das verificações por empresa."""

from __future__ import annotations

import logging
from datetime import timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import (
    Business,
    BusinessSource,
    Organization,
    SearchEvent,
    SearchResult,
    SearchStatus,
    SearchTask,
    SearchUnit,
    User,
    Verification,
    utcnow,
)
from app.providers.base import Location, ProviderError
from app.providers.registry import place_provider, web_provider
from app.services import queue
from app.services.costs import budget_status, record_usage
from app.services.dedup import flag_possible_duplicates, ingest_record
from app.services.scoring import compute_score
from app.verification.ai import ai_analyzer
from app.verification.classifier import VerifyOptions, verify
from app.verification.matcher import BusinessSnapshot
from app.verification.site_checker import SiteChecker

log = logging.getLogger(__name__)


class RetryLater(Exception):
    pass


class Defer(Exception):
    """Adia a tarefa sem consumir tentativas (ex.: pesquisa pausada ou fim do tempo do tick)."""

    def __init__(self, reason: str = "", delay_s: float = 30):
        super().__init__(reason)
        self.delay_s = delay_s


def log_event(db: Session, search_id: int, message: str, level: str = "info", provider: str | None = None) -> None:
    db.add(SearchEvent(search_id=search_id, message=message[:2000], level=level, provider=provider))


def build_units(db: Session, search: SearchTask) -> None:
    if search.units:
        return
    cfg = search.config
    seen = set()
    for loc in cfg.get("locations") or [{}]:
        location = Location.from_dict(loc)
        for cat in cfg.get("categories") or []:
            for src in cfg.get("sources") or []:
                key = (src, location.key(), cat.strip().lower())
                if key in seen:
                    continue  # evita unidades duplicadas
                seen.add(key)
                db.add(SearchUnit(search_id=search.id, source=src, location=loc, location_key=location.key(),
                                  category=cat.strip()))
    db.flush()
    db.refresh(search)


def needs_verification(b: Business, force: bool = False) -> bool:
    if force or b.last_verified_at is None or b.digital_status == "VERIFICACAO_PENDENTE":
        return True
    last = b.last_verified_at if b.last_verified_at.tzinfo else b.last_verified_at.replace(tzinfo=utcnow().tzinfo)
    return last < utcnow() - timedelta(days=settings.verification_ttl_days)


def schedule_verification(db: Session, business: Business, search_id: int | None, force: bool = False,
                          user_id: int | None = None) -> bool:
    payload = {"business_id": business.id, "search_id": search_id, "force": force, "user_id": user_id}
    job = queue.enqueue(db, "verify_business", payload, dedup_key=f"verify:{business.id}")
    if job is None:
        return False
    business.verification_state = "queued"
    if search_id:
        db.execute(update(SearchTask).where(SearchTask.id == search_id)
                   .values(total_to_verify=SearchTask.total_to_verify + 1))
    return True


def maybe_finalize(db: Session, search_id: int) -> None:
    search = db.get(SearchTask, search_id)
    if search is None or search.status not in (SearchStatus.running.value,):
        return
    db.refresh(search)
    units = search.units
    if any(u.status in ("pending", "running") for u in units):
        return
    if search.total_verified < search.total_to_verify:
        return
    all_error = units and all(u.status == "error" for u in units)
    search.status = SearchStatus.failed.value if all_error and search.total_found == 0 else SearchStatus.completed.value
    search.finished_at = utcnow()
    log_event(db, search.id, f"Pesquisa finalizada: {search.total_found} empresas, {search.total_verified} verificadas.")
    db.commit()


async def run_search(search_id: int, client: httpx.AsyncClient, deadline: float | None = None) -> None:
    """Processa os lotes da pesquisa. Com `deadline` (relógio monotônico), devolve a tarefa à fila
    ao fim do tempo disponível; o checkpoint por página permite continuar exatamente de onde parou."""
    import time
    with SessionLocal() as db:
        search = db.get(SearchTask, search_id)
        if search is None or search.status in (SearchStatus.paused.value, SearchStatus.cancelled.value,
                                                SearchStatus.completed.value):
            return
        user = db.get(User, search.created_by) if search.created_by else None
        search.status = SearchStatus.running.value
        search.started_at = search.started_at or utcnow()
        build_units(db, search)
        db.commit()
        cfg = search.config
        max_results = min(int(cfg.get("max_results") or settings.default_max_results_per_search),
                          settings.hard_max_results_per_search)
        force = bool(cfg.get("force_reverify"))
        retry_needed = False

        for unit in sorted(search.units, key=lambda u: u.id):
            if unit.status in ("done", "skipped"):
                continue
            if unit.status == "error" and unit.attempts >= settings.job_max_attempts:
                continue
            db.refresh(search)
            if search.status != SearchStatus.running.value:
                log_event(db, search.id, "Pesquisa interrompida pelo usuário; progresso salvo.")
                db.commit()
                return
            if search.total_found >= max_results:
                unit.status = "skipped"
                unit.last_error = "limite de empresas por pesquisa atingido"
                db.commit()
                continue
            if user is not None:
                b = budget_status(db, user)
                if b["level"] == "exceeded":
                    search.status = SearchStatus.paused.value
                    search.error_message = "Limite mensal de consumo do usuário atingido. Ajuste o limite para retomar."
                    log_event(db, search.id, search.error_message, "warning")
                    db.commit()
                    return
            provider = place_provider(unit.source)
            if provider is None or not provider.available():
                unit.status = "error"
                unit.attempts = settings.job_max_attempts
                unit.last_error = "fonte indisponível ou sem credenciais"
                log_event(db, search.id, f"Fonte '{unit.source}' indisponível (credenciais não configuradas).", "warning", unit.source)
                db.commit()
                continue

            location = Location.from_dict(unit.location)
            unit.status = "running"
            unit.attempts += 1
            unit.last_error = None  # o erro anterior não vale mais enquanto tenta de novo
            if not unit.checkpoint:
                retry = f" (tentativa {unit.attempts})" if unit.attempts > 1 else ""
                log_event(db, search.id, f"Buscando '{unit.category}' em {location.label()} — {provider.label}{retry}…",
                          provider=provider.name)
            db.commit()
            try:
                while True:
                    if deadline is not None and time.monotonic() > deadline:
                        unit.status = "pending"
                        unit.attempts = max(0, unit.attempts - 1)
                        db.commit()
                        raise Defer("tempo do tick esgotado; continua no próximo", delay_s=0)
                    remaining = max_results - search.total_found
                    if remaining <= 0:
                        break
                    token = (unit.checkpoint or {}).get("next_token")
                    page = await provider.search(client, unit.category, location, token, remaining)
                    unit.requests_made += page.requests
                    if page.requests or page.cached:
                        record_usage(db, org_id=search.org_id, user_id=search.created_by, search_id=search.id,
                                     provider=provider.name, operation="discovery", units=max(page.requests, 1),
                                     cost=page.cost_usd, cached=page.cached)
                        search.actual_cost_usd += page.cost_usd
                    for rec in page.records[:remaining]:
                        biz, is_new = ingest_record(db, search.org_id, rec, location)
                        link = db.scalar(select(SearchResult).where(SearchResult.search_id == search.id,
                                                                    SearchResult.business_id == biz.id))
                        if link is None:
                            db.add(SearchResult(search_id=search.id, business_id=biz.id, is_new=is_new))
                            search.total_found += 1
                            search.total_new += 1 if is_new else 0
                            unit.results_count += 1
                        if is_new:
                            flag_possible_duplicates(db, search.org_id, biz)
                        if needs_verification(biz, force):
                            schedule_verification(db, biz, search.id, force)
                        elif is_new is False:
                            biz.lead_score, biz.score_breakdown = compute_score(biz, _weights(db, search.org_id))
                    unit.checkpoint = {"next_token": page.next_token} if page.next_token else None
                    db.commit()  # checkpoint salvo a cada página
                    if not page.next_token:
                        break
                unit.status = "done"
                unit.last_error = None
                log_event(db, search.id, f"{provider.label}: '{unit.category}' em {location.label()} → {unit.results_count} empresas.", provider=provider.name)
                db.commit()
            except ProviderError as e:
                db.rollback()
                unit = db.get(SearchUnit, unit.id)
                unit.status = "error"
                unit.last_error = str(e)
                level = "error"
                msg = f"Erro de integração: {e}"
                if e.quota_exhausted:
                    msg = (f"Cota gratuita de {provider.label} atingida: a busca nesta fonte parou para evitar cobrança. "
                           "Os demais lotes continuam; retome a pesquisa quando a cota renovar.")
                    search.error_message = "Cota gratuita atingida em uma das fontes. Use 'Retomar' quando a cota renovar."
                    for other in search.units:
                        if other.source == unit.source and other.status == "pending":
                            other.status, other.last_error = "error", "cota gratuita atingida"
                            other.attempts = settings.job_max_attempts
                    level = "warning"
                elif e.billing:
                    msg += " — verifique cota, faturamento e credenciais do provedor."
                if not e.retryable:
                    unit.attempts = settings.job_max_attempts
                else:
                    retry_needed = True
                log_event(db, search.id, msg, level, unit.source)
                db.commit()
        if retry_needed:
            log_event(db, search.id, "Falha temporária: nova tentativa automática agendada (backoff exponencial).", "warning")
            db.commit()
            raise RetryLater("unidades com falha temporária; nova tentativa agendada")
        maybe_finalize(db, search.id)


def _weights(db: Session, org_id: int) -> dict | None:
    org = db.get(Organization, org_id)
    return org.scoring_weights if org else None


def snapshot(b: Business) -> BusinessSnapshot:
    src_sites = [(s.source, s.website) for s in b.source_records]
    return BusinessSnapshot(id=b.id, name=b.name, city=b.city, state=b.state, country=b.country, address=b.address,
                            neighborhood=b.neighborhood, postal_code=b.postal_code,
                            phone_normalized=b.phone_normalized, category=b.category,
                            source_websites=src_sites, sources=list(b.sources or []))


def apply_outcome(db: Session, b: Business, outcome, search_id: int | None, user_id: int | None) -> Verification:
    b.digital_status = outcome.status
    b.confidence = outcome.confidence
    b.classification_reason = outcome.reason
    b.ai_summary = outcome.ai_summary
    b.official_website = outcome.official_website
    b.official_domain = outcome.official_domain
    b.candidate_website = outcome.candidate_website
    b.social_only = outcome.social_only
    if outcome.social_links:
        b.social_links = sorted(set((b.social_links or []) + outcome.social_links))[:10]
    if outcome.directory_links:
        b.directory_links = sorted(set((b.directory_links or []) + outcome.directory_links))[:10]
    if outcome.public_email and not b.email:
        b.email = outcome.public_email
    b.last_verified_at = utcnow()
    b.verification_state = "done" if outcome.status != "VERIFICACAO_PENDENTE" else "error"
    b.lead_score, b.score_breakdown = compute_score(b, _weights(db, b.org_id))
    v = Verification(business_id=b.id, search_id=search_id, status=outcome.status, confidence=outcome.confidence,
                     reason=outcome.reason, evidence=outcome.evidence, sources_consulted=outcome.sources_consulted,
                     candidates=outcome.candidates, ai_used=outcome.ai_used, ai_summary=outcome.ai_summary,
                     cost_usd=outcome.cost_usd)
    db.add(v)
    if outcome.cost_usd:
        record_usage(db, org_id=b.org_id, user_id=user_id, search_id=search_id, provider="verification",
                     operation="web_search+ai", units=max(1, outcome.web_queries), cost=outcome.cost_usd)
        if search_id:
            db.execute(update(SearchTask).where(SearchTask.id == search_id)
                       .values(actual_cost_usd=SearchTask.actual_cost_usd + outcome.cost_usd))
    return v


async def run_verification(payload: dict, client: httpx.AsyncClient, checker: SiteChecker) -> None:
    business_id = payload["business_id"]
    search_id = payload.get("search_id")
    with SessionLocal() as db:
        b = db.get(Business, business_id)
        if b is None:
            mark_verified(db, search_id)
            return
        search = db.get(SearchTask, search_id) if search_id else None
        if search is not None and search.status == SearchStatus.paused.value:
            raise Defer("pesquisa pausada")
        if search is not None and search.status == SearchStatus.cancelled.value:
            b.verification_state = "pending"
            db.commit()
            return
        cfg = (search.config if search else payload.get("options")) or {}
        user_id = search.created_by if search else payload.get("user_id")
        opts = VerifyOptions(web_search=bool(cfg.get("web_verification", True)),
                             domain_guessing=bool(cfg.get("domain_guessing", settings.enable_domain_guessing)),
                             use_ai=bool(cfg.get("use_ai", True)),
                             web_queries=int(cfg.get("web_queries_per_business") or settings.web_queries_per_business))
        web = web_provider(cfg.get("web_provider")) if opts.web_search else None
        snap = snapshot(b)
    outcome = await verify(snap, client=client, web=web, checker=checker, ai=ai_analyzer, options=opts)
    with SessionLocal() as db:
        b = db.get(Business, business_id)
        if b is None:
            return
        if outcome.status == "VERIFICACAO_PENDENTE" and any(e["type"] == "web_search" and "Falha" in e["detail"] for e in outcome.evidence):
            b.verification_state = "queued"
            db.commit()
            raise RetryLater(outcome.reason)
        apply_outcome(db, b, outcome, search_id, user_id)
        db.commit()
        mark_verified(db, search_id)


def mark_verified(db: Session, search_id: int | None) -> None:
    if not search_id:
        return
    db.execute(update(SearchTask).where(SearchTask.id == search_id)
               .values(total_verified=SearchTask.total_verified + 1))
    db.commit()
    maybe_finalize(db, search_id)


def mark_verification_failed(payload: dict, error: str) -> None:
    """Chamado quando a verificação esgota as tentativas: registra como pendente e libera a pesquisa."""
    with SessionLocal() as db:
        b = db.get(Business, payload["business_id"])
        if b is not None:
            b.verification_state = "error"
            if b.digital_status in (None, "", "VERIFICACAO_PENDENTE"):
                b.digital_status = "VERIFICACAO_PENDENTE"
                b.classification_reason = f"Não foi possível concluir a verificação: {error[:300]}"
            db.add(Verification(business_id=b.id, search_id=payload.get("search_id"), status="VERIFICACAO_PENDENTE",
                                confidence=0, reason=f"Falha após novas tentativas: {error[:500]}", evidence=[],
                                sources_consulted=[]))
            db.commit()
        mark_verified(db, payload.get("search_id"))


def mark_search_failed(search_id: int, error: str) -> None:
    """Chamado quando a descoberta esgota as tentativas: a pesquisa fica retomável manualmente."""
    with SessionLocal() as db:
        search = db.get(SearchTask, search_id)
        if search is None or search.status not in (SearchStatus.running.value, SearchStatus.queued.value):
            return
        if search.total_found > 0 and search.total_verified >= search.total_to_verify:
            search.status = SearchStatus.completed.value
            search.error_message = "Concluída parcialmente: alguns lotes falharam. Use 'Retomar' para tentar novamente."
        else:
            search.status = SearchStatus.failed.value
            search.error_message = f"Falha nas integrações após novas tentativas: {error[:300]}. Use 'Retomar'."
        search.finished_at = utcnow()
        log_event(db, search.id, search.error_message, "error")
        db.commit()


def purge_retention() -> int:
    """Remove payloads brutos de fontes cuja retenção expirou (ex.: Google Places)."""
    with SessionLocal() as db:
        res = db.execute(update(BusinessSource).where(BusinessSource.expires_at < utcnow(),
                                                      BusinessSource.raw.is_not(None)).values(raw=None))
        db.commit()
        return res.rowcount or 0
