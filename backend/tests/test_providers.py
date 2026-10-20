"""Testes das integrações reais com respostas HTTP simuladas (formato oficial das APIs)."""

import httpx
import pytest
import respx

from app.config import settings
from app.providers.base import Location, ProviderError
from app.providers.google_places import ENDPOINT, GooglePlacesProvider
from app.providers.osm_overpass import OsmOverpassProvider, category_filters
from app.providers.web_search import BraveSearchProvider


GOOGLE_RESPONSE = {
    "places": [
        {"id": "ChIJ1", "displayName": {"text": "Barbearia do Zé"}, "formattedAddress": "R. A, 10 - Centro, Curitiba - PR",
         "addressComponents": [{"longText": "Curitiba", "shortText": "Curitiba", "types": ["administrative_area_level_2"]},
                               {"longText": "Paraná", "shortText": "PR", "types": ["administrative_area_level_1"]},
                               {"longText": "Centro", "shortText": "Centro", "types": ["sublocality_level_1", "sublocality"]},
                               {"longText": "80000-000", "shortText": "80000-000", "types": ["postal_code"]},
                               {"longText": "Brasil", "shortText": "BR", "types": ["country"]}],
         "location": {"latitude": -25.43, "longitude": -49.27}, "internationalPhoneNumber": "+55 41 3333-4444",
         "googleMapsUri": "https://maps.google.com/?cid=1", "rating": 4.8, "userRatingCount": 210,
         "businessStatus": "OPERATIONAL", "primaryTypeDisplayName": {"text": "Barbearia"}},
        {"id": "ChIJ2", "displayName": {"text": "Barber Prime"}, "websiteUri": "https://barberprime.com.br/"},
    ],
    "nextPageToken": "tok2",
}


@pytest.mark.asyncio
@respx.mock
async def test_google_places_parse(monkeypatch):
    monkeypatch.setattr(settings, "google_places_api_key", "k")
    route = respx.post(ENDPOINT).respond(200, json=GOOGLE_RESPONSE)
    async with httpx.AsyncClient() as c:
        page = await GooglePlacesProvider().search(c, "barbearia", Location(city="Curitiba", state="PR"), None, 20)
    body = route.calls[0].request
    assert body.headers["X-Goog-FieldMask"].count("websiteUri") == 1
    assert b"barbearia em Curitiba, PR, Brasil" in body.content
    assert page.next_token == "tok2" and page.cost_usd > 0
    z = page.records[0]
    assert (z.city, z.state, z.neighborhood, z.website) == ("Curitiba", "PR", "Centro", None)
    assert z.reviews_count == 210 and z.business_status == "operational"
    assert page.records[1].website == "https://barberprime.com.br/"


@pytest.mark.asyncio
@respx.mock
async def test_google_sem_chave_e_403(monkeypatch):
    monkeypatch.setattr(settings, "google_places_api_key", None)
    async with httpx.AsyncClient() as c:
        with pytest.raises(ProviderError) as e:
            await GooglePlacesProvider().search(c, "x", Location(city="Curitiba"), None, 20)
        assert not e.value.retryable
        monkeypatch.setattr(settings, "google_places_api_key", "k")
        respx.post(ENDPOINT).respond(403, json={"error": {"message": "billing"}})
        with pytest.raises(ProviderError) as e:
            await GooglePlacesProvider().search(c, "x", Location(city="Curitiba"), None, 20)
        assert e.value.billing and not e.value.retryable


@pytest.mark.asyncio
@respx.mock
async def test_retentativa_em_429(monkeypatch):
    monkeypatch.setattr(settings, "google_places_api_key", "k")
    monkeypatch.setattr("app.providers.base.asyncio.sleep", _nosleep)
    respx.post(ENDPOINT).mock(side_effect=[httpx.Response(429), httpx.Response(200, json={"places": []})])
    async with httpx.AsyncClient() as c:
        page = await GooglePlacesProvider().search(c, "x", Location(city="Curitiba"), None, 20)
    assert page.records == []


async def _nosleep(_):
    return None


