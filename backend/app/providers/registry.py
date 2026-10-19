"""Registro de provedores. Para adicionar uma nova fonte, implemente `PlaceProvider` ou
`WebSearchProvider` e registre-a aqui."""

from __future__ import annotations

from app.providers.base import PlaceProvider, ProviderInfo, WebSearchProvider
from app.providers.google_places import GooglePlacesProvider
from app.providers.osm_overpass import OsmOverpassProvider
from app.providers.web_search import BraveSearchProvider, GoogleCseProvider

_PLACE: dict[str, PlaceProvider] = {}
_WEB: dict[str, WebSearchProvider] = {}


def register_place(p: PlaceProvider) -> None:
    _PLACE[p.name] = p


def register_web(p: WebSearchProvider) -> None:
    _WEB[p.name] = p


register_place(GooglePlacesProvider())
register_place(OsmOverpassProvider())
register_web(BraveSearchProvider())
register_web(GoogleCseProvider())


def place_provider(name: str) -> PlaceProvider | None:
    return _PLACE.get(name)


def place_providers() -> list[PlaceProvider]:
    return list(_PLACE.values())


def web_providers() -> list[WebSearchProvider]:
    return list(_WEB.values())


def web_provider(preferred: str | None = None) -> WebSearchProvider | None:
    """Retorna o provedor de busca web solicitado ou o primeiro disponível."""
    if preferred and preferred in _WEB and _WEB[preferred].available():
        return _WEB[preferred]
    for p in _WEB.values():
        if p.available():
            return p
    return None


def all_infos() -> list[ProviderInfo]:
    return [p.info() for p in _PLACE.values()] + [p.info() for p in _WEB.values()]
