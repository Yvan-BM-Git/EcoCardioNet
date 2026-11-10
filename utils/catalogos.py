"""
Catálogos que casi no cambian, cacheados para no consultar la base en
cada interacción (Streamlit vuelve a ejecutar la página entera cada vez
que se toca un widget, y cada consulta a Neon cuesta un viaje de red).

- variables(): las ~100 variables del Excel, en el orden clínico.
- pacientes(): lista liviana (RUT y nombre) para los buscadores.

Las copias son objetos simples (no ORM): se pueden leer como v.codigo,
v.tipo, etc., pero no se deben modificar.
"""
from __future__ import annotations

from types import SimpleNamespace

import streamlit as st

from database.database import SessionLocal
from database.models import Paciente, Variable

_COLUMNAS_VARIABLE = [c.name for c in Variable.__table__.columns]


@st.cache_resource(ttl=600, show_spinner=False)
def variables() -> tuple:
    session = SessionLocal()
    try:
        filas = (session.query(Variable)
                 .order_by(Variable.orden.is_(None), Variable.orden, Variable.categoria)
                 .all())
        return tuple(SimpleNamespace(**{c: getattr(v, c) for c in _COLUMNAS_VARIABLE}) for v in filas)
    finally:
        session.close()


def variables_por_codigo() -> dict:
    return {v.codigo: v for v in variables()}


@st.cache_data(ttl=300, show_spinner=False)
def pacientes() -> list[dict]:
    session = SessionLocal()
    try:
        filas = (session.query(Paciente.rut, Paciente.nombres, Paciente.apellido_paterno,
                               Paciente.apellido_materno)
                 .order_by(Paciente.apellido_paterno, Paciente.nombres).all())
    finally:
        session.close()
    return [{"rut": r, "nombres": n or "", "apellido_paterno": ap or "", "apellido_materno": am or ""}
            for r, n, ap, am in filas]


def limpiar_pacientes() -> None:
    """Llamar después de crear, editar o eliminar pacientes."""
    pacientes.clear()
