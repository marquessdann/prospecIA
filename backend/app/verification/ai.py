"""Módulo de IA opcional (Anthropic Claude), configurado só no servidor.

Regras de segurança contra alucinação:
- O modelo recebe apenas as evidências coletadas e responde em JSON com esquema fixo.
- Ele só pode escolher um domínio que já esteja na lista de candidatos; qualquer outro é descartado.
- Telefones, e-mails e domínios do resumo nunca são lidos da resposta do modelo.
- Recusa, erro ou resposta inválida => a classificação determinística prevalece.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.config import settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Você é um analista de presença digital de pequenas empresas. Você recebe dados públicos de uma empresa e "
    "uma lista de sites candidatos com as evidências coletadas automaticamente. Decida, para cada candidato, se ele "
    "é o site oficial da empresa, considerando que empresas homônimas em outras cidades são comuns. Use somente as "
    "evidências fornecidas; não presuma fatos que não estejam nelas. Se as evidências não bastarem, responda "
    "'incerto'. Redes sociais, marketplaces e diretórios não são sites próprios. O resumo deve ter no máximo 3 "
    "frases em português, citar apenas fatos presentes nas evidências e não incluir telefones ou e-mails."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["oficial", "nao_pertence", "incerto"]},
                    "confidence": {"type": "integer"},
                    "rationale": {"type": "string"},
                },
                "required": ["domain", "verdict", "confidence", "rationale"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["candidates", "summary"],
    "additionalProperties": False,
}


@dataclass
class AiVerdict:
    domain: str
    verdict: str
    confidence: int
    rationale: str


@dataclass
class AiResult:
    verdicts: dict[str, AiVerdict]
    summary: str | None
    cost_usd: float


class AiAnalyzer:
    def __init__(self):
        self._client = None

    @property
    def enabled(self) -> bool:
        return settings.ai_enabled

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=2, timeout=60)
        return self._client

    async def adjudicate(self, business: dict, candidates: list[dict], context: dict) -> AiResult | None:
        if not self.enabled or not candidates:
            return None
        allowed = {c["domain"] for c in candidates}
        user_content = json.dumps(
            {"empresa": business, "candidatos": candidates, "contexto": context}, ensure_ascii=False
        )
        try:
            import anthropic

            client = self._get_client()
            kwargs = dict(
                model=settings.ai_model,
                max_tokens=2000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
                output_config={"effort": settings.ai_effort, "format": {"type": "json_schema", "schema": SCHEMA}},
            )
            if settings.ai_use_server_fallbacks:
                resp = await client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
                )
            else:
                resp = await client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            log.warning("IA: limite de requisições atingido; seguindo sem IA")
            return None
        except anthropic.APIStatusError as e:
            log.warning("IA: erro da API (%s); seguindo sem IA", e.status_code)
            return None
        except anthropic.APIConnectionError:
            log.warning("IA: falha de conexão; seguindo sem IA")
            return None
        usage = getattr(resp, "usage", None)
        cost = 0.0
        if usage is not None:
            cost = (usage.input_tokens * settings.ai_input_price_per_mtok
                    + usage.output_tokens * settings.ai_output_price_per_mtok) / 1_000_000
        if resp.stop_reason in ("refusal", "max_tokens"):
            return AiResult({}, None, cost)
        text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), None)
        try:
            data = json.loads(text or "")
        except json.JSONDecodeError:
            return AiResult({}, None, cost)
        verdicts: dict[str, AiVerdict] = {}
        for item in data.get("candidates", []):
            dom = str(item.get("domain", "")).lower()
            if dom not in allowed:  # nunca aceitar domínios inventados
                continue
            verdicts[dom] = AiVerdict(dom, item.get("verdict", "incerto"),
                                      max(0, min(100, int(item.get("confidence", 0)))),
                                      str(item.get("rationale", ""))[:500])
        summary = str(data.get("summary") or "")[:800] or None
        return AiResult(verdicts, summary, cost)


ai_analyzer = AiAnalyzer()
