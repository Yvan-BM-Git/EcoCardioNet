"""
Pantalla de inicio de sesión de EcoCardioNet.

Por qué está hecha así
----------------------
Los gestores de contraseñas de los navegadores (Chrome, Edge, Firefox,
Safari, Brave) solo ofrecen guardar y autocompletar cuando ven un
<form> HTML real, con un campo de usuario (autocomplete="username") y uno
de contraseña (autocomplete="current-password") dentro del mismo
formulario, que además se "envía". Los campos de Streamlit no cumplen
eso: el RUT y la clave estaban en contenedores distintos y no hay un
<form> de verdad, por eso el navegador no recordaba las credenciales.

Solución:
1. El formulario visible es HTML propio (st.html, en el documento
   principal, sin iframe), con nombres y autocomplete estándar.
2. Al enviarlo, el navegador hace un envío real hacia un iframe oculto
   (about:blank): no recarga la página ni manda la clave a ningún
   servidor, pero cuenta como inicio de sesión para el gestor de claves.
3. En el mismo evento, un script copia RUT y clave a un formulario
   puente de Streamlit (oculto) y lo envía; Python valida como siempre.
   El puente se vacía al enviarse (clear_on_submit).
"""
from __future__ import annotations

import base64
import html

import streamlit as st

CLAVE_PUENTE = "login_puente"
KEY_RUT = "puente_rut"
KEY_PASS = "puente_clave"


def formatear_rut(texto: str) -> str:
    """'123456789' / '12.345.678-9' / '12345678-k' -> '12.345.678-9' (DV en mayúscula)."""
    limpio = "".join(c for c in (texto or "").upper() if c.isdigit() or c == "K")[:9]
    if len(limpio) < 2:
        return limpio
    cuerpo, dv = limpio[:-1], limpio[-1]
    if not cuerpo.isdigit():
        return limpio
    return f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}"


_CSS = """
<style>
  /* Pantalla de login: sin barra superior ni márgenes de Streamlit */
  [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
  [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }
  [data-testid="stAppViewContainer"] { background: #f4f6fa; }
  .block-container, [data-testid="stMainBlockContainer"] { padding-top: 0 !important; max-width: 100% !important; }

  /* Formulario puente: existe para Streamlit, invisible para el usuario y los gestores de claves */
  .st-key-__PUENTE__ { position: absolute !important; left: -10000px !important; top: 0 !important;
                       width: 1px !important; height: 1px !important; overflow: hidden !important; }

  .ecn-wrap { min-height: 92vh; display: flex; align-items: center; justify-content: center;
              font-family: "Source Sans 3", "Source Sans Pro", -apple-system, BlinkMacSystemFont,
              "Segoe UI", Roboto, sans-serif; }
  .ecn-card { width: 100%; max-width: 380px; background: #fff; border: 1px solid #e3e7ee;
              border-radius: 14px; padding: 36px 32px 26px; box-shadow: 0 8px 28px rgba(16,32,64,.07); }
  .ecn-brand { text-align: center; margin-bottom: 26px; }
  .ecn-logo { width: 46px; height: 46px; border-radius: 12px; background: #fdecec;
              display: inline-flex; align-items: center; justify-content: center; margin-bottom: 12px; }
  .ecn-brand h1 { font-size: 1.45rem; font-weight: 700; color: #16213a; margin: 0; padding: 0; letter-spacing: -.01em; }
  .ecn-brand p { font-size: .9rem; color: #69758a; margin: 4px 0 0; }
  .ecn-field { margin-bottom: 16px; }
  .ecn-field label { display: block; font-size: .82rem; font-weight: 600; color: #36415a; margin-bottom: 6px; }
  .ecn-input { position: relative; }
  .ecn-input input { width: 100%; box-sizing: border-box; height: 44px; padding: 0 12px;
                     font-size: .98rem; color: #16213a; background: #fff; border: 1px solid #ccd3de;
                     border-radius: 8px; outline: none; transition: border-color .15s, box-shadow .15s; }
  .ecn-input input:focus { border-color: #c62f3c; box-shadow: 0 0 0 3px rgba(198,47,60,.13); }
  .ecn-input input.ecn-pass { padding-right: 76px; }
  .ecn-toggle { position: absolute; right: 6px; top: 6px; height: 32px; padding: 0 10px; border: 0;
                background: transparent; color: #56627a; font-size: .8rem; font-weight: 600;
                border-radius: 6px; cursor: pointer; }
  .ecn-toggle:hover { background: #f1f3f7; }
  .ecn-error { display: none; background: #fdf0f0; border: 1px solid #f3c8cb; color: #9b1c27;
               border-radius: 8px; padding: 9px 12px; font-size: .86rem; margin-bottom: 16px; }
  .ecn-error.visible { display: block; }
  .ecn-btn { width: 100%; height: 44px; margin-top: 6px; border: 0; border-radius: 8px;
             background: #c62f3c; color: #fff; font-size: 1rem; font-weight: 600; cursor: pointer;
             transition: background .15s; }
  .ecn-btn:hover { background: #ab2632; }
  .ecn-btn:disabled { background: #d98a91; cursor: wait; }
  .ecn-help { text-align: center; font-size: .8rem; color: #7a8598; margin: 18px 0 0; line-height: 1.4; }
</style>
""".replace("__PUENTE__", CLAVE_PUENTE)

