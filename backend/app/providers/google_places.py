"""Google Places API (New) — Text Search.

Documentação: https://developers.google.com/maps/documentation/places/web-service/text-search
Requer GOOGLE_PLACES_API_KEY com a "Places API (New)" habilitada e faturamento ativo.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.providers.base import DiscoveryPage, Location, PlaceProvider, PlaceRecord, ProviderError

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELDS = [
    "places.id", "places.displayName", "places.formattedAddress", "places.addressComponents",
    "places.location", "places.nationalPhoneNumber", "places.internationalPhoneNumber",
    "places.websiteUri", "places.googleMapsUri", "places.rating", "places.userRatingCount",
    "places.businessStatus", "places.primaryType", "places.primaryTypeDisplayName", "places.types",
    "nextPageToken",
]
COUNTRY_CODES = {"brasil": "BR", "brazil": "BR", "portugal": "PT", "argentina": "AR", "estados unidos": "US",
                 "united states": "US", "mexico": "MX", "méxico": "MX", "chile": "CL", "colombia": "CO", "colômbia": "CO"}


class GooglePlacesProvider(PlaceProvider):
    name = "google_places"
    label = "Google Places API (New)"
    requires_credentials = True
    max_results_per_query = 60

    @property
    def rps(self) -> float:  # type: ignore[override]
        return settings.google_places_rps

    @property
    def cache_hours(self) -> int:  # type: ignore[override]
        return settings.google_places_cache_hours

    @property
    def cost_per_request(self) -> float:  # type: ignore[override]
        return settings.cost_google_text_search_per_request

    coverage = (
        "Até 20 resultados por página e no máximo 60 por consulta (3 páginas). Para cobrir uma cidade grande, "
        "divida a pesquisa por bairros/CEPs. Cobertura depende do que está cadastrado no Google Maps."
    )
    terms_notes = (
        "Pago por requisição (SKU Text Search Enterprise ao solicitar site/telefone/avaliação). "
        "Os termos da Google Maps Platform limitam cache/armazenamento de conteúdo: o place_id pode ser "
        "guardado; os demais campos devem ser atualizados periodicamente (retenção configurável)."
    )

    def available(self) -> bool:
        return bool(settings.google_places_api_key)

    async def search(self, client: httpx.AsyncClient, category: str, location: Location,
                     page_token: str | None, limit: int) -> DiscoveryPage:
        if not self.available():
            raise ProviderError(self.name, "GOOGLE_PLACES_API_KEY não configurada", retryable=False)
        where = ", ".join(p for p in [location.address, location.neighborhood, location.postal_code,
                                      location.city, location.state, location.country] if p)
        body: dict = {
            "textQuery": f"{category} em {where}" if where else category,
            "languageCode": settings.google_places_language,
            "pageSize": min(20, max(1, limit)),
        }
        if code := COUNTRY_CODES.get((location.country or "").lower()):
            body["regionCode"] = code
        if location.lat is not None and location.lng is not None:
            body["locationBias"] = {"circle": {
                "center": {"latitude": location.lat, "longitude": location.lng},
                "radius": min(50000.0, (location.radius_km or 5) * 1000),
            }}
        if page_token:
            body["pageToken"] = page_token
        data, cached = await self._request(
            "POST", ENDPOINT, client=client, json=body, cache_payload=body,
            headers={"X-Goog-Api-Key": settings.google_places_api_key or "",
                     "X-Goog-FieldMask": ",".join(FIELDS), "Content-Type": "application/json"},
        )
        records = [self._parse(p) for p in data.get("places", [])]
        return DiscoveryPage(records=[r for r in records if r], next_token=data.get("nextPageToken"),
                             requests=0 if cached else 1, cost_usd=0.0 if cached else self.cost_per_request,
                             cached=cached)

    @staticmethod
    def _parse(p: dict) -> PlaceRecord | None:
        name = (p.get("displayName") or {}).get("text")
        if not name or not p.get("id"):
            return None
        comps = {}
        for c in p.get("addressComponents", []):
            for t in c.get("types", []):
                comps.setdefault(t, c)
        def comp(*types: str, short: bool = False) -> str | None:
            for t in types:
                if t in comps:
                    return comps[t].get("shortText" if short else "longText")
            return None
        loc = p.get("location") or {}
        return PlaceRecord(
            source="google_places",
            external_id=p["id"],
            name=name,
            category=(p.get("primaryTypeDisplayName") or {}).get("text") or p.get("primaryType"),
            categories=p.get("types", [])[:10],
            address=p.get("formattedAddress"),
            neighborhood=comp("sublocality_level_1", "sublocality", "neighborhood"),
            city=comp("locality", "administrative_area_level_2"),
            state=comp("administrative_area_level_1", short=True),
            country=comp("country"),
            postal_code=comp("postal_code"),
            lat=loc.get("latitude"),
            lng=loc.get("longitude"),
            phone=p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber"),
            website=p.get("websiteUri"),
            maps_url=p.get("googleMapsUri"),
            source_url=p.get("googleMapsUri"),
            rating=p.get("rating"),
            reviews_count=p.get("userRatingCount"),
            business_status=(p.get("businessStatus") or "").lower() or None,
            raw={"id": p["id"], "types": p.get("types", [])[:10], "businessStatus": p.get("businessStatus")},
        )
