"""Contratos das integrações. Cada fonte é um módulo independente que implementa
`PlaceProvider` (descoberta de empresas) ou `WebSearchProvider` (busca web autorizada)."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from app.config import settings
from app.services import quota
from app.services.cache import cache_get, cache_key, cache_set
from app.services.ratelimit import get_limiter

log = logging.getLogger(__name__)


class ProviderError(Exception):
    """Falha de integração. `retryable` indica se uma nova tentativa faz sentido."""

    def __init__(self, provider: str, message: str, retryable: bool = True, billing: bool = False,
                 quota_exhausted: bool = False):
        super().__init__(f"[{provider}] {message}")
        self.provider = provider
        self.retryable = retryable
        self.billing = billing  # cota/cobrança: avisar o usuário
        self.quota_exhausted = quota_exhausted  # cota gratuita do mês/dia atingida (modo gratuito)


@dataclass
class Location:
    country: str | None = "Brasil"
    state: str | None = None
    city: str | None = None
    neighborhood: str | None = None
    postal_code: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    radius_km: float | None = None

    def label(self) -> str:
        parts = [self.address, self.neighborhood, self.postal_code, self.city, self.state, self.country]
        txt = ", ".join(p for p in parts if p)
        if self.lat is not None and self.lng is not None:
            txt = (txt + " " if txt else "") + f"({self.lat:.5f},{self.lng:.5f} r={self.radius_km or 2}km)"
        return txt or "(sem localização)"

    def key(self) -> str:
        return self.label().lower()[:300]

    @classmethod
    def from_dict(cls, d: dict) -> Location:
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


@dataclass
class PlaceRecord:
    source: str
    external_id: str
    name: str
    category: str | None = None
    categories: list[str] = field(default_factory=list)
    address: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None
    lat: float | None = None
    lng: float | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    social_links: list[str] = field(default_factory=list)
    maps_url: str | None = None
    source_url: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    business_status: str | None = None
    raw: dict | None = None


@dataclass
class DiscoveryPage:
    records: list[PlaceRecord]
    next_token: str | None = None
    requests: int = 1
    cost_usd: float = 0.0
    cached: bool = False


@dataclass
class WebResult:
    url: str
    title: str | None
    snippet: str | None
    rank: int


@dataclass
class WebSearchResponse:
    query: str
    results: list[WebResult]
    cost_usd: float = 0.0
    cached: bool = False


@dataclass
class ProviderInfo:
    name: str
    label: str
    kind: str  # places | web_search
    available: bool
    requires_credentials: bool
    cost_per_request_usd: float
    coverage: str
    terms_notes: str
    max_results_per_query: int | None = None


class _HttpMixin:
    name: str = "base"
    rps: float = 1.0
    cache_hours: int = 0
    cost_per_request: float = 0.0

    def billable_cost(self) -> float:
        """Custo de uma requisição; zero no modo gratuito (as requisições ficam dentro da cota grátis)."""
        return 0.0 if settings.free_tier_only else self.cost_per_request

    async def _request(
        self,
        method: str,
        url: str,
        *,
        client: httpx.AsyncClient,
        cache_payload: dict | None = None,
        retries: int = 3,
        **kwargs,
    ) -> tuple[dict, bool]:
        """Executa a requisição com rate limit, cache e novas tentativas controladas."""
        key = None
        if cache_payload is not None and self.cache_hours > 0:
            key = cache_key(self.name, cache_payload)
            if (hit := cache_get(key)) is not None:
                return hit, True
        delay = 1.0
        last: Exception | None = None
        for attempt in range(retries):
            await get_limiter(self.name, self.rps).acquire()
            allowed, used, limit = quota.reserve(self.name)
            if not allowed:
                raise ProviderError(self.name, f"cota gratuita atingida ({used}/{limit} requisições no período); "
                                    "bloqueado para evitar cobrança", retryable=False, billing=True,
                                    quota_exhausted=True)
            try:
                resp = await client.request(method, url, **kwargs)
            except httpx.HTTPError as e:
                quota.release(self.name)  # a requisição não chegou ao provedor: não é cobrada
                last = ProviderError(self.name, f"erro de rede: {e.__class__.__name__}")
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    if key:
                        cache_set(key, self.name, data, self.cache_hours)
                    return data, False
                body = resp.text[:300]
                if resp.status_code in (401, 403):
                    raise ProviderError(self.name, f"credencial inválida ou sem permissão (HTTP {resp.status_code}): {body}", retryable=False, billing=True)
                if resp.status_code == 402:
                    raise ProviderError(self.name, "falha de cobrança/limite do plano (HTTP 402)", retryable=False, billing=True)
                if resp.status_code == 400:
                    raise ProviderError(self.name, f"requisição inválida: {body}", retryable=False)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("retry-after")
                    last = ProviderError(self.name, "limite de requisições/cota atingido (HTTP 429)", billing=True)
                    if retry_after and retry_after.isdigit():
                        delay = max(delay, min(float(retry_after), 60))
                elif resp.status_code >= 500:
                    last = ProviderError(self.name, f"servidor do provedor sobrecarregado ou fora do ar (HTTP {resp.status_code})")
                else:
                    last = ProviderError(self.name, f"HTTP {resp.status_code}: {body}")
            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
        assert last is not None
        raise last


class PlaceProvider(_HttpMixin, ABC):
    label: str = ""
    requires_credentials: bool = True
    cost_per_request: float = 0.0
    max_results_per_query: int | None = None
    coverage: str = ""
    terms_notes: str = ""

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    async def search(
        self, client: httpx.AsyncClient, category: str, location: Location, page_token: str | None, limit: int
    ) -> DiscoveryPage: ...

    def info(self) -> ProviderInfo:
        return ProviderInfo(self.name, self.label, "places", self.available(), self.requires_credentials,
                            self.cost_per_request, self.coverage, self.terms_notes, self.max_results_per_query)


class WebSearchProvider(_HttpMixin, ABC):
    label: str = ""
    requires_credentials: bool = True
    cost_per_request: float = 0.0
    coverage: str = ""
    terms_notes: str = ""

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    async def search(self, client: httpx.AsyncClient, query: str, country: str | None) -> WebSearchResponse: ...

    def info(self) -> ProviderInfo:
        return ProviderInfo(self.name, self.label, "web_search", self.available(), self.requires_credentials,
                            self.cost_per_request, self.coverage, self.terms_notes)
