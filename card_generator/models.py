from pydantic import BaseModel, Field


class CommercialBlock(BaseModel):
    suitable_for: list[str] = Field(min_length=1)
    tasks_solved: list[str] = Field(min_length=1)


class LLMCard(BaseModel):
    """То, что генерирует модель. Характеристики сюда намеренно не входят."""
    seo_title: str
    seo_description: str
    search_queries: list[str] = Field(min_length=3, max_length=5)
    commercial_block: CommercialBlock
    missing_data: list[str] = Field(default_factory=list)


_STR_LIST = {"type": "array", "items": {"type": "string"}}

# Схемы совместимы с strict-режимом Groq: все поля required, additionalProperties=false.
CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "seo_title": {"type": "string"},
        "seo_description": {"type": "string"},
        "search_queries": _STR_LIST,
        "commercial_block": {
            "type": "object",
            "properties": {"suitable_for": _STR_LIST, "tasks_solved": _STR_LIST},
            "required": ["suitable_for", "tasks_solved"],
            "additionalProperties": False,
        },
        "missing_data": _STR_LIST,
    },
    "required": ["seo_title", "seo_description", "search_queries", "commercial_block", "missing_data"],
    "additionalProperties": False,
}

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "manufacturer": {"type": "string"},
        "specs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
                "required": ["name", "value"],
                "additionalProperties": False,
            },
        },
        "description": {"type": "string"},
    },
    "required": ["name", "manufacturer", "specs", "description"],
    "additionalProperties": False,
}
