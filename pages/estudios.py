# Archivo: pages/estudios.py
import streamlit as st

# ==================================================
# CONFIGURACIÓN DE PÁGINA (Debe ser la primera instrucción)
# ==================================================
st.set_page_config(page_title="Nuevo Estudio", page_icon="🩺", layout="wide")

from menu import generar_menu

# 1. Dibujar el menú dinámico
generar_menu()

# 2. Candado de seguridad
if not st.session_state.get("autenticado", False):
    st.warning("🛑 Debes iniciar sesión para ver esta página.")
    st.stop()
     
import pandas as pd
from datetime import date, datetime
import io
import re

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from database.database import SessionLocal
from database.models import Paciente, Estudio, Variable, Medicion

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
    variables_db = _session.query(Variable).order_by(Variable.categoria, Variable.nombre).all()
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
            tab_padre = "Ventrículos"
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
def clasificar_automatico(valores, sexo_paciente):
    auto = {}

    def obtener_float(codigo):
        v = valores.get(codigo, "")
        if v and str(v).strip():
            try: return int(str(v).replace(",", "."))
            except ValueError:
                try: return float(str(v).replace(",", "."))
                except ValueError: return None
        return None 

    vol_ai = obtener_float("VOLUMEN_AI")
    if vol_ai is not None:
        if vol_ai <= 34: auto["GRADO_DILATACION_AI"] = "Normal"
        elif vol_ai <= 41: auto["GRADO_DILATACION_AI"] = "Leve"
        elif vol_ai <= 48: auto["GRADO_DILATACION_AI"] = "Moderada"
        else: auto["GRADO_DILATACION_AI"] = "Severa"

    derrame = obtener_float("MAGNITUD_DERRAME_PERICARDICO")
    if derrame is not None:
        if derrame == 0: auto["GRADO_DERRAME_PERICARDICO"] = "Sin derrame"
        elif derrame <= 10: auto["GRADO_DERRAME_PERICARDICO"] = "Leve"
        elif derrame <= 20: auto["GRADO_DERRAME_PERICARDICO"] = "Moderado"
        else: auto["GRADO_DERRAME_PERICARDICO"] = "Severo"

    masa_idx = obtener_float("MASA_VI_INDEXADA")
    if masa_idx is not None and sexo_paciente:
        es_hombre = sexo_paciente in ("Masculino", "M")
        if es_hombre:
            if masa_idx <= 115: auto["GRADO_HIPERTROFIA_VI"] = "Normal"
            elif masa_idx <= 131: auto["GRADO_HIPERTROFIA_VI"] = "Leve"
            elif masa_idx <= 148: auto["GRADO_HIPERTROFIA_VI"] = "Moderada"
            else: auto["GRADO_HIPERTROFIA_VI"] = "Severa"
        else:
            if masa_idx <= 95: auto["GRADO_HIPERTROFIA_VI"] = "Normal"
            elif masa_idx <= 108: auto["GRADO_HIPERTROFIA_VI"] = "Leve"
            elif masa_idx <= 121: auto["GRADO_HIPERTROFIA_VI"] = "Moderada"
            else: auto["GRADO_HIPERTROFIA_VI"] = "Severa"

    psap = obtener_float("PSAP")
    if psap is not None:
        if psap <= 35: auto["PSAP_GRADO"] = "Normal"
        elif psap <= 50: auto["PSAP_GRADO"] = "Leve"
        elif psap <= 70: auto["PSAP_GRADO"] = "Moderada"
        else: auto["PSAP_GRADO"] = "Severa"

    vpeak_ao = obtener_float("VELOCIDAD_PICO_AORTICA")
    if vpeak_ao is not None:
        if vpeak_ao < 2.0: auto["GRADO_ESTENOSIS_AO_VPEAK"] = "Normal"
        elif vpeak_ao < 3.0: auto["GRADO_ESTENOSIS_AO_VPEAK"] = "Leve"
        elif vpeak_ao < 4.0: auto["GRADO_ESTENOSIS_AO_VPEAK"] = "Moderada"
        else: auto["GRADO_ESTENOSIS_AO_VPEAK"] = "Severa"

    gdte_ao = obtener_float("GRADIENTE_MEDIO_AORTICO")
    if gdte_ao is not None:
        if gdte_ao < 20: auto["GRADO_ESTENOSIS_AO_GDTE"] = "Normal/Leve"
        elif gdte_ao < 40: auto["GRADO_ESTENOSIS_AO_GDTE"] = "Moderada"
        else: auto["GRADO_ESTENOSIS_AO_GDTE"] = "Severa"

    avao = obtener_float("AREA_VALVULAR_AORTICA_CONTINUIDAD")
    if avao is not None:
        if avao > 1.5: auto["GRADO_ESTENOSIS_AO_AVAO"] = "Leve"
        elif avao >= 1.0: auto["GRADO_ESTENOSIS_AO_AVAO"] = "Moderada"
        else: auto["GRADO_ESTENOSIS_AO_AVAO"] = "Severa"

    ivd = obtener_float("INDICE_VELOCIDAD_DOPPLER")
    if ivd is not None:
        if ivd > 0.50: auto["GRADO_ESTENOSIS_AO_IVD"] = "Normal"
        elif ivd >= 0.25: auto["GRADO_ESTENOSIS_AO_IVD"] = "Moderada"
        else: auto["GRADO_ESTENOSIS_AO_IVD"] = "Severa"

    tap = obtener_float("TIEMPO_ACELERACION_PULMONAR")
    if tap is not None:
        if tap > 120: auto["GRADO_TAP"] = "Normal"
        elif tap >= 100: auto["GRADO_TAP"] = "Límite"
        else: auto["GRADO_TAP"] = "Sugerente de HTP"

    wilkins = obtener_float("SCORE_WILKINS")
    if wilkins is not None:
        if wilkins <= 8: auto["GRADO_WILKINS"] = "Favorable"
        elif wilkins <= 11: auto["GRADO_WILKINS"] = "Intermedio"
        else: auto["GRADO_WILKINS"] = "Desfavorable"

    area_mit = obtener_float("AREA_MITRAL")
    if area_mit is not None:
        if area_mit >= 4.0: auto["GRADO_ESTENOSIS_MITRAL_AREA"] = "Normal"
        elif area_mit > 1.5: auto["GRADO_ESTENOSIS_MITRAL_AREA"] = "Leve"
        elif area_mit >= 1.1: auto["GRADO_ESTENOSIS_MITRAL_AREA"] = "Moderada"
        else: auto["GRADO_ESTENOSIS_MITRAL_AREA"] = "Severa"

    gdte_mit = obtener_float("GRADIENTE_MEDIO_MITRAL")
    if gdte_mit is not None:
        if gdte_mit <= 5: auto["GRADO_ESTENOSIS_MITRAL_GDTE"] = "Normal"
        elif gdte_mit <= 10: auto["GRADO_ESTENOSIS_MITRAL_GDTE"] = "Moderada"
        else: auto["GRADO_ESTENOSIS_MITRAL_GDTE"] = "Severa"

    vc_mit = obtener_float("VENA_CONTRACTA_MITRAL")
    if vc_mit is not None:
        if vc_mit < 3: auto["GRADO_RM_VC"] = "Leve"
        elif vc_mit < 7: auto["GRADO_RM_VC"] = "Moderada"
        else: auto["GRADO_RM_VC"] = "Severa"

    eroa_mit = obtener_float("EROA_MITRAL")
    if eroa_mit is not None:
        if eroa_mit < 0.20: auto["GRADO_RM_EROA"] = "Leve"
        elif eroa_mit < 0.40: auto["GRADO_RM_EROA"] = "Moderada"
        else: auto["GRADO_RM_EROA"] = "Severa"

    vol_rg = obtener_float("VOLUMEN_REGURGITANTE_MITRAL")
    if vol_rg is not None:
        if vol_rg < 30: auto["GRADO_RM_VOL"] = "Leve"
        elif vol_rg < 60: auto["GRADO_RM_VOL"] = "Moderada"
        else: auto["GRADO_RM_VOL"] = "Severa"

    return auto

