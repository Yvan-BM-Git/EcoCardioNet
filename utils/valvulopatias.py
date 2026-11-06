# Archivo: utils/valvulopatias.py
"""
Motor ÚNICO de interpretación de las 8 valvulopatías nativas.

Lo usan tanto la redacción automática de estudios.py como el PDF
(pdf_informe.py), para que ambos digan exactamente lo mismo.

Valvulopatías evaluadas
-----------------------
1. Estenosis aórtica         5. Estenosis tricuspídea
2. Insuficiencia aórtica     6. Insuficiencia tricuspídea
3. Estenosis mitral          7. Estenosis pulmonar
4. Insuficiencia mitral      8. Insuficiencia pulmonar

Principios (comunes a las 8)
----------------------------
- Dato ausente != dato normal: solo se interpreta lo que fue ingresado.
- Evaluación multiparamétrica: un único parámetro no basta para declarar
  una severidad definitiva; se informa como "probable" o "sugestiva".
- La discordancia entre parámetros se informa explícitamente.
- Los hallazgos de apoyo (dilatación de cavidades, PSAP, VCI) se integran
  como evidencia secundaria, no como criterio único.
- Con prótesis valvular, los umbrales de válvula nativa no son aplicables
  y se advierte en el texto.

Umbrales según guías
--------------------
- Estenosis valvulares: EAE/ASE 2009 (Baumgartner et al.) y su
  actualización EACVI/ASE 2017 para estenosis aórtica.
- Regurgitaciones nativas: ASE 2017 (Zoghbi et al.) y EACVI 2022
  (Lancellotti et al.), incluida la graduación masiva/torrencial de la IT.
- Manejo clínico: ACC/AHA 2020 y ESC/EACTS 2021.

Este motor apoya, pero no reemplaza, el juicio del cardiólogo informante.
"""

import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# ESCALA DE SEVERIDAD COMÚN
# ============================================================
# 0 ausente | 0.5 mínima | 1 leve | 1.5 leve-moderada | 2 moderada
# 2.5 moderada-severa | 3 severa | 4 masiva | 5 torrencial (solo IT)

ETIQUETAS = {
    0: "ausente",
    0.5: "mínima",
    1: "leve",
    1.5: "leve a moderada",
    2: "moderada",
    2.5: "moderada a severa",
    3: "severa",
    4: "masiva",
    5: "torrencial",
}


def _etiqueta(nivel: float) -> str:
    return ETIQUETAS.get(nivel, ETIQUETAS[min(ETIQUETAS, key=lambda k: abs(k - nivel))])


def _mayus(texto: str) -> str:
    """Primera letra en mayúscula sin alterar el resto (respeta 'PSAP', 'mmHg')."""
    return texto[:1].upper() + texto[1:] if texto else texto


def _redondear_medio(x: float) -> float:
    """Redondea al 0,5 más cercano (2,2 -> 2 ; 2,3 -> 2,5)."""
    return round(x * 2) / 2


# ============================================================
# UTILIDADES DE LECTURA
# ============================================================

def _normalizar_codigo(texto: Any) -> str:
    if texto is None:
        return ""
    s = str(texto).strip().upper()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Z0-9]+", "_", s)
    return s.strip("_")


def _to_float(valor: Any) -> Optional[float]:
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        v = float(valor)
        return v if math.isfinite(v) else None
    s = str(valor).strip().replace("−", "-").replace(",", ".")
    s = re.sub(r"[^0-9eE+\-.]", "", s)
    try:
        v = float(s)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _fmt(valor: Optional[float], decimales: int = 1) -> str:
    if valor is None:
        return ""
    if decimales == 0:
        return str(int(round(valor)))
    return f"{valor:.{decimales}f}".replace(".", ",")


class _Lector:
    """Acceso tolerante a los valores: normaliza códigos y acepta alias."""

    def __init__(self, valores: Dict[str, Any]):
        self.v = {}
        for k, val in (valores or {}).items():
            if val is None or str(val).strip() == "":
                continue
            self.v[_normalizar_codigo(k)] = val

    def raw(self, *codigos: str) -> Any:
        for c in codigos:
            c = _normalizar_codigo(c)
            if c in self.v:
                return self.v[c]
        return None

    def num(self, *codigos: str) -> Optional[float]:
        return _to_float(self.raw(*codigos))

    def txt(self, *codigos: str) -> Optional[str]:
        val = self.raw(*codigos)
        return str(val).strip() if val is not None else None


def grado_cualitativo(texto: Optional[str]) -> Optional[float]:
    """
    Traduce la graduación cualitativa del operador a la escala común.

    Acepta las opciones del Excel: No observable, Mínima, Leve,
    Leve-Moderada, Moderada, Moderada-Severa, Severa (y Masiva/Torrencial).
    El orden de las comprobaciones importa: "Leve-Moderada" debe leerse
    como 1,5 y no como "moderada"; "Moderada-Severa" como 2,5 y no "severa".
    """
    if not texto:
        return None
    t = _normalizar_codigo(texto).lower()
    tokens = t.split("_")

    if "torrencial" in t:
        return 5
    if "masiv" in t:
        return 4
    if "moderad" in t and ("sever" in t or "grave" in t):
        return 2.5
    if ("leve" in t or "liger" in t) and "moderad" in t:
        return 1.5
    if "sever" in t or "grave" in t:
        return 3
    if "moderad" in t:
        return 2
    if "leve" in t or "liger" in t:
        return 1
    if "minim" in t or "trivial" in t or "fisiolog" in t:
        return 0.5
    if tokens[0] in ("no", "sin", "ausente", "normal", "nada") or "ausente" in t:
        return 0
    return None


def _es_mujer(sexo: Optional[str]) -> bool:
    """Acepta F, Femenino, Mujer. Por defecto usa límites masculinos (más conservador)."""
    if not sexo:
        return False
    s = str(sexo).strip().lower()
    return s.startswith(("f", "mujer"))


def _protesis_relevante(texto: Optional[str]) -> Optional[str]:
    """Devuelve el tipo de prótesis si invalida los criterios nativos."""
    if not texto:
        return None
    t = _normalizar_codigo(texto).lower()
    if t.startswith("ausente") or t in ("no", "sin", "ninguna"):
        return None
    if "plastia" in t:
        return "plastia"
    return texto.strip()


