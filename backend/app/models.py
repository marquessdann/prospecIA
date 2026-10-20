"""Modelo de dados (SQLAlchemy 2)."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    member = "member"


class DigitalStatus(str, enum.Enum):
    """Classificações de presença digital (requisito central do produto)."""

    sem_site = "SEM_SITE_IDENTIFICADO"
    nao_informado = "SITE_NAO_INFORMADO_NO_MAPS"
    possui_site = "POSSUI_SITE"
    indisponivel = "SITE_INDISPONIVEL"
    suspeito = "SITE_SUSPEITO"
    pendente = "VERIFICACAO_PENDENTE"


class LeadStatus(str, enum.Enum):
    novo = "novo"
    revisado = "revisado"
    contato_realizado = "contato_realizado"
    aguardando_resposta = "aguardando_resposta"
    interessado = "interessado"
    proposta_enviada = "proposta_enviada"
    convertido = "convertido"
    sem_interesse = "sem_interesse"
    nao_contatar = "nao_contatar"


class SearchStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    scoring_weights: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default=Role.member.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    monthly_budget_usd: Mapped[float] = mapped_column(Float, default=25.0)
    max_results_per_search: Mapped[int] = mapped_column(Integer, default=200)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    org: Mapped[Organization] = relationship()


class SearchTask(Base):
    __tablename__ = "search_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default=SearchStatus.queued.value, index=True)
    config: Mapped[dict] = mapped_column(JSONType)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    actual_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_found: Mapped[int] = mapped_column(Integer, default=0)
    total_new: Mapped[int] = mapped_column(Integer, default=0)
    total_verified: Mapped[int] = mapped_column(Integer, default=0)
    total_to_verify: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    units: Mapped[list[SearchUnit]] = relationship(back_populates="search", cascade="all, delete-orphan")


class SearchUnit(Base):
    """Uma combinação (fonte × localização × categoria) processada com checkpoint."""

    __tablename__ = "search_units"
    __table_args__ = (UniqueConstraint("search_id", "source", "location_key", "category"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("search_tasks.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(40))
    location: Mapped[dict] = mapped_column(JSONType)
    location_key: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|done|error|skipped
    checkpoint: Mapped[dict | None] = mapped_column(JSONType)  # ex.: next_page_token
    results_count: Mapped[int] = mapped_column(Integer, default=0)
    requests_made: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)

    search: Mapped[SearchTask] = relationship(back_populates="units")


class Business(Base):
    __tablename__ = "businesses"
    __table_args__ = (
        Index("ix_businesses_org_status", "org_id", "digital_status"),
        Index("ix_businesses_org_city", "org_id", "city"),
        Index("ix_businesses_org_phone", "org_id", "phone_normalized"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    normalized_name: Mapped[str] = mapped_column(String(300), index=True)
    category: Mapped[str | None] = mapped_column(String(200))
    categories: Mapped[list | None] = mapped_column(JSONType)
    address: Mapped[str | None] = mapped_column(String(500))
    neighborhood: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str | None] = mapped_column(String(200))
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    phone: Mapped[str | None] = mapped_column(String(50))
    phone_normalized: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(320))
    maps_url: Mapped[str | None] = mapped_column(String(1000))
    source_website: Mapped[str | None] = mapped_column(String(1000))  # site informado na fonte original
    official_website: Mapped[str | None] = mapped_column(String(1000))  # site oficial identificado pela pesquisa
    official_domain: Mapped[str | None] = mapped_column(String(300))
    candidate_website: Mapped[str | None] = mapped_column(String(1000))  # domínio suspeito/não confirmado
    social_links: Mapped[list | None] = mapped_column(JSONType)
    directory_links: Mapped[list | None] = mapped_column(JSONType)
    rating: Mapped[float | None] = mapped_column(Float)
    reviews_count: Mapped[int | None] = mapped_column(Integer)
    business_status: Mapped[str | None] = mapped_column(String(40))
    sources: Mapped[list | None] = mapped_column(JSONType)  # nomes das fontes onde a empresa aparece

    digital_status: Mapped[str] = mapped_column(String(40), default=DigitalStatus.pendente.value)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    classification_reason: Mapped[str | None] = mapped_column(Text)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    social_only: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_state: Mapped[str] = mapped_column(String(20), default="pending")  # pending|queued|done|error
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lead_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    score_breakdown: Mapped[dict | None] = mapped_column(JSONType)
    lead_status: Mapped[str] = mapped_column(String(30), default=LeadStatus.novo.value, index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    possible_duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("businesses.id", ondelete="SET NULL"))
    is_fictitious: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    source_records: Mapped[list[BusinessSource]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    verifications: Mapped[list[Verification]] = relationship(
        back_populates="business", cascade="all, delete-orphan", order_by="Verification.id.desc()"
    )
    interactions: Mapped[list[Interaction]] = relationship(
        back_populates="business", cascade="all, delete-orphan", order_by="Interaction.id.desc()"
    )


class BusinessSource(Base):
    __tablename__ = "business_sources"
    __table_args__ = (UniqueConstraint("org_id", "source", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(40))
    external_id: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    website: Mapped[str | None] = mapped_column(String(1000))  # campo de site informado por esta fonte
    raw: Mapped[dict | None] = mapped_column(JSONType)  # payload minimizado; removido após retenção
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    business: Mapped[Business] = relationship(back_populates="source_records")


class SearchResult(Base):
    """Liga uma pesquisa às empresas que ela retornou (permite reabrir pesquisas antigas)."""

    __tablename__ = "search_results"
    __table_args__ = (UniqueConstraint("search_id", "business_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("search_tasks.id", ondelete="CASCADE"), index=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    is_new: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Verification(Base):
    __tablename__ = "verifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    search_id: Mapped[int | None] = mapped_column(ForeignKey("search_tasks.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSONType)
    sources_consulted: Mapped[list] = mapped_column(JSONType)
    candidates: Mapped[list | None] = mapped_column(JSONType)
    ai_used: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    business: Mapped[Business] = relationship(back_populates="verifications")


class Interaction(Base):
    __tablename__ = "interactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(30))  # note|call|email|whatsapp|meeting|status_change|other
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    business: Mapped[Business] = relationship(back_populates="interactions")
    user: Mapped[User | None] = relationship()


class ApiUsage(Base):
    __tablename__ = "api_usage"
    __table_args__ = (Index("ix_api_usage_user_created", "user_id", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    search_id: Mapped[int | None] = mapped_column(ForeignKey("search_tasks.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(40))
    operation: Mapped[str] = mapped_column(String(60))
    units: Mapped[int] = mapped_column(Integer, default=1)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProviderQuotaUsage(Base):
    """Contador de requisições cobráveis por provedor e período (mês ou dia), para respeitar cotas gratuitas."""

    __tablename__ = "provider_quota_usage"
    __table_args__ = (UniqueConstraint("provider", "period"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    period: Mapped[str] = mapped_column(String(10))  # "2026-10" (mensal) ou "2026-10-20" (diário)
    count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ApiCache(Base):
    __tablename__ = "api_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    response: Mapped[dict] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SearchEvent(Base):
    """Log de progresso e erros de integração por pesquisa."""

    __tablename__ = "search_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("search_tasks.id", ondelete="CASCADE"), index=True)
    level: Mapped[str] = mapped_column(String(10), default="info")  # info|warning|error
    provider: Mapped[str | None] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    """Fila de tarefas persistente (durável, com retentativas e retomada)."""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_run_after", "status", "run_after"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))  # run_search | verify_business
    payload: Mapped[dict] = mapped_column(JSONType)
    dedup_key: Mapped[str | None] = mapped_column(String(200), index=True)
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.queued.value)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=4)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(100))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
