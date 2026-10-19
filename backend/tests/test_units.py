import httpx
import pytest
import respx

from app.models import Business
from app.services.scoring import compute_score
from app.verification import site_checker
from app.verification.domains import classify_url
from app.verification.matcher import BusinessSnapshot, score_candidate
from app.verification.normalize import normalize_name, normalize_phone, phone_variants, registrable_domain
from app.verification.site_checker import SiteChecker, extract_page_info


def test_normalize_phone_br():
    assert normalize_phone("(41) 99876-5432") == "5541998765432"
    assert normalize_phone("+55 41 3333-4444") == "554133334444"
    assert normalize_phone("041 3333 4444") == "554133334444"
    assert "4133334444" in phone_variants("554133334444")


def test_normalize_name_removes_legal_suffix():
    assert normalize_name("Padaria São José LTDA - ME") == "padaria sao jose"


def test_registrable_domain():
    assert registrable_domain("https://www.loja.minhaempresa.com.br/x") == "minhaempresa.com.br"
    assert registrable_domain("blog.exemplo.com") == "exemplo.com"


@pytest.mark.parametrize("url,kind", [
    ("https://instagram.com/x", "social"), ("https://www.ifood.com.br/delivery/x", "marketplace"),
    ("https://www.doctoralia.com.br/x", "marketplace"), ("https://g.page/x", "directory"),
    ("https://minhaloja.wixsite.com/site", "builder"), ("https://padariajose.com.br", "own"),
    ("not a url", "invalid"),
])
def test_classify_url(url, kind):
    assert classify_url(url).kind == kind


def test_nome_parecido_sem_contato_nao_passa_de_55():
    b = BusinessSnapshot(id=1, name="Auto Center Silva", city="Curitiba", phone_normalized="554133334444")
    m = score_candidate(b, "autocentersilva.com.br", "Auto Center Silva", "Bem-vindo", [], "web_search")
    assert m.score <= 55
    m2 = score_candidate(b, "autocentersilva.com.br", "Auto Center Silva", "Fone 41 3333-4444 Curitiba", [], "web_search")
    assert m2.score >= 70 and m2.phone_match


def test_extract_page_info_parked():
    info = extract_page_info("<html><title>Domain</title><body>This domain is for sale! Buy now</body></html>")
    assert info["parked"]
    info = extract_page_info('<title>Oficina Zé</title><a href="tel:+554133334444">Ligue</a> <p>' + "conteúdo " * 20 + "</p>")
    assert "554133334444" in info["phones"] and not info["parked"]


@pytest.fixture
def no_ssrf(monkeypatch):
    async def ok(url):
        return None
    monkeypatch.setattr(site_checker, "_guard_ssrf", ok)


@pytest.mark.asyncio
@respx.mock
async def test_site_checker_ok_e_404(no_ssrf):
    respx.get("https://ok.example/robots.txt").respond(404)
    respx.get("https://ok.example/").respond(200, html="<title>Empresa OK</title><body>" + "texto " * 30 + "</body>")
    respx.get("https://quebrado.example/robots.txt").respond(404)
    respx.get("https://quebrado.example/").respond(404)
    respx.get("http://quebrado.example/robots.txt").respond(404)
    respx.get("http://quebrado.example/").respond(404)
    chk = SiteChecker()
    ok = await chk.check("ok.example")
    assert ok.reachable and ok.title == "Empresa OK" and ok.content_analyzed
    bad = await chk.check("quebrado.example")
    assert not bad.reachable and bad.error == "http_error" and bad.http_status == 404
    await chk.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_site_checker_respeita_robots_e_bloqueio(no_ssrf):
    respx.get("https://privado.example/robots.txt").respond(200, text="User-agent: *\nDisallow: /")
    respx.get("https://privado.example/").respond(200, html="<title>X</title>")
    respx.get("https://cf.example/robots.txt").respond(404)
    respx.get("https://cf.example/").respond(403)
    chk = SiteChecker()
    r = await chk.check("https://privado.example/")
    assert r.reachable and r.robots_disallowed and not r.content_analyzed
    r2 = await chk.check("https://cf.example/")
    assert r2.reachable and r2.restricted  # não tenta contornar o bloqueio
    await chk.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_site_checker_timeout(no_ssrf):
    respx.get("https://lento.example/robots.txt").respond(404)
    respx.get("https://lento.example/").mock(side_effect=httpx.ConnectTimeout("t"))
    chk = SiteChecker()
    r = await chk.check("https://lento.example/")
    assert not r.reachable and r.error == "timeout"
    await chk.aclose()


@pytest.mark.asyncio
async def test_ssrf_bloqueia_rede_interna():
    chk = SiteChecker()
    for url in ("http://127.0.0.1:8000/", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/"):
        r = await chk.check(url)
        assert not r.reachable and r.error == "ssrf", url
    assert (await chk.check("http://localhost/")).error == "invalid"
    await chk.aclose()


def test_scoring_prioriza_sem_site_e_respeita_nao_contatar():
    a = Business(name="A", digital_status="SEM_SITE_IDENTIFICADO", confidence=85, maps_url="x", phone="1",
                 reviews_count=120, rating=4.6, business_status="operational", address="r", city="c", lat=1, category="x",
                 lead_status="novo")
    b = Business(name="B", digital_status="POSSUI_SITE", confidence=90, maps_url="x", phone="1", reviews_count=120,
                 rating=4.6, business_status="operational", address="r", city="c", lat=1, category="x", lead_status="novo")
    sa, _ = compute_score(a)
    sb, _ = compute_score(b)
    assert sa > 80 and sb < 70 and sa > sb
    a.lead_status = "nao_contatar"
    assert compute_score(a)[0] == 0
    s_custom, br = compute_score(b, {"no_website": 0})
    assert br["weights"]["no_website"] == 0 and s_custom > sb
