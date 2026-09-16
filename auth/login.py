"""
Login a Kakobuy en dos fases, porque el sitio pide un código de verificación
por email (OTP) además de usuario/contraseña — no hay forma de saltearlo.

Fase 1 — pedir el código (llena usuario/contraseña y dispara el envío del
email con el código):

    KAKOBUY_EMAIL=... KAKOBUY_PASSWORD=... python auth/login.py request

Revisá el email y ejecutá la fase 2 con el código de 6 dígitos que llegó:

    KAKOBUY_EMAIL=... KAKOBUY_PASSWORD=... python auth/login.py verify 123456

La fase 2 vuelve a completar el formulario desde cero (usuario, contraseña y
código) en una sola corrida — el código no queda atado a la sesión de
Playwright que lo pidió, así que no hace falta mantener el navegador abierto
entre fases. Al terminar, guarda las cookies de sesión en
auth/storage_state.json (gitignored) para que el resto de los scripts no
tengan que loguearse de nuevo.
"""

import argparse
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

STORAGE_STATE_PATH = Path(__file__).parent / "storage_state.json"
LOGIN_URL = "https://kakobuy.com/login"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _get_credentials() -> tuple[str, str]:
    email = os.environ.get("KAKOBUY_EMAIL")
    password = os.environ.get("KAKOBUY_PASSWORD")
    if not email or not password:
        sys.exit("Faltan KAKOBUY_EMAIL / KAKOBUY_PASSWORD en el entorno.")
    return email, password


def request_code() -> None:
    email, password = _get_credentials()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(LOGIN_URL, wait_until="networkidle")
        page.fill('input[name="username"]', email)
        page.fill('input[name="password"]', password)
        page.click(".submit-btn")
        page.wait_for_selector("input.captcha-email", timeout=10000)
        page.click("text=Send")
        page.wait_for_timeout(2000)
        browser.close()
    print(f"Código solicitado. Revisá el email de {email} y corré:")
    print("  python auth/login.py verify <codigo>")


def verify(code: str) -> None:
    email, password = _get_credentials()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="networkidle")
        page.fill('input[name="username"]', email)
        page.fill('input[name="password"]', password)
        page.click(".submit-btn")
        page.wait_for_selector("input.captcha-email", timeout=10000)
        page.fill("input.captcha-email", code)
        page.click(".submit-btn")
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

        cookie_names = [c["name"] for c in page.context.cookies()]
        if "token" not in cookie_names:
            browser.close()
            sys.exit(
                "No se encontró la cookie 'token' tras el login — el código "
                "puede haber expirado (dura pocos minutos). Pedí uno nuevo con "
                "'python auth/login.py request'."
            )

        STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        page.context.storage_state(path=str(STORAGE_STATE_PATH))
        browser.close()
    print(f"Login OK. Sesión guardada en {STORAGE_STATE_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("request")
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("code")
    args = parser.parse_args()

    if args.action == "request":
        request_code()
    else:
        verify(args.code)


if __name__ == "__main__":
    main()
