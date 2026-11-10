# Archivo: pages/estudios.py
import streamlit as st

# ==================================================
# CONFIGURACIÓN DE PÁGINA (Debe ser la primera instrucción)
# ==================================================
st.set_page_config(page_title="Nuevo Estudio", page_icon="🩺", layout="wide")

from menu import generar_menu

# 1. Dibujar el menú dinámico
generar_menu()

# 2. Candado de seguridad: Para que el usuario no pueda acceder a esta página sin iniciar sesión
if not st.session_state.get("autenticado", False):
    st.warning("🛑 Debes iniciar sesión para ver esta página.")
    # Botón para redirigir al login
    if st.button("🔑 Ir a Iniciar Sesión"):
        st.session_state["vista_actual"] = "login" # Nos aseguramos de que app.py muestre la pantalla de login (no la de recuperar)
        st.switch_page("app.py")                   # Nombre del script principal
    st.stop()     

import html
import os
import tempfile
import io
import re
import unicodedata
from PIL import Image, ImageOps

# Soporte opcional para fotos HEIC/HEIF del iPhone (pip install pillow-heif)
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    _TIPOS_IMAGEN = ["png", "jpg", "jpeg", "heic", "heif"]
except ImportError:
    _TIPOS_IMAGEN = ["png", "jpg", "jpeg"]
import pandas as pd
from datetime import date, datetime

from database.database import SessionLocal, asegurar_bd
from database.models import Paciente, Estudio, Variable, Medicion

asegurar_bd()  # crea tablas/migraciones una vez; si la BD no responde, mensaje claro
from utils.pdf_informe import generar_pdf_desde_historial
from utils.pdf_informe import (
    _normalizar_codigo as _normalizar_codigo_informe,
    construir_informe_automatico as motor_informe,
    informe_a_texto_agrupado,
)
from utils.valvulopatias import evaluar_valvulopatias, conclusion_global_valvular
from utils.validacion import (
    DECIMALES_MAX,
    advertencia_rango,
    inyectar_bloqueo_numerico,
    permite_negativo,
    texto_normalizado,
    validar_numero,
)

# Inicializar la lista de médicos en la memoria de la sesión
if "lista_medicos_bd" not in st.session_state:
    st.session_state["lista_medicos_bd"] = [
        "Seleccione", 
        "Dr. Eric Fuentes Latorre", 
        "Dr. Felipe Norambuena R.", 
        "Dr. Jorge Ardiles González", 
        "Dr. Viet Nguyen"
    ]

# ==================================================
# EDICIÓN TEMPORAL DEL ESTUDIO
# ==================================================
# Cada paciente tiene su propio borrador temporal dentro de la sesión.
# Estos borradores NO se guardan en la base de datos hasta "Guardar informe".
if "borradores_estudios" not in st.session_state:
    st.session_state["borradores_estudios"] = {}

if "borrador_estudio" not in st.session_state:
    st.session_state["borrador_estudio"] = {}

def _restaurar_campo_estudio(key, default=""):
    """Restaura un campo desde el borrador temporal del paciente activo."""
    if key not in st.session_state:
        st.session_state[key] = st.session_state["borrador_estudio"].get(key, default)

def _guardar_campos_estudio_temporales():
    """Copia los valores actuales al borrador temporal del paciente activo."""
    borrador = st.session_state["borrador_estudio"]
    for key in [
        "medico_seleccionado_estudio", "medico_otro_estudio", "tipo_estudio",
        "fecha_estudio", "ficha_clinica", "patologias_seleccionadas",
        "otra_patologia", "procedencia", "destino", "peso_input", "talla_input",
        "pas", "pad", "ritmo", "fcia", "observaciones",
        "hallazgos_editables", "conclusiones_editables"
    ]:
        if key in st.session_state:
            borrador[key] = st.session_state[key]

    for key, value in list(st.session_state.items()):
        if key.startswith("var_"):
            borrador[key] = value

def _guardar_snapshot_paciente_actual():
    """Guarda una copia completa de la edición actual solo en memoria."""
    rut_activo = st.session_state.get("paciente_estudio_activo")
    if not rut_activo:
        return
    _guardar_campos_estudio_temporales()
    st.session_state["borradores_estudios"][rut_activo] = dict(
        st.session_state.get("borrador_estudio", {})
    )


def _limpiar_widgets_estudio():
    """Limpia solo los widgets del estudio para cargar otro borrador."""
    for key in list(st.session_state.keys()):
        if key.startswith("var_") or key in {
            "medico_seleccionado_estudio", "medico_otro_estudio", "tipo_estudio",
            "fecha_estudio", "ficha_clinica", "patologias_seleccionadas",
            "otra_patologia", "procedencia", "destino", "peso_input", "talla_input",
            "pas", "pad", "ritmo", "fcia", "observaciones",
            "hallazgos_editables", "conclusiones_editables"
        }:
            st.session_state.pop(key, None)

def _cambiar_paciente_temporal(rut_nuevo):
    """Guarda el trabajo del paciente anterior y carga el del nuevo."""
    if not rut_nuevo:
        return

    rut_anterior = st.session_state.get("paciente_estudio_activo")

    # Antes de cambiar, conserva TODO lo que se estaba editando del paciente anterior.
    if rut_anterior and rut_anterior != rut_nuevo:
        _guardar_snapshot_paciente_actual()

    if rut_anterior != rut_nuevo:
        # Recupera el borrador existente del nuevo paciente, si lo tenía.
        borrador_nuevo = st.session_state["borradores_estudios"].get(rut_nuevo, {})
        st.session_state["borrador_estudio"] = dict(borrador_nuevo)
        st.session_state["paciente_estudio_activo"] = rut_nuevo
        _limpiar_widgets_estudio()

        # Reinicia el contador del aviso para el paciente que acaba de abrirse.
        st.session_state["inicio_edicion_estudio"] = datetime.now()


# ==================================================
# FUNCIONES DE FORMATEO (Agregar en pages/estudios.py)
# ==================================================
def formatear_rut_dinamico(k):
    rut_actual = st.session_state.get(k, "")
    if not rut_actual:
        return

    # Mantener solo números y K
    rut_limpio = "".join(c for c in rut_actual.upper() if c.isdigit() or c == "K")

    # Máximo 9 caracteres: 8 del cuerpo + DV
    rut_limpio = rut_limpio[:9]

    if len(rut_limpio) < 2:
        st.session_state[k] = rut_limpio
        return

    cuerpo = rut_limpio[:-1]
    dv = rut_limpio[-1]

    if cuerpo.isdigit():
        cuerpo_formateado = f"{int(cuerpo):,}".replace(",", ".")
        st.session_state[k] = f"{cuerpo_formateado}-{dv}"

def formatear_telefono_dinamico(k):
    telf_actual = st.session_state.get(k, "")

    if not telf_actual:
        return

    # Mantener solo números
    numeros = "".join(c for c in str(telf_actual) if c.isdigit())

    # Restringir estrictamente a un máximo de 9 dígitos
    numeros = numeros[:9]

    # Formateo progresivo en bloques de 3
    if len(numeros) <= 3:
        st.session_state[k] = numeros
    elif len(numeros) <= 6:
        st.session_state[k] = f"{numeros[:3]} {numeros[3:]}"
    else:
        st.session_state[k] = f"{numeros[:3]} {numeros[3:6]} {numeros[6:]}"

##############################################################################
st.title("📝 Nuevo Estudio Ecocardiográfico")

st.markdown("""
<style>
section[data-testid="stMain"] > div:first-child {
    max-width: 1000px;
    margin: 0 auto;
}
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] > div {
    max-width: 250px;
}

/* --- NUEVOS ESTILOS PARA EL TOOLTIP NO ENFOCABLE --- */
.tooltip-container {
    position: relative;
    display: inline-flex;
    align-items: center;
    cursor: default;
}
.tooltip-icon {
    margin-left: 6px;
    color: #A0AEC0;
    border: 1px solid #A0AEC0;
    border-radius: 50%;
    width: 16px;
    height: 16px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: bold;
}
.tooltip-text {
    visibility: hidden;
    width: 240px;
    background-color: #2D3748;
    color: #FFFFFF;
    text-align: left;
    border-radius: 6px;
    padding: 8px 12px;
    position: absolute;
    z-index: 9999;
    bottom: 130%;
    left: 50%;
    transform: translateX(-50%);
    opacity: 0;
    transition: opacity 0.2s;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    font-size: 12px;
    font-weight: normal;
    line-height: 1.4;
    pointer-events: none;
}
.tooltip-container:hover .tooltip-text {
    visibility: visible;
    opacity: 1;
}
.tooltip-text::after {
    content: "";
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border-width: 6px;
    border-style: solid;
    border-color: #2D3748 transparent transparent transparent;
}
</style>
""", unsafe_allow_html=True)


# =====================================================================
# 1. CARGA GLOBAL DE VARIABLES (Estructura Jerárquica para Subsecciones)
# =====================================================================
_session = SessionLocal()
try:
    # Orden global de la columna Orden del Excel: así las pestañas y
    # subsecciones aparecen en el orden clínico definido allí (no alfabético).
    variables_db = (
        _session.query(Variable)
        .order_by(Variable.orden.is_(None), Variable.orden, Variable.categoria)
        .all()
    )
    variables_por_codigo = {v.codigo: v for v in variables_db}
    
    # Estructura: { "Nombre Pestaña": { "Nombre Subsección": [Variables] } }
    tabs_estructura = {}
    
    categorias_ventriculos = [
        "aorta y auriculas",
        "aorta y aurículas",
        "ventrículo derecho",
        "ventriculo derecho",
        "ventrículo izquierdo",
        "ventriculo izquierdo",
        "pericardio"
    ]
    
    for v in variables_db:
        cat_original = v.categoria if v.categoria else "Sin categoría"
        cat_lower = cat_original.lower()
        
        if cat_lower.startswith("valvula") or cat_lower.startswith("válvula"):
            tab_padre = "Válvulas"
        elif cat_lower in categorias_ventriculos:
            tab_padre = "Cavidades y aorta"
        else:
            tab_padre = cat_original
            
        if tab_padre not in tabs_estructura:
            tabs_estructura[tab_padre] = {}
            
        if cat_original not in tabs_estructura[tab_padre]:
            tabs_estructura[tab_padre][cat_original] = []
            
        tabs_estructura[tab_padre][cat_original].append(v)
