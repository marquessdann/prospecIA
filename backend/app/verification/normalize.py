"""Normalização de nomes, telefones, URLs e domínios."""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

LEGAL_SUFFIXES = {
    "ltda", "me", "epp", "eireli", "sa", "s/a", "s.a", "ss", "mei", "cia", "inc", "llc", "ltd",
    "limitada", "sociedade", "simples",
}
STOPWORDS = {
    "de", "da", "do", "das", "dos", "e", "a", "o", "the", "and", "em", "na", "no", "&",
}
# Palavras genéricas de segmento: pouco discriminantes para casar nome x domínio.
GENERIC_WORDS = {
    "clinica", "clinicas", "consultorio", "odontologia", "odontologica", "odonto", "restaurante",
    "bar", "lanchonete", "pizzaria", "academia", "salao", "beleza", "barbearia", "oficina",
    "mecanica", "auto", "imobiliaria", "imoveis", "advocacia", "advogados", "advogado",
    "contabilidade", "contabil", "escritorio", "pet", "shop", "petshop", "loja", "modas", "moda",
    "construtora", "construcao", "servicos", "comercio", "center", "centro", "studio", "estudio",
    "espaco", "casa", "grupo", "dr", "dra", "medica", "medico", "saude", "psicologia", "psicologo",
    "psicologa", "store", "brasil", "cafe", "padaria", "mercado", "farmacia",
}


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize_name(name: str) -> str:
    text = strip_accents(name or "").lower()
    text = re.sub(r"[^a-z0-9& ]+", " ", text)
    tokens = [t for t in text.split() if t not in LEGAL_SUFFIXES]
    return " ".join(tokens).strip()


def name_tokens(name: str, drop_generic: bool = False) -> list[str]:
    tokens = [t for t in normalize_name(name).split() if t not in STOPWORDS and len(t) > 1]
    if drop_generic:
        specific = [t for t in tokens if t not in GENERIC_WORDS]
        return specific or tokens
    return tokens


def name_is_generic(name: str) -> bool:
    """Nomes curtos ou compostos só de termos genéricos geram muitos falsos positivos na busca."""
    tokens = name_tokens(name)
    specific = [t for t in tokens if t not in GENERIC_WORDS]
    return len(specific) == 0 or (len(specific) == 1 and len(specific[0]) <= 3)


def normalize_phone(phone: str | None, default_country: str = "55") -> str | None:
    """Retorna apenas dígitos em formato E.164 sem '+', ex.: 5541999998888."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    if phone.strip().startswith("+"):
        return digits
    digits = digits.lstrip("0")
    if default_country == "55" and len(digits) in (10, 11):
        return "55" + digits
    return digits


def phone_variants(phone_normalized: str | None) -> set[str]:
    """Variações para procurar o telefone no texto de um site (com/sem DDI, com/sem 9º dígito)."""
    if not phone_normalized:
        return set()
    p = phone_normalized
    out = {p}
    if p.startswith("55") and len(p) in (12, 13):
        local = p[2:]
        out.add(local)
        out.add(local[2:])  # sem DDD
        if len(local) == 11 and local[2] == "9":
            out.add(local[:2] + local[3:])
    return {v for v in out if len(v) >= 8}


def digits_in_text(text: str) -> str:
    return re.sub(r"\D", "", text)


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if not re.match(r"^https?://", url, re.I):
        url = "http://" + url
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or "." not in host:
        return None
    netloc = host
    if parts.port and parts.port not in (80, 443):
        netloc = f"{host}:{parts.port}"
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))


def hostname(url: str | None) -> str | None:
    n = normalize_url(url)
    if not n:
        return None
    return urlsplit(n).hostname


# Sufixos públicos de dois níveis comuns (lista enxuta; evita dependência externa).
_TWO_LEVEL_SUFFIXES = {
    "com.br", "net.br", "org.br", "adv.br", "med.br", "odo.br", "eng.br", "arq.br", "ind.br",
    "eti.br", "art.br", "psi.br", "vet.br", "imb.br", "tur.br", "blog.br", "app.br", "dev.br",
    "co.uk", "org.uk", "com.ar", "com.mx", "com.pt", "com.co", "com.pe", "com.uy", "com.py",
    "com.au", "co.nz", "co.jp", "com.es",
}


def registrable_domain(url_or_host: str | None) -> str | None:
    host = url_or_host or ""
    if "/" in host or ":" in host:
        host = hostname(host) or ""
    host = host.lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    labels = host.split(".")
    if len(labels) < 2:
        return None
    if ".".join(labels[-2:]) in _TWO_LEVEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def domain_label(domain: str | None) -> str:
    """Parte "nome" do domínio: clinicasorriso.com.br -> clinicasorriso."""
    if not domain:
        return ""
    d = registrable_domain(domain) or domain
    for suffix in sorted(_TWO_LEVEL_SUFFIXES, key=len, reverse=True):
        if d.endswith("." + suffix):
            return d[: -(len(suffix) + 1)]
    return d.rsplit(".", 1)[0]


def compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", strip_accents(text or "").lower())
