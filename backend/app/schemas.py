"""Esquemas de entrada/saída (validação com Pydantic)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import DigitalStatus, LeadStatus, Role


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class RegisterIn(BaseModel):
    organization: str = Field(min_length=2, max_length=200)
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    # Sem validação estrita no login: contas podem usar domínios internos (ex.: demo@prospecia.local).
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORM):
    id: int
    org_id: int
    email: str
    name: str
    role: str
    is_active: bool
    monthly_budget_usd: float
    max_results_per_search: int


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role = Role.member
    monthly_budget_usd: float = Field(default=25.0, ge=0, le=100000)
    max_results_per_search: int = Field(default=200, ge=1, le=2000)


class UserUpdate(BaseModel):
    name: str | None = None
    role: Role | None = None
    is_active: bool | None = None
    monthly_budget_usd: float | None = Field(default=None, ge=0, le=100000)
    max_results_per_search: int | None = Field(default=None, ge=1, le=2000)


# ---------- Pesquisa ----------
class LocationIn(BaseModel):
    country: str | None = Field(default="Brasil", max_length=100)
    state: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=200)
    neighborhood: str | None = Field(default=None, max_length=200)
    postal_code: str | None = Field(default=None, max_length=20)
    address: str | None = Field(default=None, max_length=300)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=50)


class SearchConfig(BaseModel):
    name: str | None = Field(default=None, max_length=300)
    locations: list[LocationIn] = Field(min_length=1, max_length=100)
    categories: list[str] = Field(min_length=1, max_length=30)
    sources: list[str] = Field(default_factory=lambda: ["osm"], min_length=1)
    web_verification: bool = True
    web_provider: str | None = None
    domain_guessing: bool = True
    use_ai: bool = True
    web_queries_per_business: int | None = Field(default=None, ge=1, le=2)
    max_results: int = Field(default=100, ge=1, le=2000)
    force_reverify: bool = False

    @field_validator("categories")
    @classmethod
    def clean_categories(cls, v: list[str]) -> list[str]:
        out = []
        for c in v:
            c = c.strip()[:200]
            if c and c.lower() not in [x.lower() for x in out]:
                out.append(c)
        if not out:
            raise ValueError("informe ao menos um segmento")
        return out

    @field_validator("locations")
    @classmethod
    def check_locations(cls, v: list[LocationIn]) -> list[LocationIn]:
        for loc in v:
            if not any([loc.city, loc.neighborhood, loc.postal_code, loc.address, loc.state,
                        loc.lat is not None and loc.lng is not None]):
                raise ValueError("cada localização precisa de cidade, estado, bairro, CEP, endereço ou coordenadas")
        return v


class SearchOut(ORM):
    id: int
    name: str
    status: str
    config: dict
    estimated_cost_usd: float
    actual_cost_usd: float
    total_found: int
    total_new: int
    total_verified: int
    total_to_verify: int
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SearchUnitOut(ORM):
    id: int
    source: str
    location: dict
    category: str
    status: str
    results_count: int
    requests_made: int
    attempts: int
    last_error: str | None


class SearchEventOut(ORM):
    id: int
    level: str
    provider: str | None
    message: str
    created_at: datetime


class SearchActivity(BaseModel):
    """O que a pesquisa está fazendo agora, em linguagem simples."""

    state: str  # searching | waiting_retry | queued | verifying | paused | done | failed | cancelled
    message: str
    next_retry_at: datetime | None = None
    units_done: int = 0
    units_total: int = 0


class SearchDetail(SearchOut):
    units: list[SearchUnitOut]
    events: list[SearchEventOut]
    status_counts: dict[str, int]
    activity: SearchActivity


# ---------- Empresas ----------
class BusinessOut(ORM):
    id: int
    name: str
    category: str | None
    address: str | None
    neighborhood: str | None
    city: str | None
    state: str | None
    country: str | None
    postal_code: str | None
    lat: float | None
    lng: float | None
    phone: str | None
    email: str | None
    maps_url: str | None
    source_website: str | None
    official_website: str | None
    official_domain: str | None
    candidate_website: str | None
    social_links: list | None
    directory_links: list | None
    rating: float | None
    reviews_count: int | None
    business_status: str | None
    sources: list | None
    digital_status: str
    confidence: int
    classification_reason: str | None
    ai_summary: str | None
    social_only: bool
    verification_state: str
    last_verified_at: datetime | None
    lead_score: int
    lead_status: str
    assignee_id: int | None
    possible_duplicate_of: int | None
    is_fictitious: bool
    created_at: datetime


class SourceRecordOut(ORM):
    id: int
    source: str
    external_id: str
    source_url: str | None
    website: str | None
    fetched_at: datetime
    expires_at: datetime | None


class VerificationOut(ORM):
    id: int
    search_id: int | None
    status: str
    confidence: int
    reason: str
    evidence: list
    sources_consulted: list
    candidates: list | None
    ai_used: bool
    ai_summary: str | None
    cost_usd: float
    created_at: datetime


class InteractionOut(ORM):
    id: int
    kind: str
    content: str
    created_at: datetime
    user_id: int | None
    user_name: str | None = None


class BusinessDetail(BusinessOut):
    categories: list | None
    score_breakdown: dict | None
    source_records: list[SourceRecordOut]
    verifications: list[VerificationOut]
    interactions: list[InteractionOut]


class BusinessUpdate(BaseModel):
    """Correção manual de registros (LGPD: direito de correção)."""

    name: str | None = Field(default=None, max_length=300)
    category: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    lead_status: LeadStatus | None = None
    assignee_id: int | None = None
    digital_status: DigitalStatus | None = None


class InteractionIn(BaseModel):
    kind: str = Field(pattern="^(note|call|email|whatsapp|meeting|other)$")
    content: str = Field(min_length=1, max_length=5000)


class BulkUpdate(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)
    lead_status: LeadStatus | None = None
    assignee_id: int | None = None


class Page(BaseModel):
    items: list[BusinessOut]
    total: int
    page: int
    page_size: int


class WeightsIn(BaseModel):
    weights: dict[str, float]
