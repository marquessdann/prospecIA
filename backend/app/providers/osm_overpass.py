"""OpenStreetMap: geocodificação via Nominatim e busca de estabelecimentos via Overpass API.

Fonte aberta (ODbL) que funciona sem credenciais. Políticas de uso:
- Nominatim: no máximo 1 requisição/s, User-Agent identificável, sem uso massivo.
  https://operations.osmfoundation.org/policies/nominatim/
- Overpass: uso moderado; instâncias públicas têm cotas por IP.
Para volume alto, hospede instâncias próprias (OVERPASS_URL / NOMINATIM_URL).
"""

from __future__ import annotations

import re

import httpx

from app.config import settings
from app.providers.base import DiscoveryPage, Location, PlaceProvider, PlaceRecord, ProviderError
from app.verification.normalize import strip_accents

# Segmentos conhecidos -> filtros de tags OSM.
CATEGORY_TAGS: dict[str, list[str]] = {
    "restaurantes": ['["amenity"~"^(restaurant|fast_food|cafe|food_court)$"]'],
    "clinicas medicas": ['["amenity"~"^(clinic|doctors)$"]', '["healthcare"~"^(clinic|doctor|centre)$"]'],
    "consultorios odontologicos": ['["amenity"="dentist"]', '["healthcare"="dentist"]'],
    "dentistas": ['["amenity"="dentist"]', '["healthcare"="dentist"]'],
    "psicologos": ['["healthcare"="psychotherapist"]', '["healthcare:speciality"~"psych"]'],
    "academias": ['["leisure"="fitness_centre"]', '["sport"="fitness"]'],
    "saloes de beleza": ['["shop"="beauty"]', '["shop"="hairdresser"]["hairdresser"!="barber"]'],
    "barbearias": ['["shop"="hairdresser"]["hairdresser"="barber"]', '["shop"="barber"]'],
    "oficinas mecanicas": ['["shop"="car_repair"]', '["craft"="car_repair"]'],
    "imobiliarias": ['["office"="estate_agent"]'],
    "advogados": ['["office"="lawyer"]'],
    "contadores": ['["office"~"^(accountant|tax_advisor)$"]'],
    "pet shops": ['["shop"="pet"]', '["amenity"="veterinary"]'],
    "lojas de roupas": ['["shop"~"^(clothes|boutique|shoes)$"]'],
    "empresas de construcao": ['["craft"~"^(builder|carpenter|electrician|plumber|roofer|tiler)$"]', '["office"="construction_company"]', '["shop"~"^(doityourself|hardware)$"]'],
    "prestadores de servicos": ['["craft"]', '["office"~"^(company|consulting)$"]'],
    "pequenos negocios": ['["shop"]', '["craft"]'],
    "padarias": ['["shop"~"^(bakery|pastry)$"]'],
    "farmacias": ['["amenity"="pharmacy"]'],
    "hoteis": ['["tourism"~"^(hotel|guest_house|hostel|motel)$"]'],
    "escolas": ['["amenity"~"^(school|language_school|music_school|driving_school)$"]'],
}
ALIASES = {
    "restaurante": "restaurantes", "clinica": "clinicas medicas", "clinicas": "clinicas medicas",
    "clinicas odontologicas": "consultorios odontologicos", "odontologia": "consultorios odontologicos",
    "dentista": "dentistas", "psicologo": "psicologos", "psicologia": "psicologos", "academia": "academias",
    "salao de beleza": "saloes de beleza", "barbearia": "barbearias", "oficina mecanica": "oficinas mecanicas",
    "oficinas": "oficinas mecanicas", "imobiliaria": "imobiliarias", "advogado": "advogados",
    "advocacia": "advogados", "contador": "contadores", "contabilidade": "contadores", "pet shop": "pet shops",
    "petshop": "pet shops", "loja de roupas": "lojas de roupas", "construcao": "empresas de construcao",
    "construtoras": "empresas de construcao", "padaria": "padarias", "farmacia": "farmacias", "hotel": "hoteis",
}


def category_filters(category: str) -> list[str]:
    key = strip_accents(category.lower()).strip()
    key = ALIASES.get(key, key)
    if key in CATEGORY_TAGS:
        return CATEGORY_TAGS[key]
    # Segmento personalizado: busca por nome em estabelecimentos comerciais.
    term = re.sub(r'["\\\[\]]', "", category).strip()[:60]
    return [f'["name"~"{term}",i]["shop"]', f'["name"~"{term}",i]["amenity"]',
            f'["name"~"{term}",i]["office"]', f'["name"~"{term}",i]["craft"]',
            f'["name"~"{term}",i]["healthcare"]']


