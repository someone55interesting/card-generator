import os
from pathlib import Path


def load_env(path: str = ".env") -> None:
    """Минимальный загрузчик .env (переменные окружения имеют приоритет)."""
    env = Path(path)
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