def generar_pdf_desde_historial(estudio, paciente, mediciones_estudio):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )

    # Estilos
    styles = getSampleStyleSheet()
    style_h1 = ParagraphStyle('Header1', fontName='Helvetica-Bold', fontSize=12, leading=14, spaceAfter=10)
    style_h2 = ParagraphStyle('Header2', fontName='Helvetica-Bold', fontSize=10, leading=12, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#1A365D"))
    style_body = ParagraphStyle('Body', fontName='Helvetica', fontSize=9, leading=12)
    style_body_bold = ParagraphStyle('BodyBold', fontName='Helvetica-Bold', fontSize=9, leading=12)
    
    story = []

    # Título
    story.append(Paragraph("<b>Ecocardiograma con EcoCardioNet</b>", style_h1))
    story.append(Spacer(1, 6))

    # Fecha y hora del estudio
    hora_estudio = (estudio.fecha_creacion.strftime('%H:%M') if hasattr(estudio, 'fecha_creacion') and estudio.fecha_creacion else "")
    fecha_str = estudio.fecha_estudio.strftime('%d/%m/%Y')
    
    if hora_estudio:
        texto_fecha = f"<b>Fecha:</b> {fecha_str} &nbsp;&nbsp;&nbsp; <b>Hora:</b> {hora_estudio}"
    else:
        texto_fecha = f"<b>Fecha:</b> {fecha_str}"
        
    story.append(Paragraph(texto_fecha, style_body))
    story.append(Spacer(1, 6))  

    # Header del Paciente
    nombre_p = f"{paciente.nombres} {paciente.apellido_paterno} {paciente.apellido_materno or ''}".strip().upper()
    edad_p = ((datetime.today().date() - paciente.fecha_nacimiento).days // 365 if paciente.fecha_nacimiento else "—")
    prevision_p = paciente.prevision if hasattr(paciente, 'prevision') and paciente.prevision else "—"
    
    # CORRECCIÓN: Se extrae desde 'estudio', no desde 'paciente'
    ficha_clinica_p = estudio.ficha_clinica if hasattr(estudio, 'ficha_clinica') and estudio.ficha_clinica else "—"
    
    asc_val = f"{estudio.asc_valor} m2" if hasattr(estudio, 'asc_valor') and estudio.asc_valor else "—"
    ritmo_val = estudio.ritmo if hasattr(estudio, 'ritmo') and estudio.ritmo else "—"
    fcia_val = f"{estudio.fcia} Lpm" if hasattr(estudio, 'fcia') and estudio.fcia else "—"
    pas_val = estudio.pas if hasattr(estudio, 'pas') and estudio.pas else "___"
    pad_val = estudio.pad if hasattr(estudio, 'pad') and estudio.pad else "___"

    # Matriz reorganizada para balancear perfectamente ambos lados
    data_header = [
        [Paragraph(f"<b>Paciente:</b> {nombre_p}", style_body), Paragraph(f"<b>R.U.T:</b> {paciente.rut}", style_body)],
        [Paragraph(f"<b>ASC:</b> {asc_val}", style_body), Paragraph(f"<b>Ritmo:</b> {ritmo_val} &nbsp;&nbsp; <b>FC:</b> {fcia_val}", style_body)],
        [Paragraph(f"<b>Edad:</b> {edad_p} Años &nbsp;&nbsp;&nbsp;", style_body), Paragraph(f"<b>Previsión:</b> {prevision_p}", style_body)],
        [Paragraph(f"<b>Dg.:</b> {estudio.diagnostico or '—'}", style_body), Paragraph(f"<b>PA:</b> {pas_val} / {pad_val} mm Hg", style_body)],
        [Paragraph(f"<b>Procedencia:</b> {estudio.procedencia or '—'}", style_body), Paragraph(f"<b>Ficha Clínica:</b> {ficha_clinica_p}", style_body)]
    ]  

    t_header = Table(data_header, colWidths=[3.5*inch, 3.5*inch])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(t_header)
    story.append(Spacer(1, 15))
    story.append(Paragraph("<b>Mediciones y Descripción</b>", style_h1))
    story.append(Spacer(1, 5))

    # Agrupar mediciones por categoría
    categorias_pdf = {
        "AORTA Y VÁLVULA AÓRTICA": [],
        "AURÍCULAS Y SEPTUM IA": [],
        "VENTRÍCULO IZQUIERDO": [],
        "VENTRÍCULO DERECHO": [],
        "VÁLVULA MITRAL": [],
        "VÁLVULA TRICÚSPIDE": [],
        "VÁLVULA PULMONAR": [],
        "PERICARDIO": [],
        "OTROS": []
    }

    # Mapeo de categorías
    for m, v in mediciones_estudio:
        cat_orig = (v.categoria or "").upper()
        valor_str = str(m.valor_num) if m.valor_num is not None else (m.valor_texto or "")
        unidad = v.unidad if v and v.unidad else ""
        nombre = v.nombre if v and v.nombre else m.codigo_variable

        dest_cat = "OTROS"
        if "AORTA" in cat_orig and "VÁLVULA" not in cat_orig: dest_cat = "AORTA Y VÁLVULA AÓRTICA"
        elif "AURICULA" in cat_orig or "AURÍCULA" in cat_orig: dest_cat = "AURÍCULAS Y SEPTUM IA"
        elif "IZQUIERDO" in cat_orig: dest_cat = "VENTRÍCULO IZQUIERDO"
        elif "DERECHO" in cat_orig: dest_cat = "VENTRÍCULO DERECHO"
        elif "MITRAL" in cat_orig: dest_cat = "VÁLVULA MITRAL"
        elif "TRICUSP" in cat_orig or "TRICÚSP" in cat_orig: dest_cat = "VÁLVULA TRICÚSPIDE"
        elif "PULMONAR" in cat_orig: dest_cat = "VÁLVULA PULMONAR"
        elif "PERICARDIO" in cat_orig: dest_cat = "PERICARDIO"
        elif "AORTIC" in cat_orig or "AÓRTIC" in cat_orig: dest_cat = "AORTA Y VÁLVULA AÓRTICA"
        
        categorias_pdf[dest_cat].append((nombre, valor_str, unidad))

    # Parsear los "Hallazgos" 
    obs_completas = estudio.observaciones or ""
    hallazgos_str = ""
    conclusiones_str = ""
    
    if "[HALLAZGOS]:" in obs_completas:
        partes = obs_completas.split("[HALLAZGOS]:")
        resto = partes[1]
        if "[CONCLUSIONES]:" in resto:
            hallazgos_str = resto.split("[CONCLUSIONES]:")[0].strip()
            conclusiones_str = resto.split("[CONCLUSIONES]:")[1].strip()
        else:
            hallazgos_str = resto.strip()
    else:
        hallazgos_str = obs_completas

    dict_descripciones = {k: [] for k in categorias_pdf.keys()}
    current_key = "OTROS"

    mapeo_desc = {
        "ventrículo izquierdo": "VENTRÍCULO IZQUIERDO",
        "ventrículo derecho": "VENTRÍCULO DERECHO",
        "aurículas y septum": "AURÍCULAS Y SEPTUM IA",
        "aorta y v. aorta": "AORTA Y VÁLVULA AÓRTICA",
        "válvula mitral": "VÁLVULA MITRAL",
        "válvula tricúspide": "VÁLVULA TRICÚSPIDE",
        "válvula pulmonar": "VÁLVULA PULMONAR",
        "pericardio": "PERICARDIO"
    }

    for linea in hallazgos_str.split('\n'):
        if not linea.strip(): continue
        encontrado = False
        for prefijo, cat_pdf in mapeo_desc.items():
            if linea.lower().startswith(prefijo.lower() + ":"):
                current_key = cat_pdf
                dict_descripciones[current_key].append(linea[len(prefijo)+1:].strip())
                encontrado = True
                break
        
        if not encontrado:
            dict_descripciones[current_key].append(linea.strip())

    for cat, variables in categorias_pdf.items():
        textos_cat = dict_descripciones.get(cat, [])
        if not variables and not textos_cat:
            continue

        story.append(Paragraph(cat, style_h2))

        if variables:
            data_var = []
            for nombre, valor, unidad in variables:
                data_var.append([Paragraph(nombre, style_body), Paragraph(f"<b>{valor}</b>", style_body), Paragraph(unidad, style_body)])
            
            t_var = Table(data_var, colWidths=[2.5*inch, 1*inch, 1.5*inch])
            t_var.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 1),
                ('TOPPADDING', (0,0), (-1,-1), 1),
            ]))
            story.append(t_var)
            story.append(Spacer(1, 4))

        if textos_cat:
            texto_unido = " ".join(textos_cat)
            story.append(Paragraph(texto_unido, style_body))
            story.append(Spacer(1, 6))

    # CONCLUSIONES
    story.append(Spacer(1, 15))
    story.append(Paragraph("<b>Conclusiones:</b>", style_h1))
    
    if conclusiones_str:
        for linea in conclusiones_str.split('\n'):
            if linea.strip():
                story.append(Paragraph(linea.strip(), style_body))
    else:
        story.append(Paragraph("Sin conclusiones registradas.", style_body))

    # FIRMA MEDICO
    story.append(Spacer(1, 50))
    medico_firma = estudio.medico if estudio.medico else "Dr. Eric Fuentes Latorre"
    story.append(Paragraph(f"<b>{medico_firma}</b>", style_body))
    story.append(Paragraph("Cardiólogo Ecocardiografista", style_body))
    story.append(Paragraph("Imagen Cardiaca Avanzada", style_body))

    doc.build(story)
    buffer.seek(0)
    return buffer


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
    
    nuevas_categorias = clasificar_automatico(valores_temp, sexo_pac)
    
    for cod_cat, valor_calculado in nuevas_categorias.items():
        key_cat = f"var_{cod_cat}"
        var_obj = variables_por_codigo.get(cod_cat)
        if var_obj and var_obj.tipo == "categoria":
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

