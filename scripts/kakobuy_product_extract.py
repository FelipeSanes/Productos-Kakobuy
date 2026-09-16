"""
Extracción determinística de una página de producto de Kakobuy, para que el
subagente kakobuy-product-vetter no tenga que navegar con Playwright él
mismo (eso lo hace este script; el subagente solo compara/juzga).

Uso:
    python scripts/kakobuy_product_extract.py <url_producto>

Donde <url_producto> es la URL que devuelve kakobuy_searcher.py, con forma
https://item.kakobuy.com/item/details?url=<marketplace url original>

Devuelve por stdout un JSON con: titulo, fotos (thumbnails de la galería),
precio_cny, precio_usd, ventas_listado, url_original (1688/Taobao/Weidian).

Limitaciones reales del sitio (confirmadas por inspección manual, ver
docs/guia-agente-kakobuy.md):
- Kakobuy NO muestra fotos de QC (quality control) de compradores reales
  en su propia página de producto, ni un rating de estrellas del vendedor.
- El contador "Sales" de la página de detalle del producto es FALSO: el
  mismo producto mostró 15, 212, 293, 874 y 903 ventas en cargas
  consecutivas de la misma página (segundos entre cada una) — es un
  patrón de urgencia de marketing generado client-side, no un dato real.
  Por eso este script NO lo extrae. El contador de ventas confiable es el
  que aparece en el LISTADO de búsqueda (campo "ventas" que ya devuelve
  kakobuy_searcher.py), que se mantuvo estable entre corridas separadas
  por varios minutos — usá ese, pasado por el orquestador, no vuelvas a
  pedirlo acá.
- La pestaña "Product details" es una sola imagen vertical gigante (la
  descripción del vendedor como infografía, práctica común en 1688/Taobao),
  no texto plano — por eso no hay un campo "descripcion" de texto: leer
  menciones de "batch"/calidad ahí requeriría visión sobre una imagen muy
  larga, no vale el costo salvo que el producto ya pase el filtro visual.
"""

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

STORAGE_STATE_PATH = Path(__file__).parent.parent / "auth" / "storage_state.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

TITLE_SELECTOR = ".item-title"
PRICE_SELECTOR = ".sku-price"
GALLERY_SELECTOR = ".item-imgs-box .item-img img"
ORIGINAL_URL_SELECTOR = ".seller-url"

PRICE_RE = re.compile(r"CNY\D*([\d.,]+).*?\$\D*([\d.,]+)", re.S)


def extract(url: str) -> dict:
    if not STORAGE_STATE_PATH.exists():
        raise SystemExit(
            f"No existe {STORAGE_STATE_PATH}. Corré primero:\n"
            "  python auth/login.py request\n"
            "  python auth/login.py verify <codigo>"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STORAGE_STATE_PATH), user_agent=USER_AGENT)
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        page.wait_for_selector(TITLE_SELECTOR, timeout=15000)
        page.wait_for_timeout(1000)

        titulo = page.locator(TITLE_SELECTOR).inner_text()
        precio_texto = page.locator(PRICE_SELECTOR).inner_text()
        fotos = [el.get_attribute("src") for el in page.locator(GALLERY_SELECTOR).all()]
        url_original = (
            page.locator(ORIGINAL_URL_SELECTOR).get_attribute("href")
            if page.locator(ORIGINAL_URL_SELECTOR).count()
            else None
        )

        browser.close()

    precio_match = PRICE_RE.search(precio_texto)

    return {
        "url": url,
        "titulo": titulo,
        "fotos": fotos,
        "precio_cny": float(precio_match.group(1)) if precio_match else None,
        "precio_usd": float(precio_match.group(2)) if precio_match else None,
        "url_original": url_original,
        "fotos_qc": [],  # no disponible en Kakobuy, ver docstring
        "descripcion": None,  # descripción es una imagen, no texto, ver docstring
        # El conteo de ventas confiable viene del listado de búsqueda
        # (kakobuy_searcher.py), no de esta página — ver docstring.
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python scripts/kakobuy_product_extract.py <url_producto>")
    print(json.dumps(extract(sys.argv[1]), ensure_ascii=False, indent=2))
