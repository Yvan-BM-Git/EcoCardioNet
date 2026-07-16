# Archivo: pages/historial.py
import streamlit as st
import re
import unicodedata
import math

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
    if st.button("🔑 Ir a Iniciar Sesión"):
        st.session_state["vista_actual"] = "login"
        st.switch_page("app.py")
    st.stop()

import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, date

import pdfplumber

from database.database import SessionLocal
from database.models import Paciente, Estudio, Medicion, Variable
from utils.pacientes_utils import (
    OPTS_PREV, OPTS_SEXO, DIC_PREFIJOS, LISTA_PREFIJOS,
    formatear_rut_dinamico, formatear_telefono_dinamico,
    separar_prefijo_numero, formatear_busqueda_rut,
)
from utils.pdf_informe import generar_pdf_desde_historial

st.title("📊 Panel de gestión clínica - Ecocardiografía")

# ==================================================
# CALLBACK DE FORMATEO (usa la key propia de esta página)
# ==================================================
def formatear_busqueda_callback():
    busqueda_actual = st.session_state.get("busqueda_input", "")
    st.session_state.busqueda_input = formatear_busqueda_rut(busqueda_actual)


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


def _buscar_valor_categorico(texto_normalizado, etiqueta, opciones):
    """Busca la etiqueta y verifica si alguna de las opciones conocidas aparece cerca."""
    et_norm = _normalizar(etiqueta)
    idx = texto_normalizado.find(et_norm)
    if idx == -1:
        return None
    ventana = texto_normalizado[idx: idx + len(et_norm) + 40]
    for opcion in opciones:
        if _normalizar(opcion) in ventana:
            return opcion
    return None


def extraer_mediciones(texto, variables_por_codigo):
    """
    Intenta extraer valores del texto de un informe y mapearlos a los códigos
    de la tabla Variable, respetando el tipo de cada variable (numero, categoria,
    texto). Devuelve {codigo: valor_str}.
    No pretende ser exhaustivo: el usuario revisa/corrige antes de guardar.
    """
    texto_norm = _normalizar(texto)
    resultados = {}

    # 1. Alias conocidos (numéricas, curadas a mano) — más confiables
    for codigo, etiquetas in ALIASES_MEDICIONES.items():
        var = variables_por_codigo.get(codigo)
        if not var or var.tipo != "numero":
            continue
        valor = _buscar_valor(texto_norm, etiquetas)
        if valor:
            resultados[codigo] = valor

    # 2. Fallback genérico por nombre de Variable, respetando el tipo
    for codigo, var in variables_por_codigo.items():
        if codigo in resultados:
            continue
        nombre_norm = _normalizar(var.nombre or "")
        if not nombre_norm or len(nombre_norm) < 3:
            continue

        if var.tipo == "numero":
            patron = re.escape(nombre_norm) + r'[^0-9\-]{0,15}' + _NUM
            m = re.search(patron, texto_norm)
            if m:
                resultados[codigo] = m.group(1).replace(",", ".")

        elif var.tipo == "categoria":
            opciones = [
                o.strip() for o in (getattr(var, "opciones", "") or "").split(";")
                if o.strip()
            ]
            if opciones:
                valor = _buscar_valor_categorico(texto_norm, nombre_norm, opciones)
                if valor:
                    resultados[codigo] = valor

        # "texto" se deja fuera de la extracción automática: el riesgo de falsos
        # positivos es alto y no aporta valor real revisarlo/corregirlo a ciegas.

    return resultados

