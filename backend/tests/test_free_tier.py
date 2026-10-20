"""Modo somente gratuito, cotas e modo de usuário único."""

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.providers.base import Location, ProviderError
from app.providers.google_places import ENDPOINT, GooglePlacesProvider
from app.providers.web_search import BraveSearchProvider
from app.services import quota
from app.services.costs import estimate
from app.verification.classifier import VerifyOptions, verify
from app.verification.matcher import BusinessSnapshot
from tests.fakes import FakeChecker, FakeWeb


@pytest.fixture
def free_mode(monkeypatch):
    monkeypatch.setattr(settings, "free_tier_only", True)
    monkeypatch.setattr(settings, "free_tier_safety_percent", 100)
    monkeypatch.setattr(settings, "google_places_api_key", "k")
    monkeypatch.setattr(settings, "brave_search_api_key", "k")
    monkeypatch.setattr(settings, "web_search_cache_hours", 0)
    monkeypatch.setattr(settings, "google_places_cache_hours", 0)


@pytest.mark.asyncio
@respx.mock
async def test_google_bloqueia_ao_atingir_cota(free_mode, monkeypatch):
    monkeypatch.setattr(settings, "google_places_free_monthly_requests", 2)
    route = respx.post(ENDPOINT).respond(200, json={"places": []})
    async with httpx.AsyncClient() as c:
        for _ in range(2):
            page = await GooglePlacesProvider().search(c, "x", Location(city="Curitiba"), None, 20)
            assert page.cost_usd == 0  # dentro da cota grátis
        with pytest.raises(ProviderError) as e:
            await GooglePlacesProvider().search(c, "x", Location(city="Curitiba"), None, 20)
    assert e.value.quota_exhausted and not e.value.retryable
    assert route.call_count == 2  # a 3ª requisição nunca foi enviada
    u = quota.usage("google_places")
    assert u["used"] == 2 and u["remaining"] == 0


@pytest.mark.asyncio
@respx.mock
async def test_erro_de_rede_nao_consome_cota(free_mode, monkeypatch):
    monkeypatch.setattr("app.providers.base.asyncio.sleep", _nosleep)
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        side_effect=[httpx.ConnectError("x"), httpx.Response(200, json={"web": {"results": []}})])
    async with httpx.AsyncClient() as c:
        await BraveSearchProvider().search(c, "q", "Brasil")
    assert quota.usage("brave_search")["used"] == 1


async def _nosleep(_):
    return None


def test_contagem_sem_bloqueio_fora_do_modo_gratuito(monkeypatch):
    monkeypatch.setattr(settings, "free_tier_only", False)
    monkeypatch.setattr(settings, "brave_search_free_monthly_requests", 1)
    for _ in range(3):
        assert quota.reserve("brave_search")[0]
    assert quota.usage("brave_search")["used"] == 3
    assert quota.reserve("osm")[0]  # OSM não tem cota


@pytest.mark.asyncio
async def test_cota_de_busca_esgotada_nao_vira_sem_site():
    class QuotaWeb(FakeWeb):
        async def search(self, client, query, country):
            raise ProviderError(self.name, "cota", retryable=False, quota_exhausted=True)

    b = BusinessSnapshot(id=1, name="Oficina do Zé", city="Curitiba", phone_normalized="554133334444",
                         source_websites=[("google_places", None)], sources=["google_places"])
    async with httpx.AsyncClient() as c:
        out = await verify(b, client=c, web=QuotaWeb(), checker=FakeChecker({}), options=VerifyOptions(domain_guessing=False))
    assert out.status == "SITE_NAO_INFORMADO_NO_MAPS"
    assert "cota gratuita" in out.reason


@pytest.mark.asyncio
async def test_uma_busca_por_empresa():
    web = FakeWeb({})
    b = BusinessSnapshot(id=1, name="Oficina do Zé", city="Curitiba", phone_normalized="554133334444",
                         source_websites=[("google_places", None)], sources=["google_places"])
    async with httpx.AsyncClient() as c:
        out = await verify(b, client=c, web=web, checker=FakeChecker({}),
                           options=VerifyOptions(domain_guessing=False, web_queries=1))
    assert len(web.queries) == 1 and out.status == "SEM_SITE_IDENTIFICADO"


def test_estimativa_gratuita(free_mode, monkeypatch):
    monkeypatch.setattr(settings, "google_places_free_monthly_requests", 2)
    cfg = {"locations": [{"city": "Curitiba"}], "categories": ["dentistas"], "sources": ["google_places"],
           "max_results": 60, "web_verification": True, "web_queries_per_business": 1}
    est = estimate(cfg)
    assert est["total_usd"] == 0 and est["free_tier_only"]
    assert any("Google Places" in w and "sem cobrança" in w for w in est["quota_warnings"])  # 60 empresas = 3 req > 2 grátis
    brave = next(l for l in est["lines"] if l["provider"] == "Brave Search API")
    assert brave["requests"] == 60 and "cota grátis" in brave["note"]


def test_modo_usuario_unico(monkeypatch):
    monkeypatch.setattr(settings, "single_user_mode", True)
    body = {"organization": "Eu", "name": "Eu", "email": "eu@ex.com", "password": "senha-forte-1"}
    with TestClient(app) as c:
        assert c.get("/api/auth/options").json()["registration_open"] is True
        assert c.post("/api/auth/register", json=body).status_code == 201
        assert c.get("/api/auth/options").json()["registration_open"] is False
        h = {"X-Requested-With": "prospecia"}
        r = c.post("/api/users", json={"name": "Beto", "email": "b@ex.com", "password": "senha-forte-2"}, headers=h)
        assert r.status_code == 403
        q = c.get("/api/settings").json()
        assert q["single_user_mode"] and {x["provider"] for x in q["quotas"]} >= {"google_places", "brave_search"}
    with TestClient(app) as other:
        assert other.post("/api/auth/register", json={**body, "email": "outro@ex.com"}).status_code == 403
