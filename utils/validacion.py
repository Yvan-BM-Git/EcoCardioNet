# Archivo: utils/validacion.py
"""
Validación de campos numéricos compartida por pages/estudios.py y
pages/historial.py.

Reglas
------
- Separador decimal: punto. La coma se convierte en punto
  (el teclado chileno escribe coma en el teclado numérico).
- Máximo de decimales: DECIMALES_MAX (2). Los campos enteros
  (PAS, PAD, FC) no admiten decimales.
- Signo negativo: solo en las variables que pueden ser negativas por
  definición (strain miocárdico; ver permite_negativo()).
- Límites de plausibilidad (ValorMinimo / ValorMaximo de la tabla
  `variables`): fuera de rango se ADVIERTE, no se bloquea.

Dos capas
---------
1. Navegador: inyectar_bloqueo_numerico() impide escribir caracteres
   inválidos mientras se teclea (y al pegar).
2. Servidor: validar_numero() valida y normaliza el valor en el
   on_change y antes de guardar. Esta capa es la que garantiza que
   ningún dato inválido llegue a la base de datos, aunque el script
   del navegador no se haya cargado.
"""

from __future__ import annotations

import json
import re
from typing import Dict, Optional, Tuple, Union

import streamlit as st
import streamlit.components.v1 as components

Numero = Union[int, float]

DECIMALES_MAX = 2

# Variables que admiten valores negativos. Se definen por patrón de
# código para que una variable de strain nueva cargada desde el Excel
# quede cubierta sin tocar el código:
#   STRAIN_LONGITUDINAL_GLOBAL_VI  -> sí (normal ≈ -20 %)
#   STRAIN_AI_LASR                 -> no (strain auricular de reservorio, positivo)
#   FEVI_POR_STRAIN                -> no (FEVI, positiva)
_PATRON_NEGATIVO = re.compile(r"^STRAIN_(?!AI_)")


def permite_negativo(codigo: Optional[str]) -> bool:
    """True si la variable con este código puede tomar valores negativos."""
    return bool(codigo) and bool(_PATRON_NEGATIVO.match(str(codigo).strip().upper()))


def _patron(permitir_negativo: bool, decimales: int) -> re.Pattern:
    signo = "-?" if permitir_negativo else ""
    if decimales <= 0:
        return re.compile(rf"^{signo}\d+$")
    # "12", "12.", "12.5", "12.50", ".5"
    return re.compile(rf"^{signo}(\d+(\.\d{{0,{decimales}}})?|\.\d{{1,{decimales}}})$")


def normalizar_texto_numero(valor) -> str:
    """Quita espacios y convierte la coma decimal en punto."""
    if valor is None:
        return ""
    return str(valor).strip().replace(" ", "").replace(",", ".")


def validar_numero(
    valor,
    *,
    permitir_negativo: bool = False,
    decimales: int = DECIMALES_MAX,
    nombre: str = "El valor",
) -> Tuple[Optional[Numero], Optional[str]]:
    """
    Valida lo que escribió el usuario en un campo numérico.

    Devuelve (numero, error):
      - vacío                     -> (None, None)   (no es obligatorio aquí)
      - válido sin parte decimal  -> (int, None)    "70"    -> 70
      - válido con parte decimal  -> (float, None)  "12,5"  -> 12.5
      - inválido                  -> (None, mensaje)
    """
    if valor is None or isinstance(valor, bool):
        return None, None
    if isinstance(valor, (int, float)):
        if valor < 0 and not permitir_negativo:
            return None, f"{nombre} no puede ser negativo."
        if decimales <= 0 and isinstance(valor, float) and not valor.is_integer():
            return None, f"{nombre} debe ser un número entero."
        return valor, None

    texto = normalizar_texto_numero(valor)
    if texto == "":
        return None, None

    if _patron(permitir_negativo, decimales).match(texto):
        if "." in texto:
            numero = float(texto)
            if decimales <= 0:  # no debería ocurrir por el patrón
                return None, f"{nombre} debe ser un número entero."
            return numero, None
        return int(texto), None

    # Mensaje específico según el motivo del rechazo
    if texto.startswith("-") and not permitir_negativo:
        return None, f"{nombre} no puede ser negativo."
    if decimales <= 0 and re.fullmatch(r"-?\d*\.\d+", texto):
        return None, f"{nombre} debe ser un número entero (sin decimales)."
    if re.fullmatch(r"-?\d*\.\d+", texto):
        return None, f"{nombre}: máximo {decimales} decimales."
    return None, f"{nombre}: «{valor}» no es un número. Use cifras y punto decimal (ej.: 12.5)."


