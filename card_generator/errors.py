class CardError(Exception):
    """Базовая ошибка сервиса; сообщение понятно пользователю."""


class InputError(CardError):
    """Некорректный входной JSON."""


class LLMError(CardError):
    """Ошибка обращения к LLM API."""
