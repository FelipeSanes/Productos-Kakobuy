"""
Agente 2 — Kakobuy Searcher (automatización pura, sin LLM).

Ejecuta una búsqueda en Kakobuy (por texto y/o por imagen de referencia) y
devuelve el listado de resultados tal como aparece en la vista de lista
(sin abrir cada producto). Usa la sesión guardada por auth/login.py.

Uso:
    python scripts/kakobuy_searcher.py --text "nombre del producto" \
        [--image data/<slug>/reference/img1.jpg] \
        --out data/<slug>/results/listado.json

NOTA: pendiente de inspección manual del sitio (sección 1 de la guía):
URL de búsqueda por texto, endpoint/flujo de búsqueda por imagen, y
selectores de la página de resultados (título, precio, link, thumbnail,
rating/ventas del vendedor). Los placeholders de abajo hay que
reemplazarlos por los valores reales antes de que esto funcione.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

STORAGE_STATE_PATH = Path(__file__).parent.parent / "auth" / "storage_state.json"

SEARCH_URL_TEMPLATE = "https://kakobuy.com/search?q={query}"  # TODO: confirmar patrón real
RESULT_ITEM_SELECTOR = "TODO"
RESULT_TITLE_SELECTOR = "TODO"
RESULT_PRICE_SELECTOR = "TODO"
RESULT_LINK_SELECTOR = "TODO"
RESULT_THUMBNAIL_SELECTOR = "TODO"
RESULT_SELLER_SELECTOR = "TODO"  # rating/ventas si aparece en la vista de lista

IMAGE_SEARCH_UPLOAD_SELECTOR = "TODO"  # solo si --image


def search_by_text(page, query: str) -> list[dict]:
    page.goto(SEARCH_URL_TEMPLATE.format(query=quote(query)))
    page.wait_for_selector(RESULT_ITEM_SELECTOR)

    items = []
    for el in page.query_selector_all(RESULT_ITEM_SELECTOR):
        items.append(
            {
                "titulo": el.query_selector(RESULT_TITLE_SELECTOR).inner_text(),
                "precio": el.query_selector(RESULT_PRICE_SELECTOR).inner_text(),
                "url": el.query_selector(RESULT_LINK_SELECTOR).get_attribute("href"),
                "thumbnail": el.query_selector(RESULT_THUMBNAIL_SELECTOR).get_attribute("src"),
                "vendedor_info": (
                    el.query_selector(RESULT_SELLER_SELECTOR).inner_text()
                    if el.query_selector(RESULT_SELLER_SELECTOR)
                    else None
                ),
                "query_origen": query,
            }
        )
    return items


def search_by_image(page, image_path: str) -> list[dict]:
    raise NotImplementedError(
        "Falta inspeccionar el flujo de búsqueda por imagen de Kakobuy "
        "(¿sube a un endpoint separado? ¿input file directo?)."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", action="append", default=[], help="Query de texto (puede repetirse para variantes)")
    parser.add_argument("--image", help="Path a imagen de referencia")
    parser.add_argument("--out", required=True, help="Path del JSON de salida")
    args = parser.parse_args()

    if not STORAGE_STATE_PATH.exists():
        raise SystemExit(f"No existe {STORAGE_STATE_PATH}. Corré primero auth/login.py")

    results: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STORAGE_STATE_PATH))
        page = context.new_page()

        for query in args.text:
            results.extend(search_by_text(page, query))

        if args.image:
            results.extend(search_by_image(page, args.image))

        browser.close()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"{len(results)} resultados -> {out_path}")


if __name__ == "__main__":
    main()