def extraer_nombre_paciente(texto):
    """
    Extrae el nombre completo del paciente desde el texto del informe.

    Soporta dos formatos:
    - "Paciente : NOMBRES APELLIDO_PATERNO APELLIDO_MATERNO" (formato chileno habitual,
      sin coma).
    - "Name APELLIDO_PATERNO APELLIDO_MATERNO, NOMBRES" (equipos GE Healthcare / informes
      en inglés, con coma). En este caso las palabras ANTES de la coma son los apellidos
      (paterno y materno) y las palabras DESPUÉS de la coma son los nombres. Se descartan
      palabras de relleno como "Image" que a veces quedan intercaladas por el layout del PDF.
    """
    # Normalizar espacios y eliminar caracteres no imprimibles (la coma se conserva:
    # es parte del rango ASCII imprimible \x20-\x7E)
    texto = re.sub(r'\s+', ' ', texto)
    texto = re.sub(r'[^\x20-\x7E\u00C0-\u00FF]', '', texto)

    # --- Caso con coma: "APELLIDOS, NOMBRES" ---
    patron_coma = r'(?i)(?:paciente|nombre|patient|name)\s*:?\s*([A-ZÁÉÍÓÚÑa-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑa-záéíóúñ]+)?)\s*,'
    m_coma = re.search(patron_coma, texto)
    if m_coma:
        apellidos = [p for p in re.findall(r'[A-ZÁÉÍÓÚÑa-záéíóúñ]+', m_coma.group(1)) if len(p) >= 2]

        # Texto restante después de la coma, hasta el próximo separador de campo conocido
        resto = texto[m_coma.end():]
        m_fin = re.search(r'(?i)(?:r\.?u\.?t|rut|edad|años|patient\s*id)', resto)
        resto = resto[:m_fin.start()] if m_fin else resto

        # Descartar palabras de relleno tipo "Image 1", "Image 2" (ruido de layout del PDF)
        resto_limpio = re.sub(r'(?i)\bimage\s*\d*\b', ' ', resto)
        nombres = [p for p in re.findall(r'[A-ZÁÉÍÓÚÑa-záéíóúñ]+', resto_limpio) if len(p) >= 2]

        if not nombres or not apellidos:
            return None

        ap_paterno = apellidos[0]
        ap_materno = apellidos[1] if len(apellidos) >= 2 else ""

        # Se reordena a formato chileno (Nombres Apellido_Paterno Apellido_Materno)
        # para mantener compatibilidad con dividir_nombre_completo().
        partes_final = nombres[:2] + [p for p in (ap_paterno, ap_materno) if p]
        return " ".join(partes_final).title()

    # --- Caso sin coma: heurística chilena habitual (Nombres Apellido_Paterno Apellido_Materno) ---
    patron = r'(?i)(?:paciente|nombre|patient|name)\s*:?\s*([^:]+?)(?=\s*(?:r\.?u\.?t|rut|edad|años|\d))'
    m = re.search(patron, texto)
    if not m:
        return None

    raw = m.group(1).strip()

    # Extraer todas las palabras alfabéticas (ignora puntos, comas, etc.)
    palabras = re.findall(r'[A-ZÁÉÍÓÚÑa-záéíóúñ]+', raw)

    # Filtrar palabras de una sola letra (como la 'R' suelta)
    palabras_limpias = [p for p in palabras if len(p) >= 2]

    if len(palabras_limpias) >= 3:
        nombre_final = " ".join(palabras_limpias[:3])  # Nombres + dos apellidos
    elif len(palabras_limpias) == 2:
        nombre_final = " ".join(palabras_limpias[:2])  # Solo nombres + paterno
    else:
        return None

    return nombre_final.title()

def dividir_nombre_completo(nombre_completo):
    """
    Separa el nombre completo en:
    - Nombres
    - Apellido paterno
    - Apellido materno
    Asume el formato chileno: [Nombres] [Apellido Paterno] [Apellido Materno]
    """
    if not nombre_completo:
        return "", "", ""
    partes = nombre_completo.split()
    if len(partes) == 1:
        return partes[0], "", ""
    elif len(partes) == 2:
        return partes[0], partes[1], ""
    else:
        # El último es materno, el penúltimo paterno, el resto nombres
        return " ".join(partes[:-2]), partes[-2], partes[-1]
    
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


