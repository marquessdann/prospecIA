"""Ingestão de registros das fontes com deduplicação e correlação entre fontes."""

from __future__ import annotations

import math
from datetime import timedelta

from rapidfuzz import fuzz
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Business, BusinessSource, DigitalStatus, utcnow
from app.providers.base import Location, PlaceRecord
from app.verification.normalize import normalize_name, normalize_phone, strip_accents

NAME_GEO_THRESHOLD = 85
NAME_ONLY_THRESHOLD = 95
GEO_RADIUS_M = 150


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _same_city(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return True
    return strip_accents(a).lower().strip() == strip_accents(b).lower().strip()


def find_match(db: Session, org_id: int, rec: PlaceRecord, norm_name: str, phone_norm: str | None) -> tuple[Business | None, str]:
    """Retorna (empresa existente, motivo) — ou (None, '') se for nova."""
    src = db.scalar(select(BusinessSource).where(BusinessSource.org_id == org_id, BusinessSource.source == rec.source,
                                                 BusinessSource.external_id == rec.external_id))
    if src:
        return db.get(Business, src.business_id), "mesmo identificador na fonte"
    conds = []
    if phone_norm:
        conds.append(Business.phone_normalized == phone_norm)
    if rec.lat is not None and rec.lng is not None:
        d = 0.003  # ~300 m
        conds.append((Business.lat.between(rec.lat - d, rec.lat + d)) & (Business.lng.between(rec.lng - d, rec.lng + d)))
    first_token = norm_name.split(" ")[0] if norm_name else ""
    if first_token:
        conds.append(Business.normalized_name.like(f"{first_token}%"))
    if not conds:
        return None, ""
    q = select(Business).where(Business.org_id == org_id, Business.is_fictitious.is_(False), or_(*conds)).limit(200)
    best, best_reason, best_score = None, "", 0
    for b in db.scalars(q):
        sim = fuzz.token_sort_ratio(norm_name, b.normalized_name)
        if phone_norm and b.phone_normalized == phone_norm and sim >= 60:
            score, reason = 200 + sim, "mesmo telefone e nome compatível"
        elif (rec.lat is not None and b.lat is not None and rec.lng is not None and b.lng is not None
              and haversine_m(rec.lat, rec.lng, b.lat, b.lng) <= GEO_RADIUS_M and sim >= NAME_GEO_THRESHOLD):
            score, reason = 100 + sim, "nome compatível no mesmo local"
        elif sim >= NAME_ONLY_THRESHOLD and _same_city(rec.city, b.city) and rec.city and b.city:
            score, reason = sim, "nome praticamente idêntico na mesma cidade"
        else:
            continue
        if score > best_score:
            best, best_reason, best_score = b, reason, score
    return best, best_reason


def ingest_record(db: Session, org_id: int, rec: PlaceRecord, location: Location | None = None) -> tuple[Business, bool]:
    """Cria ou atualiza a empresa a partir de um registro de fonte. Retorna (empresa, é_nova)."""
    if location is not None:
        rec.city = rec.city or location.city
        rec.state = rec.state or location.state
        rec.country = rec.country or location.country
        rec.neighborhood = rec.neighborhood or location.neighborhood
    norm = normalize_name(rec.name)
    phone_norm = normalize_phone(rec.phone)
    biz, _reason = find_match(db, org_id, rec, norm, phone_norm)
    is_new = biz is None
    if biz is None:
        biz = Business(org_id=org_id, name=rec.name, normalized_name=norm, digital_status=DigitalStatus.pendente.value,
                       sources=[])
        db.add(biz)
    # Preenche lacunas sem sobrescrever dados já presentes (prioriza a primeira fonte).
    for attr in ("category", "address", "neighborhood", "city", "state", "country", "postal_code", "lat", "lng",
                 "phone", "email", "maps_url", "business_status"):
        val = getattr(rec, attr)
        if val is not None and getattr(biz, attr) in (None, ""):
            setattr(biz, attr, val)
    if rec.source == "google_places":
        # Dados do Google são os mais atualizados para avaliação/estado de funcionamento.
        biz.rating = rec.rating if rec.rating is not None else biz.rating
        biz.reviews_count = rec.reviews_count if rec.reviews_count is not None else biz.reviews_count
        biz.business_status = rec.business_status or biz.business_status
        biz.maps_url = rec.maps_url or biz.maps_url
    if phone_norm and not biz.phone_normalized:
        biz.phone_normalized = phone_norm
    if rec.categories:
        biz.categories = sorted(set((biz.categories or []) + rec.categories))[:15]
    if rec.website and not biz.source_website:
        biz.source_website = rec.website
    if rec.social_links:
        biz.social_links = sorted(set((biz.social_links or []) + rec.social_links))[:10]
    biz.sources = sorted(set((biz.sources or []) + [rec.source]))
    db.flush()

    src = db.scalar(select(BusinessSource).where(BusinessSource.org_id == org_id, BusinessSource.source == rec.source,
                                                 BusinessSource.external_id == rec.external_id))
    retention = settings.google_places_retention_days if rec.source == "google_places" else None
    if src is None:
        src = BusinessSource(org_id=org_id, business_id=biz.id, source=rec.source, external_id=rec.external_id)
        db.add(src)
    src.source_url = rec.source_url
    src.website = rec.website
    src.raw = rec.raw
    src.fetched_at = utcnow()
    src.expires_at = utcnow() + timedelta(days=retention) if retention else None
    db.flush()
    return biz, is_new


def flag_possible_duplicates(db: Session, org_id: int, business: Business) -> int | None:
    """Marca possíveis duplicadas de baixa certeza (nome similar, mesma cidade) para revisão humana."""
    if not business.city:
        return None
    first = business.normalized_name.split(" ")[0] if business.normalized_name else ""
    q = select(Business).where(Business.org_id == org_id, Business.id != business.id,
                               func.lower(Business.city) == business.city.lower(),
                               Business.normalized_name.like(f"{first}%")).limit(50)
    for other in db.scalars(q):
        if other.id < business.id and fuzz.token_set_ratio(business.normalized_name, other.normalized_name) >= 90:
            business.possible_duplicate_of = other.id
            return other.id
    return None
