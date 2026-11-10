"""utils/pacientes_utils.py, utils/login_ui.py, utils/catalogos.py, utils/legal.py."""
import re

import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import PACIENTES_PRUEBA, RUT_ADMIN
from utils import catalogos, legal
from utils.login_ui import CLAVE_PUENTE, _tarjeta, formatear_rut
from utils.pacientes_utils import DIC_PREFIJOS, LISTA_PREFIJOS, OPTS_PREV, OPTS_SEXO, formatear_busqueda_rut


# ---------------- RUT y teléfonos ----------------
@pytest.mark.parametrize("entrada, esperado", [
    ("123456789", "12.345.678-9"),
    ("12.345.678-9", "12.345.678-9"),
    ("12345678k", "12.345.678-K"),
    ("juan", "juan"),       # texto libre: se busca por nombre, no se toca
    ("1234", "1234"),       # aún incompleto
    ("", ""),
])
def test_formatear_busqueda_rut(entrada, esperado):
    assert formatear_busqueda_rut(entrada) == esperado


@pytest.mark.parametrize("entrada, esperado", [
    ("111111111", "11.111.111-1"),
    ("11.111.111-1", "11.111.111-1"),
    ("12345678-k", "12.345.678-K"),
    ("7654321-0", "7.654.321-0"),
    ("1", "1"),
    ("", ""),
    (None, ""),
])
def test_formatear_rut_login(entrada, esperado):
    assert formatear_rut(entrada) == esperado


def test_constantes_pacientes():
    assert OPTS_SEXO == ["", "Masculino", "Femenino"]
    assert "Fonasa" in OPTS_PREV
    assert LISTA_PREFIJOS == list(DIC_PREFIJOS)


def test_formatear_telefono_dinamico():
    def script():
        import streamlit as st
        from utils.pacientes_utils import formatear_telefono_dinamico
        for k, v in {"a": "912345678", "b": "9123", "c": "91", "d": "+56 9 1234 5678 99"}.items():
            st.session_state[k] = v
            formatear_telefono_dinamico(k)

    at = AppTest.from_function(script).run()
    assert at.session_state["a"] == "912 345 678"
    assert at.session_state["b"] == "912 3"
    assert at.session_state["c"] == "91"
    assert at.session_state["d"] == "569 123 456"   # se recorta a 9 dígitos


# ---------------- Login ----------------
def test_tarjeta_login_compatible_con_gestores_de_claves():
    html = _tarjeta("11.111.111-1", "RUT o contraseña incorrectos.")
    assert 'autocomplete="username"' in html
    assert 'autocomplete="current-password"' in html
    assert 'type="password"' in html
    assert re.search(r'<form id="ecn-login"', html)
    assert 'value="11.111.111-1"' in html
    assert "ecn-error visible" in html
    assert 'href="legal"' in html                       # enlace a Términos y Privacidad


def test_tarjeta_login_escapa_html():
    html = _tarjeta('"><script>x</script>', "<b>error</b>")
    assert "<script>x</script>" not in html
    assert "&lt;b&gt;error&lt;/b&gt;" in html


def test_mostrar_login_renderiza_puente_oculto():
    def script():
        from utils.login_ui import mostrar_login
        mostrar_login()

    at = AppTest.from_function(script).run()
    assert not at.exception
    assert [t.key for t in at.text_input] == ["puente_rut", "puente_clave"]
    assert CLAVE_PUENTE == "login_puente"


# ---------------- Catálogos ----------------
def test_catalogo_variables_ordenado_y_completo():
    vs = catalogos.variables()
    assert len(vs) > 90
    ordenes = [v.orden for v in vs if v.orden is not None]
    assert ordenes == sorted(ordenes)
    por_codigo = catalogos.variables_por_codigo()
    assert por_codigo["FEVI"].tipo == "numero"
    assert {"codigo", "nombre", "tipo", "unidad", "valor_minimo", "valor_maximo"} <= set(vars(vs[0]))


def test_catalogo_pacientes_y_limpieza(sesion_bd):
    from database.models import Paciente
    ruts = {p["rut"] for p in catalogos.pacientes()}
    assert set(PACIENTES_PRUEBA) <= ruts
    sesion_bd.add(Paciente(rut="9.999.999-9", nombres="Temporal", apellido_paterno="Cache"))
    sesion_bd.commit()
    assert "9.999.999-9" not in {p["rut"] for p in catalogos.pacientes()}   # sigue en caché
    catalogos.limpiar_pacientes()
    assert "9.999.999-9" in {p["rut"] for p in catalogos.pacientes()}
    sesion_bd.query(Paciente).filter(Paciente.rut == "9.999.999-9").delete()
    sesion_bd.commit()
    catalogos.limpiar_pacientes()


# ---------------- Términos y Privacidad ----------------
@pytest.mark.parametrize("doc", list(legal.DOCUMENTOS))
def test_textos_legales_sin_marcadores(doc):
    t = legal.texto(doc)
    assert "{" not in t and "}" not in t
    assert legal.RESPONSABLE in t
    assert legal.VERSION in t and legal.FECHA_VIGENCIA in t


def test_politica_cumple_deber_de_informacion():
    """Art. 14 ter: identidad, contacto, finalidades, base de licitud, conservación, derechos, reclamo."""
    t = legal.texto("privacidad").lower()
    for requisito in ("responsable", legal.CONTACTO, "finalidad", "base de licitud", "conservación",
                      "acceso", "rectificación", "supresión", "oposición", "portabilidad", "bloqueo",
                      "agencia de protección de datos personales", "transferencia internacional"):
        assert requisito in t, requisito


def test_compacto_reduce_titulos():
    assert legal._compacto("# A\n## B\n### C") == "#### A\n##### B\n### C"


def test_aceptacion_registrada_y_versionada(monkeypatch):
    rut = "77.777.777-7"
    assert legal.pendientes(rut) == ["terminos", "privacidad"]
    legal.registrar(rut, ["terminos"])
    assert legal.pendientes(rut) == ["privacidad"]
    legal.registrar(rut, ["privacidad"])
    assert legal.pendientes(rut) == []
    monkeypatch.setattr(legal, "VERSION", "9.9")          # documento nuevo: se vuelve a pedir
    assert legal.pendientes(rut) == ["terminos", "privacidad"]


def test_admin_sin_aceptacion_inicial():
    assert legal.pendientes(RUT_ADMIN) in (["terminos", "privacidad"], [])