class OsmOverpassProvider(PlaceProvider):
    name = "osm"
    label = "OpenStreetMap (Nominatim + Overpass)"
    requires_credentials = False
    max_results_per_query = None
    coverage = (
        "Base colaborativa: cobertura de comércios varia muito por cidade e costuma ser menor que a do Google "
        "Maps no Brasil. Retorna todos os elementos marcados com as tags do segmento dentro da área."
    )
    terms_notes = (
        "Gratuito, licença ODbL (atribuição obrigatória: © colaboradores do OpenStreetMap). Servidores "
        "públicos têm limites de uso; respeitamos 1 req/s no Nominatim e cache de 7 dias."
    )

    @property
    def rps(self) -> float:  # type: ignore[override]
        return settings.osm_rps

    @property
    def cache_hours(self) -> int:  # type: ignore[override]
        return settings.osm_cache_hours

    @property
    def cost_per_request(self) -> float:  # type: ignore[override]
        return settings.cost_osm_per_request

    def available(self) -> bool:
        return settings.osm_enabled

    def _headers(self) -> dict:
        ua = "ProspecIA/1.0"
        if settings.osm_contact_email:
            ua += f" ({settings.osm_contact_email})"
        return {"User-Agent": ua, "Accept-Language": "pt-BR,pt;q=0.9"}

    async def geocode(self, client: httpx.AsyncClient, location: Location) -> dict:
        params: dict = {"format": "jsonv2", "limit": 1, "addressdetails": 1}
        if location.postal_code and not location.city:
            params["postalcode"] = location.postal_code
            if location.country:
                params["country"] = location.country
        else:
            params["q"] = ", ".join(p for p in [location.address, location.neighborhood, location.postal_code,
                                                location.city, location.state, location.country] if p)
        data, _ = await self._request("GET", f"{settings.nominatim_url}/search", client=client, params=params,
                                      headers=self._headers(), cache_payload={"geocode": params})
        if not data:
            raise ProviderError(self.name, f"localização não encontrada: {location.label()}", retryable=False)
        return data[0]

    async def search(self, client: httpx.AsyncClient, category: str, location: Location,
                     page_token: str | None, limit: int) -> DiscoveryPage:
        requests = 0
        if location.lat is not None and location.lng is not None:
            scope = f"(around:{int((location.radius_km or 2) * 1000)},{location.lat},{location.lng})"
            prefix = ""
        else:
            place = await self.geocode(client, location)
            requests += 1
            osm_type, osm_id = place.get("osm_type"), int(place.get("osm_id", 0))
            if osm_type == "relation" and not (location.neighborhood or location.postal_code or location.address):
                prefix = f"area(id:{3600000000 + osm_id})->.a;"
                scope = "(area.a)"
            else:
                radius = int((location.radius_km or 2) * 1000)
                scope = f"(around:{radius},{place['lat']},{place['lon']})"
                prefix = ""
        filters = category_filters(category)
        body = "".join(f"nwr{f}{scope};" for f in filters)
        query = f"[out:json][timeout:90];{prefix}({body});out center tags {max(1, limit)};"
        data, cached = await self._request("POST", settings.overpass_url, client=client, data={"data": query},
                                           headers=self._headers(), cache_payload={"q": query}, retries=3)
        requests += 0 if cached else 1
        records = [r for r in (self._parse(e, category) for e in data.get("elements", [])) if r]
        return DiscoveryPage(records=records[:limit], next_token=None, requests=requests, cost_usd=0.0, cached=cached)

    @staticmethod
    def _parse(el: dict, category: str) -> PlaceRecord | None:
        tags = el.get("tags") or {}
        name = tags.get("name")
        if not name:
            return None
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lng = el.get("lon") or (el.get("center") or {}).get("lon")
        street = " ".join(x for x in [tags.get("addr:street"), tags.get("addr:housenumber")] if x)
        address = ", ".join(x for x in [street, tags.get("addr:suburb"), tags.get("addr:city"),
                                        tags.get("addr:state"), tags.get("addr:postcode")] if x) or None
        socials = [tags[k] for k in ("contact:facebook", "contact:instagram", "facebook", "instagram") if tags.get(k)]
        socials = [s if s.startswith("http") else f"https://instagram.com/{s.lstrip('@')}" for s in socials]
        kind = next((f"{k}={tags[k]}" for k in ("amenity", "shop", "office", "craft", "healthcare", "leisure", "tourism") if k in tags), None)
        osm_url = f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}"
        return PlaceRecord(
            source="osm",
            external_id=f"{el.get('type')}/{el.get('id')}",
            name=name,
            category=category,
            categories=[kind] if kind else [],
            address=address,
            neighborhood=tags.get("addr:suburb"),
            city=tags.get("addr:city"),
            state=tags.get("addr:state"),
            country=tags.get("addr:country"),
            postal_code=tags.get("addr:postcode"),
            lat=lat,
            lng=lng,
            phone=tags.get("phone") or tags.get("contact:phone") or tags.get("contact:mobile"),
            email=tags.get("email") or tags.get("contact:email"),
            website=tags.get("website") or tags.get("contact:website") or tags.get("url"),
            social_links=socials,
            maps_url=osm_url,
            source_url=osm_url,
            business_status="closed" if tags.get("disused") or tags.get("abandoned") else None,
            raw={"type": el.get("type"), "id": el.get("id"), "kind": kind},
        )
