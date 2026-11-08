import pytest

from card_generator.checks import check_card
from card_generator.errors import InputError
from card_generator.generator import generate_card
from card_generator.ingest import check_public_url, extract_product, html_to_text
from card_generator.models import CommercialBlock, LLMCard
from card_generator.product import NO_DATA, find_missing, key_specs, load_products

GOOD = '{"name":"М","manufacturer":"Х","specs":{"диапазон измерений":"0–1,6 МПа","класс точности":"1,5"},"description":"д"}'


def card(title="Манометр М", desc="а" * 900, queries=("a", "b", "c")):
    return LLMCard(seo_title=title, seo_description=desc, search_queries=list(queries),
                   commercial_block=CommercialBlock(suitable_for=["x"], tasks_solved=["y"]))


def test_bad_json():
    with pytest.raises(InputError):
        load_products("{oops")


def test_name_required_and_types():
    with pytest.raises(InputError):
        load_products('{"manufacturer":"x"}')
    with pytest.raises(InputError):
        load_products('{"name":"a","specs":[1]}')
    with pytest.raises(InputError):
        load_products("[]")


def test_empty_fields_are_missing():
    p = load_products('{"name":"a","manufacturer":" ","specs":{"класс точности":""},"description":null}')[0]
    m = find_missing(p)
    assert "производитель" in m and "характеристики (specs)" in m
    assert all(v == NO_DATA for _, v in key_specs(p))


def test_key_specs_from_input_only():
    p = load_products(GOOD)[0]
    specs = dict(key_specs(p))
    assert specs["диапазон измерений"] == "0–1,6 МПа"
    assert specs["Питание"] == NO_DATA


def test_checks():
    src = load_products(GOOD)[0].source_text()
    assert check_card(card(), src) == []
    assert any("70" in x for x in check_card(card(title="я" * 71), src))
    assert any("800" in x for x in check_card(card(desc="короткий"), src))
    assert any("25" in x for x in check_card(card(desc="давление до 25 МПа " + "а" * 900), src))
    assert check_card(card(desc="диапазон 1,6 МПа " + "а" * 900), src) == []


def test_risky_terms_need_support():
    src = load_products(GOOD)[0].source_text()
    assert any("гост" in x for x in check_card(card(desc="соответствует ГОСТ " + "а" * 900), src))
    assert any("гаранти" in x for x in check_card(card(desc="гарантия " + "а" * 900), src))


class FakeLLM:
    def __init__(self, cards=(), extracted=None):
        self.cards, self.prompts, self.extracted = list(cards), [], extracted

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.cards.pop(0)

    def complete_json(self, system, user, schema, name):
        return self.extracted


def test_retry_with_feedback():
    llm = FakeLLM([card(desc="коротко"), card()])
    res = generate_card(load_products(GOOD)[0], llm)
    assert not res.warnings and len(llm.prompts) == 2 and "не прошла проверку" in llm.prompts[1]


def test_warning_after_failed_retries():
    res = generate_card(load_products(GOOD)[0], FakeLLM([card(desc="коротко")] * 3))
    assert res.warnings


def test_extraction_drops_unverified_values():
    html = "<html><title>T</title><body><h1>Манометр DM 02</h1><p>Класс точности: 1,5</p><script>x</script></body></html>"
    title, text = html_to_text(html)
    assert "x" not in text.split() and title == "T"
    fake = FakeLLM(extracted={
        "name": "Манометр DM 02", "manufacturer": "Выдуманная Корп",
        "specs": [{"name": "Класс точности", "value": "1,5"}, {"name": "Питание", "value": "24 В"}],
        "description": ""})
    prod, dropped = extract_product(text, title, fake)
    assert prod.specs == {"Класс точности": "1,5"} and prod.manufacturer is None and len(dropped) == 1


@pytest.mark.parametrize("url", ["ftp://x.ru", "http://127.0.0.1/a", "http://localhost:8000", "file:///etc/passwd"])
def test_ssrf_blocked(url):
    with pytest.raises(InputError):
        check_public_url(url)
