"""Pontuação de leads (0–100) com critérios e pesos configuráveis por organização.

A pontuação é uma PRIORIDADE ESTIMADA para prospecção, não uma garantia de interesse.
"""

from __future__ import annotations

import math

from app.models import Business

DEFAULT_WEIGHTS: dict[str, float] = {
    "no_website": 35,       # ausência de site com evidências suficientes
    "public_profile": 10,   # perfil empresarial público (Maps/OSM)
    "contact_channel": 20,  # telefone/e-mail comercial público
    "activity": 15,         # avaliações / sinais públicos de atividade
    "operational": 10,      # evidência de que está em funcionamento
    "data_quality": 10,     # qualidade e confiabilidade dos dados
}

CRITERIA_LABELS = {
    "no_website": "Ausência de site (com evidências)",
    "public_profile": "Perfil empresarial público",
    "contact_channel": "Canal comercial público",
    "activity": "Avaliações e sinais de atividade",
    "operational": "Empresa em funcionamento",
    "data_quality": "Qualidade dos dados",
}

# Fator de oportunidade por status de presença digital.
STATUS_FACTOR = {
    "SEM_SITE_IDENTIFICADO": 1.0,
    "SITE_INDISPONIVEL": 0.85,   # site quebrado: oportunidade de reformulação
    "SITE_NAO_INFORMADO_NO_MAPS": 0.5,  # ainda não confirmado
    "SITE_SUSPEITO": 0.35,
    "VERIFICACAO_PENDENTE": 0.3,
    "POSSUI_SITE": 0.05,
}


def merge_weights(custom: dict | None) -> dict[str, float]:
    w = dict(DEFAULT_WEIGHTS)
    for k, v in (custom or {}).items():
        if k in w:
            try:
                w[k] = max(0.0, float(v))
            except (TypeError, ValueError):
                pass
    return w


def compute_score(b: Business, weights: dict | None = None) -> tuple[int, dict]:
    w = merge_weights(weights)
    total_w = sum(w.values()) or 1.0
    factors: dict[str, float] = {}

    status_factor = STATUS_FACTOR.get(b.digital_status, 0.3)
    if b.digital_status in ("SEM_SITE_IDENTIFICADO", "SITE_INDISPONIVEL"):
        status_factor *= 0.6 + 0.4 * (b.confidence or 0) / 100
    factors["no_website"] = status_factor

    factors["public_profile"] = 1.0 if b.maps_url else 0.0
    factors["contact_channel"] = min(1.0, (0.75 if b.phone else 0) + (0.25 if b.email else 0) + (0.15 if b.social_links else 0))

    reviews = b.reviews_count or 0
    activity = min(1.0, math.log10(reviews + 1) / 2)  # 100 avaliações => 1.0
    if b.rating and b.rating >= 4.0 and reviews >= 5:
        activity = min(1.0, activity + 0.1)
    factors["activity"] = activity

    status = (b.business_status or "").lower()
    factors["operational"] = 0.0 if "closed" in status else (1.0 if status == "operational" else 0.5)

    fields = [b.address, b.city, b.lat, b.category, b.phone]
    quality = sum(1 for f in fields if f) / len(fields)
    if b.sources and len(b.sources) > 1:
        quality = min(1.0, quality + 0.2)
    factors["data_quality"] = quality

    breakdown = {k: round(w[k] * factors[k] / total_w * 100, 1) for k in w}
    score = int(round(sum(breakdown.values())))
    if (b.lead_status == "nao_contatar") or "closed" in status:
        score = 0
    return max(0, min(100, score)), {"criteria": breakdown, "weights": w,
                                      "note": "Prioridade estimada; não garante interesse na contratação."}
