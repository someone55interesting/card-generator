import argparse
import sys
from pathlib import Path

from .config import load_env
from .errors import CardError
from .product import Product, find_missing, load_file, load_products


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="card_generator", description="Черновик карточки товара по JSON или ссылке")
    p.add_argument("inputs", nargs="*", help="JSON-файлы с товарами (или «-» для stdin)")
    p.add_argument("--url", action="append", default=[], help="ссылка на страницу товара (можно несколько раз)")
    p.add_argument("-o", "--out", default="output", help="папка для результата (по умолчанию output)")
    p.add_argument("--serve", action="store_true", help="запустить веб-интерфейс на http://127.0.0.1:8000")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--dry-run", action="store_true", help="проверить данные и показать пробелы, без вызова LLM")
    p.add_argument("--list-models", action="store_true", help="показать модели, доступные вашему ключу Groq")
    args = p.parse_args(argv)

    load_env()
    try:
        if args.serve:
            import uvicorn
            uvicorn.run("card_generator.web:app", host="127.0.0.1", port=args.port)
            return 0
        if args.list_models:
            from .llm import LLMClient
            print("\n".join(LLMClient().list_models()))
            return 0
        if not args.inputs and not args.url:
            p.error("укажите JSON-файл, --url или --serve")

        products: list[Product] = []
        for path in args.inputs:
            products += load_products(sys.stdin.read(), "stdin") if path == "-" else load_file(path)

        if args.url:
            from .ingest import extract_product, fetch_html, html_to_text
            from .llm import LLMClient
            llm = LLMClient()
            for url in args.url:
                print(f"→ загружаю {url}", file=sys.stderr)
                title, text = html_to_text(fetch_html(url))
                pr, dropped = extract_product(text, title, llm)
                for d in dropped:
                    print(f"  ! отброшено как неподтверждённое страницей: {d}", file=sys.stderr)
                products.append(pr)

        if args.dry_run:
            for pr in products:
                miss = find_missing(pr)
                print(f"{pr.name}: " + ("пробелов нет" if not miss else "нет данных: " + ", ".join(miss)))
            return 0

        from .generator import generate_card
        from .llm import LLMClient
        from .render import slug, to_json, to_markdown

        llm = LLMClient()
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for pr in products:
            print(f"→ {pr.name} ...", file=sys.stderr)
            res = generate_card(pr, llm)
            base = out / slug(pr.name)
            base.with_suffix(".json").write_text(to_json(res), encoding="utf-8")
            base.with_suffix(".md").write_text(to_markdown(res), encoding="utf-8")
            print(to_markdown(res))
            print(f"[сохранено: {base}.md, {base}.json]", file=sys.stderr)
    except CardError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