_SVG_LOGO = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" '
    'stroke="#c62f3c" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M19.5 12.6 12 20l-7.5-7.4A4.9 4.9 0 0 1 12 6a4.9 4.9 0 0 1 7.5 6.6z"/>'
    '<path d="M3.5 12h4l2-3 3 6 2-3h6"/></svg>'
)
# st.html limpia los <svg> en línea; como imagen data-URI se muestra siempre.
_LOGO = ('<img alt="" width="26" height="26" src="data:image/svg+xml;base64,'
         + base64.b64encode(_SVG_LOGO.encode()).decode() + '">')

_JS = """
<script>
(function () {
  const form = document.getElementById('ecn-login');
  if (!form || form.dataset.listo) return;
  form.dataset.listo = '1';
  const rut = document.getElementById('ecn-username');
  const pass = document.getElementById('ecn-password');
  const btn = document.getElementById('ecn-submit');
  const err = document.getElementById('ecn-error');

  // Envío real hacia un iframe oculto: el navegador lo registra como
  // inicio de sesión (para ofrecer guardar la clave) sin salir de la app.
  if (!document.getElementById('ecn-sink')) {
    const sink = document.createElement('iframe');
    sink.name = 'ecn-sink'; sink.id = 'ecn-sink'; sink.tabIndex = -1;
    sink.setAttribute('aria-hidden', 'true');
    sink.style.cssText = 'position:absolute;width:0;height:0;border:0;left:-10000px;';
    document.body.appendChild(sink);
  }
  form.setAttribute('action', 'about:blank');
  form.setAttribute('method', 'post');
  form.setAttribute('target', 'ecn-sink');

  function formatear(v) {
    let s = (v || '').toUpperCase().replace(/[^0-9K]/g, '').slice(0, 9);
    if (s.length < 2) return s;
    const cuerpo = s.slice(0, -1), dv = s.slice(-1);
    if (!/^[0-9]+$/.test(cuerpo)) return s;
    return cuerpo.replace(/\\B(?=(\\d{3})+(?!\\d))/g, '.') + '-' + dv;
  }
  rut.addEventListener('blur', function () { rut.value = formatear(rut.value); });

  document.getElementById('ecn-toggle').addEventListener('click', function () {
    const ver = pass.type === 'password';
    pass.type = ver ? 'text' : 'password';
    this.textContent = ver ? 'Ocultar' : 'Mostrar';
    this.setAttribute('aria-label', ver ? 'Ocultar contraseña' : 'Mostrar contraseña');
    pass.focus();
  });

  // Escribe en un input controlado por React (Streamlit) y avisa del cambio.
  function escribir(input, valor) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(input, valor);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function puente() {
    const caja = document.querySelector('.st-key-__PUENTE__');
    if (!caja) return null;
    const campos = caja.querySelectorAll('input');
    const boton = caja.querySelector('button');
    if (campos.length < 2 || !boton) return null;
    campos.forEach(function (c) { c.setAttribute('autocomplete', 'off'); c.tabIndex = -1; });
    return { rut: campos[0], clave: campos[1], boton: boton };
  }
  puente();

  form.addEventListener('submit', function (ev) {
    rut.value = formatear(rut.value);
    if (!rut.value || !pass.value) {
      ev.preventDefault();
      err.textContent = 'Ingresa tu RUT y tu contraseña.';
      err.classList.add('visible');
      (rut.value ? pass : rut).focus();
      return;
    }
    const p = puente();
    if (!p) { ev.preventDefault(); return; }
    escribir(p.rut, rut.value);
    escribir(p.clave, pass.value);
    btn.disabled = true; btn.textContent = 'Ingresando…';
    err.classList.remove('visible');
    // El envío nativo (al iframe) sigue su curso; Streamlit recibe el puente.
    setTimeout(function () { p.boton.click(); }, 0);
  });

  (rut.value ? pass : rut).focus();
})();
</script>
""".replace("__PUENTE__", CLAVE_PUENTE)


