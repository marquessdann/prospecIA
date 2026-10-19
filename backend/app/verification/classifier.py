"""Pipeline de classificação da presença digital de uma empresa.

Etapas (cada uma gera evidências registradas):
 1. Site informado nas fontes de origem (Google Maps, OSM...).
 2. Busca web autorizada por nome + cidade e por telefone.
 3. (Opcional) Teste de domínios prováveis via DNS.
 4. Verificação HTTP de cada candidato (disponibilidade, conteúdo, domínio estacionado).
 5. Correspondência determinística (nome, telefone, endereço) + adjudicação opcional por IA.
 6. Decisão com nível de confiança e justificativa.

A função `verify` não acessa o banco: recebe um snapshot e devolve um resultado.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import httpx
from rapidfuzz import fuzz

from app.providers.base import ProviderError, WebSearchProvider
from app.verification.ai import AiAnalyzer
from app.verification.domains import (
    KIND_DIRECTORY,
    KIND_INVALID,
    KIND_MARKETPLACE,
    KIND_SOCIAL,
    classify_url,
    is_site_like,
)
from app.verification.matcher import BusinessSnapshot, domain_name_match, score_candidate
from app.verification.normalize import compact, name_is_generic, name_tokens, normalize_name, phone_variants
from app.verification.site_checker import SiteCheck, SiteChecker, host_resolves

CONFIRM_THRESHOLD = 70
SUSPECT_THRESHOLD = 35
SOURCE_LABELS = {"google_places": "Google Maps", "osm": "OpenStreetMap"}

STATUS_LABELS = {
    "SEM_SITE_IDENTIFICADO": "Sem site identificado",
    "SITE_NAO_INFORMADO_NO_MAPS": "Site não informado no Maps",
    "POSSUI_SITE": "Possui site",
    "SITE_INDISPONIVEL": "Site indisponível",
    "SITE_SUSPEITO": "Site suspeito ou não confirmado",
    "VERIFICACAO_PENDENTE": "Verificação pendente",
}


@dataclass
class Candidate:
    url: str
    domain: str
    origin: str  # source:<fonte> | web_search | domain_guess
    title: str | None = None
    snippet: str | None = None
    check: dict | None = None
    score: int = 0
    signals: list[str] = field(default_factory=list)
    ai_verdict: str | None = None
    ai_confidence: int | None = None
    ai_rationale: str | None = None
    reachable: bool = False
    parked: bool = False
    phone_match: bool = False
    emails: list[str] = field(default_factory=list)


@dataclass
class VerificationOutcome:
    status: str
    confidence: int
    reason: str
    evidence: list[dict]
    sources_consulted: list[str]
    candidates: list[dict]
    official_website: str | None = None
    official_domain: str | None = None
    candidate_website: str | None = None
    social_links: list[str] = field(default_factory=list)
    directory_links: list[str] = field(default_factory=list)
    public_email: str | None = None
    social_only: bool = False
    ai_used: bool = False
    ai_summary: str | None = None
    cost_usd: float = 0.0
    web_queries: int = 0
    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class VerifyOptions:
    web_search: bool = True
    domain_guessing: bool = True
    max_web_candidates: int = 4
    use_ai: bool = True


def _ev(kind: str, source: str, detail: str, polarity: str = "0", url: str | None = None) -> dict:
    return {"type": kind, "source": source, "detail": detail, "polarity": polarity, "url": url}


def format_phone_br(phone_normalized: str | None) -> str | None:
    if not phone_normalized or not phone_normalized.startswith("55"):
        return None
    local = phone_normalized[2:]
    if len(local) == 11:
        return f"({local[:2]}) {local[2:7]}-{local[7:]}"
    if len(local) == 10:
        return f"({local[:2]}) {local[2:6]}-{local[6:]}"
    return None


def guess_domains(name: str, country: str | None) -> list[str]:
    tokens = name_tokens(name)
    specific = name_tokens(name, drop_generic=True)
    bases = []
    for t in (compact("".join(tokens)), compact("".join(specific))):
        if 5 <= len(t) <= 40 and t not in bases:
            bases.append(t)
    tlds = [".com.br", ".com"] if (country or "brasil").lower() in ("brasil", "brazil", "br") else [".com"]
    return [b + tld for b in bases for tld in tlds][:4]


def _title_similarity(name: str, title: str | None) -> int:
    if not title:
        return 0
    return int(fuzz.token_set_ratio(normalize_name(name), normalize_name(title)))


async def verify(
    biz: BusinessSnapshot,
    *,
    client: httpx.AsyncClient,
    web: WebSearchProvider | None,
    checker: SiteChecker,
    ai: AiAnalyzer | None = None,
    options: VerifyOptions | None = None,
) -> VerificationOutcome:
    opts = options or VerifyOptions()
    evidence: list[dict] = []
    consulted: list[str] = []
    candidates: dict[str, Candidate] = {}
    socials: dict[str, None] = {}
    directories: dict[str, None] = {}
    cost = 0.0

    # 1) Campos de site nas fontes de origem
    sources_without_site = []
    for source, url in biz.source_websites:
        label = SOURCE_LABELS.get(source, source)
        consulted.append(f"{label} (cadastro)")
        if not url:
            sources_without_site.append(label)
            evidence.append(_ev("source_field", label, f"O cadastro em {label} não informa site.", "-"))
            continue
        kind = classify_url(url)
        if kind.kind == KIND_INVALID:
            evidence.append(_ev("source_field", label, f"Site informado em {label} é inválido: {url}", "-", url))
        elif kind.kind == KIND_SOCIAL:
            socials[url] = None
            evidence.append(_ev("source_field", label, f"{label} informa apenas rede social ({kind.platform}).", "-", url))
        elif kind.kind in (KIND_MARKETPLACE, KIND_DIRECTORY):
            directories[url] = None
            evidence.append(_ev("source_field", label, f"{label} informa página em plataforma de terceiros ({kind.platform}), não site próprio.", "-", url))
        else:
            dom = kind.domain or kind.host or url
            candidates.setdefault(dom, Candidate(url=url, domain=dom, origin=f"source:{source}"))
            evidence.append(_ev("source_field", label, f"{label} informa o site {dom}.", "+", url))
    for s in biz.sources:
        if s not in {src for src, _ in biz.source_websites}:
            consulted.append(f"{SOURCE_LABELS.get(s, s)} (cadastro)")

    # 2) Busca web autorizada
    web_ok = 0
    web_errors: list[str] = []
    phone_query_done = False
    if opts.web_search and web is not None:
        queries = []
        place = biz.city or biz.state or biz.country or ""
        queries.append(f'"{biz.name}" {place}'.strip())
        if fp := format_phone_br(biz.phone_normalized):
            queries.append(f'"{fp}"')
        web_found: list[tuple[int, Candidate]] = []
        for q in queries:
            try:
                resp = await web.search(client, q, biz.country)
            except ProviderError as e:
                web_errors.append(str(e))
                evidence.append(_ev("web_search", web.label, f"Falha na busca '{q}': {e}", "0"))
                continue
            web_ok += 1
            if q.startswith('"('):
                phone_query_done = True
            cost += resp.cost_usd
            consulted.append(f"{web.label}: {q}")
            for r in resp.results:
                kind = classify_url(r.url)
                title_sim = _title_similarity(biz.name, r.title)
                snippet_phone = any(v in "".join(ch for ch in (r.snippet or "") + (r.title or "") if ch.isdigit())
                                    for v in phone_variants(biz.phone_normalized))
                if kind.kind == KIND_SOCIAL:
                    if title_sim >= 70 or snippet_phone:
                        socials[r.url] = None
                    continue
                if kind.kind in (KIND_MARKETPLACE, KIND_DIRECTORY):
                    if title_sim >= 70 or snippet_phone:
                        directories[r.url] = None
                    continue
                if not is_site_like(kind):
                    continue
                dom = kind.domain or kind.host or r.url
                dom_match, _ = domain_name_match(biz.name, dom)
                if not (dom_match or title_sim >= 60 or snippet_phone):
                    continue
                if dom in candidates:
                    continue
                prio = (0 if snippet_phone else 1, 0 if dom_match else 1, r.rank)
                web_found.append((prio, Candidate(url=r.url, domain=dom, origin="web_search", title=r.title,
                                                 snippet=r.snippet)))
            evidence.append(_ev("web_search", web.label, f"Busca '{q}': {len(resp.results)} resultados analisados.", "0"))
        web_found.sort(key=lambda x: x[0])
        for _, c in web_found:
            if c.domain not in candidates and sum(1 for x in candidates.values() if x.origin == "web_search") < opts.max_web_candidates:
                candidates[c.domain] = c
    elif opts.web_search:
        evidence.append(_ev("web_search", "Sistema", "Nenhum provedor de busca web configurado; a existência de site fora da fonte não foi investigada.", "0"))

    # 3) Domínios prováveis (DNS) quando nada foi encontrado nas etapas anteriores
    if opts.domain_guessing and not candidates:
        guesses = guess_domains(biz.name, biz.country)
        resolved = []
        for g in guesses:
            if await host_resolves(g):
                resolved.append(g)
                candidates[g] = Candidate(url=f"https://{g}", domain=g, origin="domain_guess")
        if guesses:
            consulted.append("DNS: " + ", ".join(guesses))
            evidence.append(_ev("domain_guess", "DNS", f"Domínios prováveis testados: {', '.join(guesses)}; registrados: {', '.join(resolved) or 'nenhum'}.", "0"))

    # 4) Verificação HTTP + correspondência
    async def _check(c: Candidate) -> None:
        chk: SiteCheck = await checker.check(c.url)
        consulted.append(f"Verificação HTTP: {c.domain}")
        c.check = chk.to_dict()
        c.reachable = chk.reachable
        c.parked = chk.parked
        c.emails = chk.emails_found
        m = score_candidate(biz, c.domain, chk.title or c.title, chk.text_excerpt, chk.phones_found, c.origin, c.snippet)
        c.score, c.signals, c.phone_match = m.score, m.signals, m.phone_match
        if chk.restricted and c.origin.startswith("source:"):
            c.signals.append("Site responde, mas bloqueia verificações automatizadas (HTTP %s)" % chk.http_status)
            c.score = max(c.score, CONFIRM_THRESHOLD)
    await asyncio.gather(*(_check(c) for c in candidates.values()))

    # 5) IA (opcional) para casos ambíguos
    ai_used = False
    ai_summary = None
    if opts.use_ai and ai is not None and ai.enabled and candidates:
        ambiguous = [c for c in candidates.values() if c.reachable and not c.parked and 20 <= c.score < 90]
        if ambiguous:
            payload_biz = {"nome": biz.name, "categoria": biz.category, "cidade": biz.city, "estado": biz.state,
                           "endereco": biz.address, "possui_telefone": bool(biz.phone_normalized)}
            payload_c = [{"domain": c.domain, "origem": c.origin, "titulo": (c.check or {}).get("title") or c.title,
                          "descricao": (c.check or {}).get("description") or c.snippet,
                          "sinais_automaticos": c.signals, "pontuacao_automatica": c.score} for c in ambiguous]
            res = await ai.adjudicate(payload_biz, payload_c, {"redes_sociais": list(socials)[:5]})
            if res is not None:
                ai_used = True
                cost += res.cost_usd
                ai_summary = res.summary
                for c in ambiguous:
                    v = res.verdicts.get(c.domain.lower())
                    if not v:
                        continue
                    c.ai_verdict, c.ai_confidence, c.ai_rationale = v.verdict, v.confidence, v.rationale
                    if v.verdict == "oficial" and v.confidence >= 70 and c.score >= SUSPECT_THRESHOLD:
                        c.score = max(c.score, min(85, v.confidence))
                        c.signals.append(f"IA: provável site oficial ({v.confidence}%) — {v.rationale}")
                    elif v.verdict == "nao_pertence" and v.confidence >= 70 and not c.phone_match:
                        c.score = min(c.score, 20)
                        c.signals.append(f"IA: provavelmente de outra empresa ({v.confidence}%) — {v.rationale}")
                consulted.append("Análise por IA das evidências")

    # 6) Decisão
    cands = list(candidates.values())
    for c in cands:
        pol = "+" if c.score >= CONFIRM_THRESHOLD else "0"
        status = "responde" if c.reachable else f"não respondeu ({(c.check or {}).get('error')})"
        if c.parked:
            status = "domínio estacionado/sem conteúdo"
        evidence.append(_ev("site_check", c.domain, f"{c.domain} ({c.origin}): {status}; correspondência {c.score}/100. " + "; ".join(c.signals), pol, c.url))

    confirmed = sorted([c for c in cands if c.reachable and not c.parked and c.score >= CONFIRM_THRESHOLD],
                       key=lambda c: -c.score)
    broken_own = [c for c in cands if c.origin.startswith("source:") and (not c.reachable or c.parked)]
    suspects = sorted([c for c in cands if c.reachable and not c.parked
                       and SUSPECT_THRESHOLD <= c.score < CONFIRM_THRESHOLD], key=lambda c: -c.score)
    out = VerificationOutcome(status="VERIFICACAO_PENDENTE", confidence=0, reason="", evidence=evidence,
                              sources_consulted=consulted, candidates=[asdict(c) for c in cands],
                              social_links=list(socials)[:10], directory_links=list(directories)[:10],
                              ai_used=ai_used, ai_summary=ai_summary, cost_usd=round(cost, 6), web_queries=web_ok)
    generic = name_is_generic(biz.name)

    if confirmed:
        best = confirmed[0]
        out.status = "POSSUI_SITE"
        out.confidence = min(98, best.score)
        out.official_website = (best.check or {}).get("final_url") or best.url
        out.official_domain = best.domain
        same_domain = [e for e in best.emails if e.split("@")[-1].endswith(best.domain)]
        out.public_email = same_domain[0] if same_domain else None
        origin = "informado no cadastro" if best.origin.startswith("source:") else "encontrado na busca web"
        out.reason = (f"Site oficial {best.domain} {origin} e acessível. Evidências: " + "; ".join(best.signals[:4]) + ".")
    elif broken_own:
        c = broken_own[0]
        err = (c.check or {}).get("error")
        out.status = "SITE_INDISPONIVEL"
        out.candidate_website = c.url
        out.official_domain = c.domain
        out.confidence = {"dns": 85, "http_error": 75, "tls": 65, "connection": 70, "timeout": 60}.get(err or "", 70)
        if c.parked:
            out.confidence = 80
            out.reason = f"O cadastro informa {c.domain}, mas o domínio está estacionado, em construção ou sem conteúdo."
        else:
            detail = {"dns": "o domínio não resolve (DNS)", "timeout": "o servidor não respondeu a tempo",
                      "connection": "a conexão foi recusada", "tls": "há erro de certificado TLS",
                      "http_error": f"o servidor respondeu HTTP {(c.check or {}).get('http_status')}"}.get(err or "", "o site não respondeu")
            out.reason = f"O cadastro informa {c.domain}, mas {detail} nas verificações realizadas."
        if suspects:
            out.reason += f" Outro domínio candidato não confirmado: {suspects[0].domain}."
    elif suspects:
        c = suspects[0]
        out.status = "SITE_SUSPEITO"
        out.candidate_website = (c.check or {}).get("final_url") or c.url
        out.confidence = c.score
        out.reason = (f"Encontrado o domínio {c.domain}, mas sem evidências suficientes (telefone/endereço) de que "
                      f"pertence a esta empresa. Sinais: " + ("; ".join(c.signals[:3]) or "apenas semelhança de nome") + ".")
    elif web_ok > 0:
        out.status = "SEM_SITE_IDENTIFICADO"
        conf = 55 + 10 * min(web_ok, 2) + (10 if phone_query_done else 0)
        if len(sources_without_site) >= 2:
            conf += 5
        if generic:
            conf -= 15
        out.confidence = max(30, min(90, conf))
        out.reason = (f"Nenhum site próprio encontrado: {', '.join(sources_without_site) or 'a fonte'} não informa site e "
                      f"{web_ok} busca(s) web autorizada(s) não retornaram domínio compatível.")
        if generic:
            out.reason += " Nome genérico reduz a confiança da busca."
    elif web_errors:
        out.status = "VERIFICACAO_PENDENTE"
        out.confidence = 0
        out.reason = "A busca web falhou (" + web_errors[0][:160] + "); a análise será concluída em nova tentativa."
    elif sources_without_site:
        out.status = "SITE_NAO_INFORMADO_NO_MAPS"
        out.confidence = 40
        out.reason = (f"{', '.join(sources_without_site)} não informa site. Isso NÃO confirma ausência de site na internet: "
                      "a busca web não foi executada (sem provedor configurado ou desativada).")
    else:
        out.status = "VERIFICACAO_PENDENTE"
        out.reason = "Não há dados suficientes para concluir a análise."

    out.social_only = out.status in ("SEM_SITE_IDENTIFICADO", "SITE_NAO_INFORMADO_NO_MAPS", "SITE_INDISPONIVEL") and bool(socials)
    if out.social_only:
        out.reason += " Presença digital limitada a redes sociais/perfis de terceiros."
    return out