# ============================================================
# MOTOR GENÉRICO DE INTEGRACIÓN (común a todas las válvulas)
# ============================================================

def _integrar(
    nombre: str,
    criterios: List[Tuple[str, float]],
    cualitativo: Optional[float] = None,
    permitir_masiva: bool = False,
) -> Dict[str, Any]:
    """
    Integra criterios cuantitativos (nombre, nivel) y la graduación
    cualitativa del operador en una única severidad.

    Reglas (adaptadas del algoritmo integrado ASE 2017 / EACVI 2022):
      - ≥2 criterios cuantitativos, todos en el mismo extremo -> definitivo.
      - Criterios en extremos opuestos (leve y severo) -> discordante.
      - Criterios intermedios -> promedio redondeado (ej. "moderada a severa").
      - Un único criterio cuantitativo: definitivo solo si la graduación
        cualitativa concuerda; si no, "probable".
      - Solo graduación cualitativa -> se respeta, indicando que falta
        cuantificación.
    """
    niveles = [n for _, n in criterios]
    nota = None

    if not niveles:
        if cualitativo is None:
            return {"estado": "sin_datos"}
        return {
            "estado": "cualitativo",
            "nivel": cualitativo,
            "etiqueta": _etiqueta(cualitativo),
        }

    tope = 5 if permitir_masiva else 3
    niveles = [min(n, tope) for n in niveles]
    mn, mx = min(niveles), max(niveles)

    if len(niveles) >= 2:
        if mn <= 1 and mx >= 3:
            return {"estado": "discordante", "nivel": None}
        if mn >= 3:
            nivel = sorted(niveles)[len(niveles) // 2] if permitir_masiva else 3
            nivel = 3 if nivel < 4 else nivel
        elif mx <= 1:
            nivel = 1
        else:
            nivel = _redondear_medio(sum(niveles) / len(niveles))
            nivel = min(max(nivel, 1.5 if mx >= 2 else 1), 2.5 if mn <= 2 else 3)
        if (cualitativo is not None and abs(cualitativo - nivel) >= 1.5
                and not (cualitativo >= 3 and nivel >= 3)):
            nota = (
                f"La graduación cualitativa ({_etiqueta(cualitativo)}) no concuerda "
                f"con la cuantificación; prevalece la cuantificación."
            )
        return {"estado": "definitivo", "nivel": nivel, "etiqueta": _etiqueta(nivel), "nota": nota}

    # Un solo criterio cuantitativo
    n = niveles[0]
    if cualitativo is not None:
        if cualitativo >= 3 and n >= 3:
            return {"estado": "definitivo", "nivel": n, "etiqueta": _etiqueta(n), "nota": None}
        if abs(cualitativo - n) <= 0.5:
            nivel = max(n, cualitativo) if n >= 3 else n
            return {"estado": "definitivo", "nivel": nivel, "etiqueta": _etiqueta(nivel), "nota": None}
        if abs(cualitativo - n) >= 1.5:
            return {"estado": "discordante", "nivel": None}
        nivel = _redondear_medio((cualitativo + n) / 2)
        return {"estado": "definitivo", "nivel": nivel, "etiqueta": _etiqueta(nivel), "nota": None}

    return {"estado": "probable", "nivel": n, "etiqueta": _etiqueta(n)}


def _resultado(
    clave: str,
    categoria: str,
    nombre: str,
    estado: str,
    texto: str,
    conclusion: Optional[str],
    nivel: Optional[float] = None,
    discordante: bool = False,
) -> Dict[str, Any]:
    return {
        "clave": clave,
        "categoria": categoria,
        "nombre": nombre,
        "estado": estado,
        "nivel": nivel,
        "texto": texto,
        "conclusion": conclusion,
        "discordante": discordante,
        "grave": nivel is not None and nivel >= 3,
    }


def _armar_regurgitacion(
    clave: str,
    categoria: str,
    nombre: str,
    criterios: List[Tuple[str, float]],
    detalle: List[str],
    cualitativo: Optional[float],
    cualitativo_txt: Optional[str],
    apoyo: List[str],
    sin_dilatacion: Optional[str],
    protesis: Optional[str],
    permitir_masiva: bool = False,
    cuantificacion: str = "vena contracta, EROA, volumen regurgitante",
) -> Optional[Dict[str, Any]]:
    """Redacta el resultado de cualquier regurgitación con el mismo formato."""
    integ = _integrar(nombre, criterios, cualitativo, permitir_masiva)
    if integ["estado"] == "sin_datos":
        return None

    params = f" ({'; '.join(detalle)})" if detalle else ""
    nota_prot = ""
    if protesis and protesis != "plastia":
        nota_prot = (
            f" Portador de prótesis ({protesis}): estos criterios corresponden a válvula "
            "nativa; la regurgitación protésica (intra o paravalvular) requiere criterios específicos."
        )

    estado = integ["estado"]

    if estado == "cualitativo":
        nivel = integ["nivel"]
        if nivel == 0:
            return _resultado(clave, categoria, nombre, "ausente",
                              f"Sin evidencia de {nombre.lower()} significativa al Doppler color.",
                              None, 0)
        if nivel == 0.5:
            return _resultado(clave, categoria, nombre, "minima",
                              f"{nombre} mínima (trivial), sin significado hemodinámico.",
                              None, 0.5)
        et = integ["etiqueta"]
        texto = (f"{nombre} {et} según evaluación cualitativa (Doppler color)."
                 + (f" No se registraron parámetros cuantitativos ({cuantificacion}) "
                    "que permitan confirmar la severidad." if nivel >= 2 else ""))
        if nivel >= 3 and apoyo:
            texto += " Hallazgos de apoyo: " + "; ".join(apoyo) + "."
        elif nivel >= 3 and sin_dilatacion:
            texto += " " + sin_dilatacion
        conclusion = f"{nombre} {et}" + (" (graduación cualitativa; se sugiere cuantificar)." if nivel >= 2 else ".")
        return _resultado(clave, categoria, nombre, et, texto + nota_prot, conclusion, nivel)

    if estado == "discordante":
        texto = (f"{nombre}: parámetros discordantes{params}; hay criterios en rango leve y "
                 "otros en rango severo. Revisar alineamiento Doppler, PISA y mecanismo de la lesión.")
        if cualitativo_txt:
            texto += f" Graduación cualitativa informada: {cualitativo_txt.lower()}."
        conclusion = f"{nombre} con parámetros discordantes; no establecer severidad definitiva sin revisar la cuantificación."
        return _resultado(clave, categoria, nombre, "discordante", texto + nota_prot, conclusion, None, True)

    nivel = integ["nivel"]
    et = integ["etiqueta"]

    if estado == "probable":
        if nivel <= 1:
            texto = f"{nombre} probablemente leve{params}; parámetro único, sin otros criterios que lo corroboren."
            return _resultado(clave, categoria, nombre, "probablemente_leve", texto + nota_prot,
                              f"{nombre} probablemente leve.", nivel)
        texto = (f"{nombre} probablemente {et}{params}. Un único parámetro cuantitativo no basta "
                 "para establecer la severidad; integrar con otros criterios.")
        if nivel >= 3 and apoyo:
            texto += " Hallazgos de apoyo: " + "; ".join(apoyo) + "."
        return _resultado(clave, categoria, nombre, f"probablemente_{et}", texto + nota_prot,
                          f"{nombre} probablemente {et}; se sugiere completar la cuantificación.", nivel, True)

    # definitivo
    texto = f"{nombre} {et} según evaluación multiparamétrica{params}."
    if integ.get("nota"):
        texto += " " + integ["nota"]
    if nivel >= 3:
        if apoyo:
            texto += " Hallazgos de apoyo: " + "; ".join(apoyo) + "."
        if sin_dilatacion:
            texto += " " + sin_dilatacion
    conclusion = f"{nombre} {et}."
    return _resultado(clave, categoria, nombre, et, texto + nota_prot, conclusion, nivel)


# ============================================================
# 1. ESTENOSIS AÓRTICA
# ============================================================
# Vmax (m/s): <2,0 normal | 2,0–2,9 leve | 3,0–3,9 moderada | ≥4,0 severa
# Gradiente medio (mmHg): <20 leve | 20–39 moderada | ≥40 severa
# AVA (cm²): >1,5 leve | 1,0–1,5 moderada | <1,0 severa
# AVAi (cm²/m²): >0,85 | 0,60–0,85 | <0,60
# Índice adimensional (DVI): >0,50 | 0,25–0,50 | <0,25
# Bajo flujo: VS indexado ≤35 mL/m²

def evaluar_estenosis_aortica(L: _Lector, fevi: Optional[float]) -> Optional[Dict[str, Any]]:
    vmax = L.num("VELOCIDAD_PICO_AORTICA", "V_PEAK_AO", "V_MAX_AO")
    gm = L.num("GRADIENTE_MEDIO_AORTICO", "GRADIENTE_AORTICO")
    ava = L.num("AREA_VALVULAR_AORTICA_CONTINUIDAD", "AVA_AO_EC", "AVAO_EC")
    ava_anat = L.num("AREA_VALVULAR_AORTICA_ANATOMICA", "AVA_AO_ANAT")
    avai = L.num("AREA_VALVULAR_AORTICA_INDEXADA", "AVA_AO_INDEX", "AVAO_INDEX")
    dvi = L.num("INDICE_VELOCIDAD_DOPPLER", "IVD")
    vsi = L.num("VOLUMEN_LATIDO_INDEXADO_AORTICO", "VOLUMEN_LATIDO_INDEXADO", "VS_INDEX")
    protesis = _protesis_relevante(L.txt("PROTESIS_AORTICA"))

    if ava is None:
        ava = ava_anat
    if all(x is None for x in (vmax, gm, ava, avai, dvi)):
        return None

    det = []
    if vmax is not None: det.append(f"Vmax {_fmt(vmax, 1)} m/s")
    if gm is not None: det.append(f"gradiente medio {_fmt(gm, 0)} mmHg")
    if ava is not None: det.append(f"AVA {_fmt(ava, 2)} cm²")
    if avai is not None: det.append(f"AVAi {_fmt(avai, 2)} cm²/m²")
    if dvi is not None: det.append(f"índice adimensional {_fmt(dvi, 2)}")
    if vsi is not None: det.append(f"VS indexado {_fmt(vsi, 0)} mL/m²")
    params = " (" + "; ".join(det) + ")"

    N = "Estenosis aórtica"
    cat = "valvula_aortica"

    if protesis and protesis != "plastia":
        texto = (f"Prótesis aórtica ({protesis}){params}. Los umbrales de estenosis de válvula "
                 "nativa no son aplicables; evaluar con área efectiva, DVI y tiempo de aceleración protésicos.")
        return _resultado("estenosis_ao", cat, N, "protesis", texto,
                          f"Prótesis aórtica ({protesis}): evaluar función con criterios protésicos.")

    # Niveles por parámetro (0 = sin estenosis)
    niv = []
    if vmax is not None: niv.append(("Vmax", 3 if vmax >= 4 else 2 if vmax >= 3 else 1 if vmax >= 2 else 0))
    if gm is not None:
        # <20 mmHg no distingue normal de leve: decide la Vmax si existe;
        # si no, <10 mmHg se considera sin estenosis.
        leve_gm = (vmax >= 2) if vmax is not None else (gm >= 10)
        niv.append(("GM", 3 if gm >= 40 else 2 if gm >= 20 else 1 if leve_gm else 0))
    if ava is not None: niv.append(("AVA", 3 if ava < 1.0 else 2 if ava <= 1.5 else 1 if ava <= 2.0 else 0))
    if avai is not None: niv.append(("AVAi", 3 if avai < 0.60 else 2 if avai <= 0.85 else 0))
    if dvi is not None: niv.append(("DVI", 3 if dvi < 0.25 else 2 if dvi <= 0.50 else 0))

    alto_gradiente = (vmax is not None and vmax >= 4) or (gm is not None and gm >= 40)
    area_severa = (ava is not None and ava < 1.0) or (avai is not None and avai < 0.60)
    valores_flujo = [x for _, x in niv if x >= 0]

    # A) Alto gradiente: Vmax ≥4 o GM ≥40 -> severa (aunque AVA falte o sea >1)
    if alto_gradiente:
        if ava is not None and ava > 1.0 and not area_severa:
            texto = (f"Estenosis aórtica severa de alto gradiente con AVA >1,0 cm²{params}. "
                     "Considerar estado de alto flujo (anemia, fístula, insuficiencia aórtica) "
                     "o subestimación del área (diámetro del TSVI).")
        else:
            texto = f"Estenosis aórtica severa de alto gradiente{params}."
        return _resultado("estenosis_ao", cat, N, "severa", texto,
                          "Estenosis aórtica severa de alto gradiente.", 3)

    # B) Área severa con gradiente bajo: clasificar según flujo y FEVI
    if area_severa:
        if vsi is not None and vsi <= 35:
            if fevi is not None and fevi < 50:
                sub = ("bajo flujo y bajo gradiente con FEVI reducida (clásica). Se sugiere ecocardiograma "
                       "de estrés con dobutamina para distinguir estenosis verdaderamente severa de pseudoseveras.")
            elif fevi is not None:
                sub = ("bajo flujo y bajo gradiente con FEVI conservada (paradójica). Se sugiere "
                       "cuantificar calcio valvular aórtico por TC para confirmar la severidad.")
            else:
                sub = "bajo flujo y bajo gradiente; integrar con la FEVI para definir la conducta."
            return _resultado("estenosis_ao", cat, N, "probablemente_severa",
                              f"Posible estenosis aórtica severa de {sub}{params}",
                              "Posible estenosis aórtica severa de bajo flujo y bajo gradiente; requiere confirmación.",
                              3, True)
        if vsi is not None and vsi > 35:
            return _resultado("estenosis_ao", cat, N, "discordante",
                              f"Área en rango severo con gradiente no severo y flujo normal{params}. "
                              "Suele corresponder a estenosis moderada o a error de medición del TSVI; revisar.",
                              "Estenosis aórtica con parámetros discordantes (área severa, gradiente moderado, flujo normal).",
                              None, True)
        return _resultado("estenosis_ao", cat, N, "discordante",
                          f"Área en rango severo con gradiente no severo{params}. Registrar el volumen sistólico "
                          "indexado y la FEVI para clasificar el flujo.",
                          "Estenosis aórtica con parámetros discordantes; completar evaluación de flujo.",
                          None, True)

    positivos = [x for x in valores_flujo if x > 0]
    if not positivos:
        return _resultado("estenosis_ao", cat, N, "no_significativa",
                          f"Sin evidencia de estenosis aórtica significativa{params}.", None, 0)

    if max(valores_flujo) == 2:
        if sum(1 for x in valores_flujo if x == 2) >= 2 or len(valores_flujo) == 1:
            estado = "moderada" if len(valores_flujo) >= 2 else "probablemente_moderada"
            nivel = 2
        else:
            estado, nivel = "leve a moderada", 1.5
    else:
        estado, nivel = "leve", 1

    et = estado.replace("probablemente_", "probablemente ")
    return _resultado("estenosis_ao", cat, N, estado,
                      f"Estenosis aórtica {et}{params}.", f"Estenosis aórtica {et}.", nivel,
                      estado.startswith("probablemente"))


# ============================================================
# 2. INSUFICIENCIA AÓRTICA
# ============================================================
# VC (mm): <3 leve | 3–6 moderada | >6 severa
# EROA (cm²): <0,10 leve | 0,10–0,19 leve-mod | 0,20–0,29 mod-sev | ≥0,30 severa
# Vol Rg (mL): <30 | 30–44 | 45–59 | ≥60   FR (%): <30 | 30–39 | 40–49 | ≥50
# PHT (ms): >500 leve | 200–500 intermedio | <200 severa
# Apoyo: VI dilatado (DdVI > límite por sexo; DsVI >50 mm o >25 mm/m²)

def evaluar_insuficiencia_aortica(L: _Lector, sexo: Optional[str]) -> Optional[Dict[str, Any]]:
    cual_txt = L.txt("GRADO_REFLUJO_AORTICO", "REFLUJO_AORTICO", "RF_AO")
    cual = grado_cualitativo(cual_txt)
    vc = L.num("VENA_CONTRACTA_AORTICA", "VC_AORTICA")
    eroa = L.num("EROA_AORTICO", "EROA_AORTICA")
    vol = L.num("VOLUMEN_REGURGITANTE_AORTICO", "VOLUMEN_REG_AORTICO", "VOL_REG_AO")
    fr = L.num("FRACCION_REGURGITANTE_AORTICA", "FRACCION_REG_AORTICA", "FR_RG_AO")
    pht = L.num("TIEMPO_HEMIPRESION_AORTICO", "THP_AORTICA", "THP", "PHT_AORTICO")

    crit, det = [], []
    if vc is not None and vc > 0:
        crit.append(("VC", 3 if vc > 6 else 2 if vc >= 3 else 1)); det.append(f"VC {_fmt(vc, 1)} mm")
    if eroa is not None and eroa > 0:
        crit.append(("EROA", 3 if eroa >= 0.30 else 2.5 if eroa >= 0.20 else 1.5 if eroa >= 0.10 else 1))
        det.append(f"EROA {_fmt(eroa, 2)} cm²")
    if vol is not None and vol > 0:
        crit.append(("VolRg", 3 if vol >= 60 else 2.5 if vol >= 45 else 1.5 if vol >= 30 else 1))
        det.append(f"Vol Rg {_fmt(vol, 0)} mL")
    if fr is not None and fr > 0:
        crit.append(("FR", 3 if fr >= 50 else 2.5 if fr >= 40 else 1.5 if fr >= 30 else 1))
        det.append(f"FR {_fmt(fr, 0)}%")
    if pht is not None and pht > 0:
        crit.append(("PHT", 3 if pht < 200 else 1 if pht > 500 else 2)); det.append(f"PHT {_fmt(pht, 0)} ms")

    # Apoyo: dilatación del VI
    ddvi = L.num("DIAMETRO_VI_DIASTOLICO", "DIMENSION_DIASTOLICA_VI", "DVI_DIAST")
    dsvi = L.num("DIAMETRO_VI_SISTOLICO", "DIMENSION_SISTOLICA_VI", "DVI_SIST")
    dsvi_i = L.num("DIAMETRO_VI_SISTOLICO_INDEXADO")
    lim_dd = 53 if _es_mujer(sexo) else 59
    apoyo, sin_dil = [], None
    if ddvi is not None and ddvi > lim_dd:
        apoyo.append(f"VI dilatado (DdVI {_fmt(ddvi, 0)} mm)")
    if (dsvi is not None and dsvi > 50) or (dsvi_i is not None and dsvi_i > 25):
        apoyo.append("DsVI >50 mm o >25 mm/m² (umbral quirúrgico ESC/AHA si es crónica severa)")
    if ddvi is not None and ddvi <= lim_dd:
        sin_dil = ("VI sin dilatación: en IA severa crónica es esperable; considerar IA aguda "
                   "o reevaluar la cuantificación.")

    return _armar_regurgitacion(
        "insuf_ao", "valvula_aortica", "Insuficiencia aórtica", crit, det, cual, cual_txt,
        apoyo, sin_dil, _protesis_relevante(L.txt("PROTESIS_AORTICA")),
        cuantificacion="vena contracta, PHT, EROA, volumen regurgitante")


# ============================================================
# 3. ESTENOSIS MITRAL
# ============================================================
# Área (cm²): ≥4 normal | >1,5 leve | 1,0–1,5 moderada | <1,0 severa
# Gradiente medio (mmHg): <5 | 5–10 | >10   (depende de FC y flujo)
# PHT (ms): <150 | 150–219 | ≥220          Apoyo: PSAP <30 | 30–50 | >50

def evaluar_estenosis_mitral(L: _Lector) -> Optional[Dict[str, Any]]:
    area = L.num("AREA_MITRAL", "AREA_VALVULAR_MITRAL", "AVA_MITRAL")
    gm = L.num("GRADIENTE_MEDIO_MITRAL")
    pht = L.num("THP_MITRAL", "PHT_MITRAL", "TIEMPO_HEMIPRESION_MITRAL")
    psap = L.num("PSAP", "PRESION_SISTOLICA_AP")
    wilkins = L.num("SCORE_WILKINS")
    protesis = _protesis_relevante(L.txt("PROTESIS_MITRAL"))
    if area is None and gm is None and pht is None:
        return None

    N, cat = "Estenosis mitral", "valvula_mitral"
    det = []
    if area is not None: det.append(f"área {_fmt(area, 2)} cm²")
    if gm is not None: det.append(f"gradiente medio {_fmt(gm, 0)} mmHg")
    if pht is not None: det.append(f"PHT {_fmt(pht, 0)} ms")
    params = " (" + "; ".join(det) + ")"

    if protesis and protesis != "plastia":
        return _resultado("estenosis_mitral", cat, N, "protesis",
                          f"Prótesis mitral ({protesis}){params}. Evaluar con criterios protésicos "
                          "(gradiente medio, VTI prótesis/TSVI, área efectiva).",
                          f"Prótesis mitral ({protesis}): evaluar función con criterios protésicos.")

    n_area = None if area is None else (0 if area >= 4.0 else 1 if area > 1.5 else 2 if area >= 1.0 else 3)
    n_gm = None if gm is None else (3 if gm > 10 else 2 if gm >= 5 else 1)
    n_pht = None if pht is None else (3 if pht >= 220 else 2 if pht >= 150 else 1)

    extras = []
    if psap is not None and psap > 50:
        extras.append(f"PSAP {_fmt(psap, 0)} mmHg (hipertensión pulmonar, apoya repercusión hemodinámica)")
    if wilkins is not None:
        favorable = "favorable" if wilkins <= 8 else "intermedio" if wilkins <= 11 else "desfavorable"
        extras.append(f"score de Wilkins {_fmt(wilkins, 0)} ({favorable} para valvuloplastia percutánea)")
    extra_txt = (" " + _mayus("; ".join(extras)) + ".") if extras else ""

    if n_area == 0 and (n_gm is None or n_gm == 1):
        return _resultado("estenosis_mitral", cat, N, "no_significativa",
                          f"Sin evidencia de estenosis mitral{params}.", None, 0)

    if n_area is not None:
        nivel = n_area
        apoyos = [x for x in (n_gm, n_pht) if x is not None]
        if apoyos and nivel == 3 and max(apoyos) == 1:
            texto = (f"Área mitral en rango severo con gradiente bajo{params}; el gradiente depende de "
                     "frecuencia cardíaca y gasto cardíaco: considerar bajo gasto o revisar la planimetría.")
            return _resultado("estenosis_mitral", cat, N, "discordante", texto + extra_txt,
                              "Estenosis mitral con parámetros discordantes (área severa, gradiente bajo).",
                              None, True)
        if apoyos and nivel == 1 and max(apoyos) == 3:
            texto = (f"Gradiente/PHT en rango severo con área >1,5 cm²{params}; considerar taquicardia, "
                     "alto flujo o insuficiencia mitral asociada.")
            return _resultado("estenosis_mitral", cat, N, "discordante", texto + extra_txt,
                              "Estenosis mitral con parámetros discordantes; correlacionar con FC y flujo.",
                              None, True)
        et = _etiqueta(nivel)
        definitivo = bool(apoyos) or nivel == 1
        if definitivo:
            texto = f"Estenosis mitral {et}{params}."
            concl = f"Estenosis mitral {et}" + (" (clínicamente significativa, área ≤1,5 cm²)." if nivel >= 2 else ".")
            return _resultado("estenosis_mitral", cat, N, et, texto + extra_txt, concl, nivel)
        texto = (f"Estenosis mitral probablemente {et}{params}; registrar gradiente medio y PHT "
                 "para confirmar.")
        return _resultado("estenosis_mitral", cat, N, f"probablemente_{et}", texto + extra_txt,
                          f"Estenosis mitral probablemente {et}.", nivel, True)

    # Sin área: solo gradiente y/o PHT
    apoyos = [x for x in (n_gm, n_pht) if x is not None]
    nivel = max(apoyos)
    if nivel == 1:
        return _resultado("estenosis_mitral", cat, N, "no_significativa",
                          f"Sin evidencia hemodinámica de estenosis mitral significativa{params}.", None, 0)
    et = _etiqueta(nivel)
    texto = (f"Hallazgos hemodinámicos sugestivos de estenosis mitral {et}{params}. El gradiente depende "
             "de la frecuencia cardíaca y del flujo; se requiere el área valvular para confirmar.")
    return _resultado("estenosis_mitral", cat, N, f"probablemente_{et}", texto + extra_txt,
                      f"Hallazgos sugestivos de estenosis mitral {et}; confirmar con área valvular.", nivel, True)


# ============================================================
# 4. INSUFICIENCIA MITRAL
# ============================================================
# VC (mm): <3 leve | 3–6,9 moderada | ≥7 severa
# EROA (cm²): <0,20 | 0,20–0,29 | 0,30–0,39 | ≥0,40
# Vol Rg (mL): <30 | 30–44 | 45–59 | ≥60   FR (%): <30 | 30–39 | 40–49 | ≥50
# Radio PISA (mm, Nyquist 30–40 cm/s): <5 | 5–9 | ≥10
# Apoyo: AI dilatada (>34 mL/m²), VI dilatado, PSAP >50 mmHg

def evaluar_insuficiencia_mitral(L: _Lector, sexo: Optional[str]) -> Optional[Dict[str, Any]]:
    cual_txt = L.txt("GRADO_REFLUJO_MITRAL", "REFLUJO_MITRAL")
    cual = grado_cualitativo(cual_txt)
    vc = L.num("VENA_CONTRACTA_MITRAL", "VC_MITRAL")
    eroa = L.num("EROA_MITRAL")
    vol = L.num("VOLUMEN_REGURGITANTE_MITRAL", "VOLUMEN_REG_MITRAL")
    fr = L.num("FRACCION_REGURGITANTE_MITRAL", "FR_RG_MITRAL")
    pisa = L.num("PISA_MITRAL")

    crit, det = [], []
    if vc is not None and vc > 0:
        crit.append(("VC", 3 if vc >= 7 else 2 if vc >= 3 else 1)); det.append(f"VC {_fmt(vc, 1)} mm")
    if eroa is not None and eroa > 0:
        crit.append(("EROA", 3 if eroa >= 0.40 else 2.5 if eroa >= 0.30 else 1.5 if eroa >= 0.20 else 1))
        det.append(f"EROA {_fmt(eroa, 2)} cm²")
    if vol is not None and vol > 0:
        crit.append(("VolRg", 3 if vol >= 60 else 2.5 if vol >= 45 else 1.5 if vol >= 30 else 1))
        det.append(f"Vol Rg {_fmt(vol, 0)} mL")
    if fr is not None and fr > 0:
        crit.append(("FR", 3 if fr >= 50 else 2.5 if fr >= 40 else 1.5 if fr >= 30 else 1))
        det.append(f"FR {_fmt(fr, 0)}%")
    if pisa is not None and pisa > 0:
        crit.append(("PISA", 3 if pisa >= 10 else 2 if pisa >= 5 else 1)); det.append(f"radio PISA {_fmt(pisa, 0)} mm")

    vol_ai = L.num("VOLUMEN_AI", "VOLUMEN_INDEXADO_AI")
    ddvi = L.num("DIAMETRO_VI_DIASTOLICO", "DIMENSION_DIASTOLICA_VI", "DVI_DIAST")
    psap = L.num("PSAP")
    lim_dd = 53 if _es_mujer(sexo) else 59

    apoyo, no_dilatado = [], []
    if vol_ai is not None:
        (apoyo if vol_ai > 34 else no_dilatado).append(
            f"AI {'dilatada' if vol_ai > 34 else 'no dilatada'} ({_fmt(vol_ai, 0)} mL/m²)")
    if ddvi is not None:
        (apoyo if ddvi > lim_dd else no_dilatado).append(
            f"VI {'dilatado' if ddvi > lim_dd else 'no dilatado'} (DdVI {_fmt(ddvi, 0)} mm)")
    if psap is not None and psap > 50:
        apoyo.append(f"PSAP {_fmt(psap, 0)} mmHg")
    sin_dil = None
    if no_dilatado and not [a for a in apoyo if a.startswith(("AI", "VI"))]:
        sin_dil = (f"{_mayus('; '.join(no_dilatado))}: en IM severa crónica se espera dilatación; "
                   "considerar IM aguda o reevaluar la cuantificación.")

    res = _armar_regurgitacion(
        "insuf_mit", "valvula_mitral", "Insuficiencia mitral", crit, det, cual, cual_txt,
        apoyo, sin_dil, _protesis_relevante(L.txt("PROTESIS_MITRAL")))
    if res and res["nivel"] is not None and res["nivel"] >= 2.5:
        res["texto"] += (" En IM secundaria (funcional), un EROA ≥0,30 cm² con orificio elíptico "
                         "puede ya corresponder a IM severa.")
    return res


# ============================================================
# 5. ESTENOSIS TRICUSPÍDEA
# ============================================================
# Criterios de estenosis significativa (EAE/ASE 2009):
# gradiente medio ≥5 mmHg | VTI de influjo >60 cm | PHT ≥190 ms | área ≤1,0 cm²
# Apoyo: AD dilatada, VCI dilatada

def evaluar_estenosis_tricuspidea(L: _Lector) -> Optional[Dict[str, Any]]:
    gm = L.num("GRADIENTE_MEDIO_TRICUSPIDEO", "GRADIENTE_MEDIO_IT", "GRADIENTE_MEDIO_TRICUSPIDE")
    area = L.num("AREA_TRICUSPIDEA", "AREA_VALVULAR_TRICUSPIDEA")
    pht = L.num("THP_TRICUSPIDEO", "PHT_TRICUSPIDEO", "TIEMPO_HEMIPRESION_TRICUSPIDEO")
    vti = L.num("VTI_TRICUSPIDEO", "VTI_INFLUJO_TRICUSPIDEO")
    if all(x is None for x in (gm, area, pht, vti)):
        return None

    N, cat = "Estenosis tricuspídea", "valvula_tricuspide"
    det, positivos, negativos = [], [], []
    if gm is not None:
        det.append(f"gradiente medio {_fmt(gm, 1)} mmHg"); (positivos if gm >= 5 else negativos).append("gradiente")
    if area is not None:
        det.append(f"área {_fmt(area, 2)} cm²"); (positivos if area <= 1.0 else negativos).append("área")
    if pht is not None:
        det.append(f"PHT {_fmt(pht, 0)} ms"); (positivos if pht >= 190 else negativos).append("PHT")
    if vti is not None:
        det.append(f"VTI de influjo {_fmt(vti, 0)} cm"); (positivos if vti > 60 else negativos).append("VTI")
    params = " (" + "; ".join(det) + ")"

    if not positivos:
        return _resultado("estenosis_it", cat, N, "no_significativa",
                          f"Sin evidencia de estenosis tricuspídea significativa{params}.", None, 0)
    if len(positivos) >= 2:
        return _resultado("estenosis_it", cat, N, "severa",
                          f"Estenosis tricuspídea hemodinámicamente significativa{params}; "
                          f"{len(positivos)} criterios EAE/ASE concordantes.",
                          "Estenosis tricuspídea significativa (severa).", 3)
    return _resultado("estenosis_it", cat, N, "sugestiva",
                      f"Un criterio sugestivo de estenosis tricuspídea ({positivos[0]}){params}. "
                      "El gradiente depende de la FC y del flujo; corroborar con área, PHT o VTI de influjo.",
                      "Hallazgos sugestivos de estenosis tricuspídea; requiere confirmación.", 2, True)


# ============================================================
# 6. INSUFICIENCIA TRICUSPÍDEA
# ============================================================
# VC (mm): <3 leve | 3–6,9 moderada | 7–13 severa | 14–20 masiva | ≥21 torrencial
# EROA (cm²): <0,20 | 0,20–0,39 | 0,40–0,59 | 0,60–0,79 | ≥0,80
# Vol Rg (mL): <30 | 30–44 | ≥45     Radio PISA (mm, Nyquist ~28): ≤5 | 6–9 | >9
# Apoyo: VD dilatado (>42 mm), AD dilatada (>18 cm²), VCI >21 mm con colapso <50 %

def evaluar_insuficiencia_tricuspidea(L: _Lector) -> Optional[Dict[str, Any]]:
    cual_txt = L.txt("GRADO_REFLUJO_TRICUSPIDEO", "REFLUJO_TRICUSPIDEO", "REFLUJO_TRICUSPIDE")
    cual = grado_cualitativo(cual_txt)
    vc = L.num("VENA_CONTRACTA_TRICUSPIDEA", "VC_TRICUSPIDEA")
    eroa = L.num("EROA_TRICUSPIDEO", "EROA_TRICUSPIDEA")
    vol = L.num("VOLUMEN_REGURGITANTE_TRICUSPIDEO")
    pisa = L.num("PISA_TRICUSPIDEO")
    if pisa is not None and pisa <= 2.5:   # el Excel lo registra en cm
        pisa = pisa * 10

    crit, det = [], []
    if vc is not None and vc > 0:
        crit.append(("VC", 5 if vc >= 21 else 4 if vc >= 14 else 3 if vc >= 7 else 2 if vc >= 3 else 1))
        det.append(f"VC {_fmt(vc, 1)} mm")
    if eroa is not None and eroa > 0:
        crit.append(("EROA", 5 if eroa >= 0.80 else 4 if eroa >= 0.60 else 3 if eroa >= 0.40 else 2 if eroa >= 0.20 else 1))
        det.append(f"EROA {_fmt(eroa, 2)} cm²")
    if vol is not None and vol > 0:
        crit.append(("VolRg", 3 if vol >= 45 else 2 if vol >= 30 else 1)); det.append(f"Vol Rg {_fmt(vol, 0)} mL")
    if pisa is not None and pisa > 0:
        crit.append(("PISA", 3 if pisa > 9 else 2 if pisa >= 6 else 1)); det.append(f"radio PISA {_fmt(pisa, 0)} mm")

    vd = L.num("DIAMETRO_VD_BASAL", "DIAMETRO_BASAL_VD", "DIAM_BASAL_VD")
    ad = L.num("AREA_AD_4_CAMARAS", "AREA_AD", "AREA_AURICULA_DERECHA")
    vci = L.num("DIAMETRO_VCI", "VENA_CAVA_INFERIOR", "VCI")
    colapso = L.num("PUNTAJE_COLAPSO_VCI", "PORCENTAJE_COLAPSO_VCI", "COLAPSO_VCI", "PTJE_VCI")

    apoyo, no_dil = [], []
    if vd is not None:
        (apoyo if vd > 42 else no_dil).append(f"VD {'dilatado' if vd > 42 else 'no dilatado'} ({_fmt(vd, 0)} mm)")
    if ad is not None:
        (apoyo if ad > 18 else no_dil).append(f"AD {'dilatada' if ad > 18 else 'no dilatada'} ({_fmt(ad, 0)} cm²)")
    if vci is not None and vci > 21 and (colapso is None or colapso < 50):
        apoyo.append(f"VCI dilatada ({_fmt(vci, 0)} mm) con colapso disminuido (presión de AD elevada)")
    sin_dil = None
    if no_dil and not [a for a in apoyo if a.startswith(("VD", "AD"))]:
        sin_dil = (f"{_mayus('; '.join(no_dil))}: en IT severa crónica se espera dilatación "
                   "de cavidades derechas; reevaluar la cuantificación.")

    res = _armar_regurgitacion(
        "insuf_it", "valvula_tricuspide", "Insuficiencia tricuspídea", crit, det, cual, cual_txt,
        apoyo, sin_dil, None, permitir_masiva=True,
        cuantificacion="vena contracta, EROA, radio PISA")
    if res and res["nivel"] is not None and res["nivel"] >= 4:
        res["texto"] += " Graduación masiva/torrencial según la escala extendida de Hahn y Zamorano (EACVI 2022)."
    return res


# ============================================================
# 7. ESTENOSIS PULMONAR
# ============================================================
# Vmax (m/s): <2,0 sin estenosis | 2,0–2,9 leve | 3,0–4,0 moderada | >4,0 severa
# Gradiente máximo (mmHg): <16 | 16–35 | 36–64 | >64
# El gradiente se DERIVA de la velocidad (4·V²): no son criterios
# independientes, así que la Vmax sola SÍ permite graduar.

def evaluar_estenosis_pulmonar(L: _Lector) -> Optional[Dict[str, Any]]:
    vmax = L.num("VELOCIDAD_PICO_PULMONAR", "V_MAX_PULMONAR", "VMAX_PULMONAR", "VELOCIDAD_MAXIMA_TP", "V_MAX_TP")
    gmax = L.num("GRADIENTE_MAXIMO_PULMONAR", "GRADIENTE_PULMONAR", "GDTE_PULMONAR")
    psap = L.num("PSAP")
    if vmax is None and gmax is None:
        return None

    N, cat = "Estenosis pulmonar", "valvula_pulmonar"
    nota = ""
    if vmax is not None and gmax is None:
        gmax_calc = 4 * vmax ** 2
        det = [f"Vmax {_fmt(vmax, 1)} m/s", f"gradiente máximo estimado {_fmt(gmax_calc, 0)} mmHg"]
        g = gmax_calc
    elif vmax is None:
        det = [f"gradiente máximo {_fmt(gmax, 0)} mmHg"]
        g = gmax
    else:
        det = [f"Vmax {_fmt(vmax, 1)} m/s", f"gradiente máximo {_fmt(gmax, 0)} mmHg"]
        g = gmax
        esperado = 4 * vmax ** 2
        if esperado > 0 and abs(gmax - esperado) / esperado > 0.25:
            nota = (f" El gradiente registrado no concuerda con la velocidad (4·V² = {_fmt(esperado, 0)} mmHg); "
                    "revisar la medición.")
    params = " (" + "; ".join(det) + ")"

    v = vmax if vmax is not None else math.sqrt(g / 4)
    if v < 2.0:
        sub = "; flujo levemente acelerado" if v >= 1.5 else ""
        return _resultado("estenosis_pulmonar", cat, N, "no_significativa",
                          f"Sin evidencia de estenosis pulmonar significativa{params}{sub}.{nota}", None, 0)

    nivel = 3 if v > 4.0 else 2 if v >= 3.0 else 1
    et = _etiqueta(nivel)
    texto = f"Estenosis pulmonar {et}{params}.{nota}"
    if nivel >= 2 and psap is not None:
        texto += (" En presencia de estenosis pulmonar, la PSAP estimada por IT refleja la presión sistólica "
                  "del VD y sobreestima la presión arterial pulmonar.")
    if nivel >= 2:
        texto += " Con disfunción del VD o bajo gasto, el gradiente puede subestimar la severidad."
    return _resultado("estenosis_pulmonar", cat, N, et, texto, f"Estenosis pulmonar {et}.", nivel)


# ============================================================
# 8. INSUFICIENCIA PULMONAR
# ============================================================
# Cualitativa (Doppler color) + cuantitativos opcionales:
# PHT del jet (ms): <100 severa | FR (%): <20 | 20–40 | >40
# Ancho del jet / anillo (%): <25 leve | 25–50 moderada | >50 severa
# Índice de IP: <0,77 severa       Apoyo: VD dilatado (>42 mm)

def evaluar_insuficiencia_pulmonar(L: _Lector) -> Optional[Dict[str, Any]]:
    cual_txt = L.txt("GRADO_REFLUJO_PULMONAR", "REFLUJO_PULMONAR", "INSUFICIENCIA_PULMONAR")
    cual = grado_cualitativo(cual_txt)
    pht = L.num("THP_REFLUJO_PULMONAR", "PHT_PULMONAR", "TIEMPO_HEMIPRESION_PULMONAR")
    fr = L.num("FRACCION_REGURGITANTE_PULMONAR")
    ancho = L.num("ANCHO_JET_PULMONAR", "RELACION_JET_ANILLO_PULMONAR")
    indice = L.num("INDICE_REFLUJO_PULMONAR", "INDICE_IP")

    crit, det = [], []
    if pht is not None and pht > 0:
        crit.append(("PHT", 3 if pht < 100 else 2 if pht < 200 else 1)); det.append(f"PHT {_fmt(pht, 0)} ms")
    if fr is not None and fr > 0:
        crit.append(("FR", 3 if fr > 40 else 2 if fr >= 20 else 1)); det.append(f"FR {_fmt(fr, 0)}%")
    if ancho is not None and ancho > 0:
        crit.append(("ancho", 3 if ancho > 50 else 2 if ancho >= 25 else 1)); det.append(f"jet/anillo {_fmt(ancho, 0)}%")
    if indice is not None and indice > 0:
        crit.append(("índice", 3 if indice < 0.77 else 1)); det.append(f"índice de IP {_fmt(indice, 2)}")

    vd = L.num("DIAMETRO_VD_BASAL", "DIAMETRO_BASAL_VD", "DIAM_BASAL_VD")
    apoyo, sin_dil = [], None
    if vd is not None and vd > 42:
        apoyo.append(f"VD dilatado ({_fmt(vd, 0)} mm)")
    elif vd is not None:
        sin_dil = (f"VD no dilatado ({_fmt(vd, 0)} mm): en IP severa crónica se espera dilatación del VD; "
                   "reevaluar la graduación.")

    res = _armar_regurgitacion(
        "insuf_pulmonar", "valvula_pulmonar", "Insuficiencia pulmonar", crit, det, cual, cual_txt,
        apoyo, sin_dil, None,
        cuantificacion="PHT del jet, fracción regurgitante, relación jet/anillo")
    return res


# ============================================================
# PUNTO DE ENTRADA
# ============================================================

ORDEN_VALVULAS = [
    "estenosis_ao", "insuf_ao", "estenosis_mitral", "insuf_mit",
    "estenosis_it", "insuf_it", "estenosis_pulmonar", "insuf_pulmonar",
]


def evaluar_valvulopatias(valores: Dict[str, Any], sexo: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Evalúa las 8 valvulopatías con los datos disponibles.

    Parámetros
    ----------
    valores : {codigo_variable: valor}. Acepta códigos con o sin normalizar.
    sexo    : "M"/"Masculino"/"F"/"Femenino"... (para límites del VI).

    Devuelve una lista ordenada de dicts con las claves:
    clave, categoria, nombre, estado, nivel, texto, conclusion,
    discordante, grave.
    """
    L = _Lector(valores)
    fevi = L.num("FEVI", "FRACCION_EYECCION")
    resultados = [
        evaluar_estenosis_aortica(L, fevi),
        evaluar_insuficiencia_aortica(L, sexo),
        evaluar_estenosis_mitral(L),
        evaluar_insuficiencia_mitral(L, sexo),
        evaluar_estenosis_tricuspidea(L),
        evaluar_insuficiencia_tricuspidea(L),
        evaluar_estenosis_pulmonar(L),
        evaluar_insuficiencia_pulmonar(L),
    ]
    return [r for r in resultados if r]


def conclusion_global_valvular(resultados: List[Dict[str, Any]]) -> Optional[str]:
    """Si todas las válvulas evaluadas son normales, lo resume en una frase."""
    if not resultados:
        return None
    if all(r["conclusion"] is None for r in resultados):
        return "Sin valvulopatías significativas en los parámetros valvulares evaluados."
    return None
