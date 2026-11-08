"""Загрузка, нормализация и проверка полноты входных данных."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .errors import InputError

# Какие группы характеристик ожидаем увидеть у прибора и по каким
# подстрокам (в нижнем регистре) ищем их среди ключей specs.
EXPECTED_SPECS: dict[str, tuple[str, ...]] = {
    "Диапазон измерений": ("диапазон",),
    "Класс точности": ("точност", "допуск"),
    "Питание": ("питани",),
    "Корпус / присоединение": ("корпус", "диаметр", "присоедин", "защит", "габарит"),
    "Интерфейсы / выходной сигнал": ("интерфейс", "выход", "сигнал"),
}
NO_DATA = "данных нет"


@dataclass
class Product:
    name: str
    manufacturer: str | None = None
    specs: dict[str, str] = field(default_factory=dict)
    description: str | None = None

    def source_text(self) -> str:
        """Весь текст, из которого разрешено брать факты."""
        parts = [self.name, self.manufacturer or "", self.description or ""]
        parts += [f"{k} {v}" for k, v in self.specs.items()]
        return "\n".join(parts)

    def to_prompt_json(self) -> str:
        return json.dumps(
            {
                "name": self.name,
                "manufacturer": self.manufacturer or NO_DATA,
                "specs": self.specs or {},
                "description": self.description or NO_DATA,
            },
            ensure_ascii=False,
            indent=2,
        )


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_product(raw: object, label: str = "товар") -> Product:
    if not isinstance(raw, dict):
        raise InputError(f"{label}: ожидается JSON-объект, получено {type(raw).__name__}")
    name = _clean(raw.get("name"))
    if not name:
        raise InputError(f"{label}: поле «name» обязательно и не должно быть пустым")
    specs_raw = raw.get("specs") or {}
    if not isinstance(specs_raw, dict):
        raise InputError(f"{label}: поле «specs» должно быть объектом «название: значение»")
    specs = {}
    for key, value in specs_raw.items():
        k, v = _clean(key), _clean(value)
        if k and v:  # пустые характеристики отбрасываем
            specs[k] = v
    return Product(
        name=name,
        manufacturer=_clean(raw.get("manufacturer")),
        specs=specs,
        description=_clean(raw.get("description")),
    )


def load_products(text: str, source: str = "вход") -> list[Product]:
    """Принимает JSON-объект (один товар) или массив объектов."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"{source}: некорректный JSON (строка {exc.lineno}, символ {exc.colno}): {exc.msg}") from exc
    items = data if isinstance(data, list) else [data]
    if not items:
        raise InputError(f"{source}: пустой список товаров")
    return [parse_product(item, f"{source}, товар №{i}") for i, item in enumerate(items, 1)]


def load_file(path: str) -> list[Product]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"Не удалось прочитать файл {path}: {exc.strerror}") from exc
    return load_products(text, path)


def find_missing(product: Product) -> list[str]:
    """Что отсутствует во входных данных (считается кодом, а не моделью)."""
    missing = []
    if not product.manufacturer:
        missing.append("производитель")
    if not product.description:
        missing.append("текстовое описание / фрагмент паспорта")
    if not product.specs:
        missing.append("характеристики (specs)")
    keys = [k.lower() for k in product.specs]
    for group, needles in EXPECTED_SPECS.items():
        if not any(n in k for k in keys for n in needles):
            missing.append(group)
    return missing


def key_specs(product: Product) -> list[tuple[str, str]]:
    """Список характеристик строится кодом из входных данных: модель
    не может исказить значения. Отсутствующие группы помечаются «данных нет»."""
    rows = list(product.specs.items())
    for group in find_missing(product):
        if group in EXPECTED_SPECS:
            rows.append((group, NO_DATA))
    return rows
