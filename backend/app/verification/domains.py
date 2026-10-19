"""Classifica URLs em site próprio, rede social, marketplace, diretório ou construtor genérico."""

from __future__ import annotations

from dataclasses import dataclass

from app.verification.normalize import hostname, registrable_domain

SOCIAL = {
    "facebook.com", "fb.com", "instagram.com", "twitter.com", "x.com", "tiktok.com", "linkedin.com",
    "youtube.com", "youtu.be", "pinterest.com", "threads.net", "wa.me", "whatsapp.com", "t.me",
    "linktr.ee", "beacons.ai", "kwai.com", "bio.link", "taplink.cc", "linkbio.co",
}
MARKETPLACE = {
    "ifood.com.br", "rappi.com.br", "ubereats.com", "mercadolivre.com.br", "mercadolibre.com",
    "shopee.com.br", "amazon.com.br", "amazon.com", "magazineluiza.com.br", "olx.com.br",
    "americanas.com.br", "aiqfome.com", "booking.com", "airbnb.com", "doctoralia.com.br",
    "boaconsulta.com", "zapimoveis.com.br", "vivareal.com.br", "imovelweb.com.br", "getninjas.com.br",
    "elo7.com.br", "enjoei.com.br", "99freelas.com.br", "agendor.com.br", "trinks.com",
    "booksy.com", "simplesagenda.com.br", "goomer.app", "anota.ai", "cardapioweb.com",
    "deliverydireto.com.br", "menudino.com", "hotmart.com", "sympla.com.br",
}
DIRECTORY = {
    "google.com", "goo.gl", "g.page", "maps.app.goo.gl", "bing.com", "yelp.com", "tripadvisor.com",
    "tripadvisor.com.br", "foursquare.com", "apontador.com.br", "guiamais.com.br", "telelistas.net",
    "solutudo.com.br", "cylex.com.br", "infobel.com", "empresaqui.com.br", "cnpj.biz", "cnpja.com",
    "econodata.com.br", "casadosdados.com.br", "consultasocio.com", "reclameaqui.com.br",
    "wikipedia.org", "openstreetmap.org", "waze.com", "yellowpages.com", "kekanto.com.br",
    "hagah.com.br", "guiafacil.com", "achei.com.br", "listamais.com.br", "encontra.com.br",
    "jusbrasil.com.br", "escavador.com", "restaurantguru.com", "cybo.com", "brownbook.net",
    "hotfrog.com.br", "linkedin.com.br", "glassdoor.com.br", "indeed.com", "catho.com.br",
    "empresas.serasaexperian.com.br", "speedio.com.br", "bizzy.com.br", "lojasabertas.com.br",
    "duckduckgo.com", "brave.com", "yahoo.com", "apple.com",
}
# Plataformas onde um subdomínio pode ser o site próprio da empresa (sinal mais fraco).
HOSTED_BUILDERS = {
    "wixsite.com", "wix.com", "wordpress.com", "blogspot.com", "webnode.com.br", "webnode.page",
    "negocio.site", "business.site", "squarespace.com", "weebly.com", "carrd.co", "site123.me",
    "godaddysites.com", "github.io", "netlify.app", "vercel.app", "nuvemshop.com.br",
    "lojaintegrada.com.br", "mercadoshops.com.br", "tray.com.br", "yampi.com.br", "shopify.com",
    "myshopify.com", "ueniweb.com", "jimdosite.com", "strikingly.com", "my.canva.site",
}

KIND_OWN = "own"
KIND_SOCIAL = "social"
KIND_MARKETPLACE = "marketplace"
KIND_DIRECTORY = "directory"
KIND_BUILDER = "builder"  # subdomínio em construtor de sites (pode ser site próprio)
KIND_INVALID = "invalid"


@dataclass(frozen=True)
class UrlKind:
    kind: str
    domain: str | None
    host: str | None
    platform: str | None = None


def _matches(host: str, domains: set[str]) -> str | None:
    for d in domains:
        if host == d or host.endswith("." + d):
            return d
    return None


def classify_url(url: str | None) -> UrlKind:
    host = hostname(url)
    if not host:
        return UrlKind(KIND_INVALID, None, None)
    domain = registrable_domain(host)
    if p := _matches(host, SOCIAL):
        return UrlKind(KIND_SOCIAL, domain, host, p)
    if p := _matches(host, MARKETPLACE):
        return UrlKind(KIND_MARKETPLACE, domain, host, p)
    if p := _matches(host, HOSTED_BUILDERS):
        # "wix.com" puro é o construtor; "minhaempresa.wixsite.com" pode ser site próprio.
        if host in (p, "www." + p):
            return UrlKind(KIND_DIRECTORY, domain, host, p)
        return UrlKind(KIND_BUILDER, host, host, p)
    if p := _matches(host, DIRECTORY):
        return UrlKind(KIND_DIRECTORY, domain, host, p)
    if host.startswith("www.google.") or ".google." in host:
        return UrlKind(KIND_DIRECTORY, domain, host, "google")
    return UrlKind(KIND_OWN, domain, host)


def is_site_like(kind: UrlKind) -> bool:
    return kind.kind in (KIND_OWN, KIND_BUILDER)
