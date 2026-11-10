"""Ramas del motor que los demás archivos no recorren (aurículas, FA, válvulas derechas, imágenes)."""
import io
from datetime import date
from types import SimpleNamespace

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

from utils.pdf_informe import (
    construir_informe_automatico as motor, evaluar_funcion_diastolica, generar_pdf_desde_historial,
    informe_a_texto, interpretar_ai,
)
from utils.valvulopatias import evaluar_valvulopatias


def texto(valores, sexo="Masculino", **kw):
    h, c = informe_a_texto(motor(valores, sexo, **kw))
    return h + "\n" + c


@pytest.mark.parametrize("vol, estado, frase", [
    (30, "normal", "tamaño conservado"),
    (38, "levemente_dilatada", "Dilatación leve de la aurícula izquierda"),
    (45, "moderadamente_dilatada", "Dilatación moderada de la aurícula izquierda"),
    (60, "severamente_dilatada", "Dilatación severa de la aurícula izquierda"),
])
def test_auricula_izquierda(vol, estado, frase):
    assert interpretar_ai(vol) == estado
    assert frase in texto({"VOLUMEN_AI": vol})


def test_auricula_izquierda_sin_dato():
    assert interpretar_ai(None) is None


# ---------------- Presión de llenado en fibrilación auricular ----------------
FA = "Fibrilación auricular"


def test_fa_dos_criterios_con_lars_e_imc_elevada():
    v = {"ONDA_E_MITRAL": 1.1, "E_PRIMA_SEPTAL": 8, "PSAP": 30, "TIEMPO_DESACELERACION_MITRAL": 200,
         "STRAIN_AI_LASR": 12}
    assert evaluar_funcion_diastolica(v, FA, imc=33)["estado"] == "elevada"


def test_fa_dos_criterios_sin_adicionales_indeterminada():
    v = {"ONDA_E_MITRAL": 1.1, "E_PRIMA_SEPTAL": 8, "PSAP": 30, "TIEMPO_DESACELERACION_MITRAL": 200}
    r = evaluar_funcion_diastolica(v, FA)
    assert r["estado"] == "indeterminada" and r["conclusion"]


def test_fa_datos_insuficientes():
    assert evaluar_funcion_diastolica({"ONDA_E_MITRAL": 1.1}, FA)["estado"] == "indeterminada"


def test_fa_usa_it_si_falta_psap():
    v = {"ONDA_E_MITRAL": 1.1, "E_PRIMA_SEPTAL": 8, "VELOCIDAD_MAXIMA_IT": 3.2, "TIEMPO_DESACELERACION_MITRAL": 140}
    assert evaluar_funcion_diastolica(v, FA)["estado"] == "elevada"


def test_sinusal_calcula_ee_y_ea_si_faltan():
    v = {"ONDA_E_MITRAL": 1.2, "ONDA_A_MITRAL": 0.5, "E_PRIMA_SEPTAL": 5, "E_PRIMA_LATERAL": 6, "PSAP": 45}
    r = evaluar_funcion_diastolica(v, "Sinusal")
    assert r["estado"] == "elevada" and "grado III" in r["conclusion"]     # E/A 2,4


def test_sin_datos_diastolicos():
    assert evaluar_funcion_diastolica({"FEVI": 60}, "Sinusal") is None


def test_marcapaso_y_ritmo_no_sinusal_en_conclusiones():
    assert "marcapaso" in texto({"FEVI": 60}, ritmo="Marcapaso").lower()


# ---------------- Válvulas: ramas menos frecuentes ----------------
def _estado(valores, clave):
    return {r["clave"]: r for r in evaluar_valvulopatias(valores, "Femenino")}[clave]


def test_estenosis_mitral_area_severa_gradiente_bajo_es_discordante():
    r = _estado({"AREA_MITRAL": 0.9, "GRADIENTE_MEDIO_MITRAL": 3}, "estenosis_mitral")
    assert r["estado"] == "discordante"


def test_estenosis_mitral_solo_gradiente():
    assert _estado({"GRADIENTE_MEDIO_MITRAL": 12}, "estenosis_mitral")["nivel"] == 3
    assert _estado({"GRADIENTE_MEDIO_MITRAL": 3}, "estenosis_mitral")["estado"] == "no_significativa"


def test_estenosis_pulmonar_solo_gradiente():
    r = _estado({"GRADIENTE_MAXIMO_PULMONAR": 70}, "estenosis_pulmonar")
    assert r["nivel"] == 3


def test_estenosis_pulmonar_gradiente_discordante_con_velocidad():
    r = _estado({"VELOCIDAD_PICO_PULMONAR": 3.0, "GRADIENTE_MAXIMO_PULMONAR": 70}, "estenosis_pulmonar")
    assert "no concuerda" in r["texto"]


def test_protesis_sin_doppler_se_informa_como_portador():
    assert "Portador de prótesis aórtica (Mecánica)" in texto({"PROTESIS_AORTICA": "Mecánica"})


def test_plastia_mitral_no_es_portador_de_protesis():
    assert "Portador de prótesis" not in texto({"PROTESIS_MITRAL": "Plastia"})


# ---------------- PDF con imágenes en distintos formatos ----------------
@pytest.mark.parametrize("modo", ["RGBA", "L", "P"])
def test_pdf_acepta_imagenes_transparentes_y_grises(modo):
    buf = io.BytesIO()
    Image.new(modo, (120, 80)).save(buf, format="PNG")
    est = SimpleNamespace(fecha_estudio=date(2026, 1, 1), tipo_estudio="Ecocardiograma", medico="X",
                          diagnostico=None, motivo=None, fecha_creacion=None, procedencia=None, asc_valor=None,
                          imc=None, ritmo=None, fcia=None, pas=None, pad=None, observaciones="")
    pac = SimpleNamespace(rut="1-9", nombres="A", apellido_paterno="B", apellido_materno="", sexo=None,
                          fecha_nacimiento=None)
    assert generar_pdf_desde_historial(est, pac, [], imagenes=[buf.getvalue()])[:5] == b"%PDF-"


# ---------------- Callback numérico genérico ----------------
def test_on_change_numerico():
    def script():
        import streamlit as st
        from utils.validacion import on_change_numerico
        st.session_state["a"] = "12,5"
        st.session_state["b"] = "abc"
        st.session_state["r_a"] = on_change_numerico("a")
        st.session_state["r_b"] = on_change_numerico("b", valor_previo="7", nombre="Peso")

    at = AppTest.from_function(script).run()
    assert at.session_state["a"] == "12.5" and at.session_state["r_a"] == (12.5, None)
    assert at.session_state["b"] == "7"
    assert "Peso" in at.session_state["r_b"][1]
    assert at.toast and "Peso" in at.toast[0].value
