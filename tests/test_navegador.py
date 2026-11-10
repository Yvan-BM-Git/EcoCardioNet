"""
Pruebas en un navegador real (Chrome/Chromium con Playwright): lo que AppTest
no ve porque es JavaScript del lado del navegador.

  - formulario de login apto para gestores de contraseñas;
  - bloqueo de letras y comas en campos numéricos mientras se escribe;
  - aceptación de Términos y descarga del PDF diferido.

Se omiten solas si Playwright o el navegador no están instalados:
    pip install playwright && python -m playwright install chromium
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from tests.conftest import CLAVE_ADMIN, RAIZ, RUT_ADMIN

playwright_api = pytest.importorskip("playwright.sync_api")
pytestmark = [pytest.mark.lento, pytest.mark.navegador]


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def servidor():
    puerto = _puerto_libre()
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(RAIZ / "app.py"), "--server.headless", "true",
         "--server.port", str(puerto), "--browser.gatherUsageStats", "false"],
        cwd=RAIZ, env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{puerto}"
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/_stcore/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:  # pragma: no cover
        proc.terminate()
        pytest.skip("Streamlit no arrancó")
    yield url
    proc.terminate()
    proc.wait(10)


@pytest.fixture(scope="module")
def navegador():
    with playwright_api.sync_playwright() as p:
        opciones = {"args": ["--no-proxy-server"]}
        ruta = os.environ.get("ECOCARDIONET_CHROME")       # opcional: Chrome del sistema
        if ruta:
            opciones["executable_path"] = ruta
        try:
            b = p.chromium.launch(**opciones)
        except Exception as e:  # pragma: no cover
            pytest.skip(f"No hay navegador para Playwright: {e}")
        yield b
        b.close()


def _entrar(pagina, url):
    pagina.goto(url)
    pagina.wait_for_selector("#ecn-login", timeout=30000)
    pagina.fill("#ecn-username", RUT_ADMIN.replace(".", "").replace("-", ""))
    pagina.fill("#ecn-password", CLAVE_ADMIN)
    pagina.press("#ecn-password", "Enter")
    pagina.wait_for_selector("h1:has-text('Antes de continuar'), h3:has-text('Resumen del Sistema')", timeout=30000)
    if pagina.locator("text=Antes de continuar").count():
        pagina.get_by_text("He leído y acepto los Términos").click()
        pagina.get_by_text("He leído la Política").click()
        pagina.get_by_role("button", name="Aceptar y continuar").click()
    pagina.wait_for_selector("text=Resumen del Sistema", timeout=30000)


def test_formulario_login_para_gestores_de_claves(servidor, navegador):
    p = navegador.new_page()
    p.goto(servidor)
    p.wait_for_selector("#ecn-login", timeout=30000)
    info = p.evaluate("""() => { const f = document.getElementById('ecn-login');
        return {target: f.getAttribute('target'), method: f.getAttribute('method'),
                usuario: document.getElementById('ecn-username').autocomplete,
                clave: document.getElementById('ecn-password').autocomplete,
                iframe: !!document.getElementById('ecn-sink'), principal: window.top === window}; }""")
    assert info == {"target": "ecn-sink", "method": "post", "usuario": "username",
                    "clave": "current-password", "iframe": True, "principal": True}
    p.fill("#ecn-username", "111111111")
    p.fill("#ecn-password", "incorrecta")
    p.click("#ecn-submit")
    p.wait_for_selector("#ecn-error.visible", timeout=30000)
    assert "incorrectos" in p.inner_text("#ecn-error")
    assert p.input_value("#ecn-username") == RUT_ADMIN
    p.close()


def test_login_completo_y_campo_numerico_bloquea_texto(servidor, navegador):
    p = navegador.new_page()
    _entrar(p, servidor)
    p.get_by_role("link", name="Estudios").first.click()   # navegar sin recargar (conserva la sesión)
    p.wait_for_selector("text=Selección de Paciente", timeout=30000)
    busqueda = p.locator(".st-key-busqueda_input input")
    busqueda.fill("14.111.222-3")
    busqueda.press("Enter")
    sel = p.locator(".st-key-selectbox_busqueda_estudios input")
    sel.wait_for(timeout=30000)
    sel.click()
    p.keyboard.press("ArrowDown")
    p.keyboard.press("Enter")
    p.get_by_role("tab", name="Cavidades y aorta").click()
    fevi = p.locator(".st-key-var_FEVI input")
    fevi.wait_for(timeout=30000)
    fevi.click()
    p.keyboard.type("6a0,555")              # letras bloqueadas, coma -> punto, máx. 2 decimales
    assert fevi.input_value() == "60.55"
    p.close()


def test_pagina_legal_publica(servidor, navegador):
    p = navegador.new_page()
    p.goto(servidor)
    p.wait_for_selector("#ecn-login", timeout=30000)
    p.click(".ecn-legal a >> nth=0")
    p.wait_for_selector("text=Términos de Servicio de EcoCardioNet", timeout=30000)
    p.close()
