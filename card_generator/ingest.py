"""Загрузка товара по ссылке: безопасный fetch → текст страницы → извлечение LLM →
ДОСЛОВНАЯ верификация: любое значение, которого нет в тексте страницы, отбрасывается."""
from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from .errors import InputError
from .models import EXTRACT_SCHEMA
from .product import Product
from .prompts import EXTRACT_PROMPT

MAX_BYTES = 2_000_000
LLM_CHARS = 14_000
_SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"}
_BLOCK = {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "table", "section", "ul", "dt", "dd"}


def check_public_url(url: str) -> None:
    """Защита от SSRF: только http(s) и только публичные адреса."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise InputError("Ссылка должна начинаться с http:// или https://")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except socket.gaierror as exc:
        raise InputError(f"Не удалось определить адрес сайта {parsed.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise InputError("Ссылки на локальные и внутренние адреса запрещены")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str]:
    p = _TextExtractor()
    p.feed(html)
    text = "".join(p.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return p.title.strip(), text


def fetch_html(url: str) -> str:
    try:
        with httpx.Client(timeout=15, follow_redirects=False,
                          headers={"User-Agent": "Mozilla/5.0 (card-generator prototype)"}) as client:
            for _ in range(4):  # редиректы обрабатываем вручную, проверяя каждый адрес
                check_public_url(url)
                resp = client.get(url)
                if resp.is_redirect and resp.headers.get("location"):
                    url = urljoin(url, resp.headers["location"])
                    continue
                resp.raise_for_status()
                if len(resp.content) > MAX_BYTES:
                    raise InputError("Страница слишком большая (> 2 МБ)")
                return resp.text
    except httpx.HTTPStatusError as exc:
        raise InputError(f"Сайт ответил ошибкой {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise InputError(f"Не удалось загрузить страницу: {exc.__class__.__name__}") from exc
    raise InputError("Слишком много перенаправлений")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip().lower()


def extract_product(text: str, title: str, llm) -> tuple[Product, list[str]]:
    """Возвращает товар и список отброшенных (неподтверждённых страницей) полей."""
    data = llm.complete_json(EXTRACT_PROMPT, "Текст страницы:\n" + text[:LLM_CHARS], EXTRACT_SCHEMA, "product_extract")
    page = _norm(text)
    dropped: list[str] = []

    def verified(value) -> str | None:
        v = str(value or "").strip()
        return v if v and _norm(v) in page else None

    name = verified(data.get("name")) or (title or None)
    if not name:
        raise InputError("На странице не удалось найти название товара")
    manufacturer = verified(data.get("manufacturer"))
    specs: dict[str, str] = {}
    for item in data.get("specs") or []:
        if not isinstance(item, dict):
            continue
        k, v = verified(item.get("name")), verified(item.get("value"))
        if k and v:
            specs[k] = v
        else:
            dropped.append(f"{item.get('name')}: {item.get('value')}")
    description = verified(data.get("description"))
    if data.get("description") and not description:
        # длинное описание часто немного искажается — оставляем только дословные предложения
        sentences = re.split(r"(?<=[.!?])\s+", str(data["description"]))
        kept = [s for s in sentences if _norm(s) in page]
        description = " ".join(kept) or None
    return Product(name, manufacturer, specs, description), dropped
