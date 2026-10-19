"""Filtros dinâmicos compartilhados entre listagem, mapa e exportação."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import Query
from sqlalchemy import Select, and_, asc, desc, func, or_, select

from app.models import Business, BusinessSource, SearchResult

SORTABLE = {
    "name": Business.name, "lead_score": Business.lead_score, "confidence": Business.confidence,
    "last_verified_at": Business.last_verified_at, "rating": Business.rating,
    "reviews_count": Business.reviews_count, "created_at": Business.created_at, "city": Business.city,
    "category": Business.category, "digital_status": Business.digital_status,
}


def _csv(v: str | None) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


@dataclass
class BusinessFilters:
    q: str | None = Query(None, description="Texto livre: nome, endereço, telefone ou domínio")
    name: str | None = None
    digital_status: str | None = Query(None, description="Lista separada por vírgula")
    lead_status: str | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    neighborhood: str | None = None
    postal_code: str | None = None
    category: str | None = None
    source: str | None = None
    has_phone: bool | None = None
    has_email: bool | None = None
    has_maps: bool | None = None
    social_only: bool | None = None
    min_rating: float | None = None
    min_reviews: int | None = None
    min_confidence: int | None = None
    max_confidence: int | None = None
    min_score: int | None = None
    verified_after: datetime | None = None
    verified_before: datetime | None = None
    search_id: int | None = None
    assignee_id: int | None = None
    ids: str | None = Query(None, description="IDs separados por vírgula (seleção)")
    fictitious: bool | None = Query(None, description="true = só fictícios; false = só reais")
    possible_duplicates: bool | None = None

    def apply(self, stmt: Select, org_id: int) -> Select:
        c = [Business.org_id == org_id]
        if self.q:
            like = f"%{self.q.strip().lower()}%"
            digits = "".join(ch for ch in self.q if ch.isdigit())
            conds = [func.lower(Business.name).like(like), func.lower(Business.address).like(like),
                     func.lower(func.coalesce(Business.official_domain, "")).like(like)]
            if len(digits) >= 4:
                conds.append(Business.phone_normalized.like(f"%{digits}%"))
            c.append(or_(*conds))
        if self.name:
            c.append(func.lower(Business.name).like(f"%{self.name.lower()}%"))
        if v := _csv(self.digital_status):
            c.append(Business.digital_status.in_(v))
        if v := _csv(self.lead_status):
            c.append(Business.lead_status.in_(v))
        for attr in ("country", "state", "city", "neighborhood"):
            if val := getattr(self, attr):
                c.append(func.lower(getattr(Business, attr)) == val.lower())
        if self.postal_code:
            c.append(Business.postal_code.like(f"{self.postal_code.strip()}%"))
        if self.category:
            c.append(func.lower(Business.category).like(f"%{self.category.lower()}%"))
        if self.source:
            c.append(Business.id.in_(select(BusinessSource.business_id).where(BusinessSource.source == self.source)))
        if self.has_phone is not None:
            c.append(Business.phone.is_not(None) if self.has_phone else Business.phone.is_(None))
        if self.has_email is not None:
            c.append(Business.email.is_not(None) if self.has_email else Business.email.is_(None))
        if self.has_maps is not None:
            c.append(Business.maps_url.is_not(None) if self.has_maps else Business.maps_url.is_(None))
        if self.social_only is not None:
            c.append(Business.social_only.is_(self.social_only))
        if self.min_rating is not None:
            c.append(Business.rating >= self.min_rating)
        if self.min_reviews is not None:
            c.append(Business.reviews_count >= self.min_reviews)
        if self.min_confidence is not None:
            c.append(Business.confidence >= self.min_confidence)
        if self.max_confidence is not None:
            c.append(Business.confidence <= self.max_confidence)
        if self.min_score is not None:
            c.append(Business.lead_score >= self.min_score)
        if self.verified_after:
            c.append(Business.last_verified_at >= self.verified_after)
        if self.verified_before:
            c.append(Business.last_verified_at <= self.verified_before)
        if self.search_id:
            c.append(Business.id.in_(select(SearchResult.business_id).where(SearchResult.search_id == self.search_id)))
        if self.assignee_id:
            c.append(Business.assignee_id == self.assignee_id)
        if ids := [int(x) for x in _csv(self.ids) if x.isdigit()]:
            c.append(Business.id.in_(ids))
        if self.fictitious is not None:
            c.append(Business.is_fictitious.is_(self.fictitious))
        if self.possible_duplicates:
            c.append(Business.possible_duplicate_of.is_not(None))
        return stmt.where(and_(*c))


def apply_sort(stmt: Select, sort: str | None, order: str | None) -> Select:
    col = SORTABLE.get(sort or "lead_score", Business.lead_score)
    direction = asc if (order or "desc") == "asc" else desc
    return stmt.order_by(direction(col).nulls_last(), Business.id.desc())
