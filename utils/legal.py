"""
Términos de Servicio y Política de Privacidad (Ley 21.719).

Los textos viven en legal/*.md. Para publicar una versión nueva basta con
editar el texto y subir VERSION; al próximo ingreso, cada usuario deberá
aceptarla de nuevo (la aceptación queda registrada con fecha y versión).
"""
from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from database.database import SessionLocal
from database.models import AceptacionLegal

RESPONSABLE = "Hospital Regional de Talca"
CONTACTO = "ybalderam@gmail.com"
VERSION = "1.0"
FECHA_VIGENCIA = "10 de noviembre de 2026"

DOCUMENTOS = {
    "terminos": "Términos de Servicio",
    "privacidad": "Política de Privacidad",
}
_CARPETA = Path(__file__).resolve().parent.parent / "legal"


@st.cache_data(show_spinner=False)
def texto(documento: str) -> str:
    plantilla = (_CARPETA / f"{documento}.md").read_text(encoding="utf-8")
    return (plantilla.replace("{version}", VERSION)
            .replace("{fecha}", FECHA_VIGENCIA)
            .replace("{responsable}", RESPONSABLE)
            .replace("{contacto}", CONTACTO))


def pendientes(usuario_rut: str) -> list[str]:
    """Documentos cuya versión vigente el usuario aún no acepta."""
    session = SessionLocal()
    try:
        aceptados = {
            d for (d,) in session.query(AceptacionLegal.documento).filter(
                AceptacionLegal.usuario_rut == usuario_rut,
                AceptacionLegal.version == VERSION,
            )
        }
    finally:
        session.close()
    return [d for d in DOCUMENTOS if d not in aceptados]


def registrar(usuario_rut: str, documentos: list[str]) -> None:
    session = SessionLocal()
    try:
        for d in documentos:
            session.add(AceptacionLegal(usuario_rut=usuario_rut, documento=d, version=VERSION))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _compacto(md: str) -> str:
    """Títulos más pequeños para mostrar dentro de la app (# → ####, ## → #####)."""
    return re.sub(r"^(#{1,2}) ", lambda m: "#" * (len(m.group(1)) + 3) + " ", md, flags=re.M)


def mostrar_documentos() -> None:
    """Ambos documentos en pestañas (página pública y pantalla de aceptación)."""
    t1, t2 = st.tabs([DOCUMENTOS["terminos"], DOCUMENTOS["privacidad"]])
    with t1:
        st.markdown(_compacto(texto("terminos")))
    with t2:
        st.markdown(_compacto(texto("privacidad")))


def pantalla_aceptacion(usuario: dict, faltan: list[str]) -> str | None:
    """
    Dibuja la pantalla de aceptación. Devuelve "aceptado", "rechazado" o None.
    """
    nuevos = " y la ".join(DOCUMENTOS[d] for d in faltan)
    st.title("Antes de continuar")
    st.markdown(
        f"Hola, **{usuario['nombre']}**. Para usar EcoCardioNet debes leer y aceptar "
        f"los {nuevos} (versión {VERSION}). EcoCardioNet trata datos de salud, que la "
        "Ley N° 21.719 protege como datos sensibles."
    )
    with st.container(height=420, border=True):
        mostrar_documentos()

    marcas = []
    if "terminos" in faltan:
        marcas.append(st.checkbox(
            "He leído y acepto los Términos de Servicio, incluido el deber de confidencialidad.",
            key="acepta_terminos"))
    if "privacidad" in faltan:
        marcas.append(st.checkbox(
            "He leído la Política de Privacidad y me comprometo a tratar los datos conforme a ella.",
            key="acepta_privacidad"))

    c1, c2, _ = st.columns([1.2, 1, 3])
    if c1.button("Aceptar y continuar", type="primary", disabled=not all(marcas), width="stretch"):
        return "aceptado"
    if c2.button("Rechazar y salir", width="stretch"):
        return "rechazado"
    return None
