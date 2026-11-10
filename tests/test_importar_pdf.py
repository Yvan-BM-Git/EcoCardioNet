"""utils/importar_pdf.py: lectura asistida de informes en PDF."""
import io
from types import SimpleNamespace

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from utils import catalogos
from utils.importar_pdf import (
    ALIASES_MEDICIONES, _buscar_valor, _buscar_valor_categorico, _normalizar, dividir_nombre_completo,
    extraer_datos_generales, extraer_mediciones, extraer_nombre_paciente, extraer_texto_pdf,
)

INFORME = """Paciente : JUAN CARLOS PEREZ SOTO
RUT: 12.345.678-9  Fecha: 05/11/2026
Sexo: masculino
Peso: 70,5 kg Talla: 170 cm FC: 72 lpm
Ritmo: sinusal
Dr. Eric Fuentes Latorre
FE(Teich) 60 %   TAPSE 18 mm   TAP 110 ms
GPR 0,45   Onda S' 12 cm/s   PSAP 35 mmHg
"""


def _pdf_con_texto(texto: str) -> io.BytesIO:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for linea in texto.splitlines():
        c.drawString(40, y, linea)
        y -= 16
    c.save()
    buf.seek(0)
    return buf


def test_normalizar():
    assert _normalizar("  Fracción   de  EYECCIÓN ") == "fraccion de eyeccion"
    assert _normalizar(None) == ""


def test_todos_los_alias_apuntan_a_variables_existentes():
    """Un alias con un código inexistente se descarta en silencio (pasaba con ONDA_S y GPR)."""
    codigos = set(catalogos.variables_por_codigo())
    assert not [c for c in ALIASES_MEDICIONES if c not in codigos]


@pytest.mark.parametrize("etiquetas, esperado", [
    (["tap"], "110"),               # no debe leer el TAPSE
    (["tapse"], "18"),
    (["fe(teich)"], "60"),
    (["gpr"], "0.45"),              # coma decimal -> punto
    (["no existe"], None),
])
def test_buscar_valor_palabra_completa(etiquetas, esperado):
    assert _buscar_valor(_normalizar(INFORME), etiquetas) == esperado


def test_buscar_valor_categorico():
    t = _normalizar("Grado de reflujo mitral: moderada a severa")
    assert _buscar_valor_categorico(t, "reflujo mitral", ["Leve", "Moderada a severa"]) == "Moderada a severa"
    assert _buscar_valor_categorico(t, "reflujo aortico", ["Leve"]) is None


def test_extraer_mediciones_usa_alias_y_respeta_tipos():
    meds = extraer_mediciones(INFORME, catalogos.variables_por_codigo())
    assert meds["FEVI"] == "60"
    assert meds["TAPSE"] == "18"
    assert meds["TIEMPO_ACELERACION_PULMONAR"] == "110"
    assert meds["GROSOR_PARIETAL_RELATIVO"] == "0.45"
    assert meds["ONDA_S_PRIMA"] == "12"
    assert meds["PSAP"] == "35"


def test_extraer_mediciones_categoricas_por_nombre():
    var = SimpleNamespace(nombre="Reflujo aórtico", tipo="categoria", opciones="Leve;Moderada;Severa")
    texto = "Reflujo aórtico: severa"
    assert extraer_mediciones(texto, {"GRADO_REFLUJO_AORTICO": var}) == {"GRADO_REFLUJO_AORTICO": "Severa"}


def test_extraer_mediciones_no_toma_variables_de_texto():
    var = SimpleNamespace(nombre="Comentario", tipo="texto", opciones=None)
    assert extraer_mediciones("Comentario 123", {"OBS": var}) == {}


def test_extraer_datos_generales():
    d = extraer_datos_generales(INFORME)
    assert d["rut"] == "12.345.678-9"
    assert d["fecha_texto"] == "05/11/2026"
    assert d["sexo"] == "Masculino"
    assert d["peso"] == "70.5" and d["talla"] == "170"
    assert d["fcia"] == "72"
    assert d["ritmo"] == "Sinusal"
    assert d["medico_sugerido"] == "Dr. Eric Fuentes Latorre"   # sin arrastrar la línea siguiente
    assert d["nombre_completo"] == "Juan Carlos Perez Soto"


def test_extraer_datos_generales_formato_ge():
    t = "Name PEREZ SOTO, JUAN Patient ID 12345678-K Birthdate 01/05/1960 Gender Male Weight 80 Height 175"
    d = extraer_datos_generales(t)
    assert d["rut"] == "12345678-K"
    assert d["fecha_nacimiento_texto"] == "01/05/1960"
    assert d["sexo"] == "Masculino"
    assert (d["peso"], d["talla"]) == ("80", "175")
    assert d["nombre_completo"] == "Juan Perez Soto"


@pytest.mark.parametrize("texto, esperado", [
    ("Paciente : JUAN CARLOS PEREZ SOTO RUT 1", "Juan Carlos Perez Soto"),
    ("Paciente: ANA SOTO RUT 1", "Ana Soto"),
    ("Paciente: X RUT", None),
    ("sin datos", None),
])
def test_extraer_nombre_paciente(texto, esperado):
    assert extraer_nombre_paciente(texto) == esperado


@pytest.mark.parametrize("nombre, esperado", [
    ("Juan Carlos Perez Soto", ("Juan Carlos", "Perez", "Soto")),
    ("Ana Perez Soto", ("Ana", "Perez", "Soto")),
    ("Ana Perez", ("Ana", "Perez", "")),
    ("Ana", ("Ana", "", "")),
    ("", ("", "", "")),
])
def test_dividir_nombre_completo(nombre, esperado):
    assert dividir_nombre_completo(nombre) == esperado


def test_extraer_texto_pdf_ida_y_vuelta():
    texto = extraer_texto_pdf(_pdf_con_texto(INFORME))
    assert "TAPSE 18" in texto
    assert extraer_datos_generales(texto)["rut"] == "12.345.678-9"