def texto_normalizado(numero: Optional[Numero], texto_original) -> str:
    """
    Texto que debe quedar en el campo tras validar: conserva lo que
    escribió el usuario pero con punto decimal ("12,5" -> "12.5").
    """
    if numero is None:
        return ""
    t = normalizar_texto_numero(texto_original)
    if t.endswith("."):
        t = t[:-1]
    if t.startswith("."):
        t = "0" + t
    if t.startswith("-."):
        t = "-0" + t[1:]
    return t


def _a_float(x) -> Optional[float]:
    try:
        if x is None or str(x).strip() == "":
            return None
        f = float(str(x).replace(",", "."))
        return None if f != f else f  # descarta NaN
    except (TypeError, ValueError):
        return None


def advertencia_rango(numero: Optional[Numero], minimo, maximo, unidad: str = "") -> Optional[str]:
    """
    Mensaje de advertencia si el número está fuera de [minimo, maximo].
    Sin límites definidos (columnas vacías en el Excel) no advierte nada.
    """
    if numero is None:
        return None
    vmin, vmax = _a_float(minimo), _a_float(maximo)
    u = f" {unidad}" if unidad else ""
    if vmin is not None and numero < vmin:
        return f"Valor bajo el mínimo plausible ({_fmt(vmin)}{u}). Revise si hay un error de tipeo."
    if vmax is not None and numero > vmax:
        return f"Valor sobre el máximo plausible ({_fmt(vmax)}{u}). Revise si hay un error de tipeo."
    return None


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


# ============================================================
# BLOQUEO EN EL NAVEGADOR
# ============================================================
def clase_widget(key: str) -> str:
    """Clase CSS que Streamlit asigna al contenedor de un widget con `key`."""
    return "st-key-" + re.sub(r"[^a-zA-Z0-9_-]", "-", key.strip())


# Código que se instala UNA vez en el documento principal de Streamlit
# (no en el iframe del componente), para que siga activo aunque el
# iframe se vuelva a montar en cada rerun.
#
# Funciona por delegación: un único listener `beforeinput` en el
# documento revisa si el campo pertenece a un widget numérico
# registrado en window.__ecoNumCfg. Si la inserción produciría un
# valor inválido, la cancela; si solo hay que corregirla (coma -> punto,
# texto pegado con letras), reemplaza el contenido con execCommand,
# que genera un evento de entrada nativo y mantiene sincronizado el
# estado de React/Streamlit.
_JS_INSTALADOR = r"""
(function () {
  var W = window;
  if (W.__ecoNumInstalado) { return; }
  W.__ecoNumInstalado = true;
  W.__ecoNumCfg = W.__ecoNumCfg || {};

  function sanitizar(v, neg, dec) {
    v = String(v).replace(/,/g, '.');
    var out = '', punto = false, ndec = 0;
    for (var i = 0; i < v.length; i++) {
      var c = v.charAt(i);
      if (c >= '0' && c <= '9') {
        if (punto) { if (ndec >= dec) { continue; } ndec++; }
        out += c;
      } else if (c === '.' && dec > 0 && !punto) {
        punto = true; out += c;
      } else if (c === '-' && neg && out.length === 0) {
        out += c;
      }
    }
    return out;
  }
  W.__ecoNumSanitizar = sanitizar;

  function configDe(el) {
    if (!el || el.tagName !== 'INPUT') { return null; }
    var n = el;
    while (n && n !== document.body) {
      if (n.classList) {
        for (var i = 0; i < n.classList.length; i++) {
          var c = n.classList[i];
          if (c.indexOf('st-key-') === 0) {
            return W.__ecoNumCfg[c] || null;
          }
        }
      }
      n = n.parentElement;
    }
    return null;
  }

  document.addEventListener('focusin', function (e) {
    var cfg = configDe(e.target);
    if (cfg) {
      e.target.setAttribute('inputmode', cfg.dec > 0 ? 'decimal' : 'numeric');
      e.target.setAttribute('autocomplete', 'off');
    }
  }, true);

  document.addEventListener('beforeinput', function (e) {
    var el = e.target;
    var cfg = configDe(el);
    if (!cfg) { return; }
    var tipo = e.inputType || '';
    if (tipo.indexOf('insert') !== 0 || tipo === 'insertCompositionText') { return; }

    var datos = e.data;
    if (datos == null && e.dataTransfer) { datos = e.dataTransfer.getData('text/plain'); }
    if (datos == null) { return; }

    var ini = el.selectionStart, fin = el.selectionEnd;
    if (ini == null || fin == null) { ini = fin = el.value.length; }
    var propuesto = el.value.slice(0, ini) + datos + el.value.slice(fin);
    var limpio = sanitizar(propuesto, cfg.neg, cfg.dec);
    if (limpio === propuesto) { return; }          // inserción válida

    e.preventDefault();
    if (limpio === el.value) { return; }            // se rechaza por completo

    // Inserción corregible (p. ej. coma -> punto): se reemplaza el texto
    // completo por la versión limpia, como si el usuario lo escribiera.
    var antesCursor = sanitizar(el.value.slice(0, ini) + datos, cfg.neg, cfg.dec).length;
    el.select();
    if (!document.execCommand('insertText', false, limpio)) {
      var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(el, limpio);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
    try { el.setSelectionRange(antesCursor, antesCursor); } catch (err) {}
  }, true);
})();
"""


