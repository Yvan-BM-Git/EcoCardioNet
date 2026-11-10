"""utils/valvulopatias.py (graduación ASE/EACVI) y generación del PDF del informe."""
import io
from datetime import date
from types import SimpleNamespace

import pdfplumber
import pytest

from utils.pdf_informe import (
    construir_informe_automatico, generar_pdf_desde_historial, informe_a_texto_agrupado,
)
from utils.valvulopatias import conclusion_global_valvular, evaluar_valvulopatias, grado_cualitativo


@pytest.mark.parametrize("texto, nivel", [
    ("Ausente", 0), ("Trivial", 0.5), ("Leve", 1), ("Leve-Moderada", 1.5),
    ("Moderada a severa", 2.5), ("Severa", 3), (None, None),
])
def test_grado_cualitativo(texto, nivel):
    assert grado_cualitativo(texto) == nivel


VALVULAS = [
    ("EA severa", {"VELOCIDAD_PICO_AORTICA": 4.5, "GRADIENTE_MEDIO_AORTICO": 50, "AREA_VALVULAR_AORTICA_CONTINUIDAD": 0.7},
     "estenosis_ao", "severa"),
    ("EA moderada", {"VELOCIDAD_PICO_AORTICA": 3.5, "GRADIENTE_MEDIO_AORTICO": 28, "AREA_VALVULAR_AORTICA_CONTINUIDAD": 1.2},
     "estenosis_ao", "moderada"),
    ("EA leve", {"VELOCIDAD_PICO_AORTICA": 2.8, "GRADIENTE_MEDIO_AORTICO": 15, "AREA_VALVULAR_AORTICA_CONTINUIDAD": 1.7},
     "estenosis_ao", "leve"),
    ("IAo severa", {"VENA_CONTRACTA_AORTICA": 7, "TIEMPO_HEMIPRESION_AORTICO": 180, "EROA_AORTICO": 0.35},
     "insuf_ao", "severa"),
    ("EM severa", {"AREA_MITRAL": 0.9, "GRADIENTE_MEDIO_MITRAL": 12}, "estenosis_mitral", "severa"),
    ("IM severa", {"EROA_MITRAL": 0.45, "VOLUMEN_REGURGITANTE_MITRAL": 65, "VENA_CONTRACTA_MITRAL": 8},
     "insuf_mit", "severa"),
    ("IM leve", {"EROA_MITRAL": 0.1, "VOLUMEN_REGURGITANTE_MITRAL": 20}, "insuf_mit", "leve"),
    ("IT severa", {"VENA_CONTRACTA_TRICUSPIDEA": 8, "GRADO_REFLUJO_TRICUSPIDEO": "Severa"}, "insuf_it", "severa"),
    ("EP severa", {"VELOCIDAD_PICO_PULMONAR": 4.5}, "estenosis_pulmonar", "severa"),
    ("IP severa", {"GRADO_REFLUJO_PULMONAR": "Severa"}, "insuf_pulmonar", "severa"),
    ("Prótesis aórtica normal", {"PROTESIS_AORTICA": "Biológica", "VELOCIDAD_PICO_AORTICA": 2.5,
                                 "GRADIENTE_MEDIO_AORTICO": 12, "INDICE_VELOCIDAD_DOPPLER": 0.4},
     "estenosis_ao", "protesis_normal"),
    ("Prótesis aórtica obstruida", {"PROTESIS_AORTICA": "Mecánica", "VELOCIDAD_PICO_AORTICA": 4.3,
                                    "GRADIENTE_MEDIO_AORTICO": 40, "INDICE_VELOCIDAD_DOPPLER": 0.2},
     "estenosis_ao", "protesis_obstruccion"),
    ("Prótesis con gradiente alto y DVI normal", {"PROTESIS_AORTICA": "Biológica", "VELOCIDAD_PICO_AORTICA": 4.2,
                                                  "GRADIENTE_MEDIO_AORTICO": 38, "INDICE_VELOCIDAD_DOPPLER": 0.35},
     "estenosis_ao", "protesis_alto_gradiente"),
    ("Prótesis con gradiente intermedio y DVI normal", {"PROTESIS_AORTICA": "Biológica", "VELOCIDAD_PICO_AORTICA": 3.6,
                                                        "GRADIENTE_MEDIO_AORTICO": 30, "INDICE_VELOCIDAD_DOPPLER": 0.35},
     "estenosis_ao", "protesis_alto_gradiente"),
    ("Prótesis con gradiente intermedio y DVI intermedio", {"PROTESIS_AORTICA": "Biológica", "VELOCIDAD_PICO_AORTICA": 3.6,
                                                            "GRADIENTE_MEDIO_AORTICO": 30, "INDICE_VELOCIDAD_DOPPLER": 0.27},
     "estenosis_ao", "protesis_posible"),
    ("Prótesis mitral obstruida", {"PROTESIS_MITRAL": "Mecánica", "GRADIENTE_MEDIO_MITRAL": 12},
     "estenosis_mitral", "protesis_obstruccion"),
]


