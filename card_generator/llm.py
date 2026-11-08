"""Клиент Groq (OpenAI-совместимый Chat Completions) с надёжным JSON-выводом.

Режимы по убыванию строгости: json_schema (strict) → json_object → обычный текст
с извлечением JSON. Если режим не сработал (модель его не поддерживает, вернула
пустой ответ или невалидный JSON), автоматически пробуем следующий.
Ответ в любом случае валидируется pydantic, а вызывающий код умеет повторять попытку.
"""
import json
import os

import groq
from pydantic import ValidationError

from .errors import LLMError
from .models import CARD_SCHEMA, LLMCard
from .prompts import SYSTEM_PROMPT

DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_TOKENS = 8000  # reasoning-моделям нужен запас: размышления тоже считаются


def _extract_json(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


class LLMClient:
    def __init__(self) -> None:
        if not os.environ.get("GROQ_API_KEY"):
            raise LLMError(
                "Не задан GROQ_API_KEY. Скопируйте .env.example в .env и впишите ключ "
                "(или экспортируйте переменную окружения)."
            )
        self.model = os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        self.client = groq.Groq(max_retries=3, timeout=90.0)  # SDK сам повторяет 429/5xx
        self._modes = ["json_schema", "json_object", "plain"]

    def list_models(self) -> list[str]:
        try:
            return sorted(m.id for m in self.client.models.list().data)
        except groq.GroqError as exc:
            raise LLMError(f"Не удалось получить список моделей: {exc}") from exc

    def _call(self, messages: list[dict], mode: str, schema: dict, name: str) -> str:
        kwargs: dict = {}
        if mode == "json_schema":
            kwargs["response_format"] = {"type": "json_schema",
                                         "json_schema": {"name": name, "strict": True, "schema": schema}}
        elif mode == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        if self.model.startswith("openai/gpt-oss"):
            kwargs["extra_body"] = {"reasoning_effort": "low"}  # меньше «размышлений» — быстрее и надёжнее
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=0.2,
            max_completion_tokens=MAX_TOKENS, **kwargs,
        )
        return resp.choices[0].message.content or ""

    def complete_json(self, system: str, user: str, schema: dict, name: str) -> dict:
        hint = "\n\nВерни ТОЛЬКО JSON-объект (без пояснений и markdown) по схеме:\n" + json.dumps(schema, ensure_ascii=False)
        messages = [{"role": "system", "content": system + hint}, {"role": "user", "content": user}]
        last_problem = "пустой ответ"
        try:
            for mode in list(self._modes):
                try:
                    content = self._call(messages, mode, schema, name)
                except groq.BadRequestError as exc:
                    msg = str(exc).lower()
                    if "does not support" in msg or "response format" in msg:
                        self._modes.remove(mode)  # режим не поддерживается моделью — больше не пробуем
                    last_problem = str(exc)[:200]
                    continue
                data = _extract_json(content)
                if data is not None:
                    return data
                last_problem = "модель вернула пустой или невалидный JSON"
        except groq.AuthenticationError as exc:
            raise LLMError("Groq отклонил ключ (401). Проверьте GROQ_API_KEY.") from exc
        except groq.RateLimitError as exc:
            raise LLMError("Превышен лимит запросов Groq (429). Повторите через минуту.") from exc
        except groq.APIConnectionError as exc:
            raise LLMError("Не удалось подключиться к Groq. Проверьте интернет/прокси.") from exc
        except groq.NotFoundError as exc:
            raise LLMError(f"Модель «{self.model}» недоступна. Выберите другую: --list-models, GROQ_MODEL.") from exc
        except groq.APIStatusError as exc:
            raise LLMError(f"Ошибка Groq API ({exc.status_code}): {exc.message}") from exc
        raise LLMError(f"Groq не смог сформировать JSON ({last_problem}). "
                       "Попробуйте другую модель: GROQ_MODEL в .env (список: --list-models).")

    def generate(self, user_prompt: str) -> LLMCard:
        data = self.complete_json(SYSTEM_PROMPT, user_prompt, CARD_SCHEMA, "product_card")
        try:
            return LLMCard.model_validate(data)
        except ValidationError as exc:
            raise LLMError(f"Ответ модели не соответствует схеме: {exc.errors()[0]['msg']}") from exc
