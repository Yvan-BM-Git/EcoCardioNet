# Archivo: utils/pacientes_utils.py
"""
Funciones y constantes compartidas para el manejo de datos de Paciente
(formateo de RUT, teléfonos, prefijos internacionales).
Usado por pages/historial.py.
"""
import streamlit as st

# ==================================================
# CONSTANTES COMPARTIDAS
# ==================================================
OPTS_PREV = ["", "Fonasa", "Isapre", "Otra"]
OPTS_SEXO = ["", "Masculino", "Femenino"]

DIC_PREFIJOS = {
    "+56": "🇨🇱 +56",
    "+54": "🇦🇷 +54",
    "+51": "🇵🇪 +51",
    "+57": "🇨🇴 +57",
    "+52": "🇲🇽 +52",
    "+58": "🇻🇪 +58",
    "+593": "🇪🇨 +593",
    "+591": "🇧🇴 +591",
    "+595": "🇵🇾 +595",
    "+598": "🇺🇾 +598",
    "+55": "🇧🇷 +55",
    "+1":  "🇺🇸/🇨🇦 +1",
    "+34": "🇪🇸 +34",
    "OTRO": "🌍 Otro..."
}
LISTA_PREFIJOS = list(DIC_PREFIJOS.keys())


# ==================================================
# CALLBACKS DE FORMATEO (operan sobre st.session_state[key])
# ==================================================


def formatear_telefono_dinamico(k):
    telf_actual = st.session_state.get(k, "")
    if not telf_actual:
        return

    numeros = "".join(c for c in str(telf_actual) if c.isdigit())
    numeros = numeros[:9]

    if len(numeros) <= 3:
        st.session_state[k] = numeros
    elif len(numeros) <= 6:
        st.session_state[k] = f"{numeros[:3]} {numeros[3:]}"
    else:
        st.session_state[k] = f"{numeros[:3]} {numeros[3:6]} {numeros[6:]}"


def formatear_busqueda_rut(busqueda_actual):
    """Versión pura (sin session_state) del formateo de búsqueda por RUT.
    Devuelve el string formateado o el original si no matchea patrón de RUT."""
    if not busqueda_actual:
        return busqueda_actual
    limpio = busqueda_actual.replace(".", "").replace("-", "").strip().upper()
    if 7 <= len(limpio) <= 9:
        cuerpo = limpio[:-1]
        dv = limpio[-1]
        if cuerpo.isdigit() and (dv.isdigit() or dv == "K"):
            cuerpo_formateado = f"{int(cuerpo):,}".replace(",", ".")
            return f"{cuerpo_formateado}-{dv}"
    return busqueda_actual