# utils/pdf_informe.py
# ============================================================
# MOTOR DE INFORME ECOCARDIOGRÁFICO
# ============================================================
# Diseño:
#   mediciones -> normalización -> interpretación -> integración
#   -> hallazgos -> conclusiones priorizadas -> PDF
#
# Compatible con la llamada existente:
#   generar_pdf_desde_historial(estudio, paciente, mediciones_estudio)
#
# IMPORTANTE:
# - No considera que un dato ausente sea normal.
# - No genera frases por variables que no fueron ingresadas.
# - No usa una única variable para diagnosticar cuando existen
#   parámetros complementarios.
# - Hallazgos y conclusiones utilizan la MISMA interpretación.
# ============================================================

from __future__ import annotations

import io
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from utils.valvulopatias import evaluar_valvulopatias, conclusion_global_valvular
except ImportError:  # ejecución fuera del paquete utils
    from valvulopatias import evaluar_valvulopatias, conclusion_global_valvular

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    Image as RLImage,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

EPS = 1e-9

# Prioridad clínica:
# 1 = mayor prioridad.
PRIORIDADES = {
    "emergencia": 1,
    "aorta": 2,
    "pericardio": 3,
    "funcion_vi": 4,
    "funcion_vd": 5,
    "valvula_aortica": 6,
    "valvula_mitral": 7,
    "valvula_tricuspide": 8,
    "valvula_pulmonar": 8,
    "presion_pulmonar": 8,
    "auriculas": 9,
    "otros": 10,
}


# ============================================================
# DATACLASS
# ============================================================

@dataclass
class Hallazgo:
    texto: str
    prioridad: int = 10
    clave: str = ""
    conclusion: bool = False
    categoria: str = "otros"


# Orden y títulos de las secciones del bloque DESCRIPCIÓN / HALLAZGOS,
# agrupando cada hallazgo según el sistema/estructura a la que pertenece
# (mismo criterio visual que un informe ecocardiográfico convencional:
# Aorta, Aurículas, Ventrículos, Válvula Aórtica, Válvula Mitral, Válvula
# Tricúspide, Válvula Pulmonar, Pericardio - Pleura).
CATEGORIAS_HALLAZGOS: List[Tuple[str, str]] = [
    ("aorta", "Aorta"),
    ("auriculas", "Aurículas y septum interatrial"),
    ("ventriculos", "Ventrículos"),
    ("valvula_aortica", "Válvula aórtica"),
    ("valvula_mitral", "Válvula mitral"),
    ("valvula_tricuspide", "Válvula tricúspide"),
    ("valvula_pulmonar", "Válvula pulmonar"),
    ("pericardio", "Pericardio - pleura"),
    ("otros", "Otros hallazgos"),
]


@dataclass
class ResultadoInterpretacion:
    hallazgos: List[Hallazgo] = field(default_factory=list)
    conclusiones: List[Hallazgo] = field(default_factory=list)
    alertas: List[str] = field(default_factory=list)


# ============================================================
# UTILIDADES GENERALES
# ============================================================

def _normalizar_codigo(texto: Any) -> str:
    """Normaliza códigos para tolerar diferencias de acentos, espacios y formato."""
    if texto is None:
        return ""

    s = str(texto).strip().upper()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Z0-9]+", "_", s)
    return s.strip("_")


def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return str(valor).strip()


def _to_float(valor: Any) -> Optional[float]:
    if valor is None:
        return None

    if isinstance(valor, bool):
        return None

    if isinstance(valor, (int, float)):
        try:
            if math.isfinite(float(valor)):
                return float(valor)
        except Exception:
            return None
        return None

    s = str(valor).strip()
    if not s:
        return None

    s = s.replace("−", "-").replace(",", ".")

    # Elimina unidades si accidentalmente llegaron junto al valor.
    s = re.sub(r"[^0-9eE+\-\.]", "", s)

    try:
        n = float(s)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def _fmt(valor: Optional[float], decimales: int = 1) -> str:
    if valor is None:
        return ""
    return f"{valor:.{decimales}f}".replace(".", ",")


def _agregar_unico(
    lista: List[Hallazgo],
    texto: str,
    prioridad: int,
    clave: str,
    categoria: str = "otros",
):
    texto = _texto(texto)
    if not texto:
        return

    if any(h.clave == clave for h in lista):
        return

    lista.append(Hallazgo(texto=texto, prioridad=prioridad, clave=clave, categoria=categoria))


# ============================================================
# NORMALIZACIÓN DE INPUTS
# ============================================================

def _extraer_mediciones(mediciones_estudio: Any) -> Dict[str, Any]:
    """
    Convierte:
        [(medicion, variable), ...]
    en:
        {codigo_variable_normalizado: valor}
    """

    valores: Dict[str, Any] = {}

    if not mediciones_estudio:
        return valores

    for item in mediciones_estudio:
        try:
            medicion, variable = item
        except (TypeError, ValueError):
            continue

        codigo = getattr(medicion, "codigo_variable", None)
        if not codigo:
            codigo = getattr(variable, "codigo", None)

        codigo_norm = _normalizar_codigo(codigo)
        if not codigo_norm:
            continue

        valor_entero = getattr(medicion, "valor_entero", None)
        valor_num = getattr(medicion, "valor_num", None)
        valor_texto = getattr(medicion, "valor_texto", None)

        if valor_entero is not None:
            valores[codigo_norm] = int(valor_entero)
        elif valor_num is not None:
            valores[codigo_norm] = valor_num
        elif valor_texto is not None and str(valor_texto).strip():
            valores[codigo_norm] = valor_texto

    return valores


def _alias(valores: Dict[str, Any], *codigos: str) -> Any:
    """Obtiene el primer código que realmente contiene un valor."""
    for codigo in codigos:
        c = _normalizar_codigo(codigo)
        if c in valores:
            valor = valores[c]
            if valor is not None and str(valor).strip() != "":
                return valor
    return None


def _num(valores: Dict[str, Any], *codigos: str) -> Optional[float]:
    return _to_float(_alias(valores, *codigos))


def _cat(valores: Dict[str, Any], *codigos: str) -> Optional[str]:
    valor = _alias(valores, *codigos)
    if valor is None:
        return None
    return _texto(valor)


# ============================================================
# INTERPRETACIÓN DE FEVI
# ============================================================

def interpretar_fevi(fevi: Optional[float]) -> Optional[Dict[str, str]]:
    if fevi is None:
        return None

    # Se utiliza una única clasificación para Hallazgos y Conclusiones.
    if fevi >= 55:
        return {
            "estado": "conservada",
            "hallazgo": f"Fracción de eyección del ventrículo izquierdo conservada, estimada por 2D en {_fmt(fevi, 0)}%.",
            "conclusion": f"Función sistólica global del ventrículo izquierdo conservada, con FEVI de {_fmt(fevi, 0)}%.",
        }

    if fevi >= 50:
        return {
            "estado": "levemente_reducida",
            "hallazgo": f"Fracción de eyección del ventrículo izquierdo levemente reducida, estimada por 2D en {_fmt(fevi, 0)}%.",
            "conclusion": f"Función sistólica global del ventrículo izquierdo levemente reducida, con FEVI de {_fmt(fevi, 0)}%.",
        }

    if fevi >= 40:
        return {
            "estado": "moderadamente_reducida",
            "hallazgo": f"Fracción de eyección del ventrículo izquierdo moderadamente reducida, estimada por 2D en {_fmt(fevi, 0)}%.",
            "conclusion": f"Disfunción sistólica global del ventrículo izquierdo de grado moderado, con FEVI de {_fmt(fevi, 0)}%.",
        }

    return {
        "estado": "reducida",
        "hallazgo": f"Fracción de eyección del ventrículo izquierdo reducida, estimada por 2D en {_fmt(fevi, 0)}%.",
        "conclusion": f"Disfunción sistólica global del ventrículo izquierdo, con FEVI de {_fmt(fevi, 0)}%.",
    }


# ============================================================
# FUNCIÓN DEL VD
# ============================================================

def interpretar_tapse(tapse: Optional[float], s_prime: Optional[float] = None) -> Optional[Dict[str, str]]:
    if tapse is None and s_prime is None:
        return None

    # Se evita llamar "disminuido" a 16 mm automáticamente.
    if tapse is not None:
        if tapse >= 17:
            estado_tapse = "normal"
        elif tapse >= 15:
            estado_tapse = "limítrofe"
        else:
            estado_tapse = "disminuido"
    else:
        estado_tapse = ""

    if s_prime is not None:
        if s_prime >= 9.5:
            estado_s = "normal"
        elif s_prime >= 8:
            estado_s = "limítrofe"
        else:
            estado_s = "disminuido"
    else:
        estado_s = ""

    if estado_tapse == "disminuido" or estado_s == "disminuido":
        estado = "disminuida"
        texto = "Disminución de la función sistólica longitudinal del ventrículo derecho"
    elif estado_tapse == "limítrofe" or estado_s == "limítrofe":
        estado = "limítrofe"
        texto = "Función sistólica longitudinal del ventrículo derecho en rango limítrofe"
    else:
        estado = "conservada"
        texto = "Función sistólica longitudinal del ventrículo derecho conservada"

    valores = []
    if tapse is not None:
        valores.append(f"TAPSE {_fmt(tapse, 0)} mm")
    if s_prime is not None:
        valores.append(f"S' {_fmt(s_prime, 1)} cm/s")

    sufijo = f" ({'; '.join(valores)})" if valores else ""

    return {
        "estado": estado,
        "hallazgo": texto + sufijo + ".",
        "conclusion": texto + sufijo + ".",
    }


# ============================================================
# AURÍCULA IZQUIERDA
# ============================================================

def interpretar_ai(vol_indexado: Optional[float]) -> Optional[str]:
    if vol_indexado is None:
        return None

    if vol_indexado <= 34:
        return "normal"
    if vol_indexado <= 41:
        return "levemente_dilatada"
    if vol_indexado <= 48:
        return "moderadamente_dilatada"
    return "severamente_dilatada"


# ============================================================
# PSAP
# ============================================================

def interpretar_psap(psap: Optional[float]) -> Optional[Dict[str, str]]:
    if psap is None:
        return None

    # No se etiqueta automáticamente como "hipertensión pulmonar".
    # Se habla de PSAP estimada y de grado de elevación.
    if psap <= 35:
        estado = "no_elevada"
        texto = "PSAP estimada dentro de rango no elevado"
    elif psap <= 45:
        estado = "limítrofe_elevada"
        texto = "PSAP estimada levemente elevada"
    elif psap <= 60:
        estado = "elevada"
        texto = "PSAP estimada elevada"
    else:
        estado = "marcadamente_elevada"
        texto = "PSAP estimada marcadamente elevada"

    return {
        "estado": estado,
        "texto": f"{texto}, {_fmt(psap, 0)} mmHg.",
    }


# ============================================================
# ESTENOSIS AÓRTICA
# ============================================================

