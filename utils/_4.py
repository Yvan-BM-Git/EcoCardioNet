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


def _agregar_unico(lista: List[Hallazgo], texto: str, prioridad: int, clave: str):
    texto = _texto(texto)
    if not texto:
        return

    if any(h.clave == clave for h in lista):
        return

    lista.append(Hallazgo(texto=texto, prioridad=prioridad, clave=clave))


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

        valor_num = getattr(medicion, "valor_num", None)
        valor_texto = getattr(medicion, "valor_texto", None)

        if valor_num is not None:
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
) -> Optional[Dict[str, Any]]:
    presentes = [v for v in (vmax, gradiente, ava, ava_index, ivd) if v is not None]
    if not presentes:
        return None

    # Evidencia de severidad según los parámetros clásicos.
    criterios_severos = 0
    criterios_moderados = 0
    criterios_no_significativos = 0

    if vmax is not None:
        if vmax >= 4.0:
            criterios_severos += 1
        elif vmax >= 3.0:
            criterios_moderados += 1
        elif vmax < 2.0:
            criterios_no_significativos += 1

    if gradiente is not None:
        if gradiente >= 40:
            criterios_severos += 1
        elif gradiente >= 20:
            criterios_moderados += 1
        elif gradiente < 20:
            criterios_no_significativos += 1

    if ava is not None:
        if ava < 1.0:
            criterios_severos += 1
        elif ava <= 1.5:
            criterios_moderados += 1
        elif ava > 1.5:
            criterios_no_significativos += 1

    if ava_index is not None:
        if ava_index <= 0.6:
            criterios_severos += 1
        elif ava_index <= 0.85:
            criterios_moderados += 1
        elif ava_index > 0.85:
            criterios_no_significativos += 1

    if ivd is not None:
        if ivd < 0.25:
            criterios_severos += 1
        elif ivd <= 0.50:
            criterios_moderados += 1
        elif ivd > 0.50:
            criterios_no_significativos += 1

    # Caso claramente sin estenosis significativa:
    # baja velocidad + bajo gradiente + AVA amplia + IVD conservado.
    sin_estenosis = (
        (vmax is None or vmax < 2.0)
        and (gradiente is None or gradiente < 20)
        and (avao := ava) is not None
        and avao > 1.5
        and (ivd is None or ivd > 0.50)
    )

    if sin_estenosis:
        return {
            "estado": "sin_estenosis_significativa",
            "texto": "Sin evidencia ecocardiográfica de estenosis aórtica significativa según los parámetros disponibles.",
            "conclusion": "Sin evidencia de estenosis aórtica significativa según los parámetros disponibles.",
            "discordante": False,
        }

    # Estenosis severa concordante.
    concordante_severa = (
        (vmax is None or vmax >= 4.0)
        and (gradiente is None or gradiente >= 40)
        and (
            ava is None
            or ava < 1.0
        )
    )

    # Área/índice severos pero velocidad y gradiente bajos:
    # no se debe etiquetar automáticamente como estenosis severa.
    discordancia_bajo_flujo = (
        ava_index is not None
        and ava_index <= 0.85
        and (vmax is None or vmax < 3.0)
        and (gradiente is None or gradiente < 20)
    )

    # Discordancia general.
    señales = {
        "vmax_alto": vmax is not None and vmax >= 3.0,
        "gradiente_alto": gradiente is not None and gradiente >= 20,
        "ava_reducida": ava is not None and ava <= 1.5,
        "avai_reducida": ava_index is not None and ava_index <= 0.85,
        "ivd_reducido": ivd is not None and ivd <= 0.50,
    }

    positivos = sum(señales.values())

    if concordante_severa:
        return {
            "estado": "severa",
            "texto": "Parámetros compatibles con estenosis aórtica severa.",
            "conclusion": "Estenosis aórtica severa según los parámetros disponibles.",
            "discordante": False,
        }

    if discordancia_bajo_flujo:
        return {
            "estado": "discordante",
            "texto": "Parámetros de la válvula aórtica discordantes, con reducción del área valvular indexada y/o índice adimensional, sin gradiente o velocidad elevados; se recomienda correlación con el volumen sistólico y el contexto clínico.",
            "conclusion": "Parámetros de estenosis aórtica discordantes; no se asigna una severidad definitiva únicamente con estos datos.",
            "discordante": True,
        }

    # Moderada solamente si hay apoyo de varios parámetros.
    if criterios_moderados >= 2 and positivos >= 2:
        return {
            "estado": "moderada",
            "texto": "Parámetros compatibles con estenosis aórtica moderada.",
            "conclusion": "Estenosis aórtica moderada según los parámetros disponibles.",
            "discordante": False,
        }

    # Leve solamente si existe evidencia real de obstrucción.
    # Vmax <2,0 no debe transformarse en "leve".
    if (
        2.0 <= (vmax if vmax is not None else 0)
        and (
            (vmax is not None and vmax < 3.0)
            or (gradiente is not None and gradiente < 20)
        )
        and (
            (ava is None or ava > 1.0)
        )
    ):
        return {
            "estado": "leve",
            "texto": "Parámetros compatibles con estenosis aórtica leve.",
            "conclusion": "Estenosis aórtica leve según los parámetros disponibles.",
            "discordante": False,
        }

    return {
        "estado": "no_concluyente",
        "texto": "Parámetros aórticos insuficientes o discordantes para establecer una severidad única de estenosis aórtica.",
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
) -> Optional[Dict[str, str]]:
    señales: List[str] = []

    if reflujo:
        r = reflujo.lower()
        if any(x in r for x in ("moderado-severo", "moderada-severa", "severo", "severa", "grave")):
            señales.append("severa")
        elif "moderado" in r or "moderada" in r:
            señales.append("moderada")
        elif "leve" in r:
            señales.append("leve")
        elif any(x in r for x in ("sin", "ausente", "no")):
            señales.append("ausente")

    if vc is not None:
        if vc >= 6:
            señales.append("severa")
        elif vc >= 3:
            señales.append("moderada")
        elif vc > 0:
            señales.append("leve")

    if eroa is not None:
        if eroa >= 0.30:
            señales.append("severa")
        elif eroa >= 0.10:
            señales.append("moderada")
        elif eroa > 0:
            señales.append("leve")

    if thp is not None:
        if thp < 200:
            señales.append("severa")
        elif thp < 300:
            señales.append("moderada")
        elif thp >= 500:
            señales.append("leve")

    if not señales:
        return None

    # Si un dato cualitativo explícito dice "sin reflujo", se respeta salvo
    # que existan mediciones cuantitativas claramente positivas.
    if señales == ["ausente"]:
        return {
            "estado": "ausente",
            "texto": "Sin evidencia de insuficiencia aórtica significativa.",
            "conclusion": None,
        }

    severidades = {"leve": 1, "moderada": 2, "severa": 3}
    valores = [severidades[s] for s in señales if s in severidades]

    if not valores:
        return None

    maximo = max(valores)
    minimo = min(valores)

    if maximo == 3 and valores.count(3) >= 2:
        estado = "severa"
    elif maximo == 3 and len(valores) == 1:
        estado = "moderada-severa"
    elif maximo == 2:
        estado = "moderada"
    else:
        estado = "leve"

    if estado == "severa":
        conclusion = "Insuficiencia aórtica severa según los parámetros disponibles."
    elif estado == "moderada-severa":
        conclusion = "Insuficiencia aórtica moderada-severa según los parámetros disponibles."
    elif estado == "moderada":
        conclusion = "Insuficiencia aórtica moderada según los parámetros disponibles."
    else:
        conclusion = "Insuficiencia aórtica leve según los parámetros disponibles."

    return {
        "estado": estado,
        "texto": f"Insuficiencia aórtica {estado.replace('-', ' ')} según los parámetros disponibles.",
        "conclusion": conclusion,
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
) -> Optional[Dict[str, str]]:
    señales: List[str] = []

    if cualitativa:
        r = cualitativa.lower()
        if "sever" in r or "grave" in r:
            señales.append("severa")
        elif "moderad" in r:
            señales.append("moderada")
        elif "leve" in r:
            señales.append("leve")
        elif "sin" in r or "ausente" in r:
            señales.append("ausente")

    if vc is not None:
        if vc >= 7:
            señales.append("severa")
        elif vc >= 3:
            señales.append("leve")
        elif vc > 0:
            señales.append("leve")

    if eroa is not None:
        if eroa >= 0.40:
            señales.append("severa")
        elif eroa >= 0.20:
            señales.append("moderada")
        elif eroa > 0:
            señales.append("leve")

    if volumen is not None:
        if volumen >= 60:
            señales.append("severa")
        elif volumen >= 30:
            señales.append("moderada")
        elif volumen > 0:
            señales.append("leve")

    if fraccion is not None:
        if fraccion >= 50:
            señales.append("severa")
        elif fraccion >= 30:
            señales.append("moderada")
        elif fraccion > 0:
            señales.append("leve")

    if not señales:
        return None

    if señales == ["ausente"]:
        return {
            "estado": "ausente",
            "texto": "Sin evidencia de insuficiencia mitral significativa.",
            "conclusion": None,
        }

    mapa = {"leve": 1, "moderada": 2, "severa": 3}
    nums = [mapa[s] for s in señales if s in mapa]

    if not nums:
        return None

    # Evita que un único dato limítrofe domine toda la clasificación.
    if nums.count(3) >= 2:
        estado = "severa"
    elif nums.count(2) >= 2:
        estado = "moderada"
    else:
        estado = "leve"

    return {
        "estado": estado,
        "texto": f"Insuficiencia mitral {estado} según los parámetros disponibles.",
        "conclusion": f"Insuficiencia mitral {estado} según los parámetros disponibles.",
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
        )

    fevi_resultado = interpretar_fevi(fevi)
    if fevi_resultado:
        _agregar_unico(
            resultado.hallazgos,
            fevi_resultado["hallazgo"],
            PRIORIDADES["funcion_vi"],
            "fevi",
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
        )

    if strain_vi is not None:
        _agregar_unico(
            resultado.hallazgos,
            f"Strain longitudinal del ventrículo izquierdo de {_fmt(strain_vi, 1)}%.",
            PRIORIDADES["funcion_vi"],
            "strain_vi",
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
        )

    # --------------------------------------------------------
    # VÁLVULA AÓRTICA
    # --------------------------------------------------------
    vmax_ao = _num(valores, "VELOCIDAD_PICO_AORTICA", "V_PEAK_AO", "V_MAX_AO")
    gdte_ao = _num(valores, "GRADIENTE_MEDIO_AORTICO", "GRADIENTE_AORTICO")
    vti_ao = _num(valores, "VTI_AORTICA", "VTI_AO")
    dm_tsvl = _num(valores, "DIAMETRO_TSVI", "DM_TSVI", "DM_TSVI_MM")
    vmax_tsvl = _num(valores, "V_MAX_TSVI", "VMAX_TSVI")
    vti_tsvl = _num(valores, "VTI_TSVI")
    area_tsvl = _num(valores, "AREA_TSVI")
    avao = _num(valores, "AREA_VALVULAR_AORTICA_CONTINUIDAD", "AVA_AO_EC", "AVAO_EC")
    avao_anat = _num(valores, "AREA_VALVULAR_AORTICA_ANATOMICA", "AVA_AO_ANAT", "AVAO_ANAT")
    avai = _num(valores, "AREA_VALVULAR_AORTICA_INDEXADA", "AVA_AO_INDEX", "AVAO_INDEX")
    ivd = _num(valores, "INDICE_VELOCIDAD_DOPPLER", "IVD")
    vs_index = _num(valores, "VOLUMEN_LATIDO_INDEXADO", "VS_INDEX")
    protesis_ao = _cat(valores, "PROTESIS_AORTICA")
    rf_ao = _cat(valores, "REFLUJO_AORTICO", "RF_AO")
    vc_ao = _num(valores, "VENA_CONTRACTA_AORTICA", "VC_AORTICA")
    pisa_ao = _num(valores, "PISA_AORTICA")
    eroa_ao = _num(valores, "EROA_AORTICA")
    thp_ao = _num(valores, "THP_AORTICA", "THP")

    est_ao = interpretar_estenosis_aortica(
        vmax_ao,
        gdte_ao,
        avao,
        avai,
        ivd,
        vti_tsvl,
        vti_ao,
    )

    parametros_ao = []
    if vmax_ao is not None:
        parametros_ao.append(f"Vmax {_fmt(vmax_ao, 1)} m/s")
    if gdte_ao is not None:
        parametros_ao.append(f"gradiente medio {_fmt(gdte_ao, 0)} mmHg")
    if avao is not None:
        parametros_ao.append(f"AVA por continuidad {_fmt(avao, 2)} cm²")
    if avai is not None:
        parametros_ao.append(f"AVA indexada {_fmt(avai, 2)} cm²/m²")
    if ivd is not None:
        parametros_ao.append(f"índice adimensional {_fmt(ivd, 2)}")
    if vti_ao is not None:
        parametros_ao.append(f"VTI {_fmt(vti_ao, 0)} cm")

    if parametros_ao:
        if est_ao:
            texto = est_ao["texto"] + " " + "; ".join(parametros_ao) + "."
        else:
            texto = "Válvula aórtica: " + "; ".join(parametros_ao) + "."

        _agregar_unico(
            resultado.hallazgos,
            texto,
            PRIORIDADES["valvula_aortica"],
            "estenosis_ao_hallazgo",
        )

        if est_ao and est_ao.get("conclusion"):
            prioridad = PRIORIDADES["emergencia"] if est_ao["estado"] == "severa" else PRIORIDADES["valvula_aortica"]
            _agregar_unico(
                resultado.conclusiones,
                est_ao["conclusion"],
                prioridad,
                "estenosis_ao",
            )

    if protesis_ao:
        _agregar_unico(
            resultado.hallazgos,
            f"Prótesis aórtica: {protesis_ao}.",
            PRIORIDADES["valvula_aortica"],
            "protesis_ao",
        )

    insuf_ao = interpretar_insuficiencia_aortica(rf_ao, vc_ao, eroa_ao, thp_ao)
    if insuf_ao:
        if insuf_ao["texto"]:
            _agregar_unico(
                resultado.hallazgos,
                insuf_ao["texto"],
                PRIORIDADES["valvula_aortica"],
                "insuf_ao",
            )
        if insuf_ao["conclusion"]:
            _agregar_unico(
                resultado.conclusiones,
                insuf_ao["conclusion"],
                PRIORIDADES["valvula_aortica"],
                "insuf_ao",
            )

    if vc_ao is not None:
        _agregar_unico(
            resultado.hallazgos,
            f"Vena contracta aórtica de {_fmt(vc_ao, 1)} mm.",
            PRIORIDADES["valvula_aortica"],
            "vc_ao",
        )

    if pisa_ao is not None:
        _agregar_unico(
            resultado.hallazgos,
            f"PISA aórtica de {_fmt(pisa_ao, 1)} mm.",
            PRIORIDADES["valvula_aortica"],
            "pisa_ao",
        )

    if eroa_ao is not None:
        _agregar_unico(
            resultado.hallazgos,
            f"EROA aórtica de {_fmt(eroa_ao, 2)} cm².",
            PRIORIDADES["valvula_aortica"],
            "eroa_ao",
        )

    if thp_ao is not None:
        _agregar_unico(
            resultado.hallazgos,
            f"Tiempo de hemipresión aórtico de {_fmt(thp_ao, 0)} ms.",
            PRIORIDADES["valvula_aortica"],
            "thp_ao",
        )

    # --------------------------------------------------------
    # MITRAL
    # --------------------------------------------------------
    area_mit = _num(valores, "AREA_MITRAL")
    gdte_mit = _num(valores, "GRADIENTE_MEDIO_MITRAL")
    wilkins = _num(valores, "SCORE_WILKINS")
    vc_mit = _num(valores, "VENA_CONTRACTA_MITRAL")
    pisa_mit = _num(valores, "PISA_MITRAL")
    eroa_mit = _num(valores, "EROA_MITRAL")
    vol_rg = _num(valores, "VOLUMEN_REGURGITANTE_MITRAL", "VOLUMEN_REG_MITRAL")
    fr_rg = _num(valores, "FRACCION_REGURGITANTE_MITRAL", "FR_RG_MITRAL")
    reflujo_mit = _cat(valores, "REFLUJO_MITRAL")
    protesis_mit = _cat(valores, "PROTESIS_MITRAL")

    mitral_partes = []
    if area_mit is not None:
        mitral_partes.append(f"área mitral de {_fmt(area_mit, 2)} cm²")
    if gdte_mit is not None:
        mitral_partes.append(f"gradiente medio de {_fmt(gdte_mit, 0)} mmHg")
    if mitral_partes:
        _agregar_unico(
            resultado.hallazgos,
            "Válvula mitral: " + "; ".join(mitral_partes) + ".",
            PRIORIDADES["valvula_mitral"],
            "mitral_estenosis",
        )

    insuf_mit = interpretar_insuficiencia_mitral(reflujo_mit, vc_mit, eroa_mit, vol_rg, fr_rg)
    if insuf_mit:
        if insuf_mit["texto"]:
            _agregar_unico(
                resultado.hallazgos,
                insuf_mit["texto"],
                PRIORIDADES["valvula_mitral"],
                "insuf_mit",
            )
        if insuf_mit["conclusion"]:
            _agregar_unico(
                resultado.conclusiones,
                insuf_mit["conclusion"],
                PRIORIDADES["valvula_mitral"],
                "insuf_mit",
            )

    if protesis_mit:
        _agregar_unico(
            resultado.hallazgos,
            f"Prótesis mitral: {protesis_mit}.",
            PRIORIDADES["valvula_mitral"],
            "protesis_mit",
        )

    for clave, texto in (
        ("vc_mit", f"Vena contracta mitral de {_fmt(vc_mit, 1)} mm." if vc_mit is not None else ""),
        ("pisa_mit", f"PISA mitral de {_fmt(pisa_mit, 1)} mm." if pisa_mit is not None else ""),
        ("eroa_mit", f"EROA mitral de {_fmt(eroa_mit, 2)} cm²." if eroa_mit is not None else ""),
        ("vol_rg", f"Volumen regurgitante mitral de {_fmt(vol_rg, 0)} mL." if vol_rg is not None else ""),
        ("fr_rg", f"Fracción regurgitante mitral de {_fmt(fr_rg, 0)}%." if fr_rg is not None else ""),
    ):
        if texto:
            _agregar_unico(resultado.hallazgos, texto, PRIORIDADES["valvula_mitral"], clave)

    # --------------------------------------------------------
    # TRICÚSPIDE / PRESIÓN PULMONAR
    # --------------------------------------------------------
    reflujo_it = _cat(valores, "REFLUJO_TRICUSPIDEO", "REFLUJO_TRICUSPIDE")
    vmax_it = _num(valores, "VELOCIDAD_MAXIMA_IT", "VEL_MAX_IT", "VMAX_IT")
    gdte_it = _num(valores, "GRADIENTE_MAXIMO_IT", "GDTE_MAX_IT")
    vci = _num(valores, "VENA_CAVA_INFERIOR", "VCI")
    ptje_vci = _num(valores, "PTJE_VCI", "PORCENTAJE_COLAPSO_VCI", "COLAPSO_VCI")
    psap = _num(valores, "PSAP")
    vc_it = _num(valores, "VENA_CONTRACTA_TRICUSPIDEA", "VC_TRICUSPIDEA")

    it_partes = []
    if vmax_it is not None:
        it_partes.append(f"Vmax IT {_fmt(vmax_it, 1)} m/s")
    if gdte_it is not None:
        it_partes.append(f"gradiente máximo IT {_fmt(gdte_it, 0)} mmHg")
    if psap is not None:
        it_partes.append(f"PSAP estimada de {_fmt(psap, 0)} mmHg")
    if vc_it is not None:
        it_partes.append(f"vena contracta de {_fmt(vc_it, 1)} mm")

    if it_partes:
        _agregar_unico(
            resultado.hallazgos,
            "Válvula tricuspídea: " + "; ".join(it_partes) + ".",
            PRIORIDADES["presion_pulmonar"],
            "tricuspide",
        )

    if reflujo_it:
        _agregar_unico(
            resultado.hallazgos,
            f"Reflujo tricuspídeo: {reflujo_it}.",
            PRIORIDADES["presion_pulmonar"],
            "reflujo_it",
        )

    if vci is not None or ptje_vci is not None:
        partes_vci = []
        if vci is not None:
            partes_vci.append(f"VCI de {_fmt(vci, 0)} mm")
        if ptje_vci is not None:
            partes_vci.append(f"colapso inspiratorio de {_fmt(ptje_vci, 0)}%")
        _agregar_unico(
            resultado.hallazgos,
            "Vena cava inferior: " + "; ".join(partes_vci) + ".",
            PRIORIDADES["presion_pulmonar"],
            "vci",
        )

    psap_resultado = interpretar_psap(psap)
    if psap_resultado:
        if psap_resultado["estado"] != "no_elevada":
            _agregar_unico(
                resultado.conclusiones,
                psap_resultado["texto"] + " Se recomienda correlación con el resto de los parámetros ecocardiográficos.",
                PRIORIDADES["presion_pulmonar"],
                "psap",
            )
        else:
            _agregar_unico(
                resultado.hallazgos,
                psap_resultado["texto"],
                PRIORIDADES["presion_pulmonar"],
                "psap_normal",
            )

    # --------------------------------------------------------
    # PULMONAR
    # --------------------------------------------------------
    tap = _num(valores, "TIEMPO_ACELERACION_PULMONAR", "TAP", "TAP_MS")
    vti_tsvd = _num(valores, "VTI_TSVD")
    if tap is not None or vti_tsvd is not None:
        partes = []
        if tap is not None:
            partes.append(f"tiempo de aceleración de {_fmt(tap, 0)} ms")
        if vti_tsvd is not None:
            partes.append(f"VTI TSVD de {_fmt(vti_tsvd, 0)} cm")
        _agregar_unico(
            resultado.hallazgos,
            "Válvula pulmonar: " + "; ".join(partes) + ".",
            PRIORIDADES["presion_pulmonar"],
            "pulmonar",
        )

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
    valor_num = getattr(medicion, "valor_num", None)
    valor_texto = getattr(medicion, "valor_texto", None)

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
    sexo = _get_attr(paciente, "sexo", default=None)

    resultado = construir_informe_automatico(valores, sexo)
    hallazgos_texto, conclusiones_texto = informe_a_texto(resultado)

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
    story.append(Paragraph("INFORME ECOCARDIOGRÁFICO", titulo))

    nombre = _safe_patient_name(paciente)
    rut = _get_attr(paciente, "rut", default="—")
    fecha = _get_attr(estudio, "fecha_estudio", "fecha_creacion", default="—")
    medico = _get_attr(estudio, "medico", default="—")
    tipo = _get_attr(estudio, "tipo_estudio", default="Ecocardiograma")

    if hasattr(fecha, "strftime"):
        fecha = fecha.strftime("%d/%m/%Y")

    datos_paciente = [
        ["Paciente", nombre or "—", "RUT", rut or "—"],
        ["Fecha", str(fecha), "Médico", medico or "—"],
        ["Estudio", tipo or "—", "Sexo", sexo or "—"],
    ]

    tabla = Table(datos_paciente, colWidths=[1.9 * cm, 6.1 * cm, 1.9 * cm, 6.1 * cm])
    tabla.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    story.append(tabla)
    story.append(Spacer(1, 8))

    # ========================================================
    # 1. TODOS LOS DATOS PRIMERO
    # ========================================================
    story.append(Paragraph("MEDICIONES ECOCARDIOGRÁFICAS REGISTRADAS", subtitulo))

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
    # ========================================================
    story.append(Spacer(1, 5))
    story.append(Paragraph("DESCRIPCIÓN / HALLAZGOS", subtitulo))

    if hallazgos_texto.strip():
        for texto in hallazgos_texto.splitlines():
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
    story.append(Paragraph("CONCLUSIONES", subtitulo))

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
        story.append(Paragraph("ALERTA PARA REVISIÓN MÉDICA", subtitulo))
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
