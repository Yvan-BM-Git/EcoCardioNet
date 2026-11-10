"""create_db.py, database/database.py (migraciones) y menu.py."""
import os

import openpyxl
from sqlalchemy import create_engine, inspect, text
from werkzeug.security import check_password_hash

from database import database
from database.database import COLUMNAS_MIGRADAS, ROLES_SISTEMA, SessionLocal
from database.models import Rol, Usuario, Variable
from tests.conftest import CLAVE_ADMIN, RAIZ, RUT_ADMIN, abrir_pagina


def test_usa_base_de_pruebas_y_no_produccion():
    assert database.DATABASE_URL.startswith("sqlite:///")
    assert "ecocardionet_tests_" in database.DATABASE_URL
    assert database.DATABASE_URL == os.environ["ECOCARDIONET_DATABASE_URL"]


def test_create_db_carga_todas_las_variables_del_excel():
    hoja = openpyxl.load_workbook(RAIZ / "variables_ecocardio.xlsx").active
    encabezado = [c.value for c in hoja[1]]
    i = encabezado.index("Codigo")
    codigos_excel = {f[i] for f in hoja.iter_rows(min_row=2, values_only=True) if f[i]}
    s = SessionLocal()
    codigos_bd = {c for (c,) in s.query(Variable.codigo)}
    fevi = s.query(Variable).filter(Variable.codigo == "FEVI").one()
    s.close()
    assert codigos_excel == codigos_bd
    assert fevi.tipo == "numero" and fevi.orden is not None


def test_create_db_roles_y_admin():
    s = SessionLocal()
    assert {r.nombre for r in s.query(Rol)} >= set(ROLES_SISTEMA)
    admin = s.query(Usuario).filter(Usuario.rut == RUT_ADMIN).one()
    rol = s.get(Rol, admin.rol_id).nombre
    s.close()
    assert rol == "Administrador" and admin.activo
    assert check_password_hash(admin.password_hash, CLAVE_ADMIN)      # hash werkzeug, no texto plano
    assert admin.password_hash != CLAVE_ADMIN


def test_init_db_es_idempotente():
    database.init_db.clear()
    assert database.init_db() is True
    database.init_db.clear()
    assert database.init_db() is True


def test_migracion_agrega_columnas_faltantes(tmp_path, monkeypatch):
    """Una base antigua sin las columnas nuevas recibe ALTER TABLE automáticamente."""
    motor = create_engine(f"sqlite:///{tmp_path / 'antigua.db'}")
    with motor.begin() as c:
        c.execute(text("CREATE TABLE estudios (id INTEGER PRIMARY KEY, paciente_rut VARCHAR)"))
        c.execute(text("CREATE TABLE variables (id INTEGER PRIMARY KEY, codigo VARCHAR)"))
        c.execute(text("CREATE TABLE mediciones (id INTEGER PRIMARY KEY, estudio_id INTEGER)"))
    monkeypatch.setattr(database, "engine", motor)
    database._migrar_columnas()
    insp = inspect(motor)
    for tabla, columna, _ in COLUMNAS_MIGRADAS:
        assert columna in {c["name"] for c in insp.get_columns(tabla)}, (tabla, columna)


def test_asegurar_bd_muestra_error_si_no_conecta(monkeypatch):
    from streamlit.testing.v1 import AppTest

    def falla():
        raise RuntimeError("sin red")
    monkeypatch.setattr(database, "init_db", falla)   # se restaura al terminar la prueba

    def script():
        import streamlit as st
        from database.database import asegurar_bd
        asegurar_bd()
        st.write("no debería verse")

    at = AppTest.from_function(script).run()
    assert at.error and "No se pudo conectar" in at.error[0].value
    assert not any("no debería verse" in m.value for m in at.markdown)


def test_menu_por_rol_y_cerrar_sesion():
    at = abrir_pagina("app.py", rol="Cardiólogo").run()
    assert any(b.label == "🚪 Cerrar Sesión" for b in at.sidebar.button)
    [b for b in at.sidebar.button if b.label == "🚪 Cerrar Sesión"][0].click().run()
    assert at.session_state["autenticado"] is False


def test_requirements_incluye_dependencias_indirectas_usadas():
    """plotly solo dibuja trendline="lowess" si statsmodels está instalado."""
    requisitos = (RAIZ / "requirements.txt").read_text().lower()
    codigo = "".join(p.read_text() for p in (RAIZ / "pages").glob("*.py"))
    if "trendline=" in codigo:
        assert "statsmodels" in requisitos
    for paquete in ("streamlit", "sqlalchemy", "psycopg2", "werkzeug", "pandas", "numpy", "openpyxl",
                    "plotly", "reportlab", "pdfplumber", "pillow"):
        assert paquete in requisitos, paquete
