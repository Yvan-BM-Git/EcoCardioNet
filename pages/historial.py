# Archivo: pages/historial.py
import streamlit as st

# ==================================================
# CONFIGURACIÓN DE PÁGINA (Debe ser la primera instrucción)
# ==================================================
st.set_page_config(page_title="Historial Clínico", page_icon="📁", layout="wide")

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

import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, date
import io
import re
import unicodedata

import pdfplumber

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from database.database import SessionLocal
from database.models import Paciente, Estudio, Medicion, Variable

# st.set_page_config(layout="wide")
st.title("📊 Panel de gestión clínica - Ecocardiografía")

# ==================================================
# CALLBACK DE FORMATEO
# ==================================================
def formatear_busqueda_callback():
    busqueda_actual = st.session_state.get("busqueda_input", "")
    if not busqueda_actual:
        return
    limpio = busqueda_actual.replace(".", "").replace("-", "").strip().upper()
    if 7 <= len(limpio) <= 9:
        cuerpo = limpio[:-1]
        dv = limpio[-1]
        if cuerpo.isdigit() and (dv.isdigit() or dv == "K"):
            cuerpo_formateado = f"{int(cuerpo):,}".replace(",", ".")
            st.session_state.busqueda_input = f"{cuerpo_formateado}-{dv}"