def _tarjeta(rut_previo: str, error: str | None) -> str:
    rut_attr = html.escape(rut_previo or "", quote=True)
    clase_err = "ecn-error visible" if error else "ecn-error"
    texto_err = html.escape(error or "")
    return f"""
<div class="ecn-wrap">
  <div class="ecn-card">
    <div class="ecn-brand">
      <div class="ecn-logo">{_LOGO}</div>
      <h1>EcoCardioNet</h1>
      <p>Registro e informes de ecocardiografía</p>
    </div>
    <form id="ecn-login" autocomplete="on" novalidate>
      <div id="ecn-error" class="{clase_err}" role="alert">{texto_err}</div>
      <div class="ecn-field">
        <label for="ecn-username">RUT</label>
        <div class="ecn-input">
          <input id="ecn-username" name="username" type="text" inputmode="text"
                 autocomplete="username" autocapitalize="characters" spellcheck="false"
                 placeholder="12.345.678-9" value="{rut_attr}" required>
        </div>
      </div>
      <div class="ecn-field">
        <label for="ecn-password">Contraseña</label>
        <div class="ecn-input">
          <input id="ecn-password" name="password" type="password" class="ecn-pass"
                 autocomplete="current-password" required>
          <button type="button" id="ecn-toggle" class="ecn-toggle" aria-label="Mostrar contraseña">Mostrar</button>
        </div>
      </div>
      <button type="submit" id="ecn-submit" class="ecn-btn">Ingresar</button>
    </form>
    <p class="ecn-help">¿Olvidaste tu contraseña? Pide al Administrador que la restablezca en Gestión de Usuarios.</p>
  </div>
</div>
"""


def mostrar_login(rut_previo: str = "", error: str | None = None):
    """
    Dibuja la pantalla de login. Devuelve (rut, clave) cuando el usuario
    envía el formulario; si no, None.
    """
    st.html(_CSS)
    st.html(_tarjeta(rut_previo, error) + _JS, unsafe_allow_javascript=True)

    with st.container(key=CLAVE_PUENTE):
        with st.form("form_login_puente", clear_on_submit=True, border=False):
            rut = st.text_input("rut", key=KEY_RUT, label_visibility="collapsed")
            clave = st.text_input("clave", key=KEY_PASS, label_visibility="collapsed")
            enviado = st.form_submit_button("entrar")
    if enviado:
        return formatear_rut(rut), clave
    return None

