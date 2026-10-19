"""Correspondência determinística entre uma empresa e um site candidato.

Evita associar o site de uma empresa a outra de nome parecido: o nome sozinho
nunca é suficiente para confirmar; exige-se telefone, endereço/cidade ou o fato
de o próprio cadastro da empresa informar o domínio.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.verification.normalize import (
    compact,
    digits_in_text,
    domain_label,
    name_tokens,
    normalize_name,
    phone_variants,
    strip_accents,
)


@dataclass
class BusinessSnapshot:
    id: int | None
    name: str
    city: str | None = None
    state: str | None = None
    country: str | None = None
    address: str | None = None
    neighborhood: str | None = None
    postal_code: str | None = None
    phone_normalized: str | None = None
    category: str | None = None
    source_websites: list[tuple[str, str]] = field(default_factory=list)  # (fonte, url)
    sources: list[str] = field(default_factory=list)


@dataclass
class MatchSignals:
    score: int
    signals: list[str]
    name_similarity: int
    domain_match: bool
    phone_match: bool
    city_match: bool
    address_match: bool


def domain_name_match(name: str, domain: str) -> tuple[bool, int]:
    label = compact(domain_label(domain))
    if not label:
        return False, 0
    specific = name_tokens(name, drop_generic=True)
    full = compact(" ".join(name_tokens(name)))
    spec_compact = compact(" ".join(specific))
    ratio = max(
        fuzz.ratio(label, full),
        fuzz.ratio(label, spec_compact) if spec_compact else 0,
        fuzz.partial_ratio(spec_compact, label) if len(spec_compact) >= 5 else 0,
    )
    tokens_in = [t for t in specific if len(t) >= 4 and compact(t) in label]
    matched = ratio >= 85 or (bool(tokens_in) and len("".join(tokens_in)) >= 5)
    return matched, int(ratio)


def score_candidate(
    biz: BusinessSnapshot,
    domain: str,
    title: str | None,
    page_text: str | None,
    page_phones: list[str] | None,
    origin: str,
    snippet: str | None = None,
) -> MatchSignals:
    signals: list[str] = []
    score = 0

    if origin.startswith("source:"):
        score += 40
        signals.append("Domínio informado no próprio cadastro da empresa na fonte")

    dom_match, dom_ratio = domain_name_match(biz.name, domain)
    if dom_match:
        score += 20
        signals.append(f"Domínio compatível com o nome (similaridade {dom_ratio}%)")

    haystack_title = " ".join(x for x in [title, snippet] if x)
    name_sim = 0
    if haystack_title:
        name_sim = int(fuzz.token_set_ratio(normalize_name(biz.name), normalize_name(haystack_title)))
        if name_sim >= 80:
            score += 15
            signals.append(f"Título/descrição compatível com o nome ({name_sim}%)")
        elif name_sim >= 60:
            score += 6

    phone_match = False
    if biz.phone_normalized:
        variants = phone_variants(biz.phone_normalized)
        page_digits = digits_in_text(page_text or "") + " " + " ".join(page_phones or [])
        snippet_digits = digits_in_text(snippet or "")
        if any(v in page_digits or v in snippet_digits for v in variants):
            phone_match = True
            score += 35
            signals.append("Telefone da empresa encontrado no site")

    text_norm = strip_accents((page_text or "") + " " + (snippet or "")).lower()
    city_match = bool(biz.city and strip_accents(biz.city).lower() in text_norm)
    if city_match:
        score += 8
        signals.append("Cidade da empresa mencionada no site")

    address_match = False
    if biz.address:
        street_tokens = [t for t in name_tokens(biz.address) if len(t) >= 5 and not t.isdigit()][:3]
        if street_tokens and sum(t in text_norm for t in street_tokens) >= min(2, len(street_tokens)):
            address_match = True
            score += 12
            signals.append("Endereço compatível encontrado no site")
    if biz.postal_code and digits_in_text(biz.postal_code) and digits_in_text(biz.postal_code) in digits_in_text(page_text or ""):
        address_match = True
        score += 8
        signals.append("CEP encontrado no site")

    # Nome compatível sem nenhum dado de contato/endereço: limita a confiança (homônimos).
    strong = phone_match or address_match or origin.startswith("source:")
    if not strong:
        score = min(score, 55)

    return MatchSignals(
        score=min(score, 100),
        signals=signals,
        name_similarity=name_sim,
        domain_match=dom_match,
        phone_match=phone_match,
        city_match=city_match,
        address_match=address_match,
    )
