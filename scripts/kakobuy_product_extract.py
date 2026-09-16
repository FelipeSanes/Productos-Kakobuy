"""
Extracción determinística de una página de producto de Kakobuy, para que el
subagente kakobuy-product-vetter no tenga que navegar con Playwright él
mismo (eso lo hace este script; el subagente solo compara/juzga).

Uso:
    python scripts/kakobuy_product_extract.py <url_producto>

Devuelve por stdout un JSON con: fotos (lista de URLs), fotos_qc (lista de
URLs de fotos subidas por compradores, si el sitio las distingue), precio,
precio_con_envio, descripcion, vendedor_rating, vendedor_ventas.

NOTA: pendiente de inspección manual del sitio — selectores TODO.
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

STORAGE_STATE_PATH = Path(__file__).parent.parent / "auth" / "storage_state.json"

PHOTOS_SELECTOR = "TODO"
QC_PHOTOS_SELECTOR = "TODO"  # sección de fotos de compradores/QC, si existe
PRICE_SELECTOR = "TODO"
SHIPPING_PRICE_SELECTOR = "TODO"
DESCRIPTION_SELECTOR = "TODO"
SELLER_RATING_SELECTOR = "TODO"
SELLER_SALES_SELECTOR = "TODO"


def extract(url: str) -> dict:
    if not STORAGE_STATE_PATH.exists():
        raise SystemExit(f"No existe {STORAGE_STATE_PATH}. Corré primero auth/login.py")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STORAGE_STATE_PATH))
        page = context.new_page()
        page.goto(url)
        page.wait_for_selector(PHOTOS_SELECTOR)

        data = {
            "url": url,
            "fotos": [el.get_attribute("src") for el in page.query_selector_all(PHOTOS_SELECTOR)],
            "fotos_qc": [el.get_attribute("src") for el in page.query_selector_all(QC_PHOTOS_SELECTOR)],
            "precio": page.query_selector(PRICE_SELECTOR).inner_text() if page.query_selector(PRICE_SELECTOR) else None,
            "precio_con_envio": (
                page.query_selector(SHIPPING_PRICE_SELECTOR).inner_text()
                if page.query_selector(SHIPPING_PRICE_SELECTOR)
                else None
            ),
            "descripcion": (
                page.query_selector(DESCRIPTION_SELECTOR).inner_text()
                if page.query_selector(DESCRIPTION_SELECTOR)
                else None
            ),
            "vendedor_rating": (
                page.query_selector(SELLER_RATING_SELECTOR).inner_text()
                if page.query_selector(SELLER_RATING_SELECTOR)
                else None
            ),
            "vendedor_ventas": (
                page.query_selector(SELLER_SALES_SELECTOR).inner_text()
                if page.query_selector(SELLER_SALES_SELECTOR)
                else None
            ),
        }

        browser.close()
    return data


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python scripts/kakobuy_product_extract.py <url_producto>")
    print(json.dumps(extract(sys.argv[1]), ensure_ascii=False, indent=2))