def inyectar_bloqueo_numerico(campos: Dict[str, Dict[str, Union[bool, int]]]) -> None:
    """
    Activa el bloqueo al teclear para los widgets indicados.

    campos: {key_del_widget: {"neg": bool, "dec": int}}
      neg -> admite signo menos
      dec -> decimales permitidos (0 = entero)

    Llamar una vez por ejecución de la página, después de definir los
    widgets (el orden no importa: el bloqueo funciona por delegación).
    """
    if not campos:
        return
    cfg = {
        clase_widget(k): {"neg": bool(v.get("neg", False)), "dec": int(v.get("dec", DECIMALES_MAX))}
        for k, v in campos.items()
    }
    html = f"""
    <script>
    (function () {{
      try {{
        // Con st.html el script corre en la página principal (window);
        // con el respaldo components.html corre en un iframe (window.parent).
        var P = (window.parent && window.parent.document) ? window.parent : window;
        P.__ecoNumCfg = Object.assign(P.__ecoNumCfg || {{}}, {json.dumps(cfg)});
        if (!P.__ecoNumInstalado) {{
          var s = P.document.createElement('script');
          s.id = 'eco-num-guard';
          s.textContent = {json.dumps(_JS_INSTALADOR)};
          P.document.head.appendChild(s);
        }}
      }} catch (e) {{ console.log('EcoCardioNet: bloqueo numérico no disponible', e); }}
    }})();
    </script>
    """
    ejecutar_script(html)


def ejecutar_script(html: str) -> None:
    """
    Ejecuta un <script> en la página.

    st.components.v1.html está obsoleto en Streamlit 1.58 (se elimina
    después de 2026-06-01); se usa st.html(unsafe_allow_javascript=True),
    que corre el script en el documento principal sin iframe. Si la
    versión de Streamlit no lo soporta, se usa el método antiguo.
    """
    try:
        st.html(html, unsafe_allow_javascript=True)
    except TypeError:
        components.html(html, height=0, width=0)


# ============================================================
# CALLBACK GENÉRICO PARA st.text_input NUMÉRICOS
# ============================================================
def on_change_numerico(
    key: str,
    *,
    permitir_negativo: bool = False,
    decimales: int = DECIMALES_MAX,
    nombre: str = "El valor",
    valor_previo: str = "",
) -> Tuple[Optional[Numero], Optional[str]]:
    """
    Valida st.session_state[key]. Si es válido lo deja con punto decimal;
    si no, restaura `valor_previo` y muestra un aviso.
    Devuelve (numero, error).
    """
    texto = st.session_state.get(key, "")
    numero, error = validar_numero(
        texto, permitir_negativo=permitir_negativo, decimales=decimales, nombre=nombre
    )
    if error:
        st.session_state[key] = valor_previo
        st.toast(error, icon="⚠️")
        return None, error
    st.session_state[key] = texto_normalizado(numero, texto)
    return numero, None
