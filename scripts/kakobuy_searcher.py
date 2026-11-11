"""
Agente 2 — Kakobuy Searcher (automatización pura, sin LLM).

Busca en Kakobuy por texto y/o imagen, en las 3 pestañas de resultados
(Top / 1688 / Taobao), y devuelve el listado tal como aparece. Usa la
sesión guardada por auth/login.py.

Uso:
    python scripts/kakobuy_searcher.py --text "精工手表" [--text ...] \
        [--image ref.jpg] [--tab taobao --tab 1688] \
        [--must "seiko|精工"] [--open-urls 10] \
        --out data/<slug>/results/listado.json

Hallazgos de la inspección real del sitio (no repetir los errores):
- CAUSA REAL de los "0 resultados" falsos: los resultados tardan 5-12s en
  aparecer (se cargan por XHR cifrado a v1.kakoapi.com) y el script viejo
  esperaba ~4s fijos. NO era flakiness del sitio: con polling de
  `.shop-card` hasta 30s la misma query sale bien a la primera.
- Búsqueda de texto: se puede navegar directo a
  /item/shop?keyword=<query> (no hace falta el form de la home).
- Hay 3 pestañas: "Top" (mezcla, sesgada a 1688), "1688" y "Taobao".
  Taobao tiene stock que en Top no aparece (ej. relojes Seiko originales
  con cientos de ventas). Taobao muestra 20 por página, 1688 ~50.
- Los títulos de 1688 vienen traducidos al inglés; los de Taobao a veces
  en chino. Filtrá con --must usando ambos idiomas.
- La primera vez aparece un modal "Search Terms of Service"
  (`.confim_true:visible`) que hay que aceptar.
- Las cards no tienen href: al clickear abren pestaña nueva hacia
  item.kakobuy.com/item/details?url=<url original>. Abrir cada card es
  lento, por eso solo se abren las que pasan --must (hasta --open-urls).
- Algunas URLs apuntan a ofertas ya borradas: validar siempre con
  kakobuy_product_extract.py antes de mandarle un link al usuario.
"""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import Page, sync_playwright

STORAGE_STATE_PATH = Path(__file__).parent.parent / "auth" / "storage_state.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

HOME_URL = "https://kakobuy.com/"
SHOP_URL = "https://kakobuy.com/item/shop?keyword="
SEARCH_FORM = "form:has(#search_btn)"
RESULT_CARD = ".shop-card"
CARD_WAIT_S = 30
TABS = {
    "top": "Top",
    "1688": "Agent Shopping from - 1688",
    "taobao": "Agent Shopping from - Taobao",
}

READ_CARDS_JS = """() => [...document.querySelectorAll('.shop-card')].map((c, i) => {
  const t = c.querySelector('h3 span[title]');
  const pr = c.querySelector('.price');
  const s = c.querySelector('.sales');
  const img = c.querySelector('.pic img');
  const icon = c.querySelector('h3 .el-image.icon img');
  return {idx: i, titulo: t ? t.title : '', precio: pr ? pr.innerText : '',
          ventas: s ? s.innerText : null, thumbnail: img ? img.src : null,
          icon: icon ? icon.src : ''};
})"""


def _first_title(page: Page) -> str | None:
    card = page.locator(RESULT_CARD).first
    if card.count() == 0:
        return None
    return card.locator("h3 span[title]").get_attribute("title")


def _wait_cards(page: Page, prev_first: str | None = None) -> int:
    """Pollea hasta que haya cards (y distintas de las de la pestaña anterior)."""
    for _ in range(CARD_WAIT_S):
        page.wait_for_timeout(1000)
        try:
            page.locator(".confim_true:visible").first.click(timeout=300)
        except Exception:
            pass
        n = page.locator(RESULT_CARD).count()
        if n and _first_title(page) != prev_first:
            return n
    return 0


def _load_lazy_images(page: Page) -> None:
    """Las miniaturas cargan con lazy-load: scrollear cada card a la vista."""
    for card in page.locator(RESULT_CARD).all():
        try:
            card.scroll_into_view_if_needed(timeout=1000)
        except Exception:
            pass
    page.wait_for_timeout(800)
    page.evaluate("window.scrollTo(0, 0)")


def _capture_url(page: Page, context, idx: int) -> str | None:
    new_page = None
    try:
        with context.expect_page(timeout=6000) as info:
            page.locator(RESULT_CARD).nth(idx).click()
        new_page = info.value
        return new_page.url
    except Exception:
        return None
    finally:
        if new_page is not None:
            try:
                new_page.close()
            except Exception:
                pass


def _collect_tabs(page: Page, context, origen: str, tabs: list[str], must, open_urls: int) -> list[dict]:
    items: list[dict] = []
    prev_first = _first_title(page) if page.locator(RESULT_CARD).count() else None
    for tab in tabs:
        if tab != "top":
            page.locator(".ant-tabs-tab", has_text=TABS[tab]).first.click()
            if not _wait_cards(page, prev_first):
                print(f"  [{origen}] pestaña {tab}: 0 resultados")
                continue
        prev_first = _first_title(page)
        _load_lazy_images(page)
        cards = page.evaluate(READ_CARDS_JS)
        print(f"  [{origen}] pestaña {tab}: {len(cards)} resultados")
        opened = 0
        for c in cards:
            relevante = bool(must.search(c["titulo"])) if must else True
            url = None
            if relevante and opened < open_urls:
                url = _capture_url(page, context, c["idx"])
                opened += 1
            items.append(
                {
                    "titulo": c["titulo"],
                    "precio": c["precio"],
                    "ventas": c["ventas"],
                    "url": url,
                    "thumbnail": c["thumbnail"],
                    "plataforma": "1688" if "1688" in (c["icon"] or "") else "taobao/weidian",
                    "pestana": tab,
                    "relevante": relevante,
                    "query_origen": origen,
                }
            )
    return items


def search_by_text(page: Page, context, query: str, tabs, must, open_urls) -> list[dict]:
    page.goto(SHOP_URL + quote(query), wait_until="domcontentloaded")
    if not _wait_cards(page) and "top" in tabs:
        print(f"  [{query!r}] pestaña top: 0 resultados tras {CARD_WAIT_S}s")
        tabs = [t for t in tabs if t != "top"]
    return _collect_tabs(page, context, query, tabs, must, open_urls)


def search_by_image(page: Page, context, image_path: str, tabs, must, open_urls) -> list[dict]:
    page.goto(HOME_URL, wait_until="networkidle")
    page.locator(f"{SEARCH_FORM} input[type='file']").set_input_files(image_path)
    if not _wait_cards(page):
        print(f"  [image:{image_path}] 0 resultados tras {CARD_WAIT_S}s")
        return []
    # la búsqueda por imagen no siempre muestra las 3 pestañas
    available = [t for t in tabs if t == "top" or page.locator(".ant-tabs-tab", has_text=TABS[t]).count()]
    return _collect_tabs(page, context, f"image:{image_path}", available, must, open_urls)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", action="append", default=[], help="Query de texto (repetible)")
    parser.add_argument("--image", action="append", default=[], help="Imagen de referencia (repetible)")
    parser.add_argument("--tab", action="append", choices=list(TABS), help="Pestañas a leer (default: todas)")
    parser.add_argument("--must", help="Regex (case-insensitive) que marca un título como relevante")
    parser.add_argument("--open-urls", type=int, default=10, help="Máx. cards relevantes a abrir por pestaña para capturar URL")
    parser.add_argument("--out", required=True, help="Path del JSON de salida")
    args = parser.parse_args()

    if not STORAGE_STATE_PATH.exists():
        raise SystemExit(
            f"No existe {STORAGE_STATE_PATH}. Corré primero:\n"
            "  python auth/login.py request\n"
            "  python auth/login.py verify <codigo>"
        )

    tabs = args.tab or list(TABS)
    must = re.compile(args.must, re.I) if args.must else None

    results: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STORAGE_STATE_PATH), user_agent=USER_AGENT)
        page = context.new_page()
        for query in args.text:
            results.extend(search_by_text(page, context, query, tabs, must, args.open_urls))
        for image in args.image:
            results.extend(search_by_image(page, context, image, tabs, must, args.open_urls))
        browser.close()

    seen = set()
    deduped = []
    for r in results:
        key = r["url"] or (r["titulo"], r["precio"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(deduped, ensure_ascii=False, indent=2))
    n_rel = sum(r["relevante"] for r in deduped)
    print(f"{len(deduped)} resultados ({n_rel} relevantes) -> {out_path}")


if __name__ == "__main__":
    main()