def calcular_asc():
    try:
        p_val = st.session_state.get("peso_input", "").replace(",", ".")
        t_val = st.session_state.get("talla_input", "").replace(",", ".")
        if p_val and t_val:
            p = float(p_val)
            t = float(t_val)
            if p > 0 and t > 0:
                asc_calc = 0.007184 * (p ** 0.425) * (t ** 0.725)
                st.session_state.asc_val = f"{asc_calc:.2f}"
            else:
                st.session_state.asc_val = ""
    except ValueError:
        st.session_state.asc_val = ""

if "asc_val" not in st.session_state:
    st.session_state.asc_val = ""


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
            if variable.tipo == "numero":
                key = f"var_{variable.codigo}"
                valor = st.text_input(
                    "", 
                    key=key,
                    label_visibility="collapsed",
                    on_change=on_numeric_change,
                    kwargs={"codigo_var": variable.codigo}
                )

            elif variable.tipo == "categoria":
                opciones = ([""] + [x.strip() for x in variable.opciones.split(";")] if variable.opciones else [""])
                valor = st.selectbox("", opciones, key=f"var_{variable.codigo}", label_visibility="collapsed")
                
            elif variable.tipo == "booleano":
                valor = st.checkbox("", key=f"var_{variable.codigo}")
            else:
                valor = st.text_input("", key=f"var_{variable.codigo}", label_visibility="collapsed")

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

