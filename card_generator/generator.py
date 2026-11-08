from dataclasses import dataclass, field

from .checks import check_card
from .errors import LLMError
from .models import LLMCard
from .product import Product, find_missing, key_specs
from .prompts import build_user_prompt

MAX_ATTEMPTS = 3


@dataclass
class Result:
    product: Product
    card: LLMCard
    specs: list[tuple[str, str]]
    missing: list[str]          # пробелы, найденные кодом + заявленные моделью
    warnings: list[str] = field(default_factory=list)  # непройденные проверки


def generate_card(product: Product, llm) -> Result:
    code_missing = find_missing(product)
    feedback: list[str] | None = None
    card, problems = None, []
    for _ in range(MAX_ATTEMPTS):
        prompt = build_user_prompt(product.to_prompt_json(), code_missing, feedback)
        card = llm.generate(prompt)
        problems = check_card(card, product.source_text())
        if not problems:
            break
        feedback = problems
    if card is None:
        raise LLMError("Не удалось получить ответ модели.")

    missing = list(code_missing)
    for item in card.missing_data:
        if item.lower() not in (m.lower() for m in missing):
            missing.append(item)
    warnings = [f"Проверка не пройдена после {MAX_ATTEMPTS} попыток: {p}" for p in problems]
    return Result(product, card, key_specs(product), missing, warnings)
