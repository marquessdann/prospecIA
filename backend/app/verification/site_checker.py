"""Verifica se um site responde, respeitando robots.txt e com proteção contra SSRF.

Não tenta contornar CAPTCHAs, autenticação ou bloqueios: respostas 401/403/429 são
registradas como "acesso restrito" e não como site inexistente.
"""

from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import socket
from dataclasses import asdict, dataclass, field
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.config import settings
from app.verification.normalize import normalize_url

PARKED_PATTERNS = [
    r"this domain (is|may be) for sale", r"dom[ií]nio (est[aá] )?(à|a) venda", r"buy this domain",
    r"domain parking", r"parked (free|domain)", r"sedoparking", r"hugedomains", r"dan\.com",
    r"registro\.br.*(dom[ií]nio|aguardando)", r"site em constru[cç][aã]o", r"under construction",
    r"coming soon", r"em breve", r"default web site page", r"welcome to nginx", r"apache2 .*default page",
    r"it works!", r"index of /", r"conta (de hospedagem )?suspensa", r"account suspended",
    r"this site can.t be reached", r"godaddy.*parked",
]
_PARKED_RE = re.compile("|".join(PARKED_PATTERNS), re.I)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_META_DESC_RE = re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', re.I | re.S)
_SCRIPT_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TEL_HREF_RE = re.compile(r'href=["\']tel:([^"\']+)["\']', re.I)


@dataclass
class SiteCheck:
    url: str
    final_url: str | None = None
    reachable: bool = False
    http_status: int | None = None
    error: str | None = None  # dns|timeout|connection|tls|http_error|blocked|ssrf|invalid
    restricted: bool = False  # 401/403/429: existe, mas bloqueia verificações automatizadas
    parked: bool = False
    robots_disallowed: bool = False
    content_analyzed: bool = False
    title: str | None = None
    description: str | None = None
    text_excerpt: str | None = None
    phones_found: list[str] = field(default_factory=list)
    emails_found: list[str] = field(default_factory=list)
    elapsed_ms: int | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("text_excerpt", None)
        return d


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (
        addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
        or addr.is_reserved or addr.is_unspecified
    )


async def resolve_host(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({i[4][0] for i in infos})


async def host_resolves(host: str) -> bool:
    try:
        return bool(await resolve_host(host))
    except (socket.gaierror, UnicodeError, OSError):
        return False


async def _guard_ssrf(url: str) -> str | None:
    """Retorna código de erro se a URL apontar para rede interna."""
    host = urlsplit(url).hostname
    if not host:
        return "invalid"
    if settings.allow_private_network_checks:
        return None
    try:
        ips = await resolve_host(host)
    except (socket.gaierror, UnicodeError, OSError):
        return "dns"
    if not ips:
        return "dns"
    if not all(_is_public_ip(ip) for ip in ips):
        return "ssrf"
    return None


def extract_page_info(body: str) -> dict:
    title_m = _TITLE_RE.search(body)
    desc_m = _META_DESC_RE.search(body)
    tel_hrefs = _TEL_HREF_RE.findall(body)
    text = _TAG_RE.sub(" ", _SCRIPT_RE.sub(" ", body))
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    emails = sorted({e.lower() for e in _EMAIL_RE.findall(body) if not e.lower().endswith((".png", ".jpg", ".webp", ".gif", ".svg"))})
    phones = sorted({re.sub(r"\D", "", t) for t in tel_hrefs})
    phones += sorted({re.sub(r"\D", "", m) for m in re.findall(r"\(?\d{2}\)?[\s.-]?\d{4,5}[\s.-]?\d{4}", text)})
    return {
        "title": html.unescape(title_m.group(1).strip())[:300] if title_m else None,
        "description": html.unescape(desc_m.group(1).strip())[:500] if desc_m else None,
        "text": text[:20000],
        "phones": sorted(set(phones))[:30],
        "emails": emails[:10],
        "parked": bool(_PARKED_RE.search(text[:5000])) or len(text) < 40,
    }


class SiteChecker:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client
        self._robots_cache: dict[str, RobotFileParser | None] = {}

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=settings.site_check_timeout_seconds,
                follow_redirects=False,
                headers={"User-Agent": settings.site_check_user_agent, "Accept": "text/html,*/*;q=0.5"},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def _robots_allows(self, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots_cache:
            rp: RobotFileParser | None = RobotFileParser()
            try:
                r = await self._http().get(base + "/robots.txt", follow_redirects=True)
                if r.status_code >= 400:
                    rp = None  # sem robots.txt => permitido
                else:
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                rp = None
            self._robots_cache[base] = rp
        rp = self._robots_cache[base]
        return True if rp is None else rp.can_fetch(settings.site_check_user_agent, url)

    async def _get_following(self, url: str, max_redirects: int = 5) -> tuple[httpx.Response, str]:
        current = url
        for _ in range(max_redirects + 1):
            if err := await _guard_ssrf(current):
                raise _CheckError(err)
            req = self._http().build_request("GET", current)
            resp = await self._http().send(req, stream=True)
            if resp.is_redirect and resp.headers.get("location"):
                await resp.aclose()
                current = urljoin(current, resp.headers["location"])
                continue
            return resp, current
        raise _CheckError("http_error", "redirecionamentos em excesso")

    async def check(self, url: str, analyze_content: bool = True) -> SiteCheck:
        norm = normalize_url(url)
        result = SiteCheck(url=url)
        if not norm:
            result.error = "invalid"
            return result
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        attempts = [norm]
        if norm.startswith("http://"):
            attempts.insert(0, "https://" + norm[len("http://"):])
        last_error: str | None = None
        for candidate in attempts:
            try:
                if analyze_content and not await self._robots_allows(candidate):
                    result.robots_disallowed = True
                    analyze_content = False
                resp, final = await self._get_following(candidate)
                try:
                    result.http_status = resp.status_code
                    result.final_url = final
                    if resp.status_code in (401, 403, 429):
                        result.restricted = True
                        result.reachable = True
                    elif resp.status_code < 400:
                        result.reachable = True
                        if analyze_content:
                            body = await _read_limited(resp, settings.site_check_max_bytes)
                            info = extract_page_info(body)
                            result.content_analyzed = True
                            result.title = info["title"]
                            result.description = info["description"]
                            result.text_excerpt = info["text"]
                            result.phones_found = info["phones"]
                            result.emails_found = info["emails"]
                            result.parked = info["parked"]
                    else:
                        result.error = "http_error"
                finally:
                    await resp.aclose()
                if result.reachable:
                    result.error = None
                    break
                last_error = result.error
            except _CheckError as e:
                last_error = e.code
            except httpx.ConnectTimeout:
                last_error = "timeout"
            except httpx.ReadTimeout:
                last_error = "timeout"
            except httpx.ConnectError as e:
                last_error = "tls" if "SSL" in str(e) or "certificate" in str(e).lower() else "connection"
            except httpx.HTTPError:
                last_error = "connection"
            if last_error in ("dns", "ssrf", "invalid"):
                break
        if not result.reachable:
            result.error = result.error or last_error
        result.elapsed_ms = int((loop.time() - t0) * 1000)
        return result


class _CheckError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


async def _read_limited(resp: httpx.Response, limit: int) -> str:
    chunks: list[bytes] = []
    size = 0
    async for chunk in resp.aiter_bytes():
        chunks.append(chunk)
        size += len(chunk)
        if size >= limit:
            break
    raw = b"".join(chunks)[:limit]
    return raw.decode(resp.encoding or "utf-8", errors="replace")