def interpretar_estenosis_aortica(
    vmax: Optional[float],
    gradiente: Optional[float],
    ava: Optional[float],
    ava_index: Optional[float],
    ivd: Optional[float],
    vti_tsvl: Optional[float] = None,
    vti_ao: Optional[float] = None,
    vs_index: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Evaluación multiparamétrica de estenosis aórtica.

    No etiqueta gravedad con un único parámetro cuando existe discordancia.
    Los criterios de EA grave de alto gradiente son Vmax >=4 m/s, gradiente
    medio >=40 mmHg y AVA <=1,0 cm² (o AVAi <=0,6 cm²/m²).
    """
    presentes = [v for v in (vmax, gradiente, ava, ava_index, ivd) if v is not None]
    if not presentes:
        return None

    severos = 0
    moderados = 0
    leves = 0
    no_significativos = 0

    if vmax is not None:
        if vmax >= 4.0: severos += 1
        elif vmax >= 3.0: moderados += 1
        elif vmax >= 2.0: leves += 1
        else: no_significativos += 1
    if gradiente is not None:
        if gradiente >= 40: severos += 1
        elif gradiente >= 20: moderados += 1
        else: no_significativos += 1
    if ava is not None:
        if ava <= 1.0: severos += 1
        elif ava <= 1.5: moderados += 1
        else: no_significativos += 1
    if ava_index is not None:
        if ava_index <= 0.60: severos += 1
        elif ava_index <= 0.85: moderados += 1
        else: no_significativos += 1
    if ivd is not None:
        if ivd <= 0.25: severos += 1
        elif ivd <= 0.50: moderados += 1
        else: no_significativos += 1

    alto_gradiente_severo = (
        (vmax is not None and vmax >= 4.0)
        or (gradiente is not None and gradiente >= 40)
    ) and (ava is not None and ava <= 1.0)

    if alto_gradiente_severo:
        return {
            "estado": "severa",
            "texto": "Parámetros ecocardiográficos compatibles con estenosis aórtica severa de alto gradiente.",
            "conclusion": "Estenosis aórtica severa según evaluación multiparamétrica (Vmax/gradiente y área valvular).",
            "discordante": False,
        }

    # Área severamente reducida con gradiente bajo: requiere contexto de flujo y FEVI.
    if ava is not None and ava <= 1.0 and (gradiente is None or gradiente < 40):
        flujo = f", con volumen sistólico indexado de {_fmt(vs_index, 0)} mL/m²" if vs_index is not None else ""
        return {
            "estado": "discordante",
            "texto": "Área valvular aórtica en rango severo con gradiente no severo; hallazgos discordantes" + flujo + ". Se requiere correlación con flujo, FEVI y revisión de las mediciones.",
            "conclusion": "Estenosis aórtica con parámetros discordantes; no establecer severidad definitiva solo con estos datos.",
            "discordante": True,
        }

    if moderados >= 2 and (vmax is None or vmax >= 3.0 or gradiente is None or gradiente >= 20):
        return {
            "estado": "moderada",
            "texto": "Parámetros compatibles con estenosis aórtica moderada.",
            "conclusion": "Estenosis aórtica moderada según los parámetros disponibles.",
            "discordante": False,
        }

    if leves >= 1 and severos == 0 and moderados <= 1:
        return {
            "estado": "leve",
            "texto": "Parámetros compatibles con estenosis aórtica leve.",
            "conclusion": "Estenosis aórtica leve según los parámetros disponibles.",
            "discordante": False,
        }

    if (vmax is not None and vmax < 2.0 and (gradiente is None or gradiente < 20)
            and (ava is None or ava > 1.5) and (ava_index is None or ava_index > 0.85)):
        return {
            "estado": "sin_estenosis_significativa",
            "texto": "Sin evidencia ecocardiográfica de estenosis aórtica significativa según los parámetros disponibles.",
            "conclusion": "Sin evidencia de estenosis aórtica significativa según los parámetros disponibles.",
            "discordante": False,
        }

    return {
        "estado": "no_concluyente",
        "texto": "Parámetros de estenosis aórtica insuficientes o discordantes para establecer una severidad única.",
        "conclusion": "Parámetros aórticos no concluyentes para establecer la severidad de una posible estenosis aórtica.",
        "discordante": True,
    }

# ============================================================
# INSUFICIENCIA AÓRTICA
# ============================================================

def interpretar_insuficiencia_aortica(
    reflujo: Optional[str],
    vc: Optional[float],
    eroa: Optional[float],
    thp: Optional[float],
    volumen: Optional[float] = None,
    fraccion: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Evaluación integrada de insuficiencia aórtica.

    No se establece gravedad definitiva por un único dato. Los parámetros
    cuantitativos se interpretan en conjunto y, cuando son discordantes,
    se informa explícitamente la discordancia.
    """
    obs = []
    niveles = []

    if reflujo:
        r = _normalizar_codigo(reflujo).lower()
        if any(x in r for x in ("sin", "ausente", "no")):
            obs.append("cualitativo_ausente")
        elif any(x in r for x in ("severo", "severa", "grave")):
            niveles.append(("cualitativo", 3))
        elif "moderad" in r:
            niveles.append(("cualitativo", 2))
        elif "leve" in r:
            niveles.append(("cualitativo", 1))

    # Umbrales ecocardiográficos de apoyo; la interpretación final es integrada.
    if vc is not None and vc > 0:
        niveles.append(("vena contracta", 3 if vc >= 6 else 2 if vc >= 3 else 1))

    if eroa is not None and eroa > 0:
        niveles.append(("EROA", 3 if eroa >= 0.30 else 2 if eroa >= 0.10 else 1))

    if volumen is not None and volumen > 0:
        niveles.append(("volumen regurgitante", 3 if volumen >= 60 else 2 if volumen >= 30 else 1))

    if fraccion is not None and fraccion > 0:
        niveles.append(("fracción regurgitante", 3 if fraccion >= 50 else 2 if fraccion >= 30 else 1))

    if thp is not None and thp > 0:
        # PHT <200 ms apoya IA severa; >500 ms hace improbable IA importante.
        niveles.append(("PHT", 3 if thp < 200 else 2 if thp < 300 else 1 if thp >= 500 else 0))

    cuant = [(n, v) for n, v in niveles if v in (1, 2, 3)]
    if not cuant:
        if "cualitativo_ausente" in obs:
            return {"estado": "ausente", "texto": "Sin evidencia cualitativa de insuficiencia aórtica significativa.", "conclusion": None}
        return None

    severas = [n for n, v in cuant if v == 3]
    moderadas = [n for n, v in cuant if v == 2]
    leves = [n for n, v in cuant if v == 1]

    # Una IA severa debe tener concordancia cuantitativa suficiente.
    if len(severas) >= 2:
        estado = "severa"
    elif len(severas) == 1 and len(cuant) >= 3 and len(moderadas) == 0:
        estado = "probablemente severa"
    elif len(moderadas) >= 2 and not severas:
        estado = "moderada"
    elif len(leves) >= 2 and not moderadas and not severas:
        estado = "leve"
    elif severas and moderadas:
        return {
            "estado": "discordante",
            "texto": "Parámetros de insuficiencia aórtica discordantes: existen criterios que apuntan a mayor gravedad y otros no concordantes. Integrar cuantificación, contexto hemodinámico y remodelado ventricular.",
            "conclusion": "Insuficiencia aórtica con parámetros discordantes; correlacionar antes de establecer la severidad definitiva.",
            "discordante": True,
        }
    else:
        return {
            "estado": "no_concluyente",
            "texto": "Datos insuficientes para establecer con seguridad la severidad de la insuficiencia aórtica; se requiere integración multiparamétrica.",
            "conclusion": "Insuficiencia aórtica: severidad no concluyente con los parámetros disponibles.",
            "discordante": True,
        }

    return {
        "estado": estado,
        "texto": f"Parámetros compatibles con insuficiencia aórtica {estado}, según la evaluación integrada disponible.",
        "conclusion": f"Insuficiencia aórtica {estado} según los parámetros disponibles.",
        "discordante": False,
    }

def interpretar_estenosis_mitral(
    area: Optional[float],
    gradiente: Optional[float],
    pht: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Evaluación integrada de estenosis mitral.

    El área mitral es el parámetro anatómico principal. El gradiente depende
    de frecuencia cardíaca y flujo, por lo que no se usa aisladamente para
    declarar severidad.
    """
    if area is None and gradiente is None and pht is None:
        return None

    criterios = []
    if area is not None and area > 0:
        if area <= 1.0:
            criterios.append(("área", 3))
        elif area <= 1.5:
            criterios.append(("área", 2))
        else:
            criterios.append(("área", 1))

    if gradiente is not None and gradiente >= 0:
        if gradiente >= 10:
            criterios.append(("gradiente", 3))
        elif gradiente > 5:
            criterios.append(("gradiente", 2))
        else:
            criterios.append(("gradiente", 1))

    if pht is not None and pht > 0:
        # PHT >150 ms apoya MVA <1.5 cm², pero tiene limitaciones.
        if pht >= 220:
            criterios.append(("PHT", 3))
        elif pht > 150:
            criterios.append(("PHT", 2))
        else:
            criterios.append(("PHT", 1))

    if area is not None and area > 1.5 and (gradiente is None or gradiente <= 5):
        return {"estado": "no_significativa", "texto": "Sin evidencia de estenosis mitral clínicamente significativa según los parámetros disponibles.", "conclusion": "Sin evidencia de estenosis mitral significativa según los parámetros disponibles.", "discordante": False}

    sev = sum(v == 3 for _, v in criterios)
    mod = sum(v == 2 for _, v in criterios)

    if area is not None and area <= 1.5:
        if area <= 1.0 and sev >= 2:
            estado = "severa"
        elif area <= 1.0 and len(criterios) == 1:
            return {"estado": "probablemente_severa", "texto": "Área mitral en rango muy reducido, pero faltan parámetros concordantes para establecer severidad definitiva.", "conclusion": "Estenosis mitral probablemente severa; integrar con gradiente, frecuencia cardíaca y morfología.", "discordante": True}
        elif area <= 1.5 and (mod >= 1 or sev >= 1):
            estado = "moderada"
        else:
            estado = "significativa"
    elif sev >= 2:
        estado = "severa"
    elif mod >= 1:
        return {"estado": "sugestiva", "texto": "Hallazgos hemodinámicos sugestivos de estenosis mitral; el gradiente debe interpretarse según frecuencia cardíaca y flujo.", "conclusion": "Estenosis mitral sugestiva; correlacionar con área valvular y condiciones hemodinámicas.", "discordante": True}
    else:
        estado = "no_concluyente"

    return {
        "estado": estado,
        "texto": f"Parámetros compatibles con estenosis mitral {estado}.",
        "conclusion": f"Estenosis mitral {estado} según los parámetros disponibles.",
        "discordante": estado == "no_concluyente",
    }
# ============================================================
# INSUFICIENCIA MITRAL
# ============================================================

def interpretar_insuficiencia_mitral(
    cualitativa: Optional[str],
    vc: Optional[float],
    eroa: Optional[float],
    volumen: Optional[float],
    fraccion: Optional[float],
) -> Optional[Dict[str, Any]]:
    """Evaluación multiparamétrica de insuficiencia mitral.

    Integra parámetros cualitativos y cuantitativos. No transforma
    automáticamente un único parámetro intermedio en una categoría definitiva.
    """
    cual = None
    if cualitativa:
        r = _normalizar_codigo(cualitativa).lower()
        if any(x in r for x in ("sin", "ausente", "no")):
            cual = 0
        elif any(x in r for x in ("severo", "severa", "grave")):
            cual = 3
        elif "moderad" in r:
            cual = 2
        elif "leve" in r:
            cual = 1

    criterios = []
    if vc is not None and vc > 0:
        criterios.append(("vena contracta", 3 if vc >= 7 else 2 if vc > 3 else 1))

    if eroa is not None and eroa > 0:
        criterios.append(("EROA", 3 if eroa >= 0.40 else 2 if eroa >= 0.20 else 1))

    if volumen is not None and volumen > 0:
        criterios.append(("volumen regurgitante", 3 if volumen >= 60 else 2 if volumen >= 30 else 1))

    if fraccion is not None and fraccion > 0:
        criterios.append(("fracción regurgitante", 3 if fraccion >= 50 else 2 if fraccion >= 30 else 1))

    if cual is not None:
        if cual == 0 and not criterios:
            return {"estado": "ausente", "texto": "Sin evidencia cualitativa de insuficiencia mitral significativa.", "conclusion": None}
        if cual > 0:
            criterios.append(("evaluación cualitativa", cual))

    if not criterios:
        return None

    sev = sum(v == 3 for _, v in criterios)
    mod = sum(v == 2 for _, v in criterios)
    leve = sum(v == 1 for _, v in criterios)

    # Concordancia cuantitativa fuerte.
    cuant = [v for n, v in criterios if n != "evaluación cualitativa"]
    if sum(v == 3 for v in cuant) >= 2:
        estado = "severa"
    elif len(cuant) >= 2 and sum(v == 2 for v in cuant) >= 2 and sev == 0:
        estado = "moderada"
    elif len(cuant) == 1 and cuant[0] == 3:
        return {"estado": "probablemente_severa", "texto": "Un parámetro cuantitativo está en rango severo, pero falta concordancia multiparamétrica.", "conclusion": "Insuficiencia mitral probablemente severa; integrar los restantes parámetros y el mecanismo de la regurgitación.", "discordante": True}
    elif mod >= 1 and sev == 0:
        estado = "moderada" if mod >= 2 or cual == 2 else "leve-moderada"
    elif leve >= 2 and sev == 0 and mod == 0:
        estado = "leve"
    elif sev and mod:
        return {"estado": "discordante", "texto": "Parámetros de insuficiencia mitral discordantes; integrar EROA, volumen, fracción, vena contracta y mecanismo de la lesión.", "conclusion": "Insuficiencia mitral con parámetros discordantes; correlacionar antes de establecer severidad definitiva.", "discordante": True}
    else:
        return {"estado": "no_concluyente", "texto": "Datos insuficientes para establecer con seguridad la severidad de la insuficiencia mitral.", "conclusion": "Insuficiencia mitral: severidad no concluyente con los parámetros disponibles.", "discordante": True}

    return {"estado": estado, "texto": f"Parámetros compatibles con insuficiencia mitral {estado}.", "conclusion": f"Insuficiencia mitral {estado} según los parámetros disponibles.", "discordante": False}

def interpretar_insuficiencia_tricuspidea(
    cualitativa: Optional[str],
    vc: Optional[float],
) -> Optional[Dict[str, Any]]:
    """Evaluación integrada disponible para insuficiencia tricuspídea.

    En el formulario actual se dispone principalmente de evaluación cualitativa
    y vena contracta; por ello no se simula una cuantificación completa cuando
    faltan PISA/EROA, volumen, flujo venoso hepático u otros criterios.
    """
    cual = None
    if cualitativa:
        r = _normalizar_codigo(cualitativa).lower()
        if any(x in r for x in ("sin", "ausente", "no")):
            cual = 0
        elif any(x in r for x in ("severo", "severa", "grave")):
            cual = 3
        elif "moderad" in r:
            cual = 2
        elif "leve" in r:
            cual = 1

    if cual is None and vc is None:
        return None
    if cual == 0 and vc is None:
        return {"estado": "ausente", "texto": "Sin evidencia cualitativa de insuficiencia tricuspídea significativa.", "conclusion": None}

    vc_nivel = None
    if vc is not None and vc > 0:
        vc_nivel = 3 if vc >= 7 else 2 if vc >= 3 else 1

    if cual == 3 and vc_nivel == 3:
        estado = "severa"
        texto = "Insuficiencia tricuspídea severa: evaluación cualitativa y vena contracta concordantes."
    elif cual == 2 and vc_nivel == 2:
        estado = "moderada"
        texto = "Insuficiencia tricuspídea moderada: parámetros disponibles concordantes."
    elif cual == 1 and (vc_nivel is None or vc_nivel == 1):
        estado = "leve"
        texto = "Insuficiencia tricuspídea leve según los parámetros disponibles."
    elif vc_nivel == 3 or cual == 3:
        estado = "probablemente_severa"
        texto = "Hallazgos sugestivos de insuficiencia tricuspídea severa, pero falta concordancia multiparamétrica."
    else:
        return {"estado": "no_concluyente", "texto": "Parámetros de insuficiencia tricuspídea insuficientes o discordantes para establecer severidad definitiva.", "conclusion": "Insuficiencia tricuspídea: severidad no concluyente; integrar parámetros cualitativos y cuantitativos disponibles.", "discordante": True}

    return {"estado": estado, "texto": texto, "conclusion": f"Insuficiencia tricuspídea {estado.replace('_', ' ')} según los parámetros disponibles.", "discordante": estado == "probablemente_severa"}

def interpretar_estenosis_tricuspidea(
    gradiente: Optional[float],
    area: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Evaluación prudente de estenosis tricuspídea.

    La TS adquirida es infrecuente y el gradiente depende de flujo y frecuencia
    cardíaca. No se declara 'severa' con un único dato sin corroboración.
    """
    if gradiente is None and area is None:
        return None

    criterios = []
    if area is not None and area > 0:
        criterios.append(("área", 3 if area <= 1.0 else 2 if area <= 1.5 else 1))

    if gradiente is not None and gradiente >= 0:
        criterios.append(("gradiente", 3 if gradiente >= 5 else 1))

    if area is not None and area > 1.5 and (gradiente is None or gradiente < 5):
        return {"estado": "no_significativa", "texto": "Sin evidencia de estenosis tricuspídea significativa según los parámetros disponibles.", "conclusion": "Sin evidencia de estenosis tricuspídea significativa según los parámetros disponibles.", "discordante": False}

    if area is not None and area <= 1.0 and gradiente is not None and gradiente >= 5:
        return {"estado": "severa", "texto": "Área tricuspídea muy reducida con gradiente medio elevado; hallazgos concordantes con estenosis tricuspídea severa.", "conclusion": "Estenosis tricuspídea severa según los parámetros disponibles.", "discordante": False}

    if area is not None and area <= 1.5 and gradiente is not None and gradiente >= 5:
        return {"estado": "significativa", "texto": "Área tricuspídea reducida y gradiente medio elevado; hallazgos compatibles con estenosis tricuspídea significativa.", "conclusion": "Estenosis tricuspídea significativa según los parámetros disponibles.", "discordante": False}

    if gradiente is not None and gradiente >= 5:
        return {"estado": "sugestiva", "texto": "Gradiente medio tricuspídeo elevado; interpretar según frecuencia cardíaca y flujo y corroborar con anatomía/área.", "conclusion": "Hallazgos sugestivos de estenosis tricuspídea; requiere correlación multiparamétrica.", "discordante": True}

    return {"estado": "no_concluyente", "texto": "Datos insuficientes para establecer la severidad de una posible estenosis tricuspídea.", "conclusion": "Estenosis tricuspídea: severidad no concluyente con los parámetros disponibles.", "discordante": True}

def interpretar_estenosis_pulmonar(
    vmax: Optional[float],
    gradiente: Optional[float],
) -> Optional[Dict[str, Any]]:
    """Evaluación integrada de estenosis pulmonar por velocidad y gradiente."""
    if vmax is None and gradiente is None:
        return None

    niveles = []
    if vmax is not None and vmax >= 0:
        niveles.append(("Vmáx", 3 if vmax >= 4.0 else 2 if vmax >= 3.0 else 1 if vmax >= 2.0 else 0))
    if gradiente is not None and gradiente >= 0:
        niveles.append(("gradiente", 3 if gradiente >= 64 else 2 if gradiente >= 36 else 1 if gradiente >= 16 else 0))

    positivos = [(n,v) for n,v in niveles if v > 0]
    if not positivos:
        return {"estado": "no_significativa", "texto": "Sin evidencia de estenosis pulmonar significativa según velocidad y gradiente disponibles.", "conclusion": "Sin evidencia de estenosis pulmonar significativa según los parámetros disponibles.", "discordante": False}

    severos = [n for n,v in positivos if v == 3]
    moderados = [n for n,v in positivos if v == 2]
    leves = [n for n,v in positivos if v == 1]

    if len(positivos) == 2 and len(severos) == 2:
        estado = "severa"
    elif len(positivos) == 2 and len(moderados) == 2:
        estado = "moderada"
    elif len(positivos) == 2 and len(leves) == 2:
        estado = "leve"
    elif len(positivos) == 2:
        return {"estado": "discordante", "texto": "Velocidad y gradiente pulmonar no son concordantes para una única categoría de severidad.", "conclusion": "Estenosis pulmonar con parámetros discordantes; correlacionar velocidad, gradiente y contexto hemodinámico.", "discordante": True}
    else:
        estado = {1:"leve",2:"moderada",3:"severa"}[positivos[0][1]]
        return {"estado": f"probablemente_{estado}", "texto": f"Un parámetro sugiere estenosis pulmonar {estado}; falta corroboración multiparamétrica.", "conclusion": f"Estenosis pulmonar probablemente {estado}; correlacionar con el otro parámetro.", "discordante": True}

    return {"estado": estado, "texto": f"Velocidad y gradiente compatibles con estenosis pulmonar {estado}.", "conclusion": f"Estenosis pulmonar {estado} según los parámetros disponibles.", "discordante": False}

def interpretar_insuficiencia_pulmonar(cualitativa: Optional[str]) -> Optional[Dict[str, Any]]:
    """Interpretación conservadora de IP con el dato que actualmente captura el formulario.

    El formulario actual no aporta un conjunto cuantitativo suficiente para una
    clasificación multiparamétrica de IP. Por eso se conserva el dato cualitativo
    sin presentarlo como una cuantificación más precisa de la que realmente existe.
    """
    if not cualitativa:
        return None
    r = _normalizar_codigo(cualitativa).lower()
    if any(x in r for x in ("sin", "ausente", "no")):
        return {"estado": "ausente", "texto": "Sin evidencia cualitativa de insuficiencia pulmonar significativa.", "conclusion": None}
    if any(x in r for x in ("severo", "severa", "grave")):
        estado = "severa"
    elif "moderad" in r:
        estado = "moderada"
    elif "leve" in r:
        estado = "leve"
    else:
        return None

    return {
        "estado": estado,
        "texto": f"Insuficiencia pulmonar {estado} según la evaluación cualitativa disponible.",
        "conclusion": f"Insuficiencia pulmonar {estado} según el dato cualitativo disponible; la severidad debe integrarse con hallazgos morfológicos y hemodinámicos.",
        "discordante": False,
    }
# ============================================================
# DERRAME PERICÁRDICO
# ============================================================

def clasificar_derrame(mm: Optional[float]) -> Optional[str]:
    if mm is None:
        return None
    if mm <= 0:
        return "sin derrame"
    if mm <= 10:
        return "leve"
    if mm <= 20:
        return "moderado"
    return "severo"


def _texto_bool(valor: Optional[str]) -> Optional[bool]:
    if valor is None:
        return None

    s = _normalizar_codigo(valor)

    if s in {"SI", "S", "YES", "TRUE", "PRESENTE", "POSITIVO", "POSITIVE"}:
        return True

    if s in {"NO", "N", "FALSE", "AUSENTE", "NEGATIVO", "NEGATIVE"}:
        return False

    return None


def evaluar_taponamiento(valores: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    derrame = _num(valores, "MAGNITUD_DERRAME_PERICARDICO", "MAGNITUD_DERRAME", "DERRAME_PERICARDICO")
    if derrame is None:
        return None

    taponamiento_input = _cat(
        valores,
        "TAPONAMIENTO",
        "TAPONAMIENTO_CARDIACO",
    )
    taponamiento_bool = _texto_bool(taponamiento_input)

    vci = _num(valores, "VENA_CAVA_INFERIOR", "VCI")
    colapso_vci = _num(valores, "PORCENTAJE_COLAPSO_VCI", "PTJE_VCI", "COLAPSO_VCI")
    tapse = _num(valores, "TAPSE", "TAPSE_VD")
    psap = _num(valores, "PSAP")

    # Si el usuario ingresó explícitamente un diagnóstico cualitativo,
    # se puede usar, pero se mantienen los hallazgos objetivos.
    if taponamiento_bool is True:
        return {
            "estado": "presente",
            "texto": "Derrame pericárdico con compromiso hemodinámico compatible con taponamiento cardíaco.",
            "conclusion": "Taponamiento cardíaco en contexto de derrame pericárdico, según los datos ingresados.",
        }

    if taponamiento_bool is False:
        return {
            "estado": "ausente",
            "texto": None,
            "conclusion": None,
        }

    # No se diagnostica taponamiento solo por tamaño.
    criterios = 0

    if derrame > 20:
        criterios += 1

    if vci is not None and vci >= 21:
        criterios += 1

    if colapso_vci is not None and colapso_vci < 50:
        criterios += 1

    if tapse is not None and tapse < 15:
        criterios += 1

    # Solo genera sospecha, no diagnóstico definitivo.
    if criterios >= 3:
        return {
            "estado": "sospecha",
            "texto": "Derrame pericárdico severo asociado a varios hallazgos de compromiso hemodinámico; correlacionar para descartar taponamiento cardíaco.",
            "conclusion": "Derrame pericárdico severo con signos ecocardiográficos sugestivos de compromiso hemodinámico; correlacionar para descartar taponamiento cardíaco.",
        }

    return {
        "estado": "no_demostrado",
        "texto": None,
        "conclusion": None,
    }


# ============================================================
# AORTA
# ============================================================

def interpretar_aorta(
    raiz: Optional[float],
    ascendente: Optional[float],
    arco: Optional[float],
) -> Optional[Dict[str, str]]:
    datos = []

    # Umbrales deliberadamente conservadores:
    # el diagnóstico final depende de ASC, sexo, edad y contexto.
    if raiz is not None:
        if raiz >= 45:
            datos.append(f"raíz aórtica marcadamente dilatada ({_fmt(raiz, 0)} mm)")
        elif raiz >= 40:
            datos.append(f"raíz aórtica dilatada ({_fmt(raiz, 0)} mm)")

    if ascendente is not None:
        if ascendente >= 50:
            datos.append(f"aorta ascendente marcadamente dilatada ({_fmt(ascendente, 0)} mm)")
        elif ascendente >= 40:
            datos.append(f"aorta ascendente dilatada ({_fmt(ascendente, 0)} mm)")

    if arco is not None and arco >= 40:
        datos.append(f"arco aórtico aumentado ({_fmt(arco, 0)} mm)")

    if not datos:
        return None

    return {
        "estado": "dilatada",
        "texto": "Aorta: " + "; ".join(datos) + ".",
        "conclusion": "Dilatación de la aorta: " + "; ".join(datos) + ".",
    }


# ============================================================
# PERICARDITIS CONSTRICTIVA
# ============================================================

def evaluar_constriccion_pericardica(valores: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    pericardio = _cat(valores, "PERICARDIO", "DESCRIPCION_PERICARDIO")
    derrame = _num(valores, "MAGNITUD_DERRAME_PERICARDICO", "MAGNITUD_DERRAME")
    e_lateral = _num(valores, "E_PRIMA_LATERAL", "E_LATERAL", "E_PRIMA_LAT")
    e_septal = _num(valores, "E_PRIMA_SEPTAL", "E_SEPTAL", "E_PRIMA_SEP")
    vci = _num(valores, "VENA_CAVA_INFERIOR", "VCI")
    tapse = _num(valores, "TAPSE", "TAPSE_VD")
    onda_e = _num(valores, "ONDA_E", "ONDA_E_MITRAL", "E_MITRAL")

    texto_pericardio = (pericardio or "").lower()

    explicitamente_constrictivo = any(
        termino in texto_pericardio
        for termino in (
            "constrict",
            "engrosado",
            "rigido",
            "rígido",
        )
    )

    criterios = 0

    if explicitamente_constrictivo:
        criterios += 2

    if e_septal is not None and e_septal >= 8:
        criterios += 1

    if e_lateral is not None and e_lateral >= 8:
        criterios += 1

    if vci is not None and vci >= 21:
        criterios += 1

    if tapse is not None and tapse >= 15:
        # En constricción la función longitudinal puede estar relativamente preservada.
        criterios += 1

    # No se diagnostica constricción solo con estos datos.
    if explicitamente_constrictivo or criterios >= 4:
        return {
            "estado": "sugestivo",
            "texto": "Hallazgos compatibles con fisiología pericárdica constrictiva; correlacionar con Doppler respiratorio y contexto clínico.",
            "conclusion": "Hallazgos sugestivos de fisiología pericárdica constrictiva; se recomienda correlación con parámetros Doppler y clínicos.",
        }

    return None


# ============================================================
# CONSTRUCCIÓN DEL INFORME
# ============================================================

def construir_informe_automatico(
    valores: Dict[str, Any],
    sexo_paciente: Optional[str] = None,
) -> ResultadoInterpretacion:

    resultado = ResultadoInterpretacion()

    # --------------------------------------------------------
    # VI / FEVI
    # --------------------------------------------------------
    fevi = _num(valores, "FEVI", "FRACCION_EYECCION")
    gpr = _num(valores, "GPR", "GPR_VI")
    masa_idx = _num(valores, "MASA_VI_INDEXADA", "MASA_VI_ASC")
    dvi_diast = _num(valores, "DIMENSION_DIASTOLICA_VI", "DVI_DIAST", "DVID")
    dvi_sist = _num(valores, "DIMENSION_SISTOLICA_VI", "DVI_SIST", "DVIS")
    strain_vi = _num(valores, "STRAIN_LONGITUDINAL", "STRAIN_VI")
    acortamiento = _num(valores, "FRACC_ACORTAMIENTO", "PORC_ACORTAMIENTO")

    vi_partes = []
    if dvi_diast is not None:
        vi_partes.append(f"diámetro diastólico de {_fmt(dvi_diast, 0)} mm")
    if dvi_sist is not None:
        vi_partes.append(f"diámetro sistólico de {_fmt(dvi_sist, 0)} mm")
    if masa_idx is not None:
        vi_partes.append(f"masa VI indexada de {_fmt(masa_idx, 0)} g/m²")
    if gpr is not None:
        vi_partes.append(f"GPR de {_fmt(gpr, 2)}")

    if vi_partes:
        _agregar_unico(
            resultado.hallazgos,
            "Ventrículo izquierdo: " + "; ".join(vi_partes) + ".",
            PRIORIDADES["funcion_vi"],
            "vi_descripcion",
            categoria="ventriculos",
        )

    fevi_resultado = interpretar_fevi(fevi)
    if fevi_resultado:
        _agregar_unico(
            resultado.hallazgos,
            fevi_resultado["hallazgo"],
            PRIORIDADES["funcion_vi"],
            "fevi",
            categoria="ventriculos",
        )
        _agregar_unico(
            resultado.conclusiones,
            fevi_resultado["conclusion"],
            PRIORIDADES["funcion_vi"],
            "fevi",
        )

    if acortamiento is not None:
        _agregar_unico(
            resultado.hallazgos,
            f"Fracción de acortamiento de {_fmt(acortamiento, 0)}%.",
            PRIORIDADES["otros"],
            "acortamiento",
            categoria="ventriculos",
        )

    if strain_vi is not None:
        _agregar_unico(
            resultado.hallazgos,
            f"Strain longitudinal del ventrículo izquierdo de {_fmt(strain_vi, 1)}%.",
            PRIORIDADES["funcion_vi"],
            "strain_vi",
            categoria="ventriculos",
        )

    # --------------------------------------------------------
    # DIÁSTOLE
    # --------------------------------------------------------
    onda_e = _num(valores, "ONDA_E", "ONDA_E_MITRAL", "E_MITRAL")
    onda_a = _num(valores, "ONDA_A", "ONDA_A_MITRAL", "A_MITRAL")
    e_a = _num(valores, "E_A", "RELACION_E_A")
    e_lat = _num(valores, "E_PRIMA_LATERAL", "E_LATERAL", "E_PRIMA_LAT")
    e_sep = _num(valores, "E_PRIMA_SEPTAL", "E_SEPTAL", "E_PRIMA_SEP")
    e_e = _num(valores, "E_E_PRIMA", "E_EPRIMA", "E_E")
    td = _num(valores, "TIEMPO_DECELERACION", "T_D", "TD")

    diastolica = []
    if onda_e is not None:
        diastolica.append(f"onda E de {_fmt(onda_e, 2)} m/s")
    if onda_a is not None:
        diastolica.append(f"onda A de {_fmt(onda_a, 2)} m/s")
    if e_a is not None:
        diastolica.append(f"relación E/A de {_fmt(e_a, 2)}")
    if td is not None:
        diastolica.append(f"tiempo de desaceleración de {_fmt(td, 0)} ms")
    if e_lat is not None:
        diastolica.append(f"e' lateral de {_fmt(e_lat, 1)} cm/s")
    if e_sep is not None:
        diastolica.append(f"e' septal de {_fmt(e_sep, 1)} cm/s")
    if e_e is not None:
        diastolica.append(f"E/e' de {_fmt(e_e, 1)}")

    if diastolica:
        _agregar_unico(
            resultado.hallazgos,
            "Función diastólica: " + "; ".join(diastolica) + ".",
            PRIORIDADES["otros"],
            "diastole",
            categoria="ventriculos",
        )

    if e_e is not None:
        if e_e > 14:
            _agregar_unico(
                resultado.conclusiones,
                "Hallazgos compatibles con aumento de las presiones de llenado del ventrículo izquierdo.",
                PRIORIDADES["otros"],
                "presiones_llenado",
            )
        elif e_e >= 8:
            _agregar_unico(
                resultado.hallazgos,
                "E/e' en rango intermedio; interpretar en conjunto con el resto de los parámetros de función diastólica.",
                PRIORIDADES["otros"],
                "ee_intermedio",
            categoria="ventriculos",
            )

    # --------------------------------------------------------
    # VD
    # --------------------------------------------------------
    tapse = _num(valores, "TAPSE", "TAPSE_VD")
    s_prime = _num(valores, "ONDA_S", "ONDA_S_PRIMA", "S_PRIMA")
    basal_vd = _num(valores, "DIAMETRO_BASAL_VD", "DIAM_BASAL_VD")
    medio_vd = _num(valores, "DIAMETRO_MEDIO_VD", "DIAM_MEDIO_VD")

    vd_partes = []
    if basal_vd is not None:
        vd_partes.append(f"diámetro basal de {_fmt(basal_vd, 0)} mm")
    if medio_vd is not None:
        vd_partes.append(f"diámetro medio de {_fmt(medio_vd, 0)} mm")
    if tapse is not None:
        vd_partes.append(f"TAPSE de {_fmt(tapse, 0)} mm")
    if s_prime is not None:
        vd_partes.append(f"onda S' de {_fmt(s_prime, 1)} cm/s")

    if vd_partes:
        _agregar_unico(
            resultado.hallazgos,
            "Ventrículo derecho: " + "; ".join(vd_partes) + ".",
            PRIORIDADES["funcion_vd"],
            "vd",
            categoria="ventriculos",
        )

    vd_resultado = interpretar_tapse(tapse, s_prime)
    if vd_resultado:
        prioridad = PRIORIDADES["emergencia"] if vd_resultado["estado"] == "disminuida" else PRIORIDADES["funcion_vd"]
        _agregar_unico(
            resultado.conclusiones,
            vd_resultado["conclusion"],
            prioridad,
            "funcion_vd",
        )

    # --------------------------------------------------------
    # AURÍCULA IZQUIERDA
    # --------------------------------------------------------
    vol_ai = _num(valores, "VOLUMEN_AI", "VOLUMEN_INDEXADO_AI", "VOL_INDEXADO_AI")
    estado_ai = interpretar_ai(vol_ai)

    if vol_ai is not None:
        if estado_ai == "normal":
            texto_ai = f"Aurícula izquierda de tamaño conservado, con volumen indexado de {_fmt(vol_ai, 0)} mL/m²."
        elif estado_ai == "levemente_dilatada":
            texto_ai = f"Aurícula izquierda levemente dilatada, con volumen indexado de {_fmt(vol_ai, 0)} mL/m²."
        elif estado_ai == "moderadamente_dilatada":
            texto_ai = f"Aurícula izquierda moderadamente dilatada, con volumen indexado de {_fmt(vol_ai, 0)} mL/m²."
        else:
            texto_ai = f"Aurícula izquierda severamente dilatada, con volumen indexado de {_fmt(vol_ai, 0)} mL/m²."

        _agregar_unico(
            resultado.hallazgos,
            texto_ai,
            PRIORIDADES["auriculas"],
            "ai",
            categoria="auriculas",
        )

        if estado_ai != "normal":
            conclusion_ai = texto_ai.replace("Aurícula izquierda ", "Dilatación ")
            # Reescritura más natural.
            conclusion_ai = (
                f"Dilatación {estado_ai.replace('_', ' ')} de la aurícula izquierda "
                f"(volumen indexado {_fmt(vol_ai, 0)} mL/m²)."
            )
            _agregar_unico(
                resultado.conclusiones,
                conclusion_ai,
                PRIORIDADES["auriculas"],
                "ai",
            )

    area_ad = _num(valores, "AREA_AD", "AREA_AURICULA_DERECHA")
    if area_ad is not None:
        _agregar_unico(
            resultado.hallazgos,
            f"Área de aurícula derecha de {_fmt(area_ad, 0)} cm².",
            PRIORIDADES["auriculas"],
            "ad",
            categoria="auriculas",
        )

    # --------------------------------------------------------
    # VALVULOPATÍAS (motor único compartido con estudios.py)
    # Ver utils/valvulopatias.py: 8 valvulopatías con criterios
    # ASE/EACVI/ESC/AHA y evaluación multiparamétrica.
    # --------------------------------------------------------
    valvulas = evaluar_valvulopatias(valores, sexo_paciente)
    valv = {r["clave"]: r for r in valvulas}

    def _agregar_valvula(clave: str) -> None:
        r = valv.get(clave)
        if not r:
            return
        prioridad = PRIORIDADES.get(r["categoria"], PRIORIDADES["otros"])
        _agregar_unico(resultado.hallazgos, r["texto"], prioridad, clave, categoria=r["categoria"])
        if r.get("conclusion"):
            prioridad_c = PRIORIDADES["emergencia"] if r["grave"] else prioridad
            _agregar_unico(resultado.conclusiones, r["conclusion"], prioridad_c, clave)

    # ---- Válvula aórtica ----
    vti_ao = _num(valores, "VTI_AORTICO", "VTI_AORTICA", "VTI_AO")
    pisa_ao = _num(valores, "PISA_AORTICO", "PISA_AORTICA")
    protesis_ao = _cat(valores, "PROTESIS_AORTICA")

    _agregar_valvula("estenosis_ao")
    _agregar_valvula("insuf_ao")
    if vti_ao is not None:
        _agregar_unico(resultado.hallazgos, f"VTI aórtica de {_fmt(vti_ao, 0)} cm.",
                       PRIORIDADES["valvula_aortica"], "vti_ao", categoria="valvula_aortica")
    if pisa_ao is not None:
        _agregar_unico(resultado.hallazgos, f"Radio PISA aórtico de {_fmt(pisa_ao, 1)} mm.",
                       PRIORIDADES["valvula_aortica"], "pisa_ao", categoria="valvula_aortica")
    if protesis_ao and _normalizar_codigo(protesis_ao) != "AUSENTE":
        _agregar_unico(resultado.hallazgos, f"Prótesis aórtica: {protesis_ao}.",
                       PRIORIDADES["valvula_aortica"], "protesis_ao", categoria="valvula_aortica")

    # ---- Válvula mitral ----
    protesis_mit = _cat(valores, "PROTESIS_MITRAL")
    _agregar_valvula("estenosis_mitral")
    _agregar_valvula("insuf_mit")
    if protesis_mit and _normalizar_codigo(protesis_mit) != "AUSENTE":
        _agregar_unico(resultado.hallazgos, f"Prótesis mitral: {protesis_mit}.",
                       PRIORIDADES["valvula_mitral"], "protesis_mit", categoria="valvula_mitral")

    # ---- Válvula tricúspide / presión pulmonar ----
    vmax_it = _num(valores, "VELOCIDAD_MAXIMA_IT", "VEL_MAX_IT", "VMAX_IT")
    gdte_it = _num(valores, "GRADIENTE_MAXIMO_IT", "GDTE_MAX_IT")
    vci = _num(valores, "DIAMETRO_VCI", "VENA_CAVA_INFERIOR", "VCI")
    ptje_vci = _num(valores, "PUNTAJE_COLAPSO_VCI", "PORCENTAJE_COLAPSO_VCI", "COLAPSO_VCI", "PTJE_VCI")
    psap = _num(valores, "PSAP")

    _agregar_valvula("estenosis_it")
    _agregar_valvula("insuf_it")

    it_partes = []
    if vmax_it is not None:
        it_partes.append(f"Vmax IT {_fmt(vmax_it, 1)} m/s")
    if gdte_it is not None:
        it_partes.append(f"gradiente máximo IT {_fmt(gdte_it, 0)} mmHg")
    if psap is not None:
        it_partes.append(f"PSAP estimada de {_fmt(psap, 0)} mmHg")
    if it_partes:
        _agregar_unico(resultado.hallazgos, "Presión pulmonar: " + "; ".join(it_partes) + ".",
                       PRIORIDADES["presion_pulmonar"], "tricuspide", categoria="valvula_tricuspide")

    if vci is not None or ptje_vci is not None:
        partes_vci = []
        if vci is not None:
            partes_vci.append(f"VCI de {_fmt(vci, 0)} mm")
        if ptje_vci is not None:
            partes_vci.append(f"colapso inspiratorio de {_fmt(ptje_vci, 0)}%")
        _agregar_unico(resultado.hallazgos, "Vena cava inferior: " + "; ".join(partes_vci) + ".",
                       PRIORIDADES["presion_pulmonar"], "vci", categoria="valvula_tricuspide")

    ep = valv.get("estenosis_pulmonar")
    hay_ep = bool(ep and ep.get("nivel") and ep["nivel"] >= 2)
    psap_resultado = interpretar_psap(psap)
    if psap_resultado and hay_ep:
        _agregar_unico(
            resultado.conclusiones,
            f"PSAP estimada de {_fmt(psap, 0)} mmHg: con estenosis pulmonar asociada refleja la presión "
            "sistólica del VD y no equivale a hipertensión pulmonar.",
            PRIORIDADES["presion_pulmonar"],
            "psap",
        )
    elif psap_resultado:
        if psap_resultado["estado"] != "no_elevada":
            _agregar_unico(
                resultado.conclusiones,
                psap_resultado["texto"] + " Se recomienda correlación con el resto de los parámetros ecocardiográficos.",
                PRIORIDADES["presion_pulmonar"],
                "psap",
            )
        else:
            _agregar_unico(resultado.hallazgos, psap_resultado["texto"], PRIORIDADES["presion_pulmonar"],
                           "psap_normal", categoria="valvula_tricuspide")

    # ---- Válvula pulmonar ----
    tap = _num(valores, "TIEMPO_ACELERACION_PULMONAR", "TAP", "TAP_MS")
    vti_tsvd = _num(valores, "VTI_TSVD")
    tronco_ap = _num(valores, "TRONCO_ARTERIA_PULMONAR")
    rvp = _num(valores, "RESISTENCIA_VASCULAR_PULMONAR", "RVP")

    _agregar_valvula("estenosis_pulmonar")
    _agregar_valvula("insuf_pulmonar")

    partes = []
    if tronco_ap is not None:
        partes.append(f"tronco de la arteria pulmonar de {_fmt(tronco_ap, 0)} mm")
    if tap is not None:
        partes.append(f"tiempo de aceleración de {_fmt(tap, 0)} ms")
    if vti_tsvd is not None:
        partes.append(f"VTI TSVD de {_fmt(vti_tsvd, 0)} cm")
    if rvp is not None:
        partes.append(f"RVP de {_fmt(rvp, 1)} UW")
    if partes:
        _agregar_unico(resultado.hallazgos, "Arteria pulmonar: " + "; ".join(partes) + ".",
                       PRIORIDADES["presion_pulmonar"], "pulmonar", categoria="valvula_pulmonar")

    global_valv = conclusion_global_valvular(valvulas)
    if global_valv:
        _agregar_unico(resultado.conclusiones, global_valv, PRIORIDADES["valvula_aortica"], "valvulas_normales")
    # --------------------------------------------------------
    # AORTA
    # --------------------------------------------------------
    raiz = _num(valores, "RAIZ_AORTICA", "RAIZ_AO")
    ascendente = _num(valores, "AORTA_ASCENDENTE", "AORTA_ASC")
    arco = _num(valores, "ARCO_AORTICO", "ARCO_AO")

    if raiz is not None or ascendente is not None or arco is not None:
        partes = []
        if raiz is not None:
            partes.append(f"raíz aórtica {_fmt(raiz, 0)} mm")
        if ascendente is not None:
            partes.append(f"aorta ascendente {_fmt(ascendente, 0)} mm")
        if arco is not None:
            partes.append(f"arco aórtico {_fmt(arco, 0)} mm")

        _agregar_unico(
            resultado.hallazgos,
            "Aorta: " + "; ".join(partes) + ".",
            PRIORIDADES["aorta"],
            "aorta_mediciones",
            categoria="aorta",
        )

    aorta_resultado = interpretar_aorta(raiz, ascendente, arco)
    if aorta_resultado:
        prioridad = PRIORIDADES["emergencia"] if (raiz is not None and raiz >= 45) or (ascendente is not None and ascendente >= 50) else PRIORIDADES["aorta"]
        _agregar_unico(
            resultado.conclusiones,
            aorta_resultado["conclusion"],
            prioridad,
            "aorta_dilatacion",
        )

    # --------------------------------------------------------
    # PERICARDIO
    # --------------------------------------------------------
    derrame = _num(valores, "MAGNITUD_DERRAME_PERICARDICO", "MAGNITUD_DERRAME")
    pericardio = _cat(valores, "PERICARDIO", "DESCRIPCION_PERICARDIO")
    tap_input = _cat(valores, "TAPONAMIENTO", "TAPONAMIENTO_CARDIACO")

    if derrame is not None:
        grado = clasificar_derrame(derrame)
        if grado == "sin derrame":
            texto = "Sin derrame pericárdico."
        else:
            texto = f"Derrame pericárdico {grado}, con magnitud máxima de {_fmt(derrame, 0)} mm."

        _agregar_unico(
            resultado.hallazgos,
            texto,
            PRIORIDADES["pericardio"],
            "derrame",
            categoria="pericardio",
        )

        if grado == "severo":
            _agregar_unico(
                resultado.conclusiones,
                texto,
                PRIORIDADES["pericardio"],
                "derrame_severo",
            )
        elif grado in ("moderado", "leve"):
            _agregar_unico(
                resultado.conclusiones,
                texto,
                PRIORIDADES["pericardio"],
                f"derrame_{grado}",
            )

    if pericardio:
        _agregar_unico(
            resultado.hallazgos,
            f"Pericardio: {pericardio}.",
            PRIORIDADES["pericardio"],
            "pericardio_texto",
            categoria="pericardio",
        )

    tap_resultado = evaluar_taponamiento(valores)
    if tap_resultado:
        if tap_resultado["texto"]:
            prioridad = PRIORIDADES["emergencia"] if tap_resultado["estado"] in ("presente", "sospecha") else PRIORIDADES["pericardio"]
            _agregar_unico(
                resultado.conclusiones,
                tap_resultado["conclusion"],
                prioridad,
                "taponamiento",
            )

    constriccion = evaluar_constriccion_pericardica(valores)
    if constriccion:
        _agregar_unico(
            resultado.conclusiones,
            constriccion["conclusion"],
            PRIORIDADES["pericardio"],
            "constriccion",
        )

    # --------------------------------------------------------
    # VOLUMEN SISTÓLICO
    # --------------------------------------------------------
    vs = _num(valores, "VOLUMEN_LATIDO", "VS")
    vs_i = _num(valores, "VOLUMEN_LATIDO_INDEXADO", "VS_INDEX")
    if vs is not None or vs_i is not None:
        partes = []
        if vs is not None:
            partes.append(f"volumen latido de {_fmt(vs, 0)} mL")
        if vs_i is not None:
            partes.append(f"volumen latido indexado de {_fmt(vs_i, 0)} mL/m²")
        _agregar_unico(
            resultado.hallazgos,
            "Volúmenes ventriculares: " + "; ".join(partes) + ".",
            PRIORIDADES["otros"],
            "volumen_latido",
            categoria="ventriculos",
        )

    # --------------------------------------------------------
    # ALERTAS
    # --------------------------------------------------------
    if raiz is not None and raiz >= 45:
        resultado.alertas.append(
            "Dilatación importante de la raíz aórtica: requiere revisión médica."
        )

    if ascendente is not None and ascendente >= 50:
        resultado.alertas.append(
            "Dilatación importante de la aorta ascendente: requiere revisión médica."
        )

    if derrame is not None and derrame > 20 and tap_resultado and tap_resultado["estado"] in ("presente", "sospecha"):
        resultado.alertas.append(
            "Derrame pericárdico severo con datos de posible compromiso hemodinámico."
        )

    # --------------------------------------------------------
    # ORDEN FINAL
    # --------------------------------------------------------
    resultado.hallazgos.sort(key=lambda h: (h.prioridad, h.texto))
    resultado.conclusiones.sort(key=lambda h: (h.prioridad, h.texto))

    return resultado


# ============================================================
# TEXTO PARA STREAMLIT
# ============================================================

def informe_a_texto(resultado: ResultadoInterpretacion) -> Tuple[str, str]:
    """
    Devuelve exactamente dos bloques:
        hallazgos
        conclusiones
    """
    hallazgos = "\n".join(h.texto for h in resultado.hallazgos)
    conclusiones = "\n".join(
        f"{i}. {h.texto}" for i, h in enumerate(resultado.conclusiones, start=1)
    )

    return hallazgos, conclusiones


def agrupar_hallazgos_por_categoria(
    resultado: ResultadoInterpretacion,
) -> List[Tuple[str, List[str]]]:
    """
    Agrupa los hallazgos según la estructura/sistema al que pertenecen
    (Aorta, Aurículas, Ventrículos, Válvula Aórtica, Válvula Mitral,
    Válvula Tricúspide, Válvula Pulmonar, Pericardio - Pleura), respetando
    el orden clínico habitual de un informe ecocardiográfico.

    Dentro de cada categoría, los hallazgos se ordenan por prioridad clínica
    (igual criterio que el resto del informe). Solo se incluyen las
    categorías que efectivamente tienen hallazgos, para no generar
    encabezados vacíos cuando no hay datos ingresados.
    """
    por_categoria: Dict[str, List[Hallazgo]] = {}
    for h in resultado.hallazgos:
        por_categoria.setdefault(h.categoria, []).append(h)

    secciones: List[Tuple[str, List[str]]] = []
    for clave_categoria, titulo in CATEGORIAS_HALLAZGOS:
        hallazgos_categoria = por_categoria.get(clave_categoria)
        if not hallazgos_categoria:
            continue
        hallazgos_categoria = sorted(hallazgos_categoria, key=lambda h: (h.prioridad, h.texto))
        secciones.append((titulo, [h.texto for h in hallazgos_categoria]))

    return secciones


# ============================================================
# MEDICIONES REGISTRADAS: ORDEN Y PRESENTACIÓN
# ============================================================

# Orden clínico del informe. Si aparece una categoría nueva en la BD,
# se incorpora al final sin perder ninguna medición.
ORDEN_CATEGORIAS_INFORME = [
    "datos generales",
    "aorta y aurículas",
    "aorta y auriculas",
    "ventrículo izquierdo",
    "ventriculo izquierdo",
    "ventrículo derecho",
    "ventriculo derecho",
    "válvula aórtica",
    "valvula aortica",
    "válvula mitral",
    "valvula mitral",
    "válvula tricuspídea",
    "valvula tricuspidea",
    "válvula pulmonar",
    "valvula pulmonar",
    "pericardio",
]


def _normalizar_categoria(valor: Any) -> str:
    if valor is None:
        return ""
    s = unicodedata.normalize("NFD", str(valor).strip().lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _indice_categoria_informe(categoria: Any) -> int:
    cat = _normalizar_categoria(categoria)
    try:
        return [
            _normalizar_categoria(x) for x in ORDEN_CATEGORIAS_INFORME
        ].index(cat)
    except ValueError:
        return len(ORDEN_CATEGORIAS_INFORME) + 1


def _formatear_valor_registrado(medicion: Any, variable: Any) -> str:
    """Formatea el valor exactamente una vez para el bloque de datos."""
    valor_entero = getattr(medicion, "valor_entero", None)
    valor_num = getattr(medicion, "valor_num", None)
    valor_texto = getattr(medicion, "valor_texto", None)

    if valor_entero is not None:
        return str(int(valor_entero))

    if valor_num is not None:
        # Conservamos precisión útil sin llenar el informe de ceros.
        try:
            n = float(valor_num)
            if n.is_integer():
                return str(int(n))
            return f"{n:.2f}".rstrip("0").rstrip(".").replace(".", ",")
        except Exception:
            return str(valor_num)

    if valor_texto is not None:
        return str(valor_texto).strip()

    return ""


def _obtener_registros_ordenados(mediciones_estudio: Any) -> List[Dict[str, Any]]:
    """
    Conserva TODAS las mediciones efectivamente ingresadas y sus metadatos.

    No filtra por diagnóstico ni por relevancia clínica: si el médico ingresó
    un dato, ese dato aparece en el bloque "Mediciones registradas".
    """
    registros = []
    if not mediciones_estudio:
        return registros

    for posicion, item in enumerate(mediciones_estudio):
        try:
            medicion, variable = item
        except (TypeError, ValueError):
            continue

        codigo = getattr(medicion, "codigo_variable", None) or getattr(variable, "codigo", None)
        nombre = getattr(variable, "nombre", None) or codigo or "Variable"
        unidad = getattr(variable, "unidad", None) or ""
        categoria = getattr(variable, "categoria", None) or "Otros"
        orden = getattr(variable, "orden", None)

        valor = _formatear_valor_registrado(medicion, variable)
        if not valor:
            continue

        try:
            orden_num = float(orden) if orden is not None else float("inf")
        except Exception:
            orden_num = float("inf")

        registros.append({
            "codigo": _normalizar_codigo(codigo),
            "nombre": str(nombre).strip(),
            "unidad": str(unidad).strip(),
            "categoria": str(categoria).strip(),
            "valor": valor,
            "categoria_idx": _indice_categoria_informe(categoria),
            "orden": orden_num,
            "posicion": posicion,
        })

    registros.sort(
        key=lambda r: (r["categoria_idx"], r["orden"], r["posicion"])
    )
    return registros


def _agrupar_registros(registros: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    grupos = []
    por_categoria = {}
    orden_grupos = []

    for registro in registros:
        clave = _normalizar_categoria(registro["categoria"]) or "otros"
        if clave not in por_categoria:
            por_categoria[clave] = []
            orden_grupos.append((registro["categoria"], clave))
        por_categoria[clave].append(registro)

    for nombre_original, clave in orden_grupos:
        grupos.append((nombre_original, por_categoria[clave]))

    return grupos


def _texto_datos(registro: Dict[str, Any]) -> str:
    unidad = registro["unidad"]
    return f"{registro['valor']} {unidad}".strip()


def _construir_tabla_mediciones(registros: List[Dict[str, Any]], styles: Dict[str, Any]) -> List[Any]:
    """
    Genera un bloque compacto de 2 pares de datos por fila.
    Así se muestran todos los inputs sin convertir el informe en una lista
    vertical interminable.
    """
    elementos = []
    if not registros:
        return elementos

    encabezado_style = ParagraphStyle(
        "GrupoDatos",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=10,
        spaceBefore=4,
        spaceAfter=3,
    )

    dato_style = ParagraphStyle(
        "DatoCompacto",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.2,
        spaceAfter=0,
    )

    for categoria, grupo in _agrupar_registros(registros):
        elementos.append(Paragraph(str(categoria), encabezado_style))

        filas = []
        for i in range(0, len(grupo), 2):
            fila = []
            pares = grupo[i:i + 2]
            for registro in pares:
                contenido = (
                    f"<b>{registro['nombre']}</b>: "
                    f"{_texto_datos(registro)}"
                )
                fila.append(Paragraph(contenido, dato_style))

            if len(pares) == 1:
                fila.append(Paragraph("", dato_style))

            filas.append(fila)

        tabla = Table(filas, colWidths=[8.0 * cm, 8.0 * cm], hAlign="LEFT")
        tabla.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LINEBELOW", (0, 0), (-1, -1), 0.2, colors.lightgrey),
        ]))
        elementos.append(tabla)
        elementos.append(Spacer(1, 3))

    return elementos


# ============================================================
# CONFIGURACIÓN DE PRESENTACIÓN DEL INFORME
# ============================================================

# Solo estas variables se imprimen en "Mediciones ecocardiográficas
# registradas". La interpretación automática sigue utilizando los datos
# disponibles para no alterar el motor clínico.
VARIABLES_VISIBLES_INFORME = {
    "RAIZ_AORTICA", "AORTA_ASCENDENTE", "ARCO_AORTICO",
    "RAIZ_AORTICA_ASC", "AORTA_ASCEND_ASC",
    "DIAMETRO_AI", "VOLUMEN_AI", "VOLUMEN_INDEXADO_AI", "VOL_INDEXADO_AI",
    "AREA_AD", "AREA_AURICULA_DERECHA", "SEPTUM", "P_POSTERIOR",
    "DIMENSION_DIASTOLICA_VI", "DVI_DIAST", "DVID",
    "DIMENSION_SISTOLICA_VI", "DVI_SIST", "DVIS",
    "FRACC_ACORTAMIENTO", "PORC_ACORTAMIENTO",
    "FEVI", "FRACCION_EYECCION", "GPR", "GPR_VI",
    "DIAMETRO_BASAL_VD", "DIAM_BASAL_VD",
    "DIAMETRO_MEDIO_VD", "DIAM_MEDIO_VD",
    "TAPSE", "TAPSE_VD", "ONDA_S", "ONDA_S_PRIMA", "S_PRIMA",
    "VENA_CAVA_INFERIOR", "VCI", "PORCENTAJE_COLAPSO_VCI",
    "PTJE_VCI", "COLAPSO_VCI",
    "ONDA_E", "ONDA_E_MITRAL", "E_MITRAL",
    "ONDA_A", "ONDA_A_MITRAL", "A_MITRAL",
    "E_A", "RELACION_E_A", "E_PRIMA_LATERAL", "E_LATERAL",
    "E_PRIMA_LAT", "E_PRIMA_SEPTAL", "E_SEPTAL", "E_PRIMA_SEP",
    "E_E_PRIMA", "E_EPRIMA", "E_E",
    "TIEMPO_DECELERACION", "T_D", "TD",
    "VELOCIDAD_PICO_AORTICA", "V_PEAK_AO", "V_MAX_AO",
    "GRADIENTE_MEDIO_AORTICO", "GRADIENTE_AORTICO",
    "VTI_AORTICA", "VTI_AO",
    "AREA_VALVULAR_AORTICA_CONTINUIDAD", "AVA_AO_EC", "AVAO_EC",
    "AREA_VALVULAR_AORTICA_INDEXADA", "AVA_AO_INDEX", "AVAO_INDEX",
    "INDICE_VELOCIDAD_DOPPLER", "IVD",
    "REFLUJO_AORTICO", "RF_AO", "VENA_CONTRACTA_AORTICA",
    "VC_AORTICA", "THP_AORTICA", "THP", "EROA_AORTICA",
    "VOLUMEN_REGURGITANTE_AORTICO", "VOLUMEN_REG_AORTICO", "VOL_REG_AO",
    "FRACCION_REGURGITANTE_AORTICA", "FRACCION_REG_AORTICA", "FR_RG_AO",
    "AREA_MITRAL", "AREA_VALVULAR_MITRAL", "AVA_MITRAL", "GRADIENTE_MEDIO_MITRAL",
    "THP_MITRAL", "PHT_MITRAL", "TIEMPO_HEMIPRESION_MITRAL", "REFLUJO_MITRAL",
    "VENA_CONTRACTA_MITRAL", "VC_MITRAL", "PISA_MITRAL",
    "EROA_MITRAL", "VOLUMEN_REGURGITANTE_MITRAL",
    "VOLUMEN_REG_MITRAL", "FRACCION_REGURGITANTE_MITRAL",
    "FR_RG_MITRAL",
    "VELOCIDAD_MAXIMA_IT", "VEL_MAX_IT", "V_MAX_IT",
    "GRADIENTE_MAXIMO_IT", "GTE_MAX_IT", "GRADIENTE_MEDIO_TRICUSPIDEO", "GRADIENTE_MEDIO_IT",
    "AREA_TRICUSPIDEA", "AREA_VALVULAR_TRICUSPIDEA", "REFLUJO_TRICUSPIDEO", "REFLUJO_TRICUSPIDE",
    "VENA_CONTRACTA_TRICUSPIDEA", "VC_TRICUSPIDEA", "PSAP",
    "PRESION_SISTOLICA_AP", "TCO_AP", "TCOAP",
    "V_MAX_PULMONAR", "VMAX_PULMONAR", "VELOCIDAD_PICO_PULMONAR",
    "GRADIENTE_MAXIMO_PULMONAR", "GRADIENTE_PULMONAR", "GDTE_PULMONAR",
    "REFLUJO_PULMONAR", "INSUFICIENCIA_PULMONAR",
    # Códigos reales del Excel de variables (válvulas)
    "GRADO_REFLUJO_AORTICO", "TIEMPO_HEMIPRESION_AORTICO", "EROA_AORTICO", "PISA_AORTICO",
    "VTI_AORTICO", "PROTESIS_AORTICA", "AREA_VALVULAR_AORTICA_ANATOMICA",
    "VOLUMEN_LATIDO_INDEXADO_AORTICO",
    "GRADO_REFLUJO_MITRAL", "PROTESIS_MITRAL", "SCORE_WILKINS",
    "GRADO_REFLUJO_TRICUSPIDEO", "PISA_TRICUSPIDEO", "DIAMETRO_VCI", "PUNTAJE_COLAPSO_VCI",
    "GRADO_REFLUJO_PULMONAR", "TRONCO_ARTERIA_PULMONAR", "TIEMPO_ACELERACION_PULMONAR",
    "VTI_TSVD", "RESISTENCIA_VASCULAR_PULMONAR",
    "MAGNITUD_DERRAME_PERICARDICO", "MAGNITUD_DERRAME",
    "DERRAME_PERICARDICO",
}

NOMBRES_VISIBLES_EXTRA = {
    "RAIZ AORTICA", "AORTA ASCENDENTE", "ARCO AORTICO",
    "DIAMETRO AI", "VOLUMEN INDEXADO AI", "VOL. INDEXADO AI",
    "AREA AD", "SEPTUM", "P. POSTERIOR",
    "DIMENSION DIAST. VI.", "DIMENSION SIST. VI.", "% ACORTAMIENTO",
    "FRAC. EYECCION", "MASA VI/ASC", "GPR",
    "DIAM. BASAL VD", "DIAM. MEDIO VD", "TAPSE", "ONDA S",
    "VENA CAVA INF.", "ONDA E", "ONDA A", "E/A", "E/E'",
    "V. MAX", "GRADIENTE MEDIO", "INSUFICIENCIA", "REFLUJO",
    "VEL. MAXIMA IT", "GDTE MAXIMA IT", "PRESION SIST. AP",
    "TCO. AP", "DERRAME PERICARDICO",
}

def _variable_de_informe_visible(registro: Dict[str, Any]) -> bool:
    codigo = _normalizar_codigo(registro.get("codigo", ""))
    nombre = _normalizar_codigo(registro.get("nombre", ""))
    visibles = {_normalizar_codigo(x) for x in VARIABLES_VISIBLES_INFORME}
    nombres = {_normalizar_codigo(x) for x in NOMBRES_VISIBLES_EXTRA}
    return codigo in visibles or nombre in nombres

def _filtrar_registros_para_informe(registros: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in registros if _variable_de_informe_visible(r)]

def _obtener_dato_paciente(obj: Any, *attrs: str, default: Any = "—") -> Any:
    valor = _get_attr(obj, *attrs, default=None)
    return default if valor is None or str(valor).strip() == "" else valor

def _calcular_sc(talla_cm: Any, peso_kg: Any) -> Optional[float]:
    talla = _to_float(talla_cm)
    peso = _to_float(peso_kg)
    if talla is None or peso is None or talla <= 0 or peso <= 0:
        return None
    return math.sqrt((talla * peso) / 3600.0)

def _formatear_fecha(valor: Any) -> str:
    if valor is None or str(valor).strip() == "":
        return "—"
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    return str(valor)

def _preparar_imagen_vertical(imagen_bytes: bytes) -> Optional[io.BytesIO]:
    """
    Normaliza una imagen recibida como bytes para incorporarla al PDF.

    La imagen se abre directamente desde memoria, sin depender de rutas ni
    nombres de archivo, por lo que el flujo es compatible con macOS, Windows
    y Linux y no depende de la codificación del sistema de archivos.

    La orientación EXIF se aplica antes de convertir la imagen. Esto corrige
    las fotografías de celulares que físicamente están guardadas en una
    orientación pero indican mediante EXIF cómo deben mostrarse.

    IMPORTANTE: no se rota una imagen solo porque sea horizontal. Una imagen
    horizontal puede ser la orientación correcta; el requisito de mostrar las
    imágenes "verticalmente" se resuelve colocándolas una debajo de otra en
    el PDF, no girando artificialmente su contenido.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None

    try:
        img = Image.open(io.BytesIO(imagen_bytes))
        img = ImageOps.exif_transpose(img)

        # Convertimos a RGB para generar un formato PDF/JPEG estable,
        # incluyendo PNG con transparencia o modos de color especiales.
        if img.mode != "RGB":
            if "A" in img.getbands():
                fondo = Image.new("RGB", img.size, "white")
                fondo.paste(img, mask=img.getchannel("A"))
                img = fondo
            else:
                img = img.convert("RGB")

        salida = io.BytesIO()
        img.save(salida, format="JPEG", quality=92, optimize=True)
        salida.seek(0)
        return salida
    except Exception:
        # Un archivo corrupto o no-imagen no debe impedir el informe.
        return None


def _agregar_imagenes_al_informe(
    story: List[Any], imagenes_bytes: Optional[Sequence[bytes]]
) -> None:
    """
    Inserta hasta 10 imágenes en una cuadrícula de 3 columnas.

    Las imágenes se procesan desde bytes y se normaliza EXIF con Pillow,
    evitando depender de rutas o de la codificación del sistema operativo.
    No se gira una imagen por ser horizontal: se respeta su orientación real.
    """
    if not imagenes_bytes:
        return

    max_por_fila = 3
    max_ancho = 5.55 * cm
    max_alto = 7.0 * cm
    celdas = []

    for datos in list(imagenes_bytes)[:10]:
        buffer_img = _preparar_imagen_vertical(datos)
        if buffer_img is None:
            continue
        try:
            rl_img = RLImage(buffer_img)
            escala = min(
                max_ancho / rl_img.imageWidth,
                max_alto / rl_img.imageHeight,
                1.0,
            )
            rl_img.drawWidth = rl_img.imageWidth * escala
            rl_img.drawHeight = rl_img.imageHeight * escala
            rl_img.hAlign = "CENTER"
            celdas.append(rl_img)
        except Exception:
            continue

    if not celdas:
        return

    for inicio in range(0, len(celdas), max_por_fila):
        fila = celdas[inicio:inicio + max_por_fila]
        while len(fila) < max_por_fila:
            fila.append("")
        tabla = Table(
            [fila],
            colWidths=[6.0 * cm] * max_por_fila,
            hAlign="CENTER",
        )
        tabla.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(tabla)
# ============================================================
# PDF
# ============================================================

def _get_attr(obj: Any, *attrs: str, default: Any = "") -> Any:
    for attr in attrs:
        if hasattr(obj, attr):
            value = getattr(obj, attr)
            if value is not None and str(value).strip() != "":
                return value
    return default


def _safe_patient_name(paciente: Any) -> str:
    nombres = _get_attr(paciente, "nombres", default="")
    ap = _get_attr(paciente, "apellido_paterno", default="")
    am = _get_attr(paciente, "apellido_materno", default="")
    return " ".join(str(x).strip() for x in (nombres, ap, am) if str(x).strip())


def generar_pdf_desde_historial(
    estudio: Any,
    paciente: Any,
    mediciones_estudio: Sequence[Tuple[Any, Any]],
    imagen_path: Optional[str] = None,
    imagenes: Optional[Sequence[bytes]] = None,
) -> bytes:
    """
    Genera el informe en cuatro bloques claramente separados:

    1. Identificación del estudio.
    2. MEDICIONES REGISTRADAS: todos los datos ingresados, ordenados y
       condensados, sin omitir ninguno.
    3. DESCRIPCIÓN / HALLAZGOS: interpretación clínica de los datos.
    4. CONCLUSIONES: síntesis priorizada.

    Las mediciones son la fuente de verdad. El texto libre almacenado en
    estudio.observaciones no se utiliza para inventar ni diagnosticar.
    """

    valores = _extraer_mediciones(mediciones_estudio)
    registros = _obtener_registros_ordenados(mediciones_estudio)
    registros = _filtrar_registros_para_informe(registros)
    sexo = _get_attr(paciente, "sexo", default=None)

    resultado = construir_informe_automatico(valores, sexo)
    _, conclusiones_texto = informe_a_texto(resultado)
    secciones_hallazgos = agrupar_hallazgos_por_categoria(resultado)

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.35 * cm,
        bottomMargin=1.35 * cm,
        title="Informe Ecocardiográfico",
        author="EcoCardioNet",
    )

    styles = getSampleStyleSheet()

    titulo = ParagraphStyle(
        "TituloEcoV2",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        alignment=TA_CENTER,
        spaceAfter=10,
    )

    subtitulo = ParagraphStyle(
        "SubtituloEcoV2",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        spaceBefore=8,
        spaceAfter=5,
    )

    normal = ParagraphStyle(
        "NormalEcoV2",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        alignment=TA_LEFT,
        spaceAfter=5,
    )

    # Encabezado de cada sección de hallazgos (p. ej. "VENTRÍCULOS",
    # "VÁLVULA MITRAL"): negrita y subrayado, igual que en el informe
    # de referencia. El subrayado se logra con la etiqueta <u> propia
    # de Paragraph de ReportLab.
    categoria_style = ParagraphStyle(
        "CategoriaHallazgoEcoV2",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=9,
        spaceBefore=6,
        spaceAfter=3,
    )

    conclusion_style = ParagraphStyle(
        "ConclusionEcoV2",
        parent=normal,
        leftIndent=8,
        firstLineIndent=-8,
        spaceAfter=4,
    )

    alerta_style = ParagraphStyle(
        "AlertaEcoV2",
        parent=normal,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    )

    story = []
    story.append(Paragraph("Informe ecocardiográfico", titulo))

    nombre = _safe_patient_name(paciente)
    rut = _obtener_dato_paciente(paciente, "rut", "RUT")
    talla = _obtener_dato_paciente(paciente, "talla", "talla_cm", "altura")
    peso = _obtener_dato_paciente(paciente, "peso", "peso_kg")
    sc = _obtener_dato_paciente(paciente, "sc", "superficie_corporal", default=None)
    if sc is None or str(sc).strip() == "":
        sc_calc = _calcular_sc(talla, peso)
        sc = f"{sc_calc:.2f}" if sc_calc is not None else "—"

    fecha_nacimiento = _obtener_dato_paciente(
        paciente, "fecha_nacimiento", "fecha_nac", "nacimiento"
    )
    edad = _obtener_dato_paciente(paciente, "edad")
    ritmo = _obtener_dato_paciente(estudio, "ritmo", default=None)
    if ritmo in (None, "—"):
        ritmo = _obtener_dato_paciente(paciente, "ritmo")
    fc = _obtener_dato_paciente(estudio, "fc", "frecuencia_cardiaca", default=None)
    if fc in (None, "—"):
        fc = _obtener_dato_paciente(paciente, "fc", "frecuencia_cardiaca")

    fecha = _formatear_fecha(
        _get_attr(estudio, "fecha_estudio", "fecha_creacion", default=None)
    )
    fecha_nacimiento = _formatear_fecha(fecha_nacimiento)
    medico = _obtener_dato_paciente(estudio, "medico")
    tipo = _obtener_dato_paciente(estudio, "tipo_estudio", default="Ecocardiograma")

    datos_paciente = [
        ["Nombre", nombre or "—", "RUT", rut],
        ["Fecha de nacimiento", fecha_nacimiento, "Edad",
         f"{edad} años" if str(edad) != "—" else "—"],
        ["Sexo", sexo or "—", "Fecha", fecha],
        ["Talla", f"{talla} cm" if str(talla) != "—" else "—",
         "Peso", f"{peso} kg" if str(peso) != "—" else "—"],
        ["SC", f"{sc} m²" if str(sc) != "—" else "—", "Ritmo", ritmo],
        ["FC", f"{fc} lpm" if str(fc) != "—" else "—", "Médico", medico],
    ]

    tabla = Table(datos_paciente, colWidths=[3.0 * cm, 5.0 * cm, 2.3 * cm, 5.7 * cm])
    tabla.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    story.append(tabla)
    story.append(Spacer(1, 8))

    # Imágenes opcionales (hasta 10), entre identificación y mediciones.
    # `imagenes` (lista de bytes) es la vía recomendada -evita rutas de
    # archivo por completo-; `imagen_path` se conserva solo por
    # compatibilidad con llamadas antiguas de una sola imagen.
    imagenes_para_informe = list(imagenes) if imagenes else None
    if imagenes_para_informe is None and imagen_path:
        try:
            with open(imagen_path, "rb") as f:
                imagenes_para_informe = [f.read()]
        except OSError:
            imagenes_para_informe = None

    _agregar_imagenes_al_informe(story, imagenes_para_informe)

    # ========================================================
    # 1. MEDICIONES SELECCIONADAS
    # ========================================================
    story.append(Paragraph("Mediciones ecocardiográficas registradas", subtitulo))

    if registros:
        story.extend(_construir_tabla_mediciones(registros, styles))
    else:
        story.append(
            Paragraph(
                "No se han ingresado mediciones ecocardiográficas.",
                normal,
            )
        )

    # ========================================================
    # 2. DESCRIPCIÓN / HALLAZGOS DESPUÉS DE TODOS LOS DATOS
    #    Organizados por sistema/estructura (Aorta, Aurículas,
    #    Ventrículos, Válvula Aórtica, Válvula Mitral, Válvula
    #    Tricúspide, Válvula Pulmonar, Pericardio - Pleura), cada uno
    #    bajo su propio subtítulo en negrita y subrayado.
    # ========================================================
    story.append(Spacer(1, 5))
    story.append(Paragraph("Descripción / Hallazgos", subtitulo))

    if secciones_hallazgos:
        for titulo_categoria, textos in secciones_hallazgos:
            story.append(Paragraph(f"<u>{titulo_categoria}</u>", categoria_style))
            for texto in textos:
                story.append(Paragraph(texto, normal))
    else:
        story.append(
            Paragraph(
                "No se han ingresado mediciones suficientes para generar hallazgos automáticos.",
                normal,
            )
        )

    # ========================================================
    # 3. CONCLUSIONES
    # ========================================================
    story.append(Spacer(1, 5))
    story.append(Paragraph("Conclusiones", subtitulo))

    if conclusiones_texto.strip():
        for linea in conclusiones_texto.splitlines():
            story.append(Paragraph(linea, conclusion_style))
    else:
        story.append(
            Paragraph(
                "No se generaron conclusiones automáticas con los datos disponibles.",
                normal,
            )
        )

    if resultado.alertas:
        story.append(Spacer(1, 7))
        story.append(Paragraph("Alerta para revisión médica", subtitulo))
        for alerta in resultado.alertas:
            story.append(Paragraph("• " + alerta, alerta_style))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Informe generado automáticamente a partir de las mediciones ingresadas. "
        "Debe ser revisado y validado por el médico responsable antes de su emisión definitiva.",
        ParagraphStyle("NotaEcoV2", parent=normal, fontSize=7.5, leading=10),
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# FUNCIÓN DE PRUEBA
# ============================================================

def analizar_mediciones_para_prueba(
    mediciones_estudio: Sequence[Tuple[Any, Any]],
    sexo_paciente: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Utilidad para probar el motor SIN generar PDF.
    """
    valores = _extraer_mediciones(mediciones_estudio)
    resultado = construir_informe_automatico(valores, sexo_paciente)

    return {
        "valores": valores,
        "hallazgos": [h.texto for h in resultado.hallazgos],
        "conclusiones": [h.texto for h in resultado.conclusiones],
        "alertas": resultado.alertas,
    }