finally:
    _session.close()


# ==================================================
# 2. FUNCIONES DE LÓGICA Y CÁLCULOS
# ==================================================
def _to_float(valor):
    """Convierte valores numéricos escritos con coma o punto a float."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        return float(texto.replace(",", "."))
    except (ValueError, TypeError):
        return None


def _normalizar_texto(valor):
    if valor is None:
        return ""
    return str(valor).strip()


# --- Validación de tipos de variables ---------------------------------
# Las reglas numéricas (punto decimal, decimales, negativos) están en
# utils/validacion.py, compartidas con pages/historial.py.


_SINONIMOS_TIPO = {
    "numero": "numero", "numerico": "numero", "numerica": "numero", "number": "numero",
    "numeric": "numero", "float": "numero", "int": "numero", "entero": "numero",
    "decimal": "numero", "real": "numero",
    "categoria": "categoria", "categorica": "categoria", "categorico": "categoria",
    "category": "categoria", "categorical": "categoria", "opcion": "categoria",
    "opciones": "categoria", "lista": "categoria", "string": "categoria",
    "booleano": "booleano", "boolean": "booleano", "bool": "booleano",
}


def tipo_variable(variable):
    """
    Devuelve el tipo normalizado de una variable: "numero", "categoria",
    "booleano" o el texto original.

    La columna `tipo` viene de la tabla `variables` (cargada desde el Excel).
    Si allí quedó "Numero", "número", "numero " (con espacio) o "Numérico",
    una comparación exacta con "numero" fallaba y el campo se trataba como
    texto libre, SIN validación. Esta función lo corrige.
    """
    t = str(getattr(variable, "tipo", "") or "").strip().lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return _SINONIMOS_TIPO.get(t, t)


def validar_valor_variable(variable, valor):
    """
    Valida el valor de una variable de tipo "numero" con sus reglas:
    punto decimal, máximo DECIMALES_MAX decimales y signo negativo solo
    si la variable lo admite (strain). Devuelve (numero, error).
    """
    return validar_numero(
        valor,
        permitir_negativo=permite_negativo(getattr(variable, "codigo", None)),
        decimales=DECIMALES_MAX,
        nombre=getattr(variable, "nombre", None) or "El valor",
    )


def convertir_numero(valor, variable=None):
    """
    Convierte lo que escribió el usuario en una variable de tipo "numero".

    - Sin parte decimal  -> int    ("70"   -> 70)
    - Con parte decimal  -> float  ("12.5" o "12,5" -> 12.5)
    - Cualquier otra cosa -> None  (dato inválido)

    Con `variable`, se aplican sus reglas (negativos, decimales). Sin
    ella, se acepta cualquier número con signo y hasta DECIMALES_MAX
    decimales.
    """
    if variable is not None:
        numero, _ = validar_valor_variable(variable, valor)
        return numero
    numero, _ = validar_numero(valor, permitir_negativo=True, decimales=DECIMALES_MAX)
    return numero


def convertir_categoria(valor, opciones_txt):
    """
    Valida una variable de tipo "categoria": siempre devuelve str.
    Si la variable tiene opciones definidas, el valor debe ser una de ellas.
    Devuelve None si el valor no es válido.
    """
    if valor is None or isinstance(valor, bool):
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    if opciones_txt:
        opciones = [x.strip() for x in str(opciones_txt).split(";") if x.strip()]
        if texto not in opciones:
            return None
    return texto


def asignar_valor_medicion(med, variable, valor):
    """
    Guarda el valor en la columna correcta según el tipo de la variable.
    Devuelve True si se asignó, False si el dato no es válido.
    """
    med.valor_entero = med.valor_num = med.valor_texto = None
    if tipo_variable(variable) == "numero":
        numero = convertir_numero(valor, variable)
        if numero is None:
            return False
        if isinstance(numero, int):
            med.valor_entero = numero      # int
        else:
            med.valor_num = float(numero)  # float
        return True
    if tipo_variable(variable) == "categoria":
        texto = convertir_categoria(valor, variable.opciones)
        if texto is None:
            return False
        med.valor_texto = texto            # str
        return True
    # Otros tipos (booleano, texto libre) se guardan como texto, como antes.
    med.valor_texto = str(valor)
    return True


def clasificar_automatico(valores, sexo_paciente):
    """Clasifica únicamente variables que realmente fueron ingresadas.

    Regla fundamental: dato ausente != dato normal.
    Esta función es la única fuente de clasificación que utilizan tanto
    las tarjetas como la redacción automática del informe.
    """
    auto = {}

    def obtener_float(codigo):
        return _to_float(valores.get(codigo))

    # -----------------------------
    # Aurícula izquierda
    # -----------------------------
    vol_ai = obtener_float("VOLUMEN_AI")
    if vol_ai is not None:
        if vol_ai <= 34:
            auto["GRADO_DILATACION_AI"] = "Normal"
        elif vol_ai <= 41:
            auto["GRADO_DILATACION_AI"] = "Leve"
        elif vol_ai <= 48:
            auto["GRADO_DILATACION_AI"] = "Moderada"
        else:
            auto["GRADO_DILATACION_AI"] = "Severa"

    # -----------------------------
    # Pericardio
    # -----------------------------
    derrame = obtener_float("MAGNITUD_DERRAME_PERICARDICO")
    if derrame is not None:
        if derrame == 0:
            auto["GRADO_DERRAME_PERICARDICO"] = "Sin derrame"
        elif derrame <= 10:
            auto["GRADO_DERRAME_PERICARDICO"] = "Leve"
        elif derrame <= 20:
            auto["GRADO_DERRAME_PERICARDICO"] = "Moderado"
        else:
            auto["GRADO_DERRAME_PERICARDICO"] = "Severo"

    # -----------------------------
    # Masa VI / hipertrofia
    # -----------------------------
    masa_idx = obtener_float("MASA_VI_INDEXADA")
    if masa_idx is not None and sexo_paciente:
        es_hombre = sexo_paciente in ("Masculino", "M")
        if es_hombre:
            if masa_idx <= 115:
                auto["GRADO_HIPERTROFIA_VI"] = "Normal"
            elif masa_idx <= 131:
                auto["GRADO_HIPERTROFIA_VI"] = "Leve"
            elif masa_idx <= 148:
                auto["GRADO_HIPERTROFIA_VI"] = "Moderada"
            else:
                auto["GRADO_HIPERTROFIA_VI"] = "Severa"
        else:
            if masa_idx <= 95:
                auto["GRADO_HIPERTROFIA_VI"] = "Normal"
            elif masa_idx <= 108:
                auto["GRADO_HIPERTROFIA_VI"] = "Leve"
            elif masa_idx <= 121:
                auto["GRADO_HIPERTROFIA_VI"] = "Moderada"
            else:
                auto["GRADO_HIPERTROFIA_VI"] = "Severa"

    # -----------------------------
    # Hipertensión pulmonar por PSAP
    # -----------------------------
    psap = obtener_float("PSAP")
    if psap is not None:
        if psap <= 35:
            auto["PSAP_GRADO"] = "Normal"
        elif psap <= 50:
            auto["PSAP_GRADO"] = "Leve"
        elif psap <= 70:
            auto["PSAP_GRADO"] = "Moderada"
        else:
            auto["PSAP_GRADO"] = "Severa"

    # -----------------------------
    # Estenosis aórtica
    # -----------------------------
    vpeak_ao = obtener_float("VELOCIDAD_PICO_AORTICA")
    if vpeak_ao is not None:
        if vpeak_ao < 2.0:
            auto["GRADO_ESTENOSIS_AO_VPEAK"] = "Normal"
        elif vpeak_ao < 3.0:
            auto["GRADO_ESTENOSIS_AO_VPEAK"] = "Leve"
        elif vpeak_ao < 4.0:
            auto["GRADO_ESTENOSIS_AO_VPEAK"] = "Moderada"
        else:
            auto["GRADO_ESTENOSIS_AO_VPEAK"] = "Severa"

    gdte_ao = obtener_float("GRADIENTE_MEDIO_AORTICO")
    if gdte_ao is not None:
        if gdte_ao < 20:
            auto["GRADO_ESTENOSIS_AO_GDTE"] = "Normal/Leve"
        elif gdte_ao < 40:
            auto["GRADO_ESTENOSIS_AO_GDTE"] = "Moderada"
        else:
            auto["GRADO_ESTENOSIS_AO_GDTE"] = "Severa"

    avao = obtener_float("AREA_VALVULAR_AORTICA_CONTINUIDAD")
    if avao is not None:
        if avao > 1.5:
            auto["GRADO_ESTENOSIS_AO_AVAO"] = "Leve"
        elif avao >= 1.0:
            auto["GRADO_ESTENOSIS_AO_AVAO"] = "Moderada"
        else:
            auto["GRADO_ESTENOSIS_AO_AVAO"] = "Severa"

    ivd = obtener_float("INDICE_VELOCIDAD_DOPPLER")
    if ivd is not None:
        if ivd > 0.50:
            auto["GRADO_ESTENOSIS_AO_IVD"] = "Normal"
        elif ivd >= 0.25:
            auto["GRADO_ESTENOSIS_AO_IVD"] = "Moderada"
        else:
            auto["GRADO_ESTENOSIS_AO_IVD"] = "Severa"

    # -----------------------------
    # Hipertensión pulmonar por TAP
    # -----------------------------
    tap = obtener_float("TIEMPO_ACELERACION_PULMONAR")
    if tap is not None:
        if tap > 120:
            auto["GRADO_TAP"] = "Normal"
        elif tap >= 100:
            auto["GRADO_TAP"] = "Límite"
        else:
            auto["GRADO_TAP"] = "Sugerente de HTP"

    # -----------------------------
    # Estenosis mitral / Wilkins
    # -----------------------------
    wilkins = obtener_float("SCORE_WILKINS")
    if wilkins is not None:
        if wilkins <= 8:
            auto["GRADO_WILKINS"] = "Favorable"
        elif wilkins <= 11:
            auto["GRADO_WILKINS"] = "Intermedio"
        else:
            auto["GRADO_WILKINS"] = "Desfavorable"

    area_mit = obtener_float("AREA_MITRAL")
    if area_mit is not None:
        if area_mit >= 4.0:
            auto["GRADO_ESTENOSIS_MITRAL_AREA"] = "Normal"
        elif area_mit > 1.5:
            auto["GRADO_ESTENOSIS_MITRAL_AREA"] = "Leve"
        elif area_mit >= 1.1:
            auto["GRADO_ESTENOSIS_MITRAL_AREA"] = "Moderada"
        else:
            auto["GRADO_ESTENOSIS_MITRAL_AREA"] = "Severa"

    gdte_mit = obtener_float("GRADIENTE_MEDIO_MITRAL")
    if gdte_mit is not None:
        if gdte_mit <= 5:
            auto["GRADO_ESTENOSIS_MITRAL_GDTE"] = "Normal"
        elif gdte_mit <= 10:
            auto["GRADO_ESTENOSIS_MITRAL_GDTE"] = "Moderada"
        else:
            auto["GRADO_ESTENOSIS_MITRAL_GDTE"] = "Severa"

    # -----------------------------
    # Insuficiencia mitral
    # -----------------------------
    vc_mit = obtener_float("VENA_CONTRACTA_MITRAL")
    if vc_mit is not None:
        # 3 mm se conserva como límite superior de leve para evitar
        # contradicción con el ejemplo trabajado anteriormente.
        if vc_mit <= 3:
            auto["GRADO_RM_VC"] = "Leve"
        elif vc_mit < 7:
            auto["GRADO_RM_VC"] = "Moderada"
        else:
            auto["GRADO_RM_VC"] = "Severa"

    eroa_mit = obtener_float("EROA_MITRAL")
    if eroa_mit is not None:
        if eroa_mit < 0.20:
            auto["GRADO_RM_EROA"] = "Leve"
        elif eroa_mit < 0.40:
            auto["GRADO_RM_EROA"] = "Moderada"
        else:
            auto["GRADO_RM_EROA"] = "Severa"

    vol_rg = obtener_float("VOLUMEN_REGURGITANTE_MITRAL")
    if vol_rg is not None:
        if vol_rg < 30:
            auto["GRADO_RM_VOL"] = "Leve"
        elif vol_rg < 60:
            auto["GRADO_RM_VOL"] = "Moderada"
        else:
            auto["GRADO_RM_VOL"] = "Severa"

    return auto


# ==================================================
# 3. SISTEMA DE CALLBACKS PRINCIPAL
# ==================================================
def on_numeric_change(codigo_var):
    key_actual = f"var_{codigo_var}"
    val = st.session_state.get(key_actual, "")
    
    if val:
        st.session_state[key_actual] = val.replace(",", ".")
        
    valores_temp = {k.replace("var_", ""): v for k, v in st.session_state.items() if k.startswith("var_")}
    sexo_pac = st.session_state.get("paciente_existente_sexo") or st.session_state.get("sexo_input", "")
    # --- Cálculo automático de AVAo por Ecuación de Continuidad ---
    area_tsvi = _to_float(valores_temp.get("AREA_TSVI"))
    vti_tsvi  = _to_float(valores_temp.get("VTI_TSVI"))
    vti_ao    = _to_float(valores_temp.get("VTI_AORTICO"))

    if area_tsvi and vti_tsvi and vti_ao and vti_ao != 0:
        avao_calc = (area_tsvi * vti_tsvi) / vti_ao
        st.session_state["var_AREA_VALVULAR_AORTICA_CONTINUIDAD"] = f"{avao_calc:.2f}"


    nuevas_categorias = clasificar_automatico(valores_temp, sexo_pac)
    
    for cod_cat, valor_calculado in nuevas_categorias.items():
        key_cat = f"var_{cod_cat}"
        var_obj = variables_por_codigo.get(cod_cat)
        if var_obj and tipo_variable(var_obj) == "categoria":
            opciones_validas = [""] + [x.strip() for x in var_obj.opciones.split(";")] if var_obj.opciones else [""]
            if valor_calculado in opciones_validas:
                st.session_state[key_cat] = valor_calculado

def formatear_busqueda_callback():
    busqueda_actual = st.session_state.get("busqueda_input", "")
    if not busqueda_actual: return

    limpio = busqueda_actual.replace(".", "").replace("-", "").strip().upper()
    if 7 <= len(limpio) <= 9:
        cuerpo = limpio[:-1]
        dv = limpio[-1]
        if cuerpo.isdigit() and (dv.isdigit() or dv == "K"):
            cuerpo_formateado = f"{int(cuerpo):,}".replace(",", ".")
            st.session_state.busqueda_input = f"{cuerpo_formateado}-{dv}"

def formatear_rut_callback():
    rut_actual = st.session_state.rut_input
    if not rut_actual: return
    rut_limpio = "".join(c for c in rut_actual if c.isalnum()).upper()
    if len(rut_limpio) < 2:
        st.session_state.rut_input = rut_limpio
        return
    cuerpo = rut_limpio[:-1]
    dv = rut_limpio[-1]
    if cuerpo.isdigit():
        st.session_state.rut_input = f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}"
    else:
        st.session_state.rut_input = f"{cuerpo}-{dv}"

def formatear_telefono_callback():
    telf_actual = st.session_state.get("telefono_input", "")
    
    if not telf_actual: 
        return
        
    # Mantener solo números
    numeros = "".join(c for c in str(telf_actual) if c.isdigit())
    
    # Restringir estrictamente a un máximo de 9 dígitos
    numeros = numeros[:9]
    
    # Formateo progresivo en bloques de 3
    if len(numeros) <= 3:
        st.session_state.telefono_input = numeros
    elif len(numeros) <= 6:
        st.session_state.telefono_input = f"{numeros[:3]} {numeros[3:]}"
    else:
        st.session_state.telefono_input = f"{numeros[:3]} {numeros[3:6]} {numeros[6:]}"

# ==================================================
# CÁLCULO AUTOMÁTICO DE ASC E IMC (UNIFICADO)
# ==================================================
# ==================================================
# CAMPOS GENERALES DEL ESTUDIO (peso, talla, PAS, PAD, FC)
# No están en la tabla `variables`, por eso aquí se define su tipo.
# Solo se exige que sean números positivos; no hay mínimos ni máximos.
#   float -> hasta DECIMALES_MAX decimales (70.5)    int -> solo enteros (120)
# ==================================================
CAMPOS_GENERALES = {
    "peso_input":  {"nombre": "Peso (kg)",  "tipo": "float"},
    "talla_input": {"nombre": "Talla (cm)", "tipo": "float"},
    "pas":         {"nombre": "PAS (mmHg)", "tipo": "int"},
    "pad":         {"nombre": "PAD (mmHg)", "tipo": "int"},
    "fcia":        {"nombre": "FC (lpm)",   "tipo": "int"},
}


def _decimales_campo_general(key):
    return 0 if CAMPOS_GENERALES[key]["tipo"] == "int" else DECIMALES_MAX


def validar_campo_general(key, texto=None):
    """
    Revisa un campo general. Devuelve (valor_convertido, mensaje_error).
    Campo vacío -> (None, None): no es obligatorio.
    """
    cfg = CAMPOS_GENERALES[key]
    if texto is None:
        texto = st.session_state.get(key, "")
    if texto is None or str(texto).strip() == "":
        return None, None

    numero, error = validar_numero(
        texto,
        permitir_negativo=False,
        decimales=_decimales_campo_general(key),
        nombre=cfg["nombre"],
    )
    if error:
        return None, error

    numero = int(numero) if cfg["tipo"] == "int" else float(numero)
    return numero, None


def on_change_campo_general(key):
    """
    Si el dato no es válido, se borra y se avisa; si es válido queda con
    punto decimal ("70,5" -> "70.5"). Peso/talla recalculan ASC e IMC.
    """
    texto = st.session_state.get(key, "")
    numero, error = validar_campo_general(key)
    if error:
        st.session_state[key] = ""
        st.toast(error, icon="⚠️")
    elif numero is not None:
        st.session_state[key] = texto_normalizado(numero, texto)
    if key in ("peso_input", "talla_input"):
        calcular_asc_imc()


# NOTA: Streamlit solo permite UN callback on_change por widget, por eso ASC e IMC
# se calculan juntos en una sola función y se engancha a peso_input y talla_input.
def calcular_asc_imc():
    try:
        p, _ = validar_campo_general("peso_input")
        t, _ = validar_campo_general("talla_input")
        if p is not None and t is not None:
            if p > 0 and t > 0:
                # Mosteller: misma fórmula con que ASE 2015 indexó sus valores
                # de referencia (Lang 2015, apéndice) y la del PDF/Historial.
                asc_calc = ((p * t) / 3600) ** 0.5
                imc_calc = p / ((t / 100) ** 2)
                st.session_state.asc_val = f"{asc_calc:.2f}"
                st.session_state.imc_val = f"{imc_calc:.2f}"
            else:
                st.session_state.asc_val = ""
                st.session_state.imc_val = ""
        else:
            st.session_state.asc_val = ""
            st.session_state.imc_val = ""
    except ValueError:
        st.session_state.asc_val = ""
        st.session_state.imc_val = ""

if "asc_val" not in st.session_state:
    st.session_state.asc_val = ""
if "imc_val" not in st.session_state:
    st.session_state.imc_val = ""


# Widgets numéricos de esta ejecución de la página: {key: {"neg": bool, "dec": int}}.
# Se llena al dibujar los campos y se envía al navegador para bloquear
# la escritura de caracteres inválidos (utils/validacion.py).
CAMPOS_NUMERICOS_PAGINA = {
    k: {"neg": False, "dec": 0 if cfg["tipo"] == "int" else DECIMALES_MAX}
    for k, cfg in CAMPOS_GENERALES.items()
}


def renderizar_variable(variable, col_contenedor):
    with col_contenedor:
        col_nombre, col_input, col_unidad = st.columns([3, 2, 1])

        with col_nombre:
            if variable.descripcion:
                # Reemplazamos st.markdown nativo con estructura HTML inmune al TAB
                html_label = f"""
                <div class="tooltip-container" style="padding-bottom:4px; font-size:15px; color:#4A5568">
                    <span>{variable.nombre}</span>
                    <span class="tooltip-icon">?</span>
                    <span class="tooltip-text">{variable.descripcion}</span>
                </div>
                """
                st.markdown(html_label, unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='padding-bottom:4px; font-size:15px; color:#4A5568'><b>{variable.nombre}</b></div>", unsafe_allow_html=True) 

        with col_input:
            key = f"var_{variable.codigo}"
            # Si el widget fue eliminado al cambiar de página, lo reconstruimos
            # desde el borrador temporal antes de volver a mostrarlo.
            if key not in st.session_state:
                default_temporal = st.session_state["borrador_estudio"].get(key, "")
                st.session_state[key] = default_temporal

            def _guardar_variable_y_calcular(codigo=variable.codigo, es_numero=(tipo_variable(variable) == "numero"), var_obj=variable):
                k = f"var_{codigo}"
                nuevo = st.session_state.get(k, "")
                # Variables numéricas: si lo escrito no es válido, se rechaza
                # y el campo vuelve a su último valor válido. Si es válido,
                # queda escrito con punto decimal.
                if es_numero and str(nuevo).strip():
                    numero, error = validar_valor_variable(var_obj, nuevo)
                    if error:
                        st.session_state[k] = st.session_state["borrador_estudio"].get(k, "")
                        st.toast(error, icon="⚠️")
                        return
                    nuevo = texto_normalizado(numero, nuevo)
                    st.session_state[k] = nuevo
                st.session_state["borrador_estudio"][k] = nuevo
                on_numeric_change(codigo)
                st.session_state["borrador_estudio"][f"var_{codigo}"] = st.session_state.get(f"var_{codigo}", "")

            if tipo_variable(variable) == "numero":
                admite_negativo = permite_negativo(variable.codigo)
                valor = st.text_input(
                    "", key=key, label_visibility="collapsed",
                    on_change=_guardar_variable_y_calcular
                )
                CAMPOS_NUMERICOS_PAGINA[key] = {"neg": admite_negativo, "dec": DECIMALES_MAX}
                if str(valor).strip():
                    numero_ing, error_ing = validar_valor_variable(variable, valor)
                    if error_ing:
                        st.markdown(
                            f"<div style='color:#d33; font-size:11px'>⚠ {html.escape(error_ing)}</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        aviso = advertencia_rango(
                            numero_ing,
                            getattr(variable, "valor_minimo", None),
                            getattr(variable, "valor_maximo", None),
                            variable.unidad or "",
                        )
                        if aviso:
                            st.markdown(
                                f"<div style='color:#C05621; font-size:11px'>⚠ {html.escape(aviso)}</div>",
                                unsafe_allow_html=True,
                            )

            elif tipo_variable(variable) == "categoria":
                opciones = ([""] + [x.strip() for x in variable.opciones.split(";")] if variable.opciones else [""])
                valor = st.selectbox(
                    "", opciones, key=key, label_visibility="collapsed",
                    on_change=_guardar_variable_y_calcular
                )
                
            elif tipo_variable(variable) == "booleano":
                valor = st.checkbox("", key=key, on_change=_guardar_variable_y_calcular)
            else:
                valor = st.text_input("", key=key, label_visibility="collapsed", on_change=_guardar_variable_y_calcular)

            # Mantener siempre una copia fuera del estado interno del widget.
            st.session_state["borrador_estudio"][key] = valor

        with col_unidad:
            st.markdown(f"<div style='padding-top:6px; font-size:10px'><i>{variable.unidad if variable.unidad else '—'}</i></div>", unsafe_allow_html=True)

    return valor

# ==================================================
# SELECCIÓN Y BÚSQUEDA DE PACIENTE
# ==================================================
st.subheader("Selección de Paciente")

_session = SessionLocal()
try:
    pacientes_db = _session.query(Paciente).order_by(Paciente.apellido_paterno, Paciente.nombres).all()
    if pacientes_db:
        df_pacientes_todos = pd.DataFrame([
            {
                "RUT": p.rut,
                "Nombre completo": f"{p.apellido_paterno} {p.apellido_materno or ''} {p.nombres}".strip(),
            }
            for p in pacientes_db
        ])
    else:
        df_pacientes_todos = pd.DataFrame(columns=["RUT", "Nombre completo"])
finally:
    _session.close()

col_link, col_search, col_seleccion = st.columns([1, 1, 1.5])

with col_link:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("➕ Registrar Nuevo Paciente", icon="👤", key="btn_mostrar_inline"):
        st.session_state["mostrar_crear_paciente"] = True

with col_search:
    busqueda = st.text_input(
        "🔎 Buscar paciente en la base de datos", 
        value="", placeholder="Ej: Nombre, Apellido o RUT",
        key="busqueda_input",
        on_change=formatear_busqueda_callback
    )

with col_seleccion:
    if df_pacientes_todos.empty:
        st.info("No hay pacientes registrados.")
        rut_seleccionado = None
    else:
        # --- SOLUCIÓN: Interceptar el nuevo paciente antes de instanciar el widget ---
        if "paciente_recien_creado" in st.session_state:
            st.session_state["selectbox_todos_estudios"] = st.session_state.pop("paciente_recien_creado")

        paciente_guardado = st.session_state.get("paciente_estudio_activo")
        if "selectbox_todos_estudios" not in st.session_state:
            st.session_state["selectbox_todos_estudios"] = paciente_guardado if paciente_guardado in df_pacientes_todos["RUT"].tolist() else None

        rut_seleccionado = st.selectbox(
            "✅ Seleccionar un paciente existente", 
            options=df_pacientes_todos["RUT"].tolist(),
            index=None,
            placeholder="Seleccionar 👇",
            format_func=lambda r: f"{df_pacientes_todos[df_pacientes_todos['RUT'] == r]['Nombre completo'].iloc[0]} ({r})",
            key="selectbox_todos_estudios",
            on_change=lambda: _cambiar_paciente_temporal(st.session_state.get("selectbox_todos_estudios"))
        )

# Selector dinámico de búsqueda (Aparece abajo si se busca algo, igual que en pacientes.py)
if busqueda and not df_pacientes_todos.empty:
    mask = (
        df_pacientes_todos["Nombre completo"].str.contains(busqueda, case=False, na=False) |
        df_pacientes_todos["RUT"].str.contains(busqueda, case=False, na=False)
    )
    df_filtrado = df_pacientes_todos[mask]

    if not df_filtrado.empty:
        st.markdown("---")
        rut_filtrado = st.selectbox(
            "🔍 Seleccione el paciente de la búsqueda",
            options=df_filtrado["RUT"].tolist(),
            index=None,
            placeholder="Resultados de búsqueda 👇",
            format_func=lambda r: f"{df_filtrado[df_filtrado['RUT'] == r]['Nombre completo'].iloc[0]} ({r})",
            key="selectbox_busqueda_estudios"
        )
        if rut_filtrado:
            rut_seleccionado = rut_filtrado  # Prioriza el paciente seleccionado en la búsqueda
            if st.session_state.get("paciente_estudio_activo") != rut_filtrado:
                _cambiar_paciente_temporal(rut_filtrado)
                # El selector principal ya se dibujó en esta ejecución y Streamlit
                # no permite cambiar su valor ahora: se sincroniza al inicio de la
                # siguiente (mismo mecanismo que "paciente_recien_creado").
                st.session_state["paciente_recien_creado"] = rut_filtrado
                st.rerun()
    else:
        st.warning("No se encontraron pacientes que coincidan con la búsqueda.")

# ==================================================
# FORMULARIO: REGISTRAR NUEVO PACIENTE (INLINE)
# ================================================== 
if st.session_state.get("mostrar_crear_paciente", False):
    st.divider()
    st.markdown("#### 👤 Registrar Nuevo Paciente")
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 1. CORRECCIÓN: Agregamos v_fono y v_cel que faltaban
    v_rut = ""
    v_nom = ""
    v_ap = ""
    v_am = ""
    v_fn = date(2000, 1, 1)
    v_fono = "" 
    v_cel = ""  
    
    opts_prev = ["", "Fonasa", "Isapre", "Otra"]
    opts_sexo = ["", "Masculino", "Femenino"]
    
    key_rut = "rut_inline_nuevo"
    key_fono = "fono_inline_nuevo"
    key_celular = "celular_inline_nuevo"

    col1, col2, col3, col4 = st.columns(4)
    with col1: 
        # 2. CORRECCIÓN: Mantenemos el nombre rut_nuevo para que coincida con el guardado
        rut_nuevo = st.text_input(
            "RUT del paciente",
            value=v_rut,
            placeholder="Ej: 12.345.678-9",
            max_chars=12,
            key=key_rut,
            on_change=formatear_rut_dinamico,
            args=(key_rut,)
        )        
    with col2: 
        nombres_nuevo = st.text_input("Nombres", value=v_nom, key="nom_inline")
    with col3: 
        apellido_paterno_nuevo = st.text_input("Apellido paterno", value=v_ap, key="ap_inline")
    with col4: 
        apellido_materno_nuevo = st.text_input("Apellido materno", value=v_am, key="am_inline")

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        fecha_nacimiento_nuevo = st.date_input("Fecha nacimiento", value=v_fn, min_value=date(1900, 1, 1), max_value=date.today(), format="DD/MM/YYYY", key="fn_inline")
    with col6:
        hoy = date.today()
        edad_paciente = hoy.year - fecha_nacimiento_nuevo.year - ((hoy.month, hoy.day) < (fecha_nacimiento_nuevo.month, fecha_nacimiento_nuevo.day))
        st.text_input("Edad calculada", value=f"{edad_paciente} años", disabled=True)
    with col7:
        prevision_nuevo = st.selectbox("Previsión", opts_prev, index=0, key="prev_inline")
    with col8:
        sexo_nuevo = st.selectbox("Sexo", opts_sexo, index=0, key="sexo_inline")        

    col9, col10, col11 = st.columns(3)
    
    # Diccionario de prefijos con la opción "OTRO" al final
    dic_prefijos = {
        "+56": "🇨🇱 +56",
        "+54": "🇦🇷 +54",
        "+51": "🇵🇪 +51",
        "+57": "🇨🇴 +57",
        "+52": "🇲🇽 +52",
        "+58": "🇻🇪 +58",
        "+593": "🇪🇨 +593",
        "+591": "🇧🇴 +591",
        "+595": "🇵🇾 +595",
        "+598": "🇺🇾 +598",
        "+55": "🇧🇷 +55",
        "+1":  "🇺🇸/🇨🇦 +1",
        "+34": "🇪🇸 +34",
        "OTRO": "🌍 Otro..." # <- Opción comodín
    }
    lista_prefijos = list(dic_prefijos.keys())

    with col9: 
        c_pref1, c_num1 = st.columns([1, 2])
        with c_pref1:
            sel_pref_fono = st.selectbox(
                "Cód.", 
                options=lista_prefijos, 
                index=0, 
                format_func=lambda x: dic_prefijos[x], 
                key="pref_fono_inline"
            )
            # Si el usuario elige "Otro...", mostramos un campo para que lo escriba
            if sel_pref_fono == "OTRO":
                prefijo_fono = st.text_input("Escriba Cód.", value="+", key="fono_manual_inline")
            else:
                prefijo_fono = sel_pref_fono

        with c_num1:
            fono_base = st.text_input(
                "Fono fijo", 
                value="", 
                placeholder="22 123 4567", 
                key="fono_base_inline", 
                max_chars=11, 
                on_change=formatear_telefono_dinamico, 
                args=("fono_base_inline",)
            )
        
        # Unimos usando el prefijo final (ya sea el del selector o el manual)
        fono_fijo_nuevo = f"{prefijo_fono} {fono_base.strip()}" if fono_base.strip() else ""

    with col10: 
        c_pref2, c_num2 = st.columns([1, 2])
        with c_pref2:
            sel_pref_cel = st.selectbox(
                "Cód.", 
                options=lista_prefijos, 
                index=0, 
                format_func=lambda x: dic_prefijos[x], 
                key="pref_cel_inline"
            )
            # Lógica idéntica para el celular
            if sel_pref_cel == "OTRO":
                prefijo_cel = st.text_input("Escriba Cód.", value="+", key="cel_manual_inline")
            else:
                prefijo_cel = sel_pref_cel

        with c_num2:
            celular_base = st.text_input(
                "Celular", 
                value="", 
                placeholder="987 654 321", 
                max_chars=11, 
                key="celular_base_inline", 
                on_change=formatear_telefono_dinamico, 
                args=("celular_base_inline",)
            )
            
        celular_nuevo = f"{prefijo_cel} {celular_base.strip()}" if celular_base.strip() else ""

    with col11: 
        email_nuevo = st.text_input("Email", value="", placeholder="ejemplo@correo.com", key="email_inline")

    st.markdown("<br>", unsafe_allow_html=True)
    
    c_btn1, c_btn2 = st.columns([1, 4])
    with c_btn1:
        if st.button("❌ Cancelar", use_container_width=True):
            st.session_state["mostrar_crear_paciente"] = False
            st.rerun()
            
    with c_btn2:
        if st.button("💾 Guardar y seleccionar paciente", type="primary", use_container_width=True):
            if not rut_nuevo or not nombres_nuevo or not apellido_paterno_nuevo:
                st.error("❌ Debe completar al menos: RUT, Nombres y Apellido paterno.")
            else:
                session = SessionLocal()
                try:
                    rut_limpio = rut_nuevo.strip()
                    existe = session.query(Paciente).filter(Paciente.rut == rut_limpio).first()
                    if existe:
                        st.error(f"⚠️ Ya existe un paciente registrado con el RUT {rut_limpio}")
                    else:
                        nuevo_p = Paciente(
                            rut=rut_limpio,
                            nombres=nombres_nuevo,
                            apellido_paterno=apellido_paterno_nuevo,
                            apellido_materno=apellido_materno_nuevo,
                            fecha_nacimiento=fecha_nacimiento_nuevo,
                            sexo=sexo_nuevo if sexo_nuevo else None,
                            telefono=celular_nuevo if celular_nuevo else None,
                            email=email_nuevo if email_nuevo else None
                        )
                        if hasattr(nuevo_p, 'prevision'): nuevo_p.prevision = prevision_nuevo
                        if hasattr(nuevo_p, 'fono_fijo'): nuevo_p.fono_fijo = fono_fijo_nuevo
                        
                        session.add(nuevo_p)
                        session.commit()
                        
                        st.session_state["paciente_recien_creado"] = rut_limpio
                        
                        st.session_state["mostrar_crear_paciente"] = False
                        st.success(f"✅ Paciente registrado con éxito.")
                        st.rerun()
                except Exception as e:
                    session.rollback()
                    st.error(f"❌ Error al guardar en la base de datos: {e}")
                finally:
                    session.close()

# ==================================================
# PROCESAMIENTO DEL PACIENTE ACTIVO PARA EL ESTUDIO
# ==================================================
rut = ""
paciente_existente = None
nombres = apellido_paterno = apellido_materno = sexo = telefono = email_paciente = ""
fecha_nacimiento = date(2000, 1, 1)

if rut_seleccionado:
    rut = rut_seleccionado
    _session = SessionLocal()
    try:
        paciente_existente = _session.query(Paciente).filter(Paciente.rut == rut_seleccionado).first()
        
        if paciente_existente:
            nombre_completo = f"{paciente_existente.nombres} {paciente_existente.apellido_paterno} {paciente_existente.apellido_materno or ''}".strip()
            
            edad_str = "—"
            if paciente_existente.fecha_nacimiento:
                hoy = date.today()
                fn = paciente_existente.fecha_nacimiento
                edad = hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
                edad_str = f"{edad} años"
            
            st.success(f"✅ **Paciente seleccionado:** {nombre_completo} | **RUT:** {paciente_existente.rut} | **Edad:** {edad_str} | **Sexo:** {paciente_existente.sexo or '—'}")
            
            with st.expander("✏️ Ver / Modificar datos del paciente", expanded=False):
                v_nom = paciente_existente.nombres
                v_ap = paciente_existente.apellido_paterno
                v_am = paciente_existente.apellido_materno or ""
                v_fn = paciente_existente.fecha_nacimiento or date(2000, 1, 1)
                
                opts_prev = ["", "Fonasa", "Isapre", "Otra"]
                v_prev = getattr(paciente_existente, 'prevision', "")
                idx_prev = opts_prev.index(v_prev) if v_prev in opts_prev else 0
                
                opts_sexo = ["", "Masculino", "Femenino"]
                v_sexo = paciente_existente.sexo or ""
                idx_sexo = opts_sexo.index(v_sexo) if v_sexo in opts_sexo else 0
                
                v_fono = getattr(paciente_existente, 'fono_fijo', "") or ""
                v_cel = paciente_existente.telefono or ""
                v_email = paciente_existente.email or ""

                with st.form(key=f"form_edit_paciente_{paciente_existente.rut}"):
                    c1, c2, c3, c4 = st.columns(4)
                    mod_rut = c1.text_input("RUT", value=paciente_existente.rut, disabled=True, help="El RUT no se puede modificar.")
                    mod_nom = c2.text_input("Nombres", value=v_nom)
                    mod_ap = c3.text_input("Apellido paterno", value=v_ap)
                    mod_am = c4.text_input("Apellido materno", value=v_am)
                    
                    c5, c6, c7, c8 = st.columns(4)
                    mod_fn = c5.date_input("Fecha nacimiento", value=v_fn, min_value=date(1900, 1, 1), max_value=date.today(), format="DD/MM/YYYY")
                    
                    hoy = date.today()
                    edad_calc = hoy.year - mod_fn.year - ((hoy.month, hoy.day) < (mod_fn.month, mod_fn.day))
                    c6.text_input("Edad Real", value=f"{edad_calc} años", disabled=True)
                    
                    mod_prev = c7.selectbox("Previsión", opts_prev, index=idx_prev)
                    mod_sexo = c8.selectbox("Sexo", opts_sexo, index=idx_sexo)
                    
                    c9, c10, c11 = st.columns(3)
                    mod_fono = c9.text_input("Fono fijo", value=v_fono)
                    mod_cel = c10.text_input("Celular", value=v_cel)
                    mod_email = c11.text_input("Email", value=v_email)
                    
                    if st.form_submit_button("💾 Actualizar Ficha del Paciente", type="primary"):
                        session_upd = SessionLocal()
                        try:
                            paciente_edit = session_upd.query(Paciente).filter(Paciente.rut == paciente_existente.rut).first()
                            if paciente_edit:
                                paciente_edit.nombres = mod_nom
                                paciente_edit.apellido_paterno = mod_ap
                                paciente_edit.apellido_materno = mod_am
                                paciente_edit.fecha_nacimiento = mod_fn
                                paciente_edit.sexo = mod_sexo if mod_sexo else None
                                paciente_edit.telefono = mod_cel if mod_cel else None
                                paciente_edit.email = mod_email if mod_email else None
                                if hasattr(paciente_edit, 'prevision'): paciente_edit.prevision = mod_prev
                                if hasattr(paciente_edit, 'fono_fijo'): paciente_edit.fono_fijo = mod_fono
                                
                                session_upd.commit()
                                st.success("✅ Datos del paciente actualizados con éxito.")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Error actualizando datos: {e}")
                        finally:
                            session_upd.close()

            st.session_state["paciente_existente_sexo"] = paciente_existente.sexo
            nombres = paciente_existente.nombres
            apellido_paterno = paciente_existente.apellido_paterno
            apellido_materno = paciente_existente.apellido_materno
            fecha_nacimiento = paciente_existente.fecha_nacimiento
            sexo = paciente_existente.sexo
            
    except Exception as e:
        st.error(f"Error procesando los datos de la ficha clínica: {e}")
    finally:
        _session.close()
else:
    st.session_state["paciente_existente_sexo"] = None
    st.info("💡 Por favor, busque y seleccione un paciente existente, o registre uno nuevo para comenzar a capturar las mediciones del estudio.")
    st.stop()

# ==================================================
# IMAGEN ADJUNTA (OPCIONAL)
# ==================================================
# Se ubica justo después de los datos del paciente (nombre, RUT, talla, etc.)
# y antes de las mediciones, replicando el mismo orden en que aparecerá
# dentro del PDF generado.
st.markdown("<br>", unsafe_allow_html=True)
st.subheader("🖼️ Imagen del estudio (opcional)")
@st.cache_data(show_spinner=False)
def normalizar_imagen(datos: bytes):
    """
    Devuelve la imagen como JPEG con la orientación ya corregida.

    Las fotos de celular suelen guardarse "acostadas" y traen una etiqueta
    EXIF que indica cómo girarlas. Aquí se aplica ese giro a los píxeles y
    se elimina la etiqueta, para que la vista previa y el PDF muestren
    exactamente lo mismo, sin importar si el archivo era JPG, PNG o HEIC.
    """
    try:
        img = Image.open(io.BytesIO(datos))
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            if "A" in img.getbands():
                fondo = Image.new("RGB", img.size, "white")
                fondo.paste(img, mask=img.getchannel("A"))
                img = fondo
            else:
                img = img.convert("RGB")
        img.thumbnail((2000, 2000))  # reduce fotos de 10+ MB sin perder calidad útil
        salida = io.BytesIO()
        img.save(salida, format="JPEG", quality=90, optimize=True)
        return salida.getvalue()
    except Exception:
        return None


imagenes_adjuntas = st.file_uploader(
    "Adjuntar imágenes (ecocardiografía, ECG, etc.)",
    type=_TIPOS_IMAGEN,
    accept_multiple_files=True,
    key="imagen_estudio_uploader",
    help="Opcional. Se insertarán en el PDF antes de las mediciones (máx. 10)."
)

imagenes_normalizadas = []
if imagenes_adjuntas:
    for archivo in imagenes_adjuntas[:10]:
        datos_ok = normalizar_imagen(archivo.getvalue())
        if datos_ok is None:
            st.warning(f"No se pudo leer la imagen «{archivo.name}». Se omitirá.")
            continue
        imagenes_normalizadas.append((archivo.name, datos_ok))

    if len(imagenes_adjuntas) > 10:
        st.warning("Solo se incluirán las primeras 10 imágenes.")

    cols_prev = st.columns(3)
    for i, (nombre, datos_ok) in enumerate(imagenes_normalizadas):
        cols_prev[i % 3].image(datos_ok, caption=nombre, width=200)

# ==================================================
# MEDICIONES Y DATOS GENERALES (SISTEMA DE PESTAÑAS)
# ================================================== 
# USUARIO AUTENTICADO 
usuario_actual = st.session_state.get("usuario_actual", {})
rol_usuario = usuario_actual.get("rol", "")
nombre_usuario = usuario_actual.get("nombre", "")

st.divider()
st.subheader("Datos Generales y Mediciones Ecocardiográficas")

valores = {}

categorias_tabs = ["Datos Generales"] + list(tabs_estructura.keys()) + ["📝 Informe Clínico"]
tabs = st.tabs(categorias_tabs)

# --- PESTAÑA 1: DATOS GENERALES --- 
with tabs[0]:
    st.markdown("<br>", unsafe_allow_html=True)

    # Restaurar campos que pertenecen al estudio actual antes de crear los widgets.
    _restaurar_campo_estudio("medico_seleccionado_estudio", "Seleccione")
    _restaurar_campo_estudio("medico_otro_estudio", "")
    _restaurar_campo_estudio("tipo_estudio", "Ecocardiograma Transtorácico")
    _restaurar_campo_estudio("fecha_estudio", date.today())
    _restaurar_campo_estudio("ficha_clinica", "")
    _restaurar_campo_estudio("patologias_seleccionadas", [])
    _restaurar_campo_estudio("otra_patologia", "")
    _restaurar_campo_estudio("procedencia", "")
    _restaurar_campo_estudio("destino", "")
    _restaurar_campo_estudio("peso_input", "")
    _restaurar_campo_estudio("talla_input", "")
    _restaurar_campo_estudio("pas", "")
    _restaurar_campo_estudio("pad", "")
    _restaurar_campo_estudio("ritmo", "")
    _restaurar_campo_estudio("fcia", "")
    _restaurar_campo_estudio("observaciones", "")

    col1, col2, col3, col4 = st.columns([3, 3, 1.5, 1.5])
    with col1:
        if rol_usuario == "Cardiólogo":
            medico = nombre_usuario
            medico_seleccionado = nombre_usuario
            st.text_input("Médico responsable", value=medico, disabled=True)
        else:
            opciones_selector = st.session_state["lista_medicos_bd"] + ["Otro..."]
            medico_seleccionado = st.selectbox(
                "Médico responsable", opciones_selector, key="medico_seleccionado_estudio"
            )
            if medico_seleccionado == "Otro...":
                medico = st.text_input(
                    "Especifique el médico", placeholder="Nombre del médico",
                    key="medico_otro_estudio"
                )
            else:
                medico = medico_seleccionado

    tipos_estudio = ["Ecocardiograma Transtorácico", "Ecocardiograma Transesofágico", "Ecocardiograma de Estrés", "Ecocardiograma 3D"]
    with col2:
        tipo_estudio = st.selectbox("Tipo de estudio", tipos_estudio, key="tipo_estudio")
    with col3:
        fecha_estudio = st.date_input("Fecha estudio", format="DD/MM/YYYY", key="fecha_estudio")
    with col4:
        ficha_clinica = st.text_input("Ficha Clínica", key="ficha_clinica")

    col5, col6, col7 = st.columns(3)
    with col5:
        opciones_patologia = [
            "Sin antecedentes", "Hipertensión arterial (HTA)", "Diabetes Mellitus tipo 2",
            "Dislipidemia", "Cardiopatía coronaria", "Fibrilación auricular",
            "Insuficiencia cardíaca", "Enfermedad renal crónica", "EPOC", "Obesidad",
            "Hipotiroidismo", "Tabaquismo", "Valvulopatía", "Cardiopatía congénita", "Otro..."
        ]
        patologias_seleccionadas = st.multiselect(
            "Patología de base", opciones_patologia,
            placeholder="Selecciona una o más patologías", key="patologias_seleccionadas"
        )
        otra_patologia = ""
        if "Otro..." in patologias_seleccionadas:
            otra_patologia = st.text_input(
                "Especifique la(s) otra(s) patología(s)",
                placeholder="Ej: Enfermedad de Chagas, etc.", key="otra_patologia"
            )
        lista_patologias_final = [p for p in patologias_seleccionadas if p != "Otro..."]
        if otra_patologia.strip():
            lista_patologias_final.append(otra_patologia.strip())
        diagnostico = ", ".join(lista_patologias_final)
    with col6:
        procedencia = st.text_input("Servicio de origen", placeholder="Ej: HRT, CESFAM, Dr. Eric Fuentes, etc.", key="procedencia")
    with col7:
        destino = st.text_input("Servicio de destino", placeholder="Ej: HRT, CESFAM, etc.", key="destino")

    cv1, cv2, cv3, cv4, cv5, cv6, cv7, cv8 = st.columns([1, 1, 1, 1, 1, 1, 2, 1])
    with cv1: peso = st.text_input("PESO (kg)", key="peso_input",
                                   on_change=on_change_campo_general, args=("peso_input",))
    with cv2: talla = st.text_input("TALLA (cm)", key="talla_input",
                                    on_change=on_change_campo_general, args=("talla_input",))
    with cv3: asc = st.text_input("ASC", value=st.session_state.asc_val, disabled=True)
    with cv4: imc = st.text_input("IMC", value=st.session_state.imc_val, disabled=True)
    with cv5: pas = st.text_input("PAS", key="pas",
                                  on_change=on_change_campo_general, args=("pas",))
    with cv6: pad = st.text_input("PAD", key="pad",
                                  on_change=on_change_campo_general, args=("pad",))
    with cv7: ritmo = st.selectbox("Ritmo", ["", "Sinusal", "Sinusal con ESV", "Sinusal con EV", "Taquicardia sinusal", "Braquicardia sinusal", "Fibrilación auricular", "Flutter auricular", "Marcapaso", "Otro"], key="ritmo")
    with cv8: fcia = st.text_input("FCia", key="fcia",
                                   on_change=on_change_campo_general, args=("fcia",))

    observaciones = st.text_area("Observaciones Generales", key="observaciones")

    # Guardar una copia temporal en cada rerun, sin tocar la base de datos.
    _guardar_campos_estudio_temporales()
    _guardar_snapshot_paciente_actual()

# --- PESTAÑAS RESTANTES: VARIABLES DINÁMICAS ---
num_categorias_dinamicas = len(tabs_estructura.keys())
for tab, nombre_tab in zip(tabs[1:num_categorias_dinamicas+1], categorias_tabs[1:num_categorias_dinamicas+1]):
    with tab:
        st.markdown("<br>", unsafe_allow_html=True)
        subcategorias = tabs_estructura[nombre_tab]
        
        for nombre_subcat, vars_categoria in subcategorias.items():
            if nombre_tab in ["Válvulas", "Cavidades y aorta"]:
                st.markdown(f"<h5 style='color:#2B6CB0; margin-top:5px; margin-bottom:0px;'>{nombre_subcat}</h5>", unsafe_allow_html=True)
                st.markdown("<hr style='margin-top: 5px; margin-bottom: 15px;'>", unsafe_allow_html=True)

            for i in range(0, len(vars_categoria), 3):
                grupo_fila = vars_categoria[i:i+3]
                cols = st.columns(3)
                for variable, col in zip(grupo_fila, cols):
                    valores[variable.codigo] = renderizar_variable(variable, col)

# Bloqueo al teclear en todos los campos numéricos de la página
# (generales + variables). La validación de Python sigue como respaldo.
inyectar_bloqueo_numerico(CAMPOS_NUMERICOS_PAGINA)

# --- ÚLTIMA PESTAÑA: INFORME CLÍNICO EDITABLE ---
def obtener_valores_reales():
    """Obtiene únicamente los inputs actualmente existentes en la sesión."""
    return {
        k.replace("var_", ""): v
        for k, v in st.session_state.items()
        if k.startswith("var_") and str(v).strip() != ""
    }


def obtener_valor_alias(valores_dict, *codigos):
    """Devuelve el primer código con contenido. Permite tolerar nombres de
    variables diferentes entre versiones de la base de datos/Excel."""
    for codigo in codigos:
        if codigo in valores_dict and str(valores_dict[codigo]).strip() != "":
            return valores_dict[codigo]
    return None


def obtener_numero_alias(valores_dict, *codigos):
    valor = obtener_valor_alias(valores_dict, *codigos)
    return _to_float(valor)


def formato_numero(valor, decimales=1):
    if valor is None:
        return None
    return f"{valor:.{decimales}f}".replace(".", ",")


def texto_cualitativo(valores_dict, *codigos):
    valor = obtener_valor_alias(valores_dict, *codigos)
    return _normalizar_texto(valor) if valor is not None else None


def construir_informe_automatico(valores_dict, sexo_paciente, ritmo=None, fc=None, asc=None, imc=None):
    """
    Redacción automática del informe en pantalla.

    Usa el MISMO motor que el PDF (utils/pdf_informe.py), para que la
    pestaña "Informe Clínico" y el PDF digan exactamente lo mismo.
    No asume normalidad cuando falta una medición.
    """
    valores = {
        _normalizar_codigo_informe(k): v
        for k, v in valores_dict.items()
        if v is not None and str(v).strip() != ""
    }
    resultado = motor_informe(valores, sexo_paciente, ritmo=ritmo, fc=fc, asc=asc, imc=imc)
    return informe_a_texto_agrupado(resultado)


def _grado_integrado_aortico(auto):
    """Integra Vmax, gradiente, AVA e IVD sin inventar datos faltantes."""
    grados = [
        auto.get("GRADO_ESTENOSIS_AO_VPEAK"),
        auto.get("GRADO_ESTENOSIS_AO_GDTE"),
        auto.get("GRADO_ESTENOSIS_AO_AVAO"),
        auto.get("GRADO_ESTENOSIS_AO_IVD"),
    ]
    grados = [g for g in grados if g]
    if not grados:
        return None
    # Si existe evidencia severa, se informa severidad; si solo hay datos
    # intermedios se evita sobreinterpretar.
    if grados.count("Severa") >= 2:
        return "Severa"
    if "Severa" in grados and len(grados) == 1:
        return "Severa"
    if "Moderada" in grados:
        return "Moderada"
    if "Leve" in grados or "Normal/Leve" in grados:
        return "Leve"
    return None


def _grado_estenosis_mitral_integrado(auto):
    grados = [auto.get("GRADO_ESTENOSIS_MITRAL_AREA"), auto.get("GRADO_ESTENOSIS_MITRAL_GDTE")]
    grados = [g for g in grados if g and g != "Normal"]
    if not grados:
        return "Normal" if auto.get("GRADO_ESTENOSIS_MITRAL_AREA") == "Normal" or auto.get("GRADO_ESTENOSIS_MITRAL_GDTE") == "Normal" else None
    if "Severa" in grados:
        return "Severa"
    if "Moderada" in grados:
        return "Moderada"
    return "Leve"


def _grado_rm_integrado(auto):
    grados = [auto.get("GRADO_RM_VC"), auto.get("GRADO_RM_EROA"), auto.get("GRADO_RM_VOL")]
    grados = [g for g in grados if g]
    if not grados:
        return None
    if "Severa" in grados:
        return "Severa"
    if "Moderada" in grados:
        return "Moderada"
    return "Leve"


with tabs[-1]:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 📝 Redacción del Informe Clínico")

    valores_reales = obtener_valores_reales()
    sexo_paciente = st.session_state.get("paciente_existente_sexo") or st.session_state.get("sexo_input", "")
    texto_automatico_findings, texto_automatico_conclusiones = construir_informe_automatico(
        valores_reales,
        sexo_paciente,
        ritmo=st.session_state.get("ritmo"),
        fc=st.session_state.get("fcia"),
        asc=st.session_state.get("asc_val"),
        imc=st.session_state.get("imc_val"),
    )

    # Session State evita que Streamlit borre las modificaciones manuales
    # del médico cada vez que se produce un rerun.
    if "hallazgos_editables" not in st.session_state:
        st.session_state["hallazgos_editables"] = st.session_state["borrador_estudio"].get("hallazgos_editables", texto_automatico_findings)
    if "conclusiones_editables" not in st.session_state:
        st.session_state["conclusiones_editables"] = st.session_state["borrador_estudio"].get("conclusiones_editables", texto_automatico_conclusiones)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("↻ Regenerar informe automático", use_container_width=True):
            st.session_state["hallazgos_editables"] = texto_automatico_findings
            st.session_state["conclusiones_editables"] = texto_automatico_conclusiones
            st.rerun()
    with c2:
        st.caption("El informe se genera solo con variables ingresadas. Los campos faltantes no se interpretan como normales.")

    findings_editado = st.text_area(
        "Hallazgos / Descripción (modificable)",
        key="hallazgos_editables",
        height=350
    )
    conclusiones_editadas = st.text_area(
        "Conclusiones (modificable)",
        key="conclusiones_editables",
        height=220
    )
    st.session_state["borrador_estudio"]["hallazgos_editables"] = st.session_state.get("hallazgos_editables", "")
    st.session_state["borrador_estudio"]["conclusiones_editables"] = st.session_state.get("conclusiones_editables", "")


# ==================================================
# CLASIFICACIONES AUTOMÁTICAS (TARJETAS)
# ==================================================
def mostrar_tarjetas_informativas():
    valores_sesion_actual = {k.replace("var_", ""): v for k, v in st.session_state.items() if k.startswith("var_")}
    sexo_p = st.session_state.get("paciente_existente_sexo") or st.session_state.get("sexo_input", "")
    auto = clasificar_automatico(valores_sesion_actual, sexo_p)
    if not auto: return

    ETIQUETAS = {
        "GRADO_DILATACION_AI": "Dilatación AI", "GRADO_DERRAME_PERICARDICO": "Derrame pericárdico", "GRADO_HIPERTROFIA_VI": "Hipertrofia VI",
        "PSAP_GRADO": "HTP (PsAP)", "GRADO_ESTENOSIS_AO_VPEAK": "Estenosis Ao (V Peak)", "GRADO_ESTENOSIS_AO_GDTE": "Estenosis Ao (Gdte)",
        "GRADO_ESTENOSIS_AO_AVAO": "Estenosis Ao (AVAo)", "GRADO_ESTENOSIS_AO_IVD": "Estenosis Ao (IVD)", "GRADO_TAP": "HTP (TAP)",
        "GRADO_WILKINS": "Score Wilkins", "GRADO_ESTENOSIS_MITRAL_AREA": "Estenosis mitral (Área)", "GRADO_ESTENOSIS_MITRAL_GDTE": "Estenosis mitral (Gdte)",
        "GRADO_RM_VC": "Reflujo mitral (VC)", "GRADO_RM_EROA": "Reflujo mitral (EROA)", "GRADO_RM_VOL": "Reflujo mitral (Vol Rg)",
    }
    COLORES = {
        "Normal": ("#276749", "#C6F6D5"), "Favorable": ("#276749", "#C6F6D5"), "Sin derrame": ("#276749", "#C6F6D5"), "Normal/Leve": ("#276749", "#C6F6D5"),
        "Leve": ("#744210", "#FEFCBF"), "Límite": ("#744210", "#FEFCBF"), "Intermedio": ("#744210", "#FEFCBF"), "Moderada": ("#7B341E", "#FEEBC8"),
        "Moderado": ("#7B341E", "#FEEBC8"), "Severa": ("#822727", "#FED7D7"), "Severo": ("#822727", "#FED7D7"), "Desfavorable": ("#822727", "#FED7D7"), "Sugerente de HTP": ("#822727", "#FED7D7"),
    }

    st.divider()
    st.markdown("#### 🔢 Resumen de Riesgos Detectados")
    cols = st.columns(4)
    for i, (codigo, valor) in enumerate(auto.items()):
        etiqueta = ETIQUETAS.get(codigo, codigo)
        color_texto, color_fondo = COLORES.get(valor, ("#4A5568", "#EDF2F7"))
        with cols[i % 4]:
            st.markdown(f"<div style='background:{color_fondo}; border-radius:8px; padding:8px 12px; margin-bottom:8px;'><div style='font-size:11px; color:{color_texto}; opacity:0.8;'>{etiqueta}</div><div style='font-size:15px; font-weight:600; color:{color_texto};'>{valor}</div></div>", unsafe_allow_html=True)

mostrar_tarjetas_informativas()


# ==================================================
# BOTÓN PDF Y GUARDAR
# ==================================================
class _EstudioSimulado: pass
est_sim = _EstudioSimulado()
est_sim.fecha_estudio, est_sim.tipo_estudio, est_sim.medico, est_sim.diagnostico, est_sim.motivo, est_sim.fecha_creacion = fecha_estudio, tipo_estudio, medico, diagnostico, "", None
est_sim.procedencia = procedencia
est_sim.asc_valor = st.session_state.asc_val
est_sim.imc = st.session_state.imc_val
est_sim.ritmo = ritmo
est_sim.fcia = fcia
est_sim.pas = pas
est_sim.pad = pad
est_sim.observaciones = f"{observaciones}\n\n[HALLAZGOS]:\n{findings_editado}\n\n[CONCLUSIONES]:\n{conclusiones_editadas}"

class _MedSimulada: pass
mediciones_pdf = []
for codigo, valor in valores.items():
    if not valor or str(valor).strip() == "": continue
    var = variables_por_codigo.get(codigo)
    if not var: continue
    m = _MedSimulada()
    if not asignar_valor_medicion(m, var, valor):
        continue  # dato inválido: no se incluye en el PDF
    m.codigo_variable = codigo
    mediciones_pdf.append((m, var))

st.divider()

# Solo generar y permitir descarga de PDF si hay un paciente seleccionado
# ==================================================
# PDF: generar una sola vez y conservarlo en memoria
# para poder guardarlo junto al estudio.
# ==================================================
pdf_data = None
pdf_nombre_archivo = None

if paciente_existente:
    imagenes_bytes = (
        [datos for _, datos in imagenes_normalizadas] or None
    )
    pdf_data = generar_pdf_desde_historial(
        est_sim,
        paciente_existente,
        mediciones_pdf,
        imagenes=imagenes_bytes,
    )

    pdf_nombre_archivo = (
        f"Informe_Ecocardiograma_"
        f"{rut.strip().replace('.', '').replace('-', '')}_"
        f"{fecha_estudio.strftime('%Y%m%d')}.pdf"
    )

    st.download_button(
        label="📥 Generar e Imprimir PDF del Informe",
        data=pdf_data,
        file_name=pdf_nombre_archivo,
        mime="application/pdf",
    )

st.markdown("<br>", unsafe_allow_html=True)

# Snapshot final de seguridad: temporal, sin escribir en PostgreSQL.
if st.session_state.get("paciente_estudio_activo"):
    _guardar_snapshot_paciente_actual()

# ==================================================
# GUARDADO DEFINITIVO DEL INFORME
# ==================================================
def _str_to_float_guardado(val):
    try:
        return float(str(val).replace(",", ".")) if val not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _str_to_int_guardado(val):
    """Acepta "120" o "120,0"; rechaza "120,5" (no es entero)."""
    numero = convertir_numero(val)
    if numero is None:
        return None
    if isinstance(numero, float):
        return int(numero) if numero.is_integer() else None
    return numero


def guardar_informe_definitivo():
    """Guarda el informe en BD solo cuando el usuario decide finalizarlo."""
    if not rut or not paciente_existente:
        st.error("❌ Debe buscar y seleccionar un paciente existente antes de guardar el informe.")
        return False

    # "Seleccione" es el texto inicial del selector, no un médico.
    if not str(medico or "").strip() or str(medico).strip() in ("Seleccione", "Otro..."):
        st.error("❌ Seleccione el médico responsable antes de guardar el informe.")
        return False

    for codigo, valor in valores.items():
        variable = variables_por_codigo[codigo]
        if variable.obligatoria == "SI" and str(valor).strip() == "":
            st.error(f"❌ Debe completar: {variable.nombre}")
            return False

    # Ningún dato con formato incorrecto llega a la base de datos.
    invalidas = []
    for key_general in CAMPOS_GENERALES:
        _, error = validar_campo_general(key_general)
        if error:
            invalidas.append(error)

    for codigo, valor in valores.items():
        if valor is None or str(valor).strip() == "":
            continue
        variable = variables_por_codigo[codigo]
        if tipo_variable(variable) == "numero":
            _, error_num = validar_valor_variable(variable, valor)
            if error_num:
                invalidas.append(error_num)
        elif tipo_variable(variable) == "categoria" and convertir_categoria(valor, variable.opciones) is None:
            invalidas.append(f"{variable.nombre}: «{valor}» no es una opción válida")
    if invalidas:
        st.error("❌ Corrija estos datos antes de guardar:\n\n- " + "\n- ".join(invalidas))
        return False

    session = SessionLocal()
    try:
        estudio = Estudio(
            paciente_rut=rut.strip(),
            fecha_estudio=fecha_estudio,
            tipo_estudio=tipo_estudio,
            medico=medico,
            diagnostico=diagnostico,
            procedencia=procedencia,
            ficha_clinica=ficha_clinica,
            peso=_str_to_float_guardado(peso),
            talla=_str_to_float_guardado(talla),
            asc_valor=_str_to_float_guardado(st.session_state.asc_val),
            imc=_str_to_float_guardado(st.session_state.imc_val),
            pas=_str_to_int_guardado(pas),
            pad=_str_to_int_guardado(pad),
            ritmo=ritmo,
            fcia=_str_to_int_guardado(fcia),
            observaciones=(
                f"{observaciones}\n\n[HALLAZGOS]:\n{findings_editado}"
                f"\n\n[CONCLUSIONES]:\n{conclusiones_editadas}"
            ),
        )
        session.add(estudio)
        session.flush()

        if pdf_data is not None and hasattr(estudio, "pdf_original"):
            estudio.pdf_original = pdf_data
        if pdf_nombre_archivo and hasattr(estudio, "pdf_nombre_archivo"):
            estudio.pdf_nombre_archivo = pdf_nombre_archivo

        for cod, var_obj in variables_por_codigo.items():
            val_ingresado = valores.get(cod)
            if not val_ingresado or str(val_ingresado).strip() == "":
                continue

            med = Medicion(
                estudio_id=estudio.id,
                variable_id=var_obj.id,
                codigo_variable=cod,
            )
            if not asignar_valor_medicion(med, var_obj, val_ingresado):
                continue  # ya validado arriba; esto es solo una protección extra
            session.add(med)

        session.commit()

        # El informe ya terminó. Se elimina SOLO el borrador de este paciente.
        # Los borradores temporales de otros pacientes siguen disponibles en la sesión.
        if rut in st.session_state.get("borradores_estudios", {}):
            st.session_state["borradores_estudios"].pop(rut, None)
        st.session_state["borrador_estudio"] = {}
        st.session_state.pop("paciente_estudio_activo", None)
        st.session_state.pop("selectbox_todos_estudios", None)
        _limpiar_widgets_estudio()

        st.success("✅ Informe guardado correctamente. Puede comenzar un nuevo estudio.")
        st.balloons()
        return True

    except Exception as e:
        session.rollback()
        st.error(f"❌ Error al guardar el informe en la base de datos: {e}")
        return False
    finally:
        session.close()


if st.button("💾 Guardar informe", type="primary"):
    guardar_informe_definitivo()


# ==================================================
# AVISO DE 10 MINUTOS: SOLO ADVERTENCIA, NO GUARDA EN BD
# ==================================================
if "inicio_edicion_estudio" not in st.session_state:
    st.session_state["inicio_edicion_estudio"] = datetime.now()

if hasattr(st, "dialog"):
    @st.dialog("Advertencia de guardado")
    def mostrar_aviso_guardado():
        st.warning(
            "Han pasado 10 minutos desde que comenzó la edición. "
            "Los datos siguen en edición temporal y todavía no se han guardado en la base de datos. "
            "Recuerde guardar el informe cuando termine."
        )
        if st.button("Continuar editando", type="primary", key="continuar_sin_guardar"):
            st.session_state["inicio_edicion_estudio"] = datetime.now()
            st.rerun()


if hasattr(st, "fragment"):
    @st.fragment(run_every="10m")
    def aviso_automatico_guardado():
        if not paciente_existente or not rut or not st.session_state.get("borrador_estudio"):
            return
        inicio = st.session_state.get("inicio_edicion_estudio")
        if inicio is None:
            st.session_state["inicio_edicion_estudio"] = datetime.now()
            return
        if (datetime.now() - inicio).total_seconds() >= 600:
            # Autoguardado temporal: conserva el trabajo en memoria, no en BD.
            _guardar_snapshot_paciente_actual()
            st.session_state["inicio_edicion_estudio"] = datetime.now()
            mostrar_aviso_guardado()

    aviso_automatico_guardado()

