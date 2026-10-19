"""Fila de tarefas persistente no PostgreSQL (FOR UPDATE SKIP LOCKED).

Durável (sobrevive a reinícios), com novas tentativas exponenciais e recuperação de
tarefas travadas. Redis é usado para rate limit compartilhado, não como fonte da verdade.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Job, JobStatus, utcnow


def enqueue(db: Session, kind: str, payload: dict, dedup_key: str | None = None, delay_s: float = 0) -> Job | None:
    """Enfileira uma tarefa; se já existir uma pendente com o mesmo dedup_key, não duplica."""
    if dedup_key:
        existing = db.scalar(select(Job).where(Job.dedup_key == dedup_key,
                                               Job.status.in_([JobStatus.queued.value, JobStatus.running.value])))
        if existing:
            return None
    job = Job(kind=kind, payload=payload, dedup_key=dedup_key, max_attempts=settings.job_max_attempts,
              run_after=utcnow() + timedelta(seconds=delay_s))
    db.add(job)
    db.flush()
    return job


def claim(db: Session, worker_id: str, limit: int = 1, kinds: list[str] | None = None) -> list[Job]:
    q = (select(Job).where(Job.status == JobStatus.queued.value, Job.run_after <= utcnow())
         .order_by(Job.run_after, Job.id).limit(limit).with_for_update(skip_locked=True))
    if kinds:
        q = q.where(Job.kind.in_(kinds))
    jobs = list(db.scalars(q))
    now = utcnow()
    for j in jobs:
        j.status = JobStatus.running.value
        j.locked_at = now
        j.locked_by = worker_id
        j.attempts += 1
    db.commit()
    return jobs


def complete(db: Session, job: Job) -> None:
    job.status = JobStatus.done.value
    job.finished_at = utcnow()
    job.last_error = None
    db.commit()


def fail(db: Session, job: Job, error: str, retryable: bool = True) -> bool:
    """Registra falha. Retorna True se a tarefa será tentada novamente."""
    job.last_error = error[:2000]
    if retryable and job.attempts < job.max_attempts:
        job.status = JobStatus.queued.value
        job.run_after = utcnow() + timedelta(seconds=min(600, 5 * 3 ** job.attempts))
        job.locked_by = None
        db.commit()
        return True
    job.status = JobStatus.failed.value
    job.finished_at = utcnow()
    db.commit()
    return False


def defer(db: Session, job: Job, seconds: float) -> None:
    job.status = JobStatus.queued.value
    job.attempts = max(0, job.attempts - 1)
    job.run_after = utcnow() + timedelta(seconds=seconds)
    job.locked_by = None
    db.commit()


def recover_stale(db: Session) -> int:
    """Devolve à fila tarefas 'running' cujo worker morreu (permite retomar pesquisas)."""
    cutoff = utcnow() - timedelta(minutes=settings.job_stale_minutes)
    res = db.execute(update(Job).where(Job.status == JobStatus.running.value, Job.locked_at < cutoff)
                     .values(status=JobStatus.queued.value, locked_by=None))
    db.commit()
    return res.rowcount or 0