@pytest.mark.asyncio
@respx.mock
async def test_osm_overpass(monkeypatch):
    monkeypatch.setattr(settings, "osm_cache_hours", 0)
    respx.get(f"{settings.nominatim_url}/search").respond(200, json=[
        {"osm_type": "relation", "osm_id": 297514, "lat": "-25.4", "lon": "-49.2"}])
    route = respx.post(settings.overpass_url).respond(200, json={"elements": [
        {"type": "node", "id": 1, "lat": -25.4, "lon": -49.2, "tags": {"name": "Dentista Feliz", "amenity": "dentist",
         "phone": "+55 41 3333-0000", "addr:street": "Rua B", "addr:housenumber": "5", "contact:instagram": "@dfeliz"}},
        {"type": "way", "id": 2, "center": {"lat": -25.41, "lon": -49.21}, "tags": {"name": "Odonto Max",
         "healthcare": "dentist", "website": "https://odontomax.com.br"}},
        {"type": "node", "id": 3, "lat": 0, "lon": 0, "tags": {"amenity": "dentist"}},  # sem nome: ignorado
    ]})
    async with httpx.AsyncClient() as c:
        page = await OsmOverpassProvider().search(c, "dentistas", Location(city="Curitiba", state="PR"), None, 50)
    q = route.calls[0].request.content.decode()
    assert "area" in q and "dentist" in q
    assert len(page.records) == 2
    assert page.records[0].social_links == ["https://instagram.com/dfeliz"]
    assert page.records[1].website == "https://odontomax.com.br" and page.records[1].lat == -25.41


def test_osm_categoria_personalizada_escapa_aspas():
    f = category_filters('Estúdio "tattoo"')
    assert all('"' not in x.split('~"')[1].split('",i')[0] for x in f)


@pytest.mark.asyncio
@respx.mock
async def test_brave(monkeypatch):
    monkeypatch.setattr(settings, "brave_search_api_key", "k")
    monkeypatch.setattr(settings, "web_search_cache_hours", 0)
    respx.get("https://api.search.brave.com/res/v1/web/search").respond(200, json={"web": {"results": [
        {"url": "https://a.com", "title": "A", "description": "d"}]}})
    async with httpx.AsyncClient() as c:
        r = await BraveSearchProvider().search(c, '"A" Curitiba', "Brasil")
    assert r.results[0].url == "https://a.com" and r.cost_usd == settings.cost_brave_search_per_request


@pytest.mark.asyncio
@respx.mock
async def test_overpass_usa_espelho_quando_principal_esta_lotado(monkeypatch):
    monkeypatch.setattr(settings, "osm_cache_hours", 0)
    monkeypatch.setattr(settings, "overpass_fallback_urls", "https://espelho.example/api/interpreter")
    monkeypatch.setattr("app.providers.base.asyncio.sleep", _nosleep)
    respx.get(f"{settings.nominatim_url}/search").respond(200, json=[
        {"osm_type": "relation", "osm_id": 1, "lat": "-25.4", "lon": "-49.2"}])
    principal = respx.post(settings.overpass_url).respond(502, text="server is currently at capacity")
    espelho = respx.post("https://espelho.example/api/interpreter").respond(200, json={"elements": [
        {"type": "node", "id": 1, "lat": -25.4, "lon": -49.2, "tags": {"name": "Bar do Zé", "amenity": "bar"}}]})
    async with httpx.AsyncClient() as c:
        page = await OsmOverpassProvider().search(c, "restaurantes", Location(city="Curitiba"), None, 50)
    assert principal.call_count == 2 and espelho.call_count == 1
    assert page.records[0].name == "Bar do Zé"


@pytest.mark.asyncio
@respx.mock
async def test_overpass_todos_lotados_gera_erro_curto_e_retentavel(monkeypatch):
    monkeypatch.setattr(settings, "osm_cache_hours", 0)
    monkeypatch.setattr(settings, "overpass_fallback_urls", "")
    monkeypatch.setattr("app.providers.base.asyncio.sleep", _nosleep)
    respx.get(f"{settings.nominatim_url}/search").respond(200, json=[
        {"osm_type": "relation", "osm_id": 1, "lat": "-25.4", "lon": "-49.2"}])
    respx.post(settings.overpass_url).respond(502, text="x" * 2000)
    async with httpx.AsyncClient() as c:
        with pytest.raises(ProviderError) as e:
            await OsmOverpassProvider().search(c, "restaurantes", Location(city="Curitiba"), None, 50)
    assert e.value.retryable and len(str(e.value)) < 400 and "ocupados" in str(e.value)
