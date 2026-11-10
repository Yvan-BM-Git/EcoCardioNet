"""
Configuración común de las pruebas de EcoCardioNet.

Las pruebas NUNCA usan la base de producción (Neon). Antes de importar
cualquier módulo de la app se define ECOCARDIONET_DATABASE_URL apuntando a
una base SQLite temporal, que se crea con create_db.py (tablas, roles,
administrador y las variables del Excel), igual que en una instalación nueva.

Ejecutar desde la carpeta del proyecto:
    python -m pytest tests            # todo
    python -m pytest tests -m "not lento"   # sin los casos de punta a punta
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
CLAVE_ADMIN = "ClaveDePrueba123"
RUT_ADMIN = "11.111.111-1"

_TMP = Path(tempfile.mkdtemp(prefix="ecocardionet_tests_"))
os.environ["ECOCARDIONET_DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["ECOCARDIONET_ADMIN_PASSWORD"] = CLAVE_ADMIN
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# Base nueva para esta sesión de pruebas, creada con el script oficial.
_creacion = subprocess.run(
    [sys.executable, str(RAIZ / "create_db.py")],
    cwd=RAIZ, env=os.environ.copy(), capture_output=True, text=True,
)
if _creacion.returncode != 0:  # pragma: no cover - solo si create_db falla
    raise RuntimeError("create_db.py falló:\n" + _creacion.stdout + _creacion.stderr)

import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

# AppTest corre una página a la vez y no admite navegar entre páginas.
st.page_link = lambda *a, **k: None
st.switch_page = lambda *a, **k: None

from database.database import SessionLocal  # noqa: E402
from database.models import Paciente  # noqa: E402

PACIENTES_PRUEBA = {
    "14.111.222-3": dict(nombres="Juan", apellido_paterno="Prueba", apellido_materno="Uno",
                         sexo="Masculino", fecha_nacimiento=date(1960, 5, 1)),
    "15.222.333-4": dict(nombres="Ana", apellido_paterno="Prueba", apellido_materno="Dos",
                         sexo="Femenino", fecha_nacimiento=date(1955, 3, 1)),
}


def _sembrar_pacientes():
    s = SessionLocal()
    try:
        for rut, datos in PACIENTES_PRUEBA.items():
            if not s.get(Paciente, rut):
                s.add(Paciente(rut=rut, **datos))
        s.commit()
    finally:
        s.close()


_sembrar_pacientes()


def abrir_pagina(ruta: str, rol: str = "Administrador", nombre: str = "Dr. Prueba",
                 rut: str = RUT_ADMIN, autenticado: bool = True) -> AppTest:
    """AppTest de una página con la sesión ya iniciada (o sin sesión)."""
    at = AppTest.from_file(str(RAIZ / ruta), default_timeout=120)
    if autenticado:
        at.session_state["autenticado"] = True
        at.session_state["usuario_actual"] = {"rut": rut, "nombre": nombre, "rol": rol}
    return at


def abrir_estudio(rut: str, rol: str = "Administrador") -> AppTest:
    """Nuevo Estudio con el paciente `rut` ya seleccionado."""
    at = abrir_pagina("pages/estudios.py", rol=rol)
    at.run()
    at.text_input(key="busqueda_input").input(rut).run()
    at.selectbox(key="selectbox_busqueda_estudios").set_value(rut).run()
    return at


def sin_excepciones(at: AppTest) -> list[str]:
    return [e.value for e in at.exception]


@pytest.fixture
def sesion_bd():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()