col_link, col_search, col_seleccion = st.columns([1, 1, 1])

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

        rut_seleccionado = st.selectbox(
            "✅ Seleccionar un paciente existente", 
            options=df_pacientes_todos["RUT"].tolist(),
            index=None,  
            placeholder="Seleccionar 👇",  
            format_func=lambda r: f"{df_pacientes_todos[df_pacientes_todos['RUT'] == r]['Nombre completo'].iloc[0]} ({r})",
            key="selectbox_todos_estudios" # Key única, sin callback conflictivo
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
    else:
        st.warning("No se encontraron pacientes que coincidan con la búsqueda.")

# ==================================================
# FORMULARIO: REGISTRAR NUEVO PACIENTE (INLINE)
# ================================================== 
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

# ==================================================
# MEDICIONES Y DATOS GENERALES (SISTEMA DE PESTAÑAS)
# ==================================================
st.divider()
st.subheader("Datos Generales y Mediciones Ecocardiográficas")

valores = {}

categorias_tabs = ["Datos Generales"] + list(tabs_estructura.keys()) + ["📝 Informe Clínico"]
tabs = st.tabs(categorias_tabs)

# --- PESTAÑA 1: DATOS GENERALES --- 
with tabs[0]:
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: 
        # Construimos las opciones sumando la lista en memoria + "Otro..."
        opciones_selector = st.session_state["lista_medicos_bd"] + ["Otro..."]
        
        medico_seleccionado = st.selectbox("Médico responsable", opciones_selector)
        
        if medico_seleccionado == "Otro...":
            medico = st.text_input("Especifique el médico", placeholder="Nombre del médico")
        else:
            medico = medico_seleccionado
            
    with col2: fecha_estudio = st.date_input("Fecha estudio", value=date.today(), format="DD/MM/YYYY")
    with col3: tipo_estudio = st.selectbox("Tipo de estudio", ["Ecocardiograma Transtorácico", "Ecocardiograma transesofágico (ECO TE)", "Ecocardiograma de estrés", "Ecocardiograma 3D"])
    with col4: ficha_clinica = st.text_input("Ficha Clínica")

    col5, col6, col7 = st.columns(3)
    with col5: diagnostico = st.text_input("Patología de base", placeholder="Ej: HTA, Diabetes tipo 2, etc.")
    with col6: procedencia = st.text_input("Servicio de origen", placeholder="Ej: HRT, CESFAM, Dr. Eric Fuentes, etc.")
    with col7: destino = st.text_input("Servicio de destino", placeholder="Ej: HRT, CESFAM, etc.")
    

    cv1, cv2, cv3, cv4, cv5, cv6, cv7, cv8, cv9 = st.columns([1, 1, 1, 1, 1, 2, 1, 1.1, 1.1])
    with cv1: peso = st.text_input("PESO (kg)", key="peso_input", on_change=calcular_asc)
    with cv2: talla = st.text_input("TALLA (cm)", key="talla_input", on_change=calcular_asc)
    with cv3: asc = st.text_input("ASC", value=st.session_state.asc_val, disabled=True)
    with cv4: pas = st.text_input("PAS")
    with cv5: pad = st.text_input("PAD") 
    with cv6: ritmo = st.selectbox("Ritmo", ["", "Sinusal a", "Sinusal con ESV", "Sinusal con EV", "Taquicardia sinusal", "Braquicardia sinusal", "Fibrilación auricular a", "Flutter auricular a", "Marcapaso", "Otro"])
    with cv7: fcia = st.text_input("FCia")
    with cv8: eco_3d = st.selectbox("ECO 3D", ["", "Si", "No"])
    with cv9: eco_estres = st.selectbox("ECO Estrés", ["", "Si", "No"])

    observaciones = st.text_area("Observaciones Generales")

# --- PESTAÑAS RESTANTES: VARIABLES DINÁMICAS ---
num_categorias_dinamicas = len(tabs_estructura.keys())
for tab, nombre_tab in zip(tabs[1:num_categorias_dinamicas+1], categorias_tabs[1:num_categorias_dinamicas+1]):
    with tab:
        st.markdown("<br>", unsafe_allow_html=True)
        subcategorias = tabs_estructura[nombre_tab]
        
        for nombre_subcat, vars_categoria in subcategorias.items():
            if nombre_tab in ["Válvulas", "Ventrículos"]:
                st.markdown(f"<h5 style='color:#2B6CB0; margin-top:5px; margin-bottom:0px;'>{nombre_subcat}</h5>", unsafe_allow_html=True)
                st.markdown("<hr style='margin-top: 5px; margin-bottom: 15px;'>", unsafe_allow_html=True)

            for i in range(0, len(vars_categoria), 3):
                grupo_fila = vars_categoria[i:i+3]
                cols = st.columns(3)
                for variable, col in zip(grupo_fila, cols):
                    valores[variable.codigo] = renderizar_variable(variable, col)

# --- ÚLTIMA PESTAÑA: INFORME CLÍNICO EDITABLE ---
with tabs[-1]:
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 📝 Redacción del Informe Clínico")

    valores_reales = {k.replace("var_", ""): v for k, v in st.session_state.items() if k.startswith("var_")}

    fevi_val = valores_reales.get("FEVI", "")
    tapse_val = valores_reales.get("TAPSE", "")
    gpr_val = valores_reales.get("GPR", "")
    onda_s_val = valores_reales.get("ONDA_S", "") or valores_reales.get("ONDA S", "")

    fevi_str = fevi_val if fevi_val else "___"
    tapse_str = tapse_val if tapse_val else "___"
    gpr_str = gpr_val if gpr_val else "___"
    onda_s_str = onda_s_val if onda_s_val else "___"

    plantilla_hallazgos = f"""Ventrículo izquierdo: Cavidad de diámetros conservados y paredes con hipertrofia ligera simétrica y concéntrica con GPR de {gpr_str}. Motilidad global y segmentaria normal con FE estimada por 2D del {fevi_str}%. Patrón de llenado diastólico anormal tipo II con aumento de las presiones de fin de diástole. Onda e' (promedio) de 3 cm/seg con E/e' de 27,0.

Ventrículo derecho: Cavidad de tamaño normal. Tapse de {tapse_str} mm y onda S' de {onda_s_str} cm/seg. Vena cava inferior no dilatada con colapso inspiratorio mayor al 50%.

Aurículas y septum: Aurícula izquierda: Moderadamente dilatada. Aurícula Derecha: De tamaño normal. Septum interatrial indemne.

Aorta y V. Aorta: Tres velos de aspecto escleróticos sin gradiente significativo con insuficiencia mínima al Doppler color.

Válvula mitral: De aspecto y movilidad normal, sin gradiente patológico con insuficiencia ligera al Doppler color.

Válvula tricúspide: Velos de aspecto normal con insuficiencia leve a moderada que permite estimar por Doppler una baja probabilidad de hipertensión pulmonar.

Pericardio: Sin derrame.

Otros: Válvula pulmonar de aspecto normal sin gradiente o insuficiencia significativa."""

    plantilla_conclusiones = f"""1.- Ventrículo izquierdo de tamaño normal y paredes con hipertrofia ligera simétrica y concéntrica. Motilidad global y segmentaria normal con FE estimada por 2D del {fevi_str}%.
2.- Patrón de llenado diastólico anormal tipo II con aumento de las presiones de fin de diástole.
3.- Dilatación moderada de la aurícula izquierda.
4.- Insuficiencia mitral ligera.
5.- Insuficiencia tricuspídea ligera a moderada que permite estimar por Doppler una baja probabilidad de HTP."""

    if fevi_val or tapse_val or gpr_val:
        texto_automatico_findings = plantilla_hallazgos
        texto_automatico_conclusiones = plantilla_conclusiones
    else:
        texto_automatico_findings = ""
        texto_automatico_conclusiones = ""

    findings_editado = st.text_area("Hallazgos / Descripción (modificable)", value=texto_automatico_findings, height=300)
    conclusiones_editadas = st.text_area("Conclusiones (modificable)", value=texto_automatico_conclusiones, height=180)


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
    if var.tipo == "numero":
        try: m.valor_num, m.valor_texto = float(valor), None
        except ValueError: continue
    else: m.valor_num, m.valor_texto = None, str(valor)
    m.codigo_variable = codigo
    mediciones_pdf.append((m, var))

st.divider()

# Solo generar y permitir descarga de PDF si hay un paciente seleccionado
if paciente_existente:
    pdf_data = generar_pdf_desde_historial(est_sim, paciente_existente, mediciones_pdf)
    st.download_button(
        label="📥 Generar e Imprimir PDF del Informe", 
        data=pdf_data, 
        file_name=f"Informe_Ecocardiograma_{rut.strip().replace('.','').replace('-','')}.pdf", 
        mime="application/pdf"
    )

st.markdown("<br>", unsafe_allow_html=True)

if st.button("💾 Guardar Estudio", type="primary"):
    
    # 1. PRIMERO: Validaciones (si algo falla aquí, st.stop() detiene el proceso)
    if not rut or not paciente_existente:
        st.error("❌ Debe buscar y seleccionar un paciente existente antes de guardar el estudio.")
        st.stop()

    for codigo, valor in valores.items():
        variable = variables_por_codigo[codigo]
        if variable.obligatoria == "SI" and str(valor).strip() == "":
            st.error(f"❌ Debe completar: {variable.nombre}")
            st.stop()

    # 2. SEGUNDO: Intentar guardar en la Base de Datos
    session = SessionLocal()
    try:
        def str_to_float(val):
            try: return float(val.replace(",", ".")) if val else None
            except ValueError: return None
        def str_to_int(val):
            try: return int(val) if val else None
            except ValueError: return None

        estudio = Estudio(
            paciente_rut=rut.strip(), fecha_estudio=fecha_estudio, tipo_estudio=tipo_estudio, medico=medico, 
            diagnostico=diagnostico, procedencia=procedencia, ficha_clinica=ficha_clinica,
            peso=str_to_float(peso), talla=str_to_float(talla), asc_valor=str_to_float(st.session_state.asc_val),
            pas=str_to_int(pas), pad=str_to_int(pad), ritmo=ritmo, fcia=str_to_int(fcia),
            observaciones=(f"{observaciones}\n\n[HALLAZGOS]:\n{findings_editado}\n\n[CONCLUSIONES]:\n{conclusiones_editadas}")
        )
        session.add(estudio)
        session.flush()

        for cod, var_obj in variables_por_codigo.items():
            val_ingresado = valores.get(cod)
            if not val_ingresado or str(val_ingresado).strip() == "":
                continue
            
            med = Medicion(estudio_id=estudio.id, codigo_variable=cod)
            if var_obj.tipo == "numero":
                try:
                    med.valor_num = float(val_ingresado)
                except ValueError:
                    pass 
            else:
                med.valor_texto = str(val_ingresado)
            session.add(med)

        session.commit() # Si llegamos aquí, se guardó todo en la BD con éxito
        
        # 3. TERCERO: Guardar el médico temporal en session_state
        if medico_seleccionado == "Otro..." and medico.strip() != "":
            medico_limpio = medico.strip()
            if medico_limpio not in st.session_state["lista_medicos_bd"]:
                st.session_state["lista_medicos_bd"].append(medico_limpio)

        # 4. CUARTO: Mensajes de éxito
        st.success("✅ Estudio guardado exitosamente.")
        st.balloons()
        
        # Nota sobre st.rerun(): Si usas st.rerun() inmediatamente, los globos no se verán 
        # porque la página se recarga al instante. Si quieres limpiar el formulario, 
        # puedes usar time.sleep(2) antes del st.rerun() o simplemente dejar que el usuario 
        # navegue de forma natural tras el éxito.
        
    except Exception as e:
        session.rollback()
        st.error(f"❌ Error al guardar en la base de datos: {e}")
    finally:
        session.close()