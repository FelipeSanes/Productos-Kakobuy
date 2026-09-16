"""
Login único a Kakobuy: guarda las cookies de sesión en auth/storage_state.json
para que el resto de los scripts (searcher, vetter) no tengan que loguearse
de nuevo en cada corrida.

Uso:
    KAKOBUY_EMAIL=... KAKOBUY_PASSWORD=... python auth/login.py

NOTA: los selectores del formulario de login (LOGIN_URL, EMAIL_SELECTOR, etc.)
todavía no están confirmados: hace falta abrir kakobuy.com una vez con
Playwright en modo visible/inspección y anotar los selectores reales antes
de que este script funcione. Este archivo es el andamiaje a completar en
ese paso.
"""

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

STORAGE_STATE_PATH = Path(__file__).parent / "storage_state.json"

LOGIN_URL = "https://kakobuy.com/login"  # TODO: confirmar URL real
EMAIL_SELECTOR = "TODO"
PASSWORD_SELECTOR = "TODO"
SUBMIT_SELECTOR = "TODO"
LOGGED_IN_SELECTOR = "TODO"  # selector que solo aparece post-login


def main() -> None:
    email = os.environ.get("KAKOBUY_EMAIL")
    password = os.environ.get("KAKOBUY_PASSWORD")
    if not email or not password:
        sys.exit("Faltan KAKOBUY_EMAIL / KAKOBUY_PASSWORD en el entorno.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(LOGIN_URL)
        page.fill(EMAIL_SELECTOR, email)
        page.fill(PASSWORD_SELECTOR, password)
        page.click(SUBMIT_SELECTOR)
        page.wait_for_selector(LOGGED_IN_SELECTOR, timeout=15000)

        page.context.storage_state(path=str(STORAGE_STATE_PATH))
        browser.close()

    print(f"Sesión guardada en {STORAGE_STATE_PATH}")


if __name__ == "__main__":
    main()