# ==================================================
# FUNCIÓN PDF (informe generado por la app)
# ==================================================
def generar_pdf_desde_historial(estudio, paciente, mediciones_estudio):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )
    styles = getSampleStyleSheet()
    style_h1 = ParagraphStyle('Header1', fontName='Helvetica-Bold', fontSize=14, leading=16,
                               textColor=colors.HexColor("#1A365D"))
    style_body_bold = ParagraphStyle('BodyBold', fontName='Helvetica-Bold', fontSize=9, leading=11)
    style_body = ParagraphStyle('Body', fontName='Helvetica', fontSize=9, leading=11)
    style_table_header = ParagraphStyle('TableHeader', fontName='Helvetica-Bold', fontSize=9,
                                        leading=11, textColor=colors.white)
    story = []

    story.append(Paragraph("<b>EcoCardioNet CARDIAC REPORT</b>", style_h1))
    story.append(Spacer(1, 12))

    nombre_p = f"{paciente.apellido_paterno} {paciente.apellido_materno or ''} {paciente.nombres}".strip()
    edad_p = (
        (datetime.today().date() - paciente.fecha_nacimiento).days // 365
        if paciente.fecha_nacimiento else "—"
    )
    hora_estudio = (
        estudio.fecha_creacion.strftime('%H:%M')
        if hasattr(estudio, 'fecha_creacion') and estudio.fecha_creacion else ""
    )
    fecha_str = f"{estudio.fecha_estudio.strftime('%d/%m/%Y')} {hora_estudio}".strip()

    data_paciente = [
        [Paragraph("<b>Paciente:</b>", style_body), Paragraph(nombre_p, style_body),
         Paragraph("<b>Fecha Estudio:</b>", style_body), Paragraph(fecha_str, style_body)],
        [Paragraph("<b>ID / RUT:</b>", style_body), Paragraph(paciente.rut, style_body),
         Paragraph("<b>Edad:</b>", style_body), Paragraph(f"{edad_p} años", style_body)],
        [Paragraph("<b>Género:</b>", style_body), Paragraph(paciente.sexo or "—", style_body),
         Paragraph("<b>Médico:</b>", style_body), Paragraph(estudio.medico or "—", style_body)],
        [Paragraph("<b>Tipo Estudio:</b>", style_body), Paragraph(estudio.tipo_estudio, style_body),
         Paragraph("<b>Motivo:</b>", style_body), Paragraph(estudio.motivo or "—", style_body)],
    ]
    t_paciente = Table(data_paciente, colWidths=[70, 200, 80, 190])
    t_paciente.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
        ('BOX',           (0, 0), (-1, -1), 1,   colors.HexColor("#CBD5E0")),
        ('INNERGRID',     (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_paciente)
    story.append(Spacer(1, 15))

    story.append(Paragraph("<b>MEDICIONES ECOCARDIOGRÁFICAS</b>", style_body_bold))
    story.append(Spacer(1, 6))

    if mediciones_estudio:
        data_mediciones = [[
            Paragraph("Variable / Parámetro", style_table_header),
            Paragraph("Valor", style_table_header),
            Paragraph("Unidad", style_table_header),
        ]]
        for m, v in mediciones_estudio:
            valor_final = str(m.valor_num) if m.valor_num is not None else (m.valor_texto or "")
            unidad_var = (v.unidad if (v and v.unidad) else "—") or "—"
            nombre_var = v.nombre if (v and v.nombre) else m.codigo_variable
            data_mediciones.append([
                Paragraph(nombre_var, style_body),
                Paragraph(f"<b>{valor_final}</b>", style_body),
                Paragraph(unidad_var, style_body),
            ])
        t_mediciones = Table(data_mediciones, colWidths=[300, 140, 100])
        t_mediciones.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  colors.HexColor("#1A365D")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
            ('BOX',           (0, 0), (-1, -1), 1,   colors.HexColor("#1A365D")),
            ('INNERGRID',     (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ('TOPPADDING',    (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t_mediciones)
    else:
        story.append(Paragraph(
            "<i>No se encontraron mediciones asociadas a este registro.</i>", style_body
        ))

    story.append(Spacer(1, 15))
    texto_obs = estudio.observaciones or "Sin observaciones registradas."
    story.append(KeepTogether([
        Paragraph("<b>INFORME CLÍNICO / OBSERVACIONES HISTÓRICAS</b>", style_body_bold),
        Spacer(1, 4),
        Paragraph(texto_obs.replace("\n", "<br/>"), style_body),
    ]))
    doc.build(story)
    buffer.seek(0)
    return buffer


# ==================================================
# UTILIDADES DE IMPORTACIÓN DE PDF (extracción asistida)
# ==================================================
def _normalizar(txt):
    """Minúsculas, sin tildes, espacios colapsados. Facilita el matching por texto."""
    if not txt:
        return ""
    txt = unicodedata.normalize('NFKD', txt)
    txt = ''.join(c for c in txt if not unicodedata.combining(c))
    txt = txt.lower()
    txt = re.sub(r'\s+', ' ', txt)
    return txt.strip()


def extraer_texto_pdf(archivo_subido):
    """Extrae el texto plano de un PDF (informe basado en texto, no imagen escaneada)."""
    texto_total = ""
    with pdfplumber.open(archivo_subido) as pdf:
        for pagina in pdf.pages:
            texto_pagina = pagina.extract_text() or ""
            texto_total += texto_pagina + "\n"
    return texto_total


_NUM = r'(-?\d+[.,]?\d*)'

# Alias de etiquetas conocidas en informes ya vistos, mapeadas al código de Variable.
# IMPORTANTE: cada equipo/clínica formatea distinto -> esta lista es de "mejor esfuerzo"
# y conviene seguir ampliándola a medida que aparezcan nuevos formatos de informe.
ALIASES_MEDICIONES = {
    "FEVI": [
        "fe(teich)", "fe (teich)", "fe teich",
        "fe estimada por simpson del", "fe estimada por 2d del",
        "fraccion de eyeccion", "frac. eyeccion", "frac eyeccion",
    ],
    "TAPSE": ["tapse"],
    "ONDA_S": ["tv s'", "onda s'", "s' promedio"],
    "GPR": ["gpr"],
    "MASA_VI_INDEXADA": ["masa vi/asc", "masa vi indexada"],
    "PSAP": ["presion sist. ap", "presion sistolica de arteria pulmonar", "psap"],
    "VELOCIDAD_PICO_AORTICA": ["vmax va", "v. max ao", "vel. maxima ao"],
    "GRADIENTE_MEDIO_AORTICO": ["va gpmax", "gradiente medio ao", "gdte medio ao"],
    "TIEMPO_ACELERACION_PULMONAR": ["tap"],
    "AREA_MITRAL": ["area valvular mitral"],
    "VENA_CONTRACTA_MITRAL": ["vena contracta mitral"],
    "EROA_MITRAL": ["eroa mitral"],
    "VOLUMEN_REGURGITANTE_MITRAL": ["volumen regurgitante mitral"],
}


def _buscar_valor(texto_normalizado, etiquetas):
    """Busca la primera etiqueta que matchee y devuelve el número más cercano a la derecha."""
    for etiqueta in etiquetas:
        et_norm = _normalizar(etiqueta)
        patron = re.escape(et_norm) + r'[^0-9\-]{0,15}' + _NUM
        m = re.search(patron, texto_normalizado)
        if m:
            return m.group(1).replace(",", ".")
    return None


def extraer_mediciones(texto, variables_por_codigo):
    """
    Intenta extraer valores numéricos del texto de un informe y mapearlos a
    los códigos de la tabla Variable. Devuelve {codigo: valor_str}.
    Solo incluye códigos donde se encontró un valor con razonable confianza.
    No pretende ser exhaustivo: el usuario revisa/corrige antes de guardar.
    """
    texto_norm = _normalizar(texto)
    resultados = {}

    # 1. Alias conocidos (más confiables, curados a mano)
    for codigo, etiquetas in ALIASES_MEDICIONES.items():
        if codigo not in variables_por_codigo:
            continue
        valor = _buscar_valor(texto_norm, etiquetas)
        if valor:
            resultados[codigo] = valor

    # 2. Fallback genérico: usar el nombre tal cual está en la BD de Variable
    for codigo, var in variables_por_codigo.items():
        if codigo in resultados:
            continue
        if var.tipo != "numero":
            continue
        nombre_norm = _normalizar(var.nombre or "")
        if not nombre_norm or len(nombre_norm) < 3:
            continue
        patron = re.escape(nombre_norm) + r'[^0-9\-]{0,15}' + _NUM
        m = re.search(patron, texto_norm)
        if m:
            resultados[codigo] = m.group(1).replace(",", ".")

    return resultados


def extraer_nombre_paciente(texto):
    """Intenta extraer el nombre completo del paciente en distintos formatos de informe."""
    # Formato "Paciente : NOMBRE APELLIDOS" (todo en mayúsculas, común en clínicas chilenas)
    m = re.search(r'[Pp]aciente\s*:\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{4,60})', texto)
    if m:
        nombre = re.sub(r'\s+', ' ', m.group(1)).strip()
        # Cortar si se coló texto de otra etiqueta cercana
        nombre = re.split(r'\d|R\.U\.T|EDAD', nombre)[0].strip()
        if len(nombre.split()) >= 2:
            return nombre.title()

    # Formato "Name APELLIDOS, NOMBRES ... Patient Id"
    m = re.search(r'Name\s+([A-ZÁÉÍÓÚÑ,\s]{4,60}?)\s*Patient Id', texto, re.DOTALL)
    if m:
        nombre = re.sub(r'\s+', ' ', m.group(1)).strip().replace(",", "")
        if len(nombre.split()) >= 2:
            return nombre.title()

    return None


def dividir_nombre_completo(nombre_completo):
    """
    Heurística simple para separar un nombre completo detectado en
    nombres / apellido paterno / apellido materno. Es solo un punto de
    partida: el usuario siempre puede corregirlo en el formulario.
    """
    if not nombre_completo:
        return "", "", ""
    partes = nombre_completo.split()
    if len(partes) >= 4:
        apellido_paterno = partes[0]
        apellido_materno = partes[1]
        nombres = " ".join(partes[2:])
    elif len(partes) == 3:
        apellido_paterno = partes[0]
        apellido_materno = partes[1]
        nombres = partes[2]
    elif len(partes) == 2:
        apellido_paterno = partes[0]
        apellido_materno = ""
        nombres = partes[1]
    else:
        apellido_paterno = nombre_completo
        apellido_materno = ""
        nombres = ""
    return nombres, apellido_paterno, apellido_materno


def extraer_datos_generales(texto):
    """Intenta detectar RUT, nombre, fecha, peso, talla, FC, ritmo, sexo y médico del informe."""
    datos = {}
    texto_norm = _normalizar(texto)

    m_rut = re.search(r'r\.?u\.?t\.?\s*:?\s*(\d{1,2}\.?\d{3}\.?\d{3}-[\dk])', texto_norm)
    if not m_rut:
        m_rut = re.search(r'patient id\s*(\d{1,8}-[\dk])', texto_norm)
    if m_rut:
        datos["rut"] = m_rut.group(1).upper()

    m_fecha = re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b', texto)
    if m_fecha:
        datos["fecha_texto"] = m_fecha.group(1)

    m_nac = re.search(r'birthdate\s+(\d{1,2}/\d{1,2}/\d{2,4})', texto_norm)
    if m_nac:
        datos["fecha_nacimiento_texto"] = m_nac.group(1)

    m_genero = re.search(r'gender\s+(masculino|femenino|male|female)|sexo\s*:?\s*(masculino|femenino)', texto_norm)
    if m_genero:
        g = (m_genero.group(1) or m_genero.group(2) or "").strip()
        if g:
            datos["sexo"] = "Masculino" if g in ("masculino", "male") else "Femenino"

    m_peso = re.search(r'(?:weight|peso)\s*' + _NUM, texto_norm)
    if m_peso:
        datos["peso"] = m_peso.group(1).replace(",", ".")

    m_talla = re.search(r'(?:height|talla)\s*' + _NUM, texto_norm)
    if m_talla:
        datos["talla"] = m_talla.group(1).replace(",", ".")

    m_fc = re.search(r'(\d{2,3})\s*lpm', texto_norm)
    if m_fc:
        datos["fcia"] = m_fc.group(1)

    if re.search(r'ritmo\s*:?\s*sinusal', texto_norm):
        datos["ritmo"] = "Sinusal"

    m_medico = re.search(r'dr\.?a?\.?\s+[a-záéíóúñ]+(?:\s+[a-záéíóúñ]+){1,3}', texto_norm)
    if m_medico:
        datos["medico_sugerido"] = m_medico.group(0).title()

    nombre_detectado = extraer_nombre_paciente(texto)
    if nombre_detectado:
        datos["nombre_completo"] = nombre_detectado

    return datos


session = SessionLocal()

try:
    # ==================================================
    # CARGA GLOBAL DE VARIABLES (para importación de PDF)
    # ==================================================
    variables_db_completas = session.query(Variable).all()
    variables_por_codigo_global = {v.codigo: v for v in variables_db_completas}

    # ==================================================
    # 1. SIDEBAR CON FILTROS GLOBALES
    # ==================================================
    st.sidebar.header("🔍 Filtros globales")

    fecha_min = session.query(Estudio.fecha_estudio).order_by(Estudio.fecha_estudio).first()
    fecha_max = session.query(Estudio.fecha_estudio).order_by(Estudio.fecha_estudio.desc()).first()
    if fecha_min and fecha_max:
        default_start = fecha_min[0]
        default_end = fecha_max[0]
    else:
        default_start = datetime.today() - timedelta(days=365)
        default_end = datetime.today()

    fecha_desde = st.sidebar.date_input("Fecha desde", value=default_start)
    fecha_hasta = st.sidebar.date_input("Fecha hasta", value=default_end)

    tipos_estudio = session.query(Estudio.tipo_estudio).distinct().all()
    tipos_estudio = [t[0] for t in tipos_estudio if t[0]]
    tipo_seleccionado = st.sidebar.multiselect("Tipo de estudio", tipos_estudio, default=tipos_estudio)

    medicos = session.query(Estudio.medico).distinct().all()
    medicos = [m[0] for m in medicos if m[0]]
    medico_seleccionado = st.sidebar.multiselect("Médico responsable", medicos, default=medicos)

    # ==================================================
    # OBTENER SOLO VARIABLES DEL PACIENTE SELECCIONADO
    # ==================================================
    rut_paciente_actual = st.session_state.get("selectbox_busqueda_historial") or st.session_state.get("selectbox_historial_paciente")

    query_vars = (
        session.query(Variable.codigo, Variable.nombre, Variable.unidad)
        .join(Medicion, Variable.codigo == Medicion.codigo_variable)
        .join(Estudio, Medicion.estudio_id == Estudio.id)
    )

    if rut_paciente_actual:
        query_vars = query_vars.filter(Estudio.paciente_rut == rut_paciente_actual)

    variables_con_mediciones = query_vars.distinct().order_by(Variable.nombre).all()
    
    if not variables_con_mediciones:
        if rut_paciente_actual:
            st.sidebar.info("💡 El paciente seleccionado aún no tiene mediciones guardadas.")
        else:
            st.sidebar.info("💡 Seleccione un paciente para ver las variables disponibles.")
        opciones_vars = {}
        var_seleccionada = None
        codigo_var = None
    else:
        opciones_vars = {f"{v.nombre}": v.codigo for v in variables_con_mediciones}
        var_seleccionada = st.sidebar.selectbox(
            "Variable a analizar (tendencia global)",
            options=list(opciones_vars.keys()),
            index=0
        )
        codigo_var = opciones_vars[var_seleccionada]

    # ==================================================
    # 2. ESTADÍSTICAS GENERALES
    # ==================================================
    total_pacientes = session.query(Paciente).count()
    total_estudios = session.query(Estudio).count()
    estudios_periodo = session.query(Estudio).filter(
        Estudio.fecha_estudio >= fecha_desde,
        Estudio.fecha_estudio <= fecha_hasta
    )
    if tipo_seleccionado:
        estudios_periodo = estudios_periodo.filter(Estudio.tipo_estudio.in_(tipo_seleccionado))
    if medico_seleccionado:
        estudios_periodo = estudios_periodo.filter(Estudio.medico.in_(medico_seleccionado))
    estudios_periodo = estudios_periodo.count()

    col1, col2, col3 = st.columns(3)
    col1.metric("🏥 Total pacientes", total_pacientes)
    col2.metric("📋 Total estudios", total_estudios)
    col3.metric("📅 Estudios en período filtrado", estudios_periodo)

    # ==================================================
    # IMPORTAR INFORME PDF (funciona con o sin paciente registrado)
    # ==================================================
    st.divider()
    with st.expander("📎 Importar Informe en PDF (paciente nuevo o existente)", expanded=False):
        st.caption(
            "Subí el PDF del informe. El sistema intenta detectar el RUT, nombre y "
            "algunos valores numéricos automáticamente. Si el paciente ya existe en la "
            "base de datos se usa su ficha; si no existe, se puede registrar en el momento. "
            "**Siempre revisá y corregí** los datos antes de confirmar."
        )
        archivo_pdf_global = st.file_uploader(
            "Selecciona el archivo PDF", type=["pdf"], key="uploader_pdf_global"
        )

        if archivo_pdf_global is not None:
            cache_key_g = f"extraccion_pdf_global_{archivo_pdf_global.name}_{archivo_pdf_global.size}"

            if cache_key_g not in st.session_state:
                with st.spinner("Extrayendo texto y datos del PDF..."):
                    archivo_pdf_global.seek(0)
                    texto_extraido_g = extraer_texto_pdf(archivo_pdf_global)
                    mediciones_detectadas_g = extraer_mediciones(texto_extraido_g, variables_por_codigo_global)
                    datos_generales_g = extraer_datos_generales(texto_extraido_g)
                    archivo_pdf_global.seek(0)
                    pdf_bytes_g = archivo_pdf_global.read()

                    st.session_state[cache_key_g] = {
                        "mediciones": mediciones_detectadas_g,
                        "generales": datos_generales_g,
                        "pdf_bytes": pdf_bytes_g,
                        "pdf_nombre": archivo_pdf_global.name,
                    }

            datos_cache_g = st.session_state[cache_key_g]
            generales_g = datos_cache_g["generales"]

            # --------------------------------------------
            # 1) RESOLUCIÓN DEL PACIENTE (existente o nuevo)
            # --------------------------------------------
            st.markdown("##### 1️⃣ Paciente")

            rut_editable = st.text_input(
                "RUT detectado (revisá / corregí si es necesario)",
                value=generales_g.get("rut", ""),
                key="rut_editable_import_global"
            )

            paciente_encontrado = None
            if rut_editable:
                rut_normalizado_busqueda = rut_editable.strip().upper()
                paciente_encontrado = session.query(Paciente).filter(
                    Paciente.rut == rut_normalizado_busqueda
                ).first()
                if not paciente_encontrado:
                    # Comparación tolerante a puntos/guión por si el formato no calza exacto
                    limpio_buscado = re.sub(r'[.\-]', '', rut_normalizado_busqueda)
                    for c in session.query(Paciente).all():
                        if re.sub(r'[.\-]', '', c.rut.upper()) == limpio_buscado:
                            paciente_encontrado = c
                            break

            usar_paciente_existente = False
            datos_paciente_nuevo = {}

            if paciente_encontrado:
                nombre_encontrado = f"{paciente_encontrado.apellido_paterno} {paciente_encontrado.apellido_materno or ''} {paciente_encontrado.nombres}".strip()
                st.success(f"✅ Paciente encontrado en la base de datos: **{nombre_encontrado}** ({paciente_encontrado.rut})")
                usar_paciente_existente = st.checkbox(
                    "Usar este paciente encontrado", value=True, key="usar_paciente_encontrado_global"
                )

            if not paciente_encontrado or not usar_paciente_existente:
                if rut_editable and not paciente_encontrado:
                    st.warning(f"⚠️ No se encontró ningún paciente con el RUT '{rut_editable}'. Completá los datos para registrarlo.")
                elif not rut_editable:
                    st.info("💡 No se detectó un RUT válido en el PDF. Ingresá los datos del paciente manualmente para registrarlo.")

                nombre_completo_detectado = generales_g.get("nombre_completo", "")
                nombres_g, ap_pat_g, ap_mat_g = dividir_nombre_completo(nombre_completo_detectado)

                if nombre_completo_detectado:
                    st.caption("⚠️ El orden de nombres/apellidos es una detección automática: verificalo, puede variar según el formato del informe.")

                cn1, cn2, cn3 = st.columns(3)
                with cn1:
                    nombres_nuevo_g = st.text_input("Nombres", value=nombres_g, key="nombres_nuevo_import_global")
                with cn2:
                    ap_paterno_nuevo_g = st.text_input("Apellido paterno", value=ap_pat_g, key="ap_paterno_nuevo_import_global")
                with cn3:
                    ap_materno_nuevo_g = st.text_input("Apellido materno", value=ap_mat_g, key="ap_materno_nuevo_import_global")

                cn4, cn5 = st.columns(2)
                with cn4:
                    fecha_nac_detectada_g = date(2000, 1, 1)
                    if generales_g.get("fecha_nacimiento_texto"):
                        try:
                            partes_fn = re.split(r'[/-]', generales_g["fecha_nacimiento_texto"])
                            d, m, a = int(partes_fn[0]), int(partes_fn[1]), int(partes_fn[2])
                            if a < 100:
                                a += 1900 if a > 30 else 2000
                            fecha_nac_detectada_g = date(a, m, d)
                        except Exception:
                            pass
                    fecha_nac_nuevo_g = st.date_input(
                        "Fecha nacimiento", value=fecha_nac_detectada_g,
                        min_value=date(1900, 1, 1), max_value=date.today(), format="DD/MM/YYYY",
                        key="fn_nuevo_import_global"
                    )
                with cn5:
                    opts_sexo_g = ["", "Masculino", "Femenino"]
                    sexo_detectado_g = generales_g.get("sexo", "")
                    idx_sexo_g = opts_sexo_g.index(sexo_detectado_g) if sexo_detectado_g in opts_sexo_g else 0
                    sexo_nuevo_g = st.selectbox("Sexo", opts_sexo_g, index=idx_sexo_g, key="sexo_nuevo_import_global")

                datos_paciente_nuevo = {
                    "rut": rut_editable.strip(),
                    "nombres": nombres_nuevo_g.strip(),
                    "apellido_paterno": ap_paterno_nuevo_g.strip(),
                    "apellido_materno": ap_materno_nuevo_g.strip(),
                    "fecha_nacimiento": fecha_nac_nuevo_g,
                    "sexo": sexo_nuevo_g if sexo_nuevo_g else None,
                }

            paciente_listo = (paciente_encontrado and usar_paciente_existente) or (
                (not paciente_encontrado or not usar_paciente_existente) and
                datos_paciente_nuevo.get("rut") and
                datos_paciente_nuevo.get("nombres") and
                datos_paciente_nuevo.get("apellido_paterno")
            )

            if not paciente_listo:
                st.info("⏳ Completá los datos del paciente (RUT, nombres y apellido paterno como mínimo) para continuar.")
            else:
                st.divider()
                st.markdown("##### 2️⃣ Datos generales del estudio")

                if datos_cache_g["mediciones"]:
                    st.success(f"✅ Se detectaron {len(datos_cache_g['mediciones'])} valores automáticamente. Revísalos abajo.")
                else:
                    st.warning("⚠️ No se detectó ningún valor automáticamente. Podés cargarlos manualmente en la tabla.")

                cg1, cg2, cg3 = st.columns(3)
                with cg1:
                    fecha_detectada_g = date.today()
                    if generales_g.get("fecha_texto"):
                        try:
                            partes_f = re.split(r'[/-]', generales_g["fecha_texto"])
                            d, m, a = int(partes_f[0]), int(partes_f[1]), int(partes_f[2])
                            if a < 100:
                                a += 2000
                            fecha_detectada_g = date(a, m, d)
                        except Exception:
                            pass
                    fecha_import_g = st.date_input(
                        "Fecha del estudio", value=fecha_detectada_g, format="DD/MM/YYYY",
                        key="fecha_import_global"
                    )
                with cg2:
                    tipo_import_g = st.selectbox(
                        "Tipo de estudio",
                        ["Ecocardiograma Transtorácico", "Ecocardiograma Transesofágico", "Ecocardiograma de Estrés", "Ecocardiograma 3D"],
                        key="tipo_import_global"
                    )
                with cg3:
                    medico_import_g = st.text_input(
                        "Médico responsable",
                        value=generales_g.get("medico_sugerido", ""),
                        key="medico_import_global"
                    )

                st.markdown("##### 3️⃣ Mediciones detectadas (editable)")
                filas_tabla_g = []
                for codigo, var in variables_por_codigo_global.items():
                    if var.tipo != "numero":
                        continue
                    if codigo not in datos_cache_g["mediciones"]:
                        continue
                    filas_tabla_g.append({
                        "Código": codigo,
                        "Nombre": var.nombre,
                        "Valor detectado": datos_cache_g["mediciones"][codigo],
                        "Unidad": var.unidad or "",
                    })

                if filas_tabla_g:
                    df_tabla_import_g = pd.DataFrame(filas_tabla_g)
                    df_editado_import_g = st.data_editor(
                        df_tabla_import_g,
                        column_config={
                            "Código": st.column_config.TextColumn(disabled=True),
                            "Nombre": st.column_config.TextColumn(disabled=True),
                            "Unidad": st.column_config.TextColumn(disabled=True),
                        },
                        hide_index=True,
                        use_container_width=True,
                        key="editor_import_global",
                    )
                else:
                    st.info("No se detectaron variables numéricas automáticamente. El informe se guardará solo como PDF adjunto, salvo que agregues valores manualmente abajo.")
                    df_editado_import_g = pd.DataFrame(columns=["Código", "Nombre", "Valor detectado", "Unidad"])

                st.markdown("##### Agregar variable manualmente (opcional)")
                cm1, cm2 = st.columns([2, 1])
                with cm1:
                    cod_manual_g = st.selectbox(
                        "Variable a agregar",
                        options=[""] + sorted([c for c, v in variables_por_codigo_global.items() if v.tipo == "numero"]),
                        key="cod_manual_import_global"
                    )
                with cm2:
                    valor_manual_g = st.text_input("Valor", key="valor_manual_import_global")

                if cod_manual_g and valor_manual_g:
                    var_manual_g = variables_por_codigo_global[cod_manual_g]
                    nueva_fila_g = pd.DataFrame([{
                        "Código": cod_manual_g, "Nombre": var_manual_g.nombre,
                        "Valor detectado": valor_manual_g, "Unidad": var_manual_g.unidad or "",
                    }])
                    df_editado_import_g = pd.concat([df_editado_import_g, nueva_fila_g], ignore_index=True)

                if st.button("✅ Confirmar e Importar al Historial", type="primary", key="btn_confirmar_import_global"):
                    session_import = SessionLocal()
                    try:
                        crear_paciente_nuevo = not (paciente_encontrado and usar_paciente_existente)
                        rut_final = datos_paciente_nuevo["rut"] if crear_paciente_nuevo else paciente_encontrado.rut

                        existe_ya = None
                        if crear_paciente_nuevo:
                            existe_ya = session_import.query(Paciente).filter(Paciente.rut == rut_final).first()

                        if existe_ya:
                            st.error(f"⚠️ Ya existe un paciente registrado con el RUT {rut_final}. Recargá la página y seleccionalo como paciente existente.")
                        else:
                            if crear_paciente_nuevo:
                                nuevo_paciente = Paciente(
                                    rut=rut_final,
                                    nombres=datos_paciente_nuevo["nombres"],
                                    apellido_paterno=datos_paciente_nuevo["apellido_paterno"],
                                    apellido_materno=datos_paciente_nuevo["apellido_materno"],
                                    fecha_nacimiento=datos_paciente_nuevo["fecha_nacimiento"],
                                    sexo=datos_paciente_nuevo["sexo"],
                                )
                                session_import.add(nuevo_paciente)
                                session_import.flush()

                            nuevo_estudio = Estudio(
                                paciente_rut=rut_final,
                                fecha_estudio=fecha_import_g,
                                tipo_estudio=tipo_import_g,
                                medico=medico_import_g or None,
                                observaciones="[IMPORTADO DESDE PDF]",
                                pdf_original=datos_cache_g["pdf_bytes"],
                                pdf_nombre_archivo=datos_cache_g["pdf_nombre"],
                            )
                            session_import.add(nuevo_estudio)
                            session_import.flush()

                            contador_guardadas_g = 0
                            for _, fila in df_editado_import_g.iterrows():
                                val = str(fila["Valor detectado"]).strip()
                                if not val or val.lower() == "nan":
                                    continue
                                med = Medicion(estudio_id=nuevo_estudio.id, codigo_variable=fila["Código"])
                                try:
                                    med.valor_num = float(val.replace(",", "."))
                                except ValueError:
                                    med.valor_texto = val
                                session_import.add(med)
                                contador_guardadas_g += 1

                            session_import.commit()
                            st.success(f"✅ Informe importado correctamente ({contador_guardadas_g} mediciones guardadas, PDF adjuntado).")
                            del st.session_state[cache_key_g]
                            st.rerun()
                    except Exception as e:
                        session_import.rollback()
                        st.error(f"❌ Error al importar: {e}")
                    finally:
                        session_import.close()

    # ==================================================
    # 3. BÚSQUEDA Y SELECCIÓN DE PACIENTE
    # ==================================================
    st.subheader("📋 Pacientes registrados")

    pacientes = session.query(Paciente).order_by(Paciente.apellido_paterno, Paciente.nombres).all()
    if pacientes:
        df_pacientes = pd.DataFrame([
            {
                "RUT": p.rut,
                "Nombre completo": f"{p.apellido_paterno} {p.apellido_materno or ''} {p.nombres}".strip(),
                "Edad": (datetime.today().date() - p.fecha_nacimiento).days // 365 if p.fecha_nacimiento else None,
                "Sexo": p.sexo or "",
                "Teléfono": p.telefono or "",
                "Email": p.email or "",
                "Informes asociados": session.query(Estudio).filter(Estudio.paciente_rut == p.rut).count(),
            }
            for p in pacientes
        ])
    else:
        df_pacientes = pd.DataFrame(columns=["RUT", "Nombre completo", "Edad", "Sexo", "Teléfono", "Email", "Informes asociados"])

    col_search, col_seleccion = st.columns([1, 1])

    with col_search:
        busqueda = st.text_input(
            "🔎 Buscar paciente en la base de datos",
            value="",
            placeholder="Ej: Nombre, Apellido o RUT",
            key="busqueda_input",
            on_change=formatear_busqueda_callback,
        )

    with col_seleccion:
        if df_pacientes.empty:
            st.info("No hay pacientes registrados en la base de datos.")
            paciente_seleccionado_rut = None
            paciente_obj = None
        else:
            opciones_todos = df_pacientes["RUT"].tolist()
            paciente_seleccionado_rut = st.selectbox(
                "✅ Seleccione el paciente para ver su historial",
                options=opciones_todos,
                index=None,
                placeholder="Seleccionar 👇",
                format_func=lambda r: f"{df_pacientes[df_pacientes['RUT'] == r]['Nombre completo'].iloc[0]} ({r})",
                key="selectbox_historial_paciente",
            )
            if paciente_seleccionado_rut:
                paciente_obj = session.query(Paciente).filter(Paciente.rut == paciente_seleccionado_rut).first()
            else:
                paciente_obj = None

    # ==================================================
    # Selector adicional que aparece SOLO si hay búsqueda (como en estudios.py)
    # ==================================================
    if busqueda and not df_pacientes.empty:
        mask = (
            df_pacientes["Nombre completo"].str.contains(busqueda, case=False, na=False) |
            df_pacientes["RUT"].str.contains(busqueda, case=False, na=False)
        )
        df_filtrado = df_pacientes[mask]

        if not df_filtrado.empty:
            st.markdown("---")  # separador visual
            rut_filtrado = st.selectbox(
                "🔍 Seleccione el paciente de la búsqueda",
                options=df_filtrado["RUT"].tolist(),
                index=None,
                placeholder="Resultados de búsqueda 👇",
                format_func=lambda r: f"{df_filtrado[df_filtrado['RUT'] == r]['Nombre completo'].iloc[0]} ({r})",
                key="selectbox_busqueda_historial",
            )
            if rut_filtrado:
                # Sobrescribe el paciente seleccionado con el de la búsqueda
                paciente_seleccionado_rut = rut_filtrado
                paciente_obj = session.query(Paciente).filter(Paciente.rut == rut_filtrado).first()
        else:
            st.warning("No se encontraron pacientes que coincidan con la búsqueda.")

    # ==================================================
    # 4. HISTORIAL DETALLADO
    # ==================================================
    if paciente_obj:
        st.divider()
        nombre_completo_paciente = (
            f"{paciente_obj.apellido_paterno} {paciente_obj.apellido_materno or ''} {paciente_obj.nombres}".strip()
        )
        st.subheader(f"📈 Historial Clínico de {nombre_completo_paciente}")

        if hasattr(paciente_obj, 'fecha_creacion') and paciente_obj.fecha_creacion:
            st.caption(
                f"🕒 *Paciente registrado el: "
                f"{paciente_obj.fecha_creacion.strftime('%d/%m/%Y a las %H:%M:%S')}*"
            )

        estudios_paciente = session.query(Estudio).filter(
            Estudio.paciente_rut == paciente_obj.rut,
            Estudio.fecha_estudio >= fecha_desde,
            Estudio.fecha_estudio <= fecha_hasta,
        )
        if tipo_seleccionado:
            estudios_paciente = estudios_paciente.filter(Estudio.tipo_estudio.in_(tipo_seleccionado))
        if medico_seleccionado:
            estudios_paciente = estudios_paciente.filter(Estudio.medico.in_(medico_seleccionado))
        estudios_paciente = estudios_paciente.order_by(Estudio.fecha_estudio.desc()).all()

        if not estudios_paciente:
            st.warning("No hay estudios para este paciente en el período seleccionado.")
        else:
            st.markdown("### 📄 Informes y Conclusiones del Cardiólogo")

            opciones_estudios = {
                f"📅 {est.fecha_estudio.strftime('%d/%m/%Y')} — {est.tipo_estudio} "
                f"(Dr/a. {est.medico or 'No registrado'})"
                + (" 📎" if getattr(est, 'pdf_original', None) else ""): est
                for est in estudios_paciente
            }

            estudio_seleccionado_obj = st.selectbox(
                "Selecciona un examen del historial:",
                options=list(opciones_estudios.keys()),
            )

            if estudio_seleccionado_obj:
                est_objeto = opciones_estudios[estudio_seleccionado_obj]

                mediciones_este_estudio = (
                    session.query(Medicion, Variable)
                    .outerjoin(Variable, Medicion.codigo_variable == Variable.codigo)
                    .filter(Medicion.estudio_id == est_objeto.id)
                    .all()
                )

                hora_registro_estudio = (
                    est_objeto.fecha_creacion.strftime('%H:%M:%S')
                    if hasattr(est_objeto, 'fecha_creacion') and est_objeto.fecha_creacion
                    else "No registrada"
                )

                with st.container(border=True):
                    c_inf1, c_inf2 = st.columns(2)
                    with c_inf1:
                        st.markdown(f"**🩺 Estudio:** {est_objeto.tipo_estudio}")
                        st.markdown(f"**🎯 Motivo:** {est_objeto.motivo or '—'}")
                    with c_inf2:
                        st.markdown(f"**👨‍⚕️ Médico:** {est_objeto.medico or '—'}")
                        st.markdown(f"**📅 Fecha:** {est_objeto.fecha_estudio.strftime('%d/%m/%Y')}")
                        st.markdown(f"**🕘 Hora de registro:** {hora_registro_estudio}")

                    st.divider()
                    st.markdown("#### 📝 Conclusiones, Hallazgos y Observaciones")

                    if est_objeto.observaciones:
                        st.info(est_objeto.observaciones)
                    else:
                        st.write("*No se registraron observaciones narrativas ni conclusiones.*")

                    col_pdf1, col_pdf2 = st.columns(2)
                    with col_pdf1:
                        pdf_historial = generar_pdf_desde_historial(
                            est_objeto, paciente_obj, mediciones_este_estudio
                        )
                        st.download_button(
                            label="📥 Re-generar y Descargar PDF de este Examen",
                            data=pdf_historial,
                            file_name=(
                                f"Informe_{est_objeto.tipo_estudio.replace(' ', '_')}_"
                                f"{paciente_obj.rut}_{est_objeto.fecha_estudio.strftime('%Y%m%d')}.pdf"
                            ),
                            mime="application/pdf",
                            key=f"pdf_btn_{est_objeto.id}",
                        )
                    with col_pdf2:
                        if getattr(est_objeto, 'pdf_original', None):
                            st.download_button(
                                label="📎 Descargar PDF Original Importado",
                                data=est_objeto.pdf_original,
                                file_name=est_objeto.pdf_nombre_archivo or f"informe_original_{est_objeto.id}.pdf",
                                mime="application/pdf",
                                key=f"pdf_original_btn_{est_objeto.id}",
                            )

            st.divider()

            # Gráficos de evolución
            mediciones = []
            for est in estudios_paciente:
                mediciones_q = session.query(
                    Medicion.codigo_variable,
                    Medicion.valor_num,
                    Medicion.valor_texto,
                    Estudio.fecha_estudio,
                    Estudio.medico,
                    Estudio.tipo_estudio,
                ).join(Estudio, Medicion.estudio_id == Estudio.id).filter(
                    Medicion.estudio_id == est.id
                ).all()
                for m in mediciones_q:
                    mediciones.append({
                        "fecha": m.fecha_estudio,
                        "variable": m.codigo_variable,
                        "valor_num": m.valor_num,
                        "valor_texto": m.valor_texto,
                        "medico": m.medico,
                        "tipo_estudio": m.tipo_estudio,
                    })

            df_med = pd.DataFrame(mediciones)
            if not df_med.empty:
                df_med["fecha_dt"] = pd.to_datetime(df_med["fecha"])
                tiene_hora = (
                    (df_med["fecha_dt"].dt.hour != 0).any() or
                    (df_med["fecha_dt"].dt.minute != 0).any()
                )
                df_med["fecha_str"] = df_med["fecha_dt"].dt.strftime(
                    "%d/%m/%Y %H:%M" if tiene_hora else "%d/%m/%Y"
                )

                vars_disponibles = sorted(df_med["variable"].unique())
                st.markdown("### 📊 Evolución Temporal de Parámetros Métricos")
                vars_a_graficar = st.multiselect(
                    "Seleccione las variables para graficar:",
                    options=vars_disponibles,
                    default=[
                        v for v in vars_disponibles
                        if v in ["FEVI", "AVAo EC", "Gradiente medio Ao"]
                    ][:3],
                )

                if vars_a_graficar:
                    df_num = df_med[
                        df_med["variable"].isin(vars_a_graficar) &
                        df_med["valor_num"].notna()
                    ].copy()
                    if not df_num.empty:
                        fig = px.line(
                            df_num,
                            x="fecha_dt", y="valor_num", color="variable",
                            markers=True,
                            title="Curva evolutiva de parámetros",
                            labels={
                                "fecha_dt": "Fecha del Examen",
                                "valor_num": "Valor Obtenido",
                                "variable": "Parámetro",
                            },
                        )
                        fig.update_xaxes(tickformat="%d/%m/%Y")
                        st.plotly_chart(fig, use_container_width=True)

                with st.expander("👁️ Ver matriz completa de datos crudos"):
                    df_all = df_med.copy()
                    df_all["Valor"] = df_all.apply(
                        lambda row: row["valor_num"] if pd.notna(row["valor_num"]) else row["valor_texto"],
                        axis=1,
                    )
                    df_show = df_all[["fecha_str", "medico", "tipo_estudio", "variable", "Valor"]].copy()
                    df_show = df_show.sort_values(["fecha_str", "variable"])
                    st.dataframe(df_show, use_container_width=True)

    # ==================================================
    # 5. TENDENCIA GLOBAL (SOLO SI HAY VARIABLES CON DATOS)
    # ==================================================
    st.divider()
    if codigo_var:
        st.subheader(f"🌍 Tendencia global de '{var_seleccionada}' en todos los pacientes")

        mediciones_globales = (
            session.query(
                Medicion.valor_num,
                Estudio.fecha_estudio,
                Paciente.nombres,
                Paciente.apellido_paterno,
                Paciente.apellido_materno,
                Paciente.rut,
            )
            .join(Estudio, Medicion.estudio_id == Estudio.id)
            .join(Paciente, Estudio.paciente_rut == Paciente.rut)
            .filter(
                Medicion.codigo_variable == codigo_var,
                Medicion.valor_num.isnot(None),
                Estudio.fecha_estudio >= fecha_desde,
                Estudio.fecha_estudio <= fecha_hasta,
            )
            .order_by(Estudio.fecha_estudio)
            .all()
        )

        if mediciones_globales:
            df_global = pd.DataFrame(
                mediciones_globales,
                columns=["valor", "fecha", "nombres", "apellido_paterno", "apellido_materno", "rut"],
            )
            df_global["fecha_dt"] = pd.to_datetime(df_global["fecha"])
            df_global["fecha_str"] = df_global["fecha_dt"].dt.strftime("%d/%m/%Y")
            df_global["paciente"] = df_global["apellido_paterno"] + " " + df_global["nombres"]

            col_grafico, col_tabla = st.columns([2, 1])
            with col_grafico:
                fig_global = px.scatter(
                    df_global,
                    x="fecha_dt", y="valor",
                    hover_data=["paciente", "rut"],
                    title=f"Evolución de {var_seleccionada} en toda la cohorte",
                    labels={"fecha_dt": "Fecha", "valor": f"{var_seleccionada}"},
                    trendline="lowess",
                )
                fig_global.update_xaxes(tickformat="%d/%m/%Y", title_text="Fecha")
                st.plotly_chart(fig_global, use_container_width=True)
            with col_tabla:
                st.write(f"**Estadísticas descriptivas ({var_seleccionada})**")
                st.dataframe(df_global["valor"].describe(), use_container_width=True)
        else:
            st.info(f"No hay mediciones numéricas para '{var_seleccionada}' en el período seleccionado.")
    else:
        st.info("No hay variables con mediciones guardadas en la base de datos.")

except Exception as e:
    st.error(f"Error inesperado en el panel: {e}")
    import traceback
    st.code(traceback.format_exc())

finally:
    session.close()