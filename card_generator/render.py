import json
import re

from .generator import Result


def to_dict(r: Result) -> dict:
    return {
        "name": r.product.name,
        "seo_title": r.card.seo_title,
        "seo_description": r.card.seo_description,
        "key_specs": [{"name": k, "value": v} for k, v in r.specs],
        "search_queries": r.card.search_queries,
        "commercial_block": r.card.commercial_block.model_dump(),
        "missing_data": r.missing,
        "warnings": r.warnings,
    }


def to_json(r: Result) -> str:
    return json.dumps(to_dict(r), ensure_ascii=False, indent=2)


def to_markdown(r: Result) -> str:
    c = r.card
    out = [f"# {r.product.name}", ""]
    if r.warnings:
        out += ["> ⚠️ **Требует проверки человеком:** " + "; ".join(r.warnings), ""]
    out += [f"**SEO-заголовок** ({len(c.seo_title)} симв.): {c.seo_title}", "",
            f"## SEO-описание ({len(c.seo_description)} симв.)", "", c.seo_description, "",
            "## Ключевые характеристики", "", "| Характеристика | Значение |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in r.specs]
    out += ["", "## Поисковые запросы", ""] + [f"- {q}" for q in c.search_queries]
    out += ["", "## Для менеджера", "", "**Кому подходит:**"]
    out += [f"- {x}" for x in c.commercial_block.suitable_for]
    out += ["", "**Какие задачи решает:**"] + [f"- {x}" for x in c.commercial_block.tasks_solved]
    out += ["", "## Что уточнить (данных нет)", ""]
    out += [f"- {m}" for m in r.missing] or ["- всё необходимое есть"]
    return "\n".join(out) + "\n"


def slug(name: str) -> str:
    s = re.sub(r"[^\w]+", "-", name.lower(), flags=re.UNICODE).strip("-")
    return s[:60] or "product"
