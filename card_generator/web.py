"""Веб-интерфейс: FastAPI + одна страница без сборки. Запуск: python -m card_generator --serve"""
import json
from functools import lru_cache
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .config import load_env
from .errors import CardError, InputError
from .generator import generate_card
from .ingest import extract_product, fetch_html, html_to_text
from .llm import LLMClient
from .product import find_missing, parse_product
from .render import to_dict, to_markdown

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Генератор карточек товаров")


@lru_cache(maxsize=1)
def get_llm() -> LLMClient:
    load_env()
    return LLMClient()


def _fail(exc: CardError) -> HTTPException:
    return HTTPException(status_code=400 if isinstance(exc, InputError) else 502, detail=str(exc))


class GenerateIn(BaseModel):
    product: dict


class ExtractIn(BaseModel):
    url: str


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/examples")
def examples() -> list[dict]:
    out = []
    for f in sorted((ROOT / "examples").glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


@app.post("/api/generate")
def generate(body: dict = Body(...)) -> dict:
    raw = body["product"] if isinstance(body.get("product"), dict) else body
    try:
        product = parse_product(raw)
        result = generate_card(product, get_llm())
    except CardError as exc:
        raise _fail(exc) from exc
    return {**to_dict(result), "markdown": to_markdown(result)}


@app.post("/api/extract")
def extract(body: ExtractIn) -> dict:
    try:
        title, text = html_to_text(fetch_html(body.url.strip()))
        if len(text) < 100:
            raise InputError("На странице почти нет текста (возможно, она строится JavaScript-ом)")
        product, dropped = extract_product(text, title, get_llm())
    except CardError as exc:
        raise _fail(exc) from exc
    return {
        "product": {"name": product.name, "manufacturer": product.manufacturer or "",
                    "specs": product.specs, "description": product.description or ""},
        "missing": find_missing(product),
        "dropped": dropped,
    }
