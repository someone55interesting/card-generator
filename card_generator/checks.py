"""Программные проверки результата модели (длины, числа, «рискованные» термины)."""
import re

from .models import LLMCard

NUM = re.compile(r"\d+(?:[.,]\d+)?")
TITLE_MAX = 70
DESC_MIN, DESC_MAX = 800, 1200

# Основы слов, которые нельзя употреблять, если их нет во входных данных:
# за ними обычно стоят выдуманные юридически значимые утверждения.
RISKY_STEMS = ("гост", "сертифи", "гаранти", "взрыв", "поверк", "межповероч", "декларац", "аттестац",
               "проверенн", "быстр", "надёжн", "надежн", "интеграц", "совместим", "упрощ", "удобн", "эффективн")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in NUM.findall(text)}


def check_card(card: LLMCard, source_text: str) -> list[str]:
    """Возвращает список проблем (пустой, если всё хорошо)."""
    problems = []
    if not card.seo_title.strip():
        problems.append("seo_title пуст")
    elif len(card.seo_title) > TITLE_MAX:
        problems.append(f"seo_title длиной {len(card.seo_title)} символов, нужно не более {TITLE_MAX}")
    n = len(card.seo_description)
    if not DESC_MIN <= n <= DESC_MAX:
        problems.append(f"seo_description длиной {n} символов, нужно {DESC_MIN}–{DESC_MAX}")

    generated = " ".join(
        [card.seo_title, card.seo_description, *card.search_queries,
         *card.commercial_block.suitable_for, *card.commercial_block.tasks_solved]
    )
    unknown = sorted(_numbers(generated) - _numbers(source_text))
    if unknown:
        problems.append("в тексте есть числа, которых нет во входных данных: " + ", ".join(unknown)
                        + " — удали их или замени формулировкой без чисел")
    gen_l, src_l = generated.lower(), source_text.lower()
    bad = sorted({w for st in RISKY_STEMS if st in gen_l and st not in src_l
                  for w in re.findall(rf"\w*{st}\w*", gen_l)})
    if bad:
        problems.append("в тексте есть утверждения без опоры на данные. Полностью перепиши предложения, "
                        "где встречаются слова: " + ", ".join(bad))
    return problems
