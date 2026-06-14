# Archivo: pages/historial.py
import streamlit as st

# ==================================================
# CONFIGURACIÓN DE PÁGINA (Debe ser la primera instrucción)
# ==================================================
st.set_page_config(page_title="Historial Clínico", page_icon="📁", layout="wide")

from menu import generar_menu

# 1. Dibujar el menú dinámico
generar_menu()

# 2. Candado de seguridad
if not st.session_state.get("autenticado", False):
    st.warning("🛑 Debes iniciar sesión para ver esta página.")
    st.stop()

import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import io

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
# FUNCIÓN PDF
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


session = SessionLocal()

try:
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
    # 1. Rescatar el RUT seleccionado dinámicamente desde el session_state
    rut_paciente_actual = st.session_state.get("selectbox_busqueda_historial") or st.session_state.get("selectbox_historial_paciente")

    # 2. Preparar la consulta uniendo Variable, Medicion y Estudio
    query_vars = (
        session.query(Variable.codigo, Variable.nombre, Variable.unidad)
        .join(Medicion, Variable.codigo == Medicion.codigo_variable)
        .join(Estudio, Medicion.estudio_id == Estudio.id)
    )

    # 3. Si hay un paciente seleccionado, filtramos estrictamente por su RUT
    if rut_paciente_actual:
        query_vars = query_vars.filter(Estudio.paciente_rut == rut_paciente_actual)

    # 4. Ejecutar la consulta evitando duplicados
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
                f"(Dr/a. {est.medico or 'No registrado'})": est
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