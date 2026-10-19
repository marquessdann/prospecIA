"""Provedores e verificadores falsos para testes (sem rede)."""

from app.providers.base import (
    DiscoveryPage,
    PlaceProvider,
    PlaceRecord,
    ProviderError,
    WebResult,
    WebSearchProvider,
    WebSearchResponse,
)
from app.verification.site_checker import SiteCheck


class FakePlaces(PlaceProvider):
    name = "fake_places"
    label = "Fake Places"
    requires_credentials = False
    cost_per_request = 0.01
    max_results_per_query = 60

    def __init__(self, pages: list[list[PlaceRecord]], fail_times: int = 0):
        self.pages = pages
        self.calls = 0
        self.fail_times = fail_times

    def available(self):
        return True

    async def search(self, client, category, location, page_token, limit):
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ProviderError(self.name, "falha temporária simulada", retryable=True)
        idx = int(page_token or 0)
        nxt = str(idx + 1) if idx + 1 < len(self.pages) else None
        return DiscoveryPage(records=self.pages[idx], next_token=nxt, requests=1, cost_usd=self.cost_per_request)


class FakeWeb(WebSearchProvider):
    name = "fake_web"
    label = "Fake Web"
    cost_per_request = 0.005

    def __init__(self, results: dict[str, list[WebResult]] | None = None, fail: bool = False):
        self.results = results or {}
        self.fail = fail
        self.queries: list[str] = []

    def available(self):
        return True

    async def search(self, client, query, country):
        self.queries.append(query)
        if self.fail:
            raise ProviderError(self.name, "HTTP 503", retryable=True)
        for key, res in self.results.items():
            if key in query:
                return WebSearchResponse(query=query, results=res, cost_usd=self.cost_per_request)
        return WebSearchResponse(query=query, results=[], cost_usd=self.cost_per_request)


class FakeChecker:
    """Mapeia domínio -> SiteCheck pré-definido."""

    def __init__(self, sites: dict[str, dict]):
        self.sites = sites
        self.checked: list[str] = []

    async def check(self, url, analyze_content=True):
        self.checked.append(url)
        for dom, spec in self.sites.items():
            if dom in url:
                text = spec.get("text", "")
                return SiteCheck(url=url, final_url=url, reachable=spec.get("reachable", True),
                                 http_status=spec.get("status", 200), error=spec.get("error"),
                                 parked=spec.get("parked", False), content_analyzed=True,
                                 title=spec.get("title"), text_excerpt=text,
                                 phones_found=spec.get("phones", []), emails_found=spec.get("emails", []))
        return SiteCheck(url=url, reachable=False, error="dns")

    async def aclose(self):
        pass


def rec(ext_id, name, phone=None, website=None, city="Curitiba", lat=None, lng=None, source="fake_places", **kw):
    return PlaceRecord(source=source, external_id=ext_id, name=name, phone=phone, website=website, city=city,
                       state="PR", country="Brasil", lat=lat, lng=lng, maps_url=f"https://maps.example/{ext_id}", **kw)