@pytest.mark.parametrize("valores, clave, estado", [pytest.param(v, c, e, id=n) for n, v, c, e in VALVULAS])
def test_graduacion_valvular(valores, clave, estado):
    res = {r["clave"]: r for r in evaluar_valvulopatias(valores, "Masculino")}
    assert res[clave]["estado"] == estado


def test_discordancia_cualitativa_vs_cuantitativa():
    res = evaluar_valvulopatias({"GRADO_REFLUJO_MITRAL": "Severa", "EROA_MITRAL": 0.1,
                                 "VOLUMEN_REGURGITANTE_MITRAL": 20}, "Femenino")
    texto = " ".join(str(r["texto"]) + str(r["conclusion"]) for r in res)
    assert "no concuerda" in texto


def test_conclusion_global():
    assert conclusion_global_valvular([]) is None
    assert conclusion_global_valvular([{"conclusion": None}]) .startswith("Sin valvulopatías significativas")
    assert conclusion_global_valvular(evaluar_valvulopatias({"EROA_MITRAL": 0.45})) is None


# ---------------- PDF ----------------
def _texto_pdf(datos: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in pdfplumber.open(io.BytesIO(datos)).pages)


@pytest.fixture
def estudio_y_paciente():
    est = SimpleNamespace(
        fecha_estudio=date(2026, 11, 5), tipo_estudio="Ecocardiograma", medico="Dr. Prueba",
        diagnostico="HTA", motivo="Control", fecha_creacion=None, procedencia="Policlínico",
        asc_valor=1.85, imc=26.1, ritmo="Sinusal", fcia=72, pas=130, pad=80, peso=75, talla=170,
        observaciones="Sin observaciones.\n\n[HALLAZGOS]:\nx\n\n[CONCLUSIONES]:\ny",
    )
    pac = SimpleNamespace(rut="14.111.222-3", nombres="Juan", apellido_paterno="Prueba", apellido_materno="Uno",
                          sexo="Masculino", fecha_nacimiento=date(1960, 5, 1))
    return est, pac


def _mediciones(valores):
    from utils import catalogos
    vs = catalogos.variables_por_codigo()
    out = []
    for cod, val in valores.items():
        m = SimpleNamespace(codigo_variable=cod, valor_num=float(val) if not isinstance(val, str) else None,
                            valor_entero=None, valor_texto=val if isinstance(val, str) else None)
        m.valor = val
        out.append((m, vs[cod]))
    return out


def test_pdf_generado_con_conclusiones(estudio_y_paciente):
    est, pac = estudio_y_paciente
    datos = generar_pdf_desde_historial(est, pac, _mediciones({"FEVI": 35, "PSAP": 60, "EROA_MITRAL": 0.45}))
    assert datos[:5] == b"%PDF-"
    texto = " ".join(_texto_pdf(datos).split())
    assert "14.111.222-3" in texto
    assert "Conclusiones" in texto
    assert "Insuficiencia mitral probablemente severa" in texto   # un solo criterio cuantitativo
    assert "FEVI de 35%" in texto


def test_pdf_con_imagen(estudio_y_paciente):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (200, 120), "gray").save(buf, format="PNG")
    est, pac = estudio_y_paciente
    datos = generar_pdf_desde_historial(est, pac, _mediciones({"FEVI": 60}), imagenes=[buf.getvalue()])
    assert datos[:5] == b"%PDF-"
    assert len(pdfplumber.open(io.BytesIO(datos)).pages[-1].images) >= 1


def test_pantalla_y_pdf_usan_el_mismo_motor(estudio_y_paciente):
    """Lo que la pantalla muestra como conclusiones aparece igual en el PDF."""
    est, pac = estudio_y_paciente
    valores = {"FEVI": 35, "PSAP": 60, "DIAMETRO_VD_BASAL": 48}
    _, conclusiones = informe_a_texto_agrupado(construir_informe_automatico(valores, "Masculino", ritmo="Sinusal"))
    texto_pdf = " ".join(_texto_pdf(generar_pdf_desde_historial(est, pac, _mediciones(valores))).split())
    for linea in conclusiones.splitlines():
        if linea.strip():
            assert linea.split(". ", 1)[-1][:35] in texto_pdf


# ---------------- Formato del PDF (revisión con el caso E publicado) ----------------
def test_pdf_lista_todas_las_mediciones_ingresadas(estudio_y_paciente):
    """Antes una lista fija ocultaba 34 de 97 variables (p. ej. el strain longitudinal global)."""
    from utils import catalogos
    est, pac = estudio_y_paciente
    todas = {v.codigo: (25 if v.tipo == "numero" else (v.opciones or "x;").split(";")[0].strip() or "x")
             for v in catalogos.variables() if v.tipo in ("numero", "categoria")}
    texto = " ".join(_texto_pdf(generar_pdf_desde_historial(est, pac, _mediciones(todas))).split())
    faltan = [v.nombre for v in catalogos.variables() if v.codigo in todas and f"{v.nombre.strip()}:" not in texto]
    assert not faltan, faltan


def test_pdf_cabecera_completa_y_sin_unidades_falsas(estudio_y_paciente):
    est, pac = estudio_y_paciente
    texto = " ".join(_texto_pdf(generar_pdf_desde_historial(
        est, pac, _mediciones({"GROSOR_PARIETAL_RELATIVO": 0.26, "GRADO_REFLUJO_AORTICO": "Severa"}))).split())
    for dato in ("Talla 170 cm", "Peso 75 kg", "SC 1,85 m²", "IMC 26,1 kg/m²", "PA 130/80 mmHg", "FC 72 lpm"):
        assert dato in texto, dato
    assert "Adimensional" not in texto and "Cualitativ" not in texto


def test_pdf_aviso_al_pie_y_conclusiones_juntas(estudio_y_paciente):
    est, pac = estudio_y_paciente
    from tests.datos.casos_publicados import CASOS
    for caso in CASOS:
        datos = generar_pdf_desde_historial(est, pac, _mediciones(caso["v"]))
        paginas = [p.extract_text() or "" for p in pdfplumber.open(io.BytesIO(datos)).pages]
        assert all("Debe ser revisado y validado por el médico responsable" in p for p in paginas)
        assert all(f"Página {i}" in p for i, p in enumerate(paginas, 1))
        con_conclusiones = [p for p in paginas if "Conclusiones" in p]
        assert len(con_conclusiones) == 1
        resto = con_conclusiones[0].split("Conclusiones", 1)[1]
        n = len([l for l in resto.splitlines() if l[:2].rstrip(".").isdigit()])
        assert n >= 1                                   # todas las conclusiones en esa misma hoja
        assert not any(p.lstrip()[:2].rstrip(".").isdigit() for p in paginas[paginas.index(con_conclusiones[0]) + 1:])
