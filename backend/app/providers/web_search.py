"""Provedores de busca web autorizados (via API oficial).

Observações de mercado (out/2026):
- Bing Web Search API foi aposentada pela Microsoft em 11/08/2025 — não é suportada.
- Google Programmable Search (Custom Search JSON API) está fechada para novos clientes e
  encerra para clientes existentes em 01/01/2027; mantida apenas para quem já possui acesso.
- Brave Search API é a opção recomendada (índice próprio, plano pago por consulta).
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.providers.base import ProviderError, WebResult, WebSearchProvider, WebSearchResponse

BRAVE_COUNTRIES = {"brasil": "BR", "brazil": "BR", "portugal": "PT", "argentina": "AR", "mexico": "MX",
                   "méxico": "MX", "estados unidos": "US", "chile": "CL"}


class BraveSearchProvider(WebSearchProvider):
    name = "brave_search"
    label = "Brave Search API"
    coverage = "Índice web próprio da Brave; até 20 resultados por consulta (usamos os 10 primeiros)."
    terms_notes = ("Plano pago por consulta (~US$ 5/1.000 no plano Search, com crédito mensal). "
                   "Respeite os termos de armazenamento de resultados do seu plano.")

    @property
    def rps(self) -> float:  # type: ignore[override]
        return settings.brave_search_rps

    @property
    def cache_hours(self) -> int:  # type: ignore[override]
        return settings.web_search_cache_hours

    @property
    def cost_per_request(self) -> float:  # type: ignore[override]
        return settings.cost_brave_search_per_request

    def available(self) -> bool:
        return bool(settings.brave_search_api_key)

    async def search(self, client: httpx.AsyncClient, query: str, country: str | None) -> WebSearchResponse:
        if not self.available():
            raise ProviderError(self.name, "BRAVE_SEARCH_API_KEY não configurada", retryable=False)
        params = {"q": query, "count": settings.web_search_results_per_query, "search_lang": "pt-br",
                  "safesearch": "moderate"}
        if c := BRAVE_COUNTRIES.get((country or "").lower()):
            params["country"] = c
        data, cached = await self._request(
            "GET", "https://api.search.brave.com/res/v1/web/search", client=client, params=params,
            headers={"X-Subscription-Token": settings.brave_search_api_key or "", "Accept": "application/json"},
            cache_payload=params,
        )
        results = [WebResult(url=r.get("url", ""), title=r.get("title"), snippet=r.get("description"), rank=i + 1)
                   for i, r in enumerate((data.get("web") or {}).get("results", [])) if r.get("url")]
        return WebSearchResponse(query=query, results=results, cost_usd=0.0 if cached else self.cost_per_request,
                                 cached=cached)


class GoogleCseProvider(WebSearchProvider):
    name = "google_cse"
    label = "Google Programmable Search (legado)"
    coverage = "Até 10 resultados por consulta. Encerramento anunciado para 01/01/2027."
    terms_notes = "100 consultas/dia gratuitas, depois US$ 5/1.000 (limite de 10 mil/dia). Fechado a novos clientes."

    @property
    def cache_hours(self) -> int:  # type: ignore[override]
        return settings.web_search_cache_hours

    @property
    def cost_per_request(self) -> float:  # type: ignore[override]
        return settings.cost_google_cse_per_request

    def available(self) -> bool:
        return bool(settings.google_cse_api_key and settings.google_cse_cx)

    async def search(self, client: httpx.AsyncClient, query: str, country: str | None) -> WebSearchResponse:
        if not self.available():
            raise ProviderError(self.name, "GOOGLE_CSE_API_KEY/GOOGLE_CSE_CX não configurados", retryable=False)
        params = {"key": settings.google_cse_api_key, "cx": settings.google_cse_cx, "q": query, "num": 10,
                  "lr": "lang_pt"}
        if c := BRAVE_COUNTRIES.get((country or "").lower()):
            params["gl"] = c.lower()
        cache_params = {k: v for k, v in params.items() if k != "key"}
        data, cached = await self._request("GET", "https://www.googleapis.com/customsearch/v1", client=client,
                                           params=params, cache_payload=cache_params)
        results = [WebResult(url=it.get("link", ""), title=it.get("title"), snippet=it.get("snippet"), rank=i + 1)
                   for i, it in enumerate(data.get("items", []) or []) if it.get("link")]
        return WebSearchResponse(query=query, results=results, cost_usd=0.0 if cached else self.cost_per_request,
                                 cached=cached)
