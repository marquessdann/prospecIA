"""Testes da classificação de presença digital (o requisito mais importante)."""

import httpx
import pytest

from app.providers.base import WebResult
from app.verification.classifier import VerifyOptions, guess_domains, verify
from app.verification.matcher import BusinessSnapshot
from tests.fakes import FakeChecker, FakeWeb



def biz(**kw):
    base = dict(id=1, name="Clínica Odontológica Sorriso Pleno", city="Curitiba", state="PR", country="Brasil",
                address="Rua XV de Novembro, 1000 - Centro", phone_normalized="5541998765432",
                source_websites=[("google_places", None)], sources=["google_places"])
    base.update(kw)
    return BusinessSnapshot(**base)


async def run(b, web=None, sites=None, **opts):
    async with httpx.AsyncClient() as client:
        return await verify(b, client=client, web=web, checker=FakeChecker(sites or {}),
                            options=VerifyOptions(domain_guessing=False, **opts))


@pytest.mark.asyncio
async def test_site_informado_e_acessivel_possui_site():
    b = biz(source_websites=[("google_places", "https://www.sorrisopleno.com.br/")])
    out = await run(b, sites={"sorrisopleno.com.br": {"title": "Sorriso Pleno Odontologia",
                                                     "text": "Ligue (41) 99876-5432 Curitiba"}})
    assert out.status == "POSSUI_SITE"
    assert out.official_domain == "sorrisopleno.com.br"
    assert out.confidence >= 70
    assert any(e["type"] == "source_field" and e["polarity"] == "+" for e in out.evidence)


@pytest.mark.asyncio
async def test_site_informado_mas_dns_falha_indisponivel():
    b = biz(source_websites=[("google_places", "http://sorrisoplenoantigo.com.br")])
    out = await run(b, sites={})  # FakeChecker devolve erro dns
    assert out.status == "SITE_INDISPONIVEL"
    assert out.confidence == 85
    assert "DNS" in out.reason


@pytest.mark.asyncio
async def test_dominio_estacionado_conta_como_indisponivel():
    b = biz(source_websites=[("google_places", "https://sorrisopleno.com.br")])
    out = await run(b, sites={"sorrisopleno.com.br": {"parked": True, "text": "This domain is for sale"}})
    assert out.status == "SITE_INDISPONIVEL"
    assert "estacionado" in out.reason


@pytest.mark.asyncio
async def test_sem_busca_web_fica_nao_informado_no_maps():
    out = await run(biz(), web=None)
    assert out.status == "SITE_NAO_INFORMADO_NO_MAPS"
    assert "NÃO confirma" in out.reason


@pytest.mark.asyncio
async def test_apenas_redes_sociais_sem_site_identificado():
    web = FakeWeb({"Sorriso Pleno": [
        WebResult("https://www.instagram.com/sorrisopleno", "Clínica Odontológica Sorriso Pleno (@sorrisopleno)", "", 1),
        WebResult("https://www.doctoralia.com.br/clinicas/sorriso-pleno", "Clínica Odontológica Sorriso Pleno - Doctoralia", "", 2),
        WebResult("https://g1.globo.com/pr/noticia", "Notícias de Curitiba", "", 3),
    ]})
    out = await run(biz(), web=web)
    assert out.status == "SEM_SITE_IDENTIFICADO"
    assert out.social_only is True
    assert any("instagram" in s for s in out.social_links)
    assert any("doctoralia" in d for d in out.directory_links)
    assert out.web_queries == 2  # nome+cidade e telefone
    assert out.confidence >= 70


@pytest.mark.asyncio
async def test_homonimo_em_outra_cidade_nao_e_confirmado():
    web = FakeWeb({"Sorriso Pleno": [WebResult("https://sorrisopleno.com.br", "Sorriso Pleno Odontologia - São Paulo", "", 1)]})
    sites = {"sorrisopleno.com.br": {"title": "Sorriso Pleno Odontologia", "text": "Av Paulista São Paulo (11) 3333-4444"}}
    out = await run(biz(), web=web, sites=sites)
    assert out.status == "SITE_SUSPEITO"
    assert out.official_website is None
    assert out.candidate_website


@pytest.mark.asyncio
async def test_site_encontrado_na_busca_com_telefone_confirma():
    web = FakeWeb({"Sorriso Pleno": [WebResult("https://sorrisopleno.com.br/contato", "Sorriso Pleno", "", 1)]})
    sites = {"sorrisopleno.com.br": {"title": "Clínica Sorriso Pleno", "text": "Curitiba WhatsApp 41 99876-5432",
                                     "emails": ["contato@sorrisopleno.com.br", "fulano@gmail.com"]}}
    out = await run(biz(), web=web, sites=sites)
    assert out.status == "POSSUI_SITE"
    assert out.public_email == "contato@sorrisopleno.com.br"  # só e-mail do próprio domínio


@pytest.mark.asyncio
async def test_falha_na_busca_fica_pendente():
    out = await run(biz(), web=FakeWeb(fail=True))
    assert out.status == "VERIFICACAO_PENDENTE"


@pytest.mark.asyncio
async def test_site_rede_social_no_cadastro_nao_conta_como_site():
    b = biz(source_websites=[("google_places", "https://facebook.com/sorrisopleno")])
    out = await run(b, web=FakeWeb({}))
    assert out.status == "SEM_SITE_IDENTIFICADO"
    assert out.social_only


@pytest.mark.asyncio
async def test_ia_nao_pode_inventar_dominio(monkeypatch):
    from app.verification.ai import AiResult, AiVerdict

    class FakeAI:
        enabled = True

        async def adjudicate(self, business, candidates, context):
            return AiResult({"inventado.com.br": AiVerdict("inventado.com.br", "oficial", 99, "x")}, "Resumo.", 0.001)

    web = FakeWeb({"Sorriso Pleno": [WebResult("https://sorrisopleno.com.br", "Sorriso Pleno", "", 1)]})
    sites = {"sorrisopleno.com.br": {"title": "Sorriso Pleno", "text": "odontologia"}}
    async with httpx.AsyncClient() as client:
        out = await verify(biz(), client=client, web=web, checker=FakeChecker(sites), ai=FakeAI(),
                           options=VerifyOptions(domain_guessing=False))
    assert out.status != "POSSUI_SITE"
    assert all(c["domain"] != "inventado.com.br" for c in out.candidates)
    assert out.ai_used


def test_guess_domains():
    assert guess_domains("Clínica Odontológica Sorriso Pleno LTDA", "Brasil")[:2] == [
        "clinicaodontologicasorrisopleno.com.br", "clinicaodontologicasorrisopleno.com"]
