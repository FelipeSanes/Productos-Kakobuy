"""
Agente 2 — Kakobuy Searcher (automatización pura, sin LLM).

Ejecuta una búsqueda en Kakobuy (por texto y/o por imagen de referencia) y
devuelve el listado de resultados tal como aparece en la vista de lista
(sin abrir cada producto en profundidad — solo se abre brevemente cada
card para capturar la URL real, porque el sitio no expone <a href> en la
lista, y se cierra esa pestaña enseguida). Usa la sesión guardada por
auth/login.py.

Uso:
    python scripts/kakobuy_searcher.py --text "nombre del producto" \
        [--text "variante en chino"] \
        [--image data/<slug>/reference/img1.jpg] \
        --out data/<slug>/results/listado.json

Notas de la inspección manual del sitio (ver docs/guia-agente-kakobuy.md):
- No hay Cloudflare challenge bloqueando la búsqueda (Turnstile está cargado
  en la página pero no se activa para este flujo).
- La home tiene DOS inputs con el mismo placeholder (uno en el header, otro
  en el buscador principal) — hay que escopear el selector al <form> que
  contiene #search_btn, si no se llena el campo equivocado.
- La primera vez que se busca en la cuenta aparece un modal "Search Terms
  of Service" que hay que aceptar (después no vuelve a aparecer).
- Las cards de resultado no tienen href: al clickear abren una pestaña
  nueva (window.open) hacia item.kakobuy.com/item/details?url=<marketplace
  url original, urlencoded>. Por eso se captura la URL con
  context.expect_page() y se cierra la pestaña sin cargarla del todo.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import Page, sync_playwright

STORAGE_STATE_PATH = Path(__file__).parent.parent / "auth" / "storage_state.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

HOME_URL = "https://kakobuy.com/"
SEARCH_FORM = "form:has(#search_btn)"
RESULT_CARD = ".shop-card"


def _accept_terms_if_present(page: Page) -> None:
    agree = page.locator(".confim_true:visible").first
    try:
        if agree.count() > 0:
            agree.click(timeout=3000)
    except Exception:
        pass


def _wait_for_results(page: Page) -> None:
    page.wait_for_timeout(2000)
    _accept_terms_if_present(page)
    page.wait_for_timeout(2000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass


def _extract_cards(page: Page, origen: str, context, max_cards: int) -> list[dict]:
    cards = page.locator(RESULT_CARD)
    n = min(cards.count(), max_cards)
    items = []
    for i in range(n):
        card = cards.nth(i)
        try:
            titulo = card.locator("h3 span[title]").get_attribute("title")
            precio = card.locator(".price").inner_text()
            thumbnail = card.locator(".pic img").get_attribute("src")
            plataforma_icon = card.locator("h3 .el-image.icon img").get_attribute("src")
            sales_text = card.locator(".sales").inner_text() if card.locator(".sales").count() else None
        except Exception:
            continue

        url = None
        new_page = None
        try:
            with context.expect_page(timeout=4000) as new_page_info:
                card.click()
            new_page = new_page_info.value
            url = new_page.url
        except Exception:
            url = None
        finally:
            if new_page is not None:
                try:
                    new_page.close()
                except Exception:
                    pass

        items.append(
            {
                "titulo": titulo,
                "precio": precio,
                "ventas": sales_text,
                "url": url,
                "thumbnail": thumbnail,
                "plataforma": "1688" if plataforma_icon and "1688" in plataforma_icon else "taobao/weidian",
                "query_origen": origen,
            }
        )
    return items


def search_by_text(page: Page, context, query: str, max_cards: int) -> list[dict]:
    page.goto(HOME_URL, wait_until="networkidle")
    search_input = page.locator(f"{SEARCH_FORM} input[type='text']")
    search_input.fill(query)
    page.click("#search_btn")
    _wait_for_results(page)
    return _extract_cards(page, query, context, max_cards)


def search_by_image(page: Page, context, image_path: str, max_cards: int) -> list[dict]:
    page.goto(HOME_URL, wait_until="networkidle")
    file_input = page.locator(f"{SEARCH_FORM} input[type='file']")
    file_input.set_input_files(image_path)
    _wait_for_results(page)
    return _extract_cards(page, f"image:{image_path}", context, max_cards)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", action="append", default=[], help="Query de texto (repetible para variantes)")
    parser.add_argument("--image", help="Path a imagen de referencia")
    parser.add_argument("--out", required=True, help="Path del JSON de salida")
    parser.add_argument(
        "--max-cards",
        type=int,
        default=10,
        help="Máximo de resultados a abrir por búsqueda para capturar su URL (default 10)",
    )
    args = parser.parse_args()

    if not STORAGE_STATE_PATH.exists():
        raise SystemExit(
            f"No existe {STORAGE_STATE_PATH}. Corré primero:\n"
            "  python auth/login.py request\n"
            "  python auth/login.py verify <codigo>"
        )

    results: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STORAGE_STATE_PATH), user_agent=USER_AGENT)
        page = context.new_page()

        for query in args.text:
            results.extend(search_by_text(page, context, query, args.max_cards))

        if args.image:
            results.extend(search_by_image(page, context, args.image, args.max_cards))

        browser.close()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"{len(results)} resultados -> {out_path}")


if __name__ == "__main__":
    main()