def calcular_asc_imc_import():
    """Calcula ASC (fórmula de Mosteller) e IMC a partir de peso/talla del formulario de importación."""
    try:
        peso_str = st.session_state.get("peso_import_input_g", "").replace(",", ".")
        talla_str = st.session_state.get("talla_import_input_g", "").replace(",", ".")
        peso_f = float(peso_str)
        talla_f = float(talla_str)
        if peso_f > 0 and talla_f > 0:
            asc = math.sqrt((peso_f * talla_f) / 3600)
            talla_m = talla_f / 100
            imc = peso_f / (talla_m ** 2)
            st.session_state["asc_import_val_g"] = f"{asc:.2f}"
            st.session_state["imc_import_val_g"] = f"{imc:.2f}"
        else:
            st.session_state["asc_import_val_g"] = ""
            st.session_state["imc_import_val_g"] = ""
    except (ValueError, ZeroDivisionError):
        st.session_state["asc_import_val_g"] = ""
        st.session_state["imc_import_val_g"] = ""


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

    col1, col2 = st.sidebar.columns(2)

    with col1:
        fecha_desde = st.date_input("Desde", value=default_start)

    with col2:
        fecha_hasta = st.date_input("Hasta", value=default_end)

    tipos_estudio = session.query(Estudio.tipo_estudio).distinct().all()
    tipos_estudio = [t[0] for t in tipos_estudio if t[0]]
    tipo_seleccionado = st.sidebar.multiselect("Tipo de estudio", tipos_estudio, default=tipos_estudio)

    st.sidebar.subheader("👨‍⚕️ Médico responsable")

    medicos_db = session.query(Estudio.medico).distinct().all()
    medicos_db = [m[0] for m in medicos_db if m[0]]

    def normalizar_medico(nombre):
        nombre = nombre.strip()
        nombre = re.sub(r"\s+", " ", nombre)
        nombre = re.sub(
            r"\b(Cardiologo|Cardiólogo|Cardiology)\b",
            "",
            nombre,
            flags=re.IGNORECASE
        )
        nombre = nombre.strip()
        clave = unicodedata.normalize("NFKD", nombre)
        clave = "".join(c for c in clave if not unicodedata.combining(c))
        clave = clave.lower()
        return clave, nombre

    medicos_dict = {}
    for nombre in medicos_db:
        clave, limpio = normalizar_medico(nombre)
        if clave not in medicos_dict:
            medicos_dict[clave] = limpio
        elif len(limpio) < len(medicos_dict[clave]):
            medicos_dict[clave] = limpio

    medicos = sorted(medicos_dict.values())

    buscar = st.sidebar.text_input("Buscar médico", placeholder="Apellido...")

    if buscar:
        medicos_filtrados = [m for m in medicos if buscar.lower() in m.lower()]
    else:
        medicos_filtrados = medicos

    medico_seleccionado = st.sidebar.multiselect(
        "Seleccionar",
        options=medicos_filtrados,
        default=medicos_filtrados,
        label_visibility="collapsed"
    )

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
            "Al subir el PDF del informe, el sistema intenta detectar el RUT, nombre y "
            "algunos valores automáticamente. Si el paciente ya existe en la "
            "base de datos se usa su ficha; si no existe, se puede registrar en el momento. "
            "**Revisar y corregir** los datos antes de confirmar."
        )
        archivo_pdf_global = st.file_uploader(
            "Selecciona el archivo PDF", type=["pdf"], key="uploader_pdf_global"
        )

        if archivo_pdf_global is not None:
            # --- Generar un sufijo único para este archivo ---
            pdf_suffix = re.sub(r'[^a-zA-Z0-9_]', '_', f"{archivo_pdf_global.name}_{archivo_pdf_global.size}")
            cache_key_g = f"extraccion_pdf_global_{pdf_suffix}"

            # --- Extraer SOLO la primera vez que se ve este archivo en la sesión ---
            archivo_pdf_global.seek(0)
            texto_extraido_g = extraer_texto_pdf(archivo_pdf_global)

            # === DEPURACIÓN ===
            st.text_area("🔍 Texto crudo extraído del PDF (primeros 1000 caracteres)", texto_extraido_g)

            if cache_key_g not in st.session_state:
                with st.spinner("Extrayendo texto y datos del PDF..."):
                    nombre_crudo = extraer_nombre_paciente(texto_extraido_g)
                    st.caption(f"🔎 Nombre crudo detectado: **{nombre_crudo}**")

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

                    # Reset de tablas manuales (solo al procesar un PDF nuevo)
                    st.session_state["manual_numericas"] = pd.DataFrame(columns=["Código", "Valor"])
                    st.session_state["manual_categoricas"] = pd.DataFrame(columns=["Código", "Valor"])
                    st.session_state["manual_texto"] = pd.DataFrame(columns=["Código", "Valor"])

                    # Limpiar editores antiguos de otros PDFs previamente cargados en esta sesión
                    for k in list(st.session_state.keys()):
                        if k.startswith("editor_") and not k.endswith(pdf_suffix):
                            st.session_state.pop(k, None)
                    st.session_state.pop("cod_categorica_actual", None)
                    st.session_state.pop("valor_categorica_actual", None)

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
                st.caption(f"Nombre completo detectado: **{nombre_completo_detectado}**")
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
                    sexo_detectado_g = generales_g.get("sexo", "")
                    idx_sexo_g = OPTS_SEXO.index(sexo_detectado_g) if sexo_detectado_g in OPTS_SEXO else 0
                    sexo_nuevo_g = st.selectbox("Sexo", OPTS_SEXO, index=idx_sexo_g, key="sexo_nuevo_import_global")

                # ------------------------------------------------
                # Campos adicionales (no vienen en el PDF de eco):
                # previsión, teléfono fijo, celular, email
                # ------------------------------------------------
                cn6, cn7 = st.columns(2)
                with cn6:
                    prevision_nuevo_g = st.selectbox(
                        "Previsión", OPTS_PREV, index=0, key="prevision_nuevo_import_global"
                    )
                with cn7:
                    email_nuevo_g = st.text_input(
                        "Email", value="", placeholder="ejemplo@correo.com",
                        key="email_nuevo_import_global"
                    )

                cn8, cn9 = st.columns(2)
                with cn8:
                    cp1, cn1_ = st.columns([1, 2])
                    with cp1:
                        idx_p_fono_g = LISTA_PREFIJOS.index("+56") if "+56" in LISTA_PREFIJOS else LISTA_PREFIJOS.index("OTRO")
                        sel_pref_fono_g = st.selectbox(
                            "Cód.", options=LISTA_PREFIJOS, index=idx_p_fono_g,
                            format_func=lambda x: DIC_PREFIJOS[x], key="p_fono_import_global"
                        )
                        if sel_pref_fono_g == "OTRO":
                            prefijo_fono_g = st.text_input("Escriba Cód.", value="+", key="m_fono_import_global")
                        else:
                            prefijo_fono_g = sel_pref_fono_g
                    with cn1_:
                        fono_base_g = st.text_input(
                            "Fono fijo", value="", placeholder="22 123 4567",
                            max_chars=11, key="fono_base_import_global",
                            on_change=formatear_telefono_dinamico, args=("fono_base_import_global",)
                        )
                    fono_fijo_final_g = f"{prefijo_fono_g} {fono_base_g.strip()}" if fono_base_g.strip() else ""

                with cn9:
                    cp2, cn2_ = st.columns([1, 2])
                    with cp2:
                        idx_p_cel_g = LISTA_PREFIJOS.index("+56") if "+56" in LISTA_PREFIJOS else LISTA_PREFIJOS.index("OTRO")
                        sel_pref_cel_g = st.selectbox(
                            "Cód.", options=LISTA_PREFIJOS, index=idx_p_cel_g,
                            format_func=lambda x: DIC_PREFIJOS[x], key="p_cel_import_global"
                        )
                        if sel_pref_cel_g == "OTRO":
                            prefijo_cel_g = st.text_input("Escriba Cód.", value="+", key="m_cel_import_global")
                        else:
                            prefijo_cel_g = sel_pref_cel_g
                    with cn2_:
                        celular_base_g = st.text_input(
                            "Celular", value="", placeholder="987 654 321",
                            max_chars=11, key="celular_base_import_global",
                            on_change=formatear_telefono_dinamico, args=("celular_base_import_global",)
                        )
                    celular_final_g = f"{prefijo_cel_g} {celular_base_g.strip()}" if celular_base_g.strip() else ""

                datos_paciente_nuevo = {
                    "rut": rut_editable.strip(),
                    "nombres": nombres_nuevo_g.strip(),
                    "apellido_paterno": ap_paterno_nuevo_g.strip(),
                    "apellido_materno": ap_materno_nuevo_g.strip(),
                    "fecha_nacimiento": fecha_nac_nuevo_g,
                    "sexo": sexo_nuevo_g if sexo_nuevo_g else None,
                    "prevision": prevision_nuevo_g if prevision_nuevo_g else None,
                    "fono_fijo": fono_fijo_final_g,
                    "celular": celular_final_g,
                    "email": email_nuevo_g.strip(),
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

                # Inicialización de los valores calculados (ASC/IMC) antes de crear los widgets
                st.session_state.setdefault("asc_import_val_g", "")
                st.session_state.setdefault("imc_import_val_g", "")

                cg1, cg2, cg3, cg4 = st.columns([3, 3, 1.5, 1.5])
                with cg1:
                    # "medicos" ya fue calculado más arriba (lista limpia y deduplicada desde la BD)
                    opciones_medico_g = medicos + ["Otro..."]
                    medico_sugerido_g = generales_g.get("medico_sugerido", "")
                    index_medico_g = (
                        opciones_medico_g.index(medico_sugerido_g)
                        if medico_sugerido_g in opciones_medico_g
                        else len(opciones_medico_g) - 1  # "Otro..."
                    )
                    medico_seleccionado_g = st.selectbox(
                        "Médico responsable", opciones_medico_g,
                        index=index_medico_g, key="medico_select_import_global"
                    )
                    if medico_seleccionado_g == "Otro...":
                        medico_import_g = st.text_input(
                            "Especifique el médico",
                            value=medico_sugerido_g if medico_sugerido_g not in opciones_medico_g else "",
                            placeholder="Nombre del médico",
                            key="medico_otro_import_global",
                        )
                    else:
                        medico_import_g = medico_seleccionado_g
                with cg2:
                    tipo_import_g = st.selectbox(
                        "Tipo de estudio",
                        ["Ecocardiograma Transtorácico", "Ecocardiograma Transesofágico", "Ecocardiograma de Estrés", "Ecocardiograma 3D"],
                        key="tipo_import_global"
                    )
                with cg3:
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
                with cg4:
                    ficha_clinica_import_g = st.text_input("Ficha Clínica", key="ficha_clinica_import_global")

                cg5, cg6, cg7 = st.columns(3)
                with cg5:
                    opciones_patologia_g = [
                        "Sin antecedentes",
                        "Hipertensión arterial (HTA)",
                        "Diabetes Mellitus tipo 2",
                        "Dislipidemia",
                        "Cardiopatía coronaria",
                        "Fibrilación auricular",
                        "Insuficiencia cardíaca",
                        "Enfermedad renal crónica",
                        "EPOC",
                        "Obesidad",
                        "Hipotiroidismo",
                        "Tabaquismo",
                        "Valvulopatía",
                        "Cardiopatía congénita",
                        "Otro..."
                    ]
                    patologias_seleccionadas_g = st.multiselect(
                        "Patología de base",
                        opciones_patologia_g,
                        placeholder="Selecciona una o más patologías",
                        key="patologia_import_global",
                    )
                    otra_patologia_g = ""
                    if "Otro..." in patologias_seleccionadas_g:
                        otra_patologia_g = st.text_input(
                            "Especifique la(s) otra(s) patología(s)",
                            placeholder="Ej: Enfermedad de Chagas, etc.",
                            key="otra_patologia_import_global",
                        )
                    lista_patologias_final_g = [p for p in patologias_seleccionadas_g if p != "Otro..."]
                    if otra_patologia_g.strip():
                        lista_patologias_final_g.append(otra_patologia_g.strip())
                    diagnostico_import_g = ", ".join(lista_patologias_final_g)
                with cg6:
                    procedencia_import_g = st.text_input(
                        "Servicio de origen", placeholder="Ej: HRT, CESFAM, Dr. Eric Fuentes, etc.",
                        key="procedencia_import_global",
                    )
                with cg7:
                    destino_import_g = st.text_input(
                        "Servicio de destino", placeholder="Ej: HRT, CESFAM, etc.",
                        key="destino_import_global",
                    )

                cv1, cv2, cv3, cv4, cv5, cv6, cv7, cv8 = st.columns([1, 1, 1, 1, 1, 1, 2, 1])
                with cv1:
                    peso_import_g = st.text_input(
                        "PESO (kg)", value=generales_g.get("peso", ""),
                        key="peso_import_input_g", on_change=calcular_asc_imc_import,
                    )
                with cv2:
                    talla_import_g = st.text_input(
                        "TALLA (cm)", value=generales_g.get("talla", ""),
                        key="talla_import_input_g", on_change=calcular_asc_imc_import,
                    )
                with cv3:
                    asc_import_g = st.text_input("ASC", value=st.session_state.asc_import_val_g, disabled=True)
                with cv4:
                    imc_import_g = st.text_input("IMC", value=st.session_state.imc_import_val_g, disabled=True)
                with cv5:
                    pas_import_g = st.text_input("PAS", key="pas_import_global")
                with cv6:
                    pad_import_g = st.text_input("PAD", key="pad_import_global")
                with cv7:
                    opciones_ritmo_g = ["", "Sinusal", "Sinusal con ESV", "Sinusal con EV", "Taquicardia sinusal",
                                        "Braquicardia sinusal", "Fibrilación auricular", "Flutter auricular",
                                        "Marcapaso", "Otro"]
                    ritmo_detectado_g = generales_g.get("ritmo", "")
                    idx_ritmo_g = opciones_ritmo_g.index(ritmo_detectado_g) if ritmo_detectado_g in opciones_ritmo_g else 0
                    ritmo_import_g = st.selectbox("Ritmo", opciones_ritmo_g, index=idx_ritmo_g, key="ritmo_import_global")
                with cv8:
                    fcia_import_g = st.text_input(
                        "FCia", value=generales_g.get("fcia", ""), key="fcia_import_global",
                    )

                st.markdown("##### 3️⃣ Mediciones detectadas (editable)")

                codigos_detectados = list(datos_cache_g["mediciones"].keys())

                df_editado_import_g = pd.DataFrame(columns=["N°", "Código", "Nombre", "Valor detectado", "Unidad"])

                if not codigos_detectados:
                    st.info("No se detectó ningún valor automáticamente. El informe se guardará solo como PDF adjunto, salvo que agregues valores manualmente abajo.")
                else:
                    detectadas_por_tipo = {"numero": [], "categoria": [], "texto": []}
                    for codigo in codigos_detectados:
                        var = variables_por_codigo_global.get(codigo)
                        if not var:
                            continue
                        detectadas_por_tipo.setdefault(var.tipo, []).append(codigo)

                    def _fila_detectada(codigo, var, valor_bruto):
                        num_fila = codigos_detectados.index(codigo) + 1
                        return {
                            "N°": num_fila,
                            "Código": codigo,
                            "Nombre": var.nombre,
                            "Valor detectado": valor_bruto,
                            "Unidad": var.unidad or "",
                        }

                    piezas_df_detectadas = []

                    codigos_num_det = detectadas_por_tipo.get("numero", [])
                    if codigos_num_det:
                        st.caption("Numéricas")
                        filas_num_det = [
                            _fila_detectada(c, variables_por_codigo_global[c], float(datos_cache_g["mediciones"][c]))
                            for c in codigos_num_det
                        ]

                        df_num_det = st.data_editor(
                            pd.DataFrame(filas_num_det),
                            column_config={
                                "N°": st.column_config.NumberColumn("N°", disabled=True),
                                "Código": st.column_config.TextColumn(disabled=True),
                                "Nombre": st.column_config.TextColumn(disabled=True),
                                "Unidad": st.column_config.TextColumn(disabled=True),
                                "Valor detectado": st.column_config.NumberColumn(format="%.4g"),
                            },
                            hide_index=True,
                            use_container_width=True,
                            key=f"editor_import_global_numericas_{pdf_suffix}",
                        )
                        piezas_df_detectadas.append(df_num_det)

                    codigos_cat_det = detectadas_por_tipo.get("categoria", [])
                    if codigos_cat_det:
                        st.caption("Categóricas")
                        filas_cat_det = []
                        opciones_por_codigo_det = {}
                        for c in codigos_cat_det:
                            var = variables_por_codigo_global[c]
                            opciones_por_codigo_det[c] = [
                                o.strip() for o in (getattr(var, "opciones", "") or "").split(";") if o.strip()
                            ]
                            filas_cat_det.append(_fila_detectada(c, var, datos_cache_g["mediciones"][c]))

                        opciones_unicas_det = {tuple(v) for v in opciones_por_codigo_det.values()}
                        if len(opciones_unicas_det) == 1 and codigos_cat_det:
                            opciones_comunes_det = opciones_por_codigo_det[codigos_cat_det[0]]
                            valor_col_config_det = st.column_config.SelectboxColumn(options=opciones_comunes_det)
                        else:
                            valor_col_config_det = st.column_config.TextColumn()

                        df_cat_det = st.data_editor(
                            pd.DataFrame(filas_cat_det),
                            column_config={
                                "N°": st.column_config.NumberColumn("N°", disabled=True),
                                "Código": st.column_config.TextColumn(disabled=True),
                                "Nombre": st.column_config.TextColumn(disabled=True),
                                "Unidad": st.column_config.TextColumn(disabled=True),
                                "Valor detectado": valor_col_config_det,
                            },
                            hide_index=True,
                            use_container_width=True,
                            key=f"editor_import_global_categoricas_{pdf_suffix}",
                        )
                        piezas_df_detectadas.append(df_cat_det)

                    if piezas_df_detectadas:
                        df_editado_import_g = pd.concat(piezas_df_detectadas, ignore_index=True)

                st.markdown("##### Agregar variables manualmente (opcional)")

                codigos_ya_detectados = set(datos_cache_g["mediciones"].keys())

                vars_numericas = {c: v for c, v in variables_por_codigo_global.items() if v.tipo == "numero" and c not in codigos_ya_detectados}
                vars_categoricas = {c: v for c, v in variables_por_codigo_global.items() if v.tipo == "categoria" and c not in codigos_ya_detectados}
                vars_texto = {c: v for c, v in variables_por_codigo_global.items() if v.tipo == "texto" and c not in codigos_ya_detectados}

                def _inicializar_df_manual(key, columnas):
                    if key not in st.session_state:
                        st.session_state[key] = pd.DataFrame(columns=columnas)

                filas_nuevas = []

                if vars_numericas:
                    st.caption("Numéricas")
                    _inicializar_df_manual("manual_numericas", ["Código", "Valor"])
                    df_num = st.data_editor(
                        st.session_state["manual_numericas"],
                        num_rows="dynamic",
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Código": st.column_config.SelectboxColumn(
                                "Código", options=sorted(vars_numericas.keys()), required=True,
                            ),
                            "Valor": st.column_config.NumberColumn(
                                "Valor", required=True, format="%.4g",
                            ),
                        },
                        key=f"editor_manual_numericas_{pdf_suffix}",
                    )
                    st.session_state["manual_numericas"] = df_num.copy()
                    for _, fila in df_num.iterrows():
                        codigo, valor = fila["Código"], fila["Valor"]
                        if pd.notna(codigo) and codigo != "" and pd.notna(valor):
                            var = vars_numericas[codigo]
                            filas_nuevas.append({
                                "Código": codigo, "Nombre": var.nombre,
                                "Valor detectado": valor, "Unidad": var.unidad or ""
                            })


                if vars_categoricas:
                    st.caption("Categóricas")
                    _inicializar_df_manual("manual_categoricas", ["Código", "Valor"])

                    col_cat_cod, col_cat_valor = st.columns(2)
                    with col_cat_cod:
                        codigo_cat_actual = st.selectbox(
                            "Variable categórica a agregar",
                            options=[""] + sorted(vars_categoricas.keys()),
                            key="cod_categorica_actual",
                        )

                    opciones_cat = []
                    if codigo_cat_actual:
                        opciones_cat = [
                            o.strip() for o in (getattr(vars_categoricas[codigo_cat_actual], "opciones", "") or "").split(";")
                            if o.strip()
                        ]

                    if codigo_cat_actual and not opciones_cat:
                        st.warning(f"La variable '{codigo_cat_actual}' no tiene opciones configuradas en la base de datos.")
                    elif codigo_cat_actual:
                        with col_cat_valor:
                            valor_cat_actual = st.selectbox("Valor", options=opciones_cat, key="valor_categorica_actual")
                        if st.button("➕ Agregar fila categórica", key="btn_add_categorica"):
                            nueva = pd.DataFrame([{"Código": codigo_cat_actual, "Valor": valor_cat_actual}])
                            st.session_state["manual_categoricas"] = pd.concat(
                                [st.session_state["manual_categoricas"], nueva], ignore_index=True
                            )
                            st.rerun()

                    df_cat = st.data_editor(
                        st.session_state["manual_categoricas"],
                        num_rows="dynamic",
                        hide_index=True,
                        use_container_width=True,
                        disabled=["Código", "Valor"],
                        key=f"editor_manual_categoricas_{pdf_suffix}",
                    )
                    st.session_state["manual_categoricas"] = df_cat.copy()
                    for _, fila in df_cat.iterrows():
                        codigo, valor = fila["Código"], fila["Valor"]
                        if pd.notna(codigo) and codigo != "" and pd.notna(valor) and str(valor).strip():
                            var = vars_categoricas[codigo]
                            filas_nuevas.append({
                                "Código": codigo, "Nombre": var.nombre,
                                "Valor detectado": valor, "Unidad": var.unidad or ""
                            })

                if vars_texto:
                    st.caption("Texto")
                    _inicializar_df_manual("manual_texto", ["Código", "Valor"])
                    df_txt = st.data_editor(
                        st.session_state["manual_texto"],
                        num_rows="dynamic",
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Código": st.column_config.SelectboxColumn(
                                "Código", options=sorted(vars_texto.keys()), required=True,
                            ),
                            "Valor": st.column_config.TextColumn("Valor", required=True),
                        },
                        key=f"editor_manual_texto_{pdf_suffix}",
                    )
                    st.session_state["manual_texto"] = df_txt.copy()
                    for _, fila in df_txt.iterrows():
                        codigo, valor = fila["Código"], fila["Valor"]
                        if pd.notna(codigo) and codigo != "" and pd.notna(valor) and str(valor).strip():
                            var = vars_texto[codigo]
                            filas_nuevas.append({
                                "Código": codigo, "Nombre": var.nombre,
                                "Valor detectado": valor, "Unidad": var.unidad or ""
                            })

                if filas_nuevas:
                    df_editado_import_g = pd.concat(
                        [df_editado_import_g, pd.DataFrame(filas_nuevas)],
                        ignore_index=True
                    )

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
                                if hasattr(nuevo_paciente, 'prevision'):
                                    nuevo_paciente.prevision = datos_paciente_nuevo.get("prevision")
                                if hasattr(nuevo_paciente, 'fono_fijo'):
                                    nuevo_paciente.fono_fijo = datos_paciente_nuevo.get("fono_fijo") or None
                                if hasattr(nuevo_paciente, 'telefono'):
                                    nuevo_paciente.telefono = datos_paciente_nuevo.get("celular") or None
                                if hasattr(nuevo_paciente, 'email'):
                                    nuevo_paciente.email = datos_paciente_nuevo.get("email") or None
                                session_import.add(nuevo_paciente)
                                session_import.flush()

                            nuevo_estudio = Estudio(
                                paciente_rut=rut_final,
                                fecha_estudio=fecha_import_g,
                                tipo_estudio=tipo_import_g,
                                medico=medico_import_g or None,
                                ficha_clinica=ficha_clinica_import_g or None,
                                diagnostico=diagnostico_import_g or None,
                                peso=float(peso_import_g.replace(",", ".")) if peso_import_g else None,
                                talla=float(talla_import_g.replace(",", ".")) if talla_import_g else None,
                                asc_valor=float(asc_import_g) if asc_import_g else None,
                                imc=float(imc_import_g) if imc_import_g else None,
                                pas=pas_import_g or None,
                                pad=pad_import_g or None,
                                ritmo=ritmo_import_g or None,
                                fcia=fcia_import_g or None,
                                observaciones="[IMPORTADO DESDE PDF]",
                                pdf_original=datos_cache_g["pdf_bytes"],
                                pdf_nombre_archivo=datos_cache_g["pdf_nombre"],
                            )
                            # Campos opcionales: solo si el modelo Estudio los define.
                            # Evita "invalid keyword argument" si la columna no existe en la BD/modelo.
                            if hasattr(nuevo_estudio, "procedencia"):
                                nuevo_estudio.procedencia = procedencia_import_g or None
                            if hasattr(nuevo_estudio, "destino"):
                                nuevo_estudio.destino = destino_import_g or None

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
            st.markdown("---")
            rut_filtrado = st.selectbox(
                "🔍 Seleccione el paciente de la búsqueda",
                options=df_filtrado["RUT"].tolist(),
                index=None,
                placeholder="Resultados de búsqueda 👇",
                format_func=lambda r: f"{df_filtrado[df_filtrado['RUT'] == r]['Nombre completo'].iloc[0]} ({r})",
                key="selectbox_busqueda_historial",
            )
            if rut_filtrado:
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