"""
Motor del informe automático (utils/pdf_informe.py).

Parte 1: 28 casos límite (bordes de cortes, sexo, formatos de entrada).
Parte 2: las 7 decisiones clínicas basadas en guías ASE (VD, FEVI por sexo,
presión de llenado ASE 2025, IM secundaria, ASC Mosteller, volumen latido).
"""
import pytest

from utils.pdf_informe import (
    _calcular_sc, _normalizar_codigo as N, construir_informe_automatico as motor,
    evaluar_funcion_diastolica, informe_a_texto, interpretar_fevi,
)

CASOS = []


def caso(nombre, vals, sexo=None, ritmo=None, fc=None, debe=(), no_debe=()):
    CASOS.append(pytest.param(vals, sexo, ritmo, fc, debe, no_debe, id=nombre))


caso("vacío", {}, debe=(), no_debe=("Hipertrofia","Dilatación","normal"))
caso("solo FEVI", {"FEVI":"60"}, debe=("FEVI de 60%",))
caso("sin sexo: masa no se gradúa", {"MASA_VI_INDEXADA":"130","GROSOR_PARIETAL_RELATIVO":"0.5"}, debe=("Remodelado concéntrico",), no_debe=("Hipertrofia",))
caso("mujer masa 100 leve concéntrica", {"MASA_VI_INDEXADA":"100","GROSOR_PARIETAL_RELATIVO":"0.45"}, sexo="Femenino", debe=("Hipertrofia concéntrica leve",))
caso("hombre masa 100 normal + GPR alto", {"MASA_VI_INDEXADA":"100","GROSOR_PARIETAL_RELATIVO":"0.45"}, sexo="Masculino", debe=("Remodelado concéntrico",), no_debe=("Hipertrofia",))
caso("límite exacto masa H 115", {"MASA_VI_INDEXADA":"115","GROSOR_PARIETAL_RELATIVO":"0.42"}, sexo="Masculino", no_debe=("Hipertrofia","Remodelado"))
caso("límite masa H 115.01", {"MASA_VI_INDEXADA":"115.01","GROSOR_PARIETAL_RELATIVO":"0.40"}, sexo="Masculino", debe=("Hipertrofia excéntrica leve",))
caso("dilatación por diámetro (sin VFDi) mujer 58", {"DIAMETRO_VI_DIASTOLICO":"58"}, sexo="Femenino", debe=("Dilatación moderada del ventrículo izquierdo",))
caso("VFDi prima sobre diámetro", {"DIAMETRO_VI_DIASTOLICO":"70","VOLUMEN_FIN_DIASTOLE_VI_INDEXADO":"60"}, sexo="Masculino", no_debe=("Dilatación",))
caso("GLS sin signo 15 con FEVI 60", {"STRAIN_LONGITUDINAL_GLOBAL_VI":"15","FEVI":"60"}, debe=("subclínica","-15,0"))
caso("GLS -17 limítrofe", {"STRAIN_LONGITUDINAL_GLOBAL_VI":"-17","FEVI":"60"}, debe=("limítrofe",), no_debe=("subclínica",))
caso("GLS reducido con FEVI baja: sin 'subclínica'", {"STRAIN_LONGITUDINAL_GLOBAL_VI":"-8","FEVI":"30"}, debe=("reducido",), no_debe=("subclínica",))
caso("coma decimal en strings", {"FEVI":"57,5","PSAP":"40,5"}, debe=("FEVI de 58%",))
caso("VD límite 41 no dilatado", {"DIAMETRO_VD_BASAL":"41","DIAMETRO_VD_MEDIO":"35"}, no_debe=("Dilatación del ventrículo derecho",))
caso("VD medio 36 dilatado", {"DIAMETRO_VD_MEDIO":"36"}, debe=("Dilatación del ventrículo derecho",))
caso("acoplamiento calculado de TAPSE/PSAP", {"TAPSE":"15","PSAP":"60"}, debe=("Desacoplamiento","0,25"))
caso("acoplamiento con PSAP 0 no se calcula", {"TAPSE":"15","PSAP":"0"}, no_debe=("Desacoplamiento","Acoplamiento"))
caso("ritmo sinusal sin conclusión", {"FEVI":"60"}, ritmo="Sinusal", fc="70", no_debe=("Examen realizado",), debe=("Ritmo durante el examen: sinusal",))
caso("marcapaso a conclusiones", {"FEVI":"60"}, ritmo="Marcapaso", fc=None, debe=("Examen realizado en marcapaso",))
caso("FC texto inválido", {"FEVI":"60"}, ritmo="Fibrilación auricular", fc="abc", debe=("fibrilación auricular",), no_debe=("FC abc",))
caso("derrame severo + taponamiento", {"MAGNITUD_DERRAME_PERICARDICO":"25","GRADO_DERRAME_PERICARDICO":"Severo","TAPONAMIENTO_CARDIACO":"Sí"}, debe=("severo",))
caso("estenosis mitral severa", {"AREA_MITRAL":"0.9","GRADIENTE_MEDIO_MITRAL":"12","SCORE_WILKINS":"7"}, debe=("stenosis mitral",))
caso("insuficiencia aórtica severa", {"GRADO_REFLUJO_AORTICO":"Severa","VENA_CONTRACTA_AORTICA":"7","TIEMPO_HEMIPRESION_AORTICO":"180","EROA_AORTICO":"0.35"}, debe=("nsuficiencia aórtica severa",))
caso("prótesis aórtica mecánica", {"PROTESIS_AORTICA":"Mecánica","VELOCIDAD_PICO_AORTICA":"3.2","GRADIENTE_MEDIO_AORTICO":"22"}, debe=("rótesis",))
caso("HTP severa", {"PSAP":"85","VELOCIDAD_MAXIMA_IT":"4.4"}, debe=("85 mmHg",))
caso("aorta 52 alerta", {"AORTA_ASCENDENTE":"52"}, debe=("ascendente",))
caso("valor con texto basura", {"FEVI":"abc","TAPSE":"--"}, no_debe=("FEVI de",))
caso("sexo en minúscula 'f'", {"MASA_VI_INDEXADA":"100","GROSOR_PARIETAL_RELATIVO":"0.45"}, sexo="f", debe=("Hipertrofia concéntrica leve",))


@pytest.mark.parametrize("vals, sexo, ritmo, fc, debe, no_debe", CASOS)
def test_casos_limite(vals, sexo, ritmo, fc, debe, no_debe):
    h, c = informe_a_texto(motor({N(k): v for k, v in vals.items()}, sexo, ritmo=ritmo, fc=fc))
    texto = h + "\n" + c
    for d in debe:
        assert d in texto, f"falta «{d}»"
    for d in no_debe:
        assert d not in texto, f"sobra «{d}»"


# ----------------------------------------------------------------
# Decisiones clínicas (ASE 2015 / 2017 / 2025)
# ----------------------------------------------------------------
def textos(r):
    return " | ".join(h.texto for h in r.hallazgos), " | ".join(c.texto for c in r.conclusiones)


def d(v, ritmo="Sinusal", **kw):
    return evaluar_funcion_diastolica(v, ritmo, **kw)


def test_decision_1_vd_basal_mayor_41():
    h, c = textos(motor({"DIAMETRO_VD_BASAL": 41}, "Masculino"))
    _check("VD basal 41 no dilatado", "Dilatación del ventrículo derecho" not in c and "dilatado" not in c.lower(), c)
    h, c = textos(motor({"DIAMETRO_VD_BASAL": 42}, "Masculino"))
    _check("VD basal 42 dilatado", "dilat" in (h + c).lower(), h)


def test_decision_2_fevi_por_sexo():
    _check("FEVI 53 hombre conservada", interpretar_fevi(53, "Masculino")["estado"] == "conservada")
    _check("FEVI 53 mujer leve", interpretar_fevi(53, "Femenino")["estado"] == "levemente_reducida")
    _check("FEVI 53 sexo desconocido leve", interpretar_fevi(53, None)["estado"] == "levemente_reducida")
    _check("FEVI 52 hombre conservada", interpretar_fevi(52, "M")["estado"] == "conservada")
    _check("FEVI 41 leve", interpretar_fevi(41, "M")["estado"] == "levemente_reducida")
    _check("FEVI 40 moderada", interpretar_fevi(40, "F")["estado"] == "moderadamente_reducida")
    _check("FEVI 29 severa", interpretar_fevi(29, "F")["estado"] == "severamente_reducida")
    _check("FEVI 76 mujer hiperdinámica", "hiperdin" in interpretar_fevi(76, "F")["hallazgo"])
    h, c = textos(motor({"FEVI": 53, "STRAIN_LONGITUDINAL_GLOBAL_VI": -14}, "Femenino"))
    _check("GLS subclínico no se dice si FEVI 53 en mujer", "subclínica" not in c, c)
    h, c = textos(motor({"FEVI": 53, "STRAIN_LONGITUDINAL_GLOBAL_VI": -14}, "Masculino"))
    _check("GLS subclínico sí con FEVI 53 en hombre", "subclínica" in c, c)


def test_decision_3_presion_de_llenado_ase_2025():
    def d(v, ritmo="Sinusal", **kw):
        return evaluar_funcion_diastolica(v, ritmo, **kw)

    normal = {"ONDA_E_MITRAL": 0.8, "RELACION_E_A_MITRAL": 1.3, "E_PRIMA_SEPTAL": 9, "E_PRIMA_LATERAL": 12,
              "RELACION_E_E_PRIMA": 7.6, "VELOCIDAD_MAXIMA_IT": 2.2}
    _check("diast normal", d(normal)["estado"] == "normal")
    g1 = {"ONDA_E_MITRAL": 0.5, "RELACION_E_A_MITRAL": 0.6, "E_PRIMA_SEPTAL": 5, "E_PRIMA_LATERAL": 7,
          "RELACION_E_E_PRIMA": 8.3, "VELOCIDAD_MAXIMA_IT": 2.3}
    _check("diast grado I", d(g1)["estado"] == "grado_1")
    g2 = {"ONDA_E_MITRAL": 1.0, "RELACION_E_A_MITRAL": 1.4, "E_PRIMA_SEPTAL": 5, "E_PRIMA_LATERAL": 6,
          "RELACION_E_E_PRIMA": 18, "PSAP": 45}
    r = d(g2)
    _check("diast 3/3 elevada grado II", r["estado"] == "elevada" and "grado II" in r["conclusion"], r)
    g3 = dict(g2, RELACION_E_A_MITRAL=2.5)
    _check("diast grado III", "grado III" in d(g3)["conclusion"])
    solo_ee = {"ONDA_E_MITRAL": 1.0, "RELACION_E_A_MITRAL": 1.2, "E_PRIMA_SEPTAL": 7, "E_PRIMA_LATERAL": 8,
               "RELACION_E_E_PRIMA": 15, "VELOCIDAD_MAXIMA_IT": 2.4}
    _check("solo E/e' sin adicionales: indeterminada", d(solo_ee)["estado"] == "indeterminada")
    _check("solo E/e' + VAI 40: elevada", d(dict(solo_ee, VOLUMEN_AI=40))["estado"] == "elevada")
    _check("solo E/e' + LARS 30 y VAI 28: normal", d(dict(solo_ee, STRAIN_AI_LASR=30, VOLUMEN_AI=28))["estado"] == "normal")
    _check("E/e' 14 aislado ya no basta para 'elevada'",
          d({"RELACION_E_E_PRIMA": 15, "E_PRIMA_SEPTAL": 8, "E_PRIMA_LATERAL": 10, "PSAP": 25})["estado"] != "elevada")
    _check("un solo parámetro: indeterminada", d({"RELACION_E_E_PRIMA": 16})["estado"] == "indeterminada")
    fa = {"ONDA_E_MITRAL": 1.1, "E_PRIMA_SEPTAL": 8, "PSAP": 45, "TIEMPO_DESACELERACION_MITRAL": 140}
    _check("FA 4 criterios: elevada", d(fa, "Fibrilación auricular")["estado"] == "elevada")
    _check("FA 1 criterio: normal",
          d({"ONDA_E_MITRAL": 0.7, "E_PRIMA_SEPTAL": 8, "PSAP": 40, "TIEMPO_DESACELERACION_MITRAL": 200},
            "Fibrilación auricular")["estado"] == "normal")
    h, c = textos(motor(dict(g2, AREA_MITRAL=1.2, GRADIENTE_MEDIO_MITRAL=9), "Femenino", ritmo="Sinusal"))
    _check("estenosis mitral: no aplicable", "no aplicable (estenosis mitral)" in h and "presiones de llenado" not in c, h)
    h, c = textos(motor(dict(g2, PROTESIS_MITRAL="Mecánica"), "Femenino", ritmo="Sinusal"))
    _check("prótesis mitral: no aplicable", "no aplicable (prótesis" in h, h)
    h, c = textos(motor(dict(g2), "Femenino", ritmo="Flutter auricular"))
    _check("flutter: no aplicable", "no aplicable (flutter" in h, h)


def test_decision_4_im_secundaria_escala_ase_2017():
    h, c = textos(motor({"EROA_MITRAL": 0.32, "VOLUMEN_REGURGITANTE_MITRAL": 48}, "Masculino"))
    _check("IM EROA 0,32: nota de IM secundaria", "IM secundaria" in h, h)


def test_decision_6_asc_mosteller():
    _check("ASC Mosteller 70 kg 170 cm = 1,82", round(_calcular_sc(170, 70), 2) == 1.82)


def test_decision_7_volumen_latido_por_ambos_metodos():
    base = {"VOLUMEN_FIN_DIASTOLE_VI": 180, "VOLUMEN_FIN_SISTOLE_VI": 80, "DIAMETRO_TSVI": 20, "VTI_TSVI": 18}
    h, c = textos(motor(dict(base, VOLUMEN_REGURGITANTE_MITRAL=60, EROA_MITRAL=0.45), "M", asc=1.8))
    _check("VL volumétrico y Doppler informados", "volumétrico (VFD − VFS) 100 mL" in h and "Doppler (TSVI × VTI) 57 mL" in h, h)
    _check("diferencia explicada por regurgitación", "volumen regurgitante" in h, h)
    h, c = textos(motor(base, "M", asc=1.8))
    _check("diferencia sin regurgitación: revisar TSVI", "revisar la medición del TSVI" in h, h)
    _check("bajo flujo Doppler <35 mL/m² en conclusión", "bajo flujo" in c, c)
    h, c = textos(motor({"VOLUMEN_LATIDO": 70}, "M"))
    _check("VL ingresado sin datos para calcular se muestra", "Volumen latido: 70 mL" in h, h)


def _check(nombre, cond, extra=""):
    assert cond, f"{nombre}: {extra}"


def test_decision_5_onda_e_tricuspidea_en_m_s():
    from utils import catalogos
    assert catalogos.variables_por_codigo()["ONDA_E_TRICUSPIDEA"].unidad == "m/s"


def test_asc_mosteller_y_valores_invalidos():
    assert round(_calcular_sc(170, 70), 2) == 1.82
    assert _calcular_sc(None, 70) is None
    assert _calcular_sc("abc", 70) is None
