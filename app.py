# app.py
import streamlit as st
from datetime import date
from sqlalchemy import func

# Importaciones de tu base de datos
from database.database import SessionLocal
from database.models import Paciente, Estudio

# 1. Configuración general de la página
st.set_page_config(
    page_title="EcoCardioNet | Inicio",
    page_icon="🫀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Obtener datos reales de la base de datos
_session = SessionLocal()
try:
    # Total de pacientes
    total_pacientes = _session.query(Paciente).count()
    
    # Total de estudios
    total_estudios = _session.query(Estudio).count()
    
    # Estudios del mes actual
    hoy = date.today()
    primer_dia_mes = date(hoy.year, hoy.month, 1)
    estudios_este_mes = _session.query(Estudio).filter(Estudio.fecha_estudio >= primer_dia_mes).count()
    
    # Médicos activos (contar nombres distintos en los estudios)
    medicos_activos = _session.query(Estudio.medico).filter(Estudio.medico.isnot(None), Estudio.medico != "").distinct().count()
finally:
    _session.close()

# 3. Encabezado principal
st.title("🫀 EcoCardioNet")
st.markdown("**Sistema integral de registro, análisis y seguimiento ecocardiográfico.**")
st.divider()

# 4. Sección de Accesos Rápidos
st.subheader("🚀 Accesos Rápidos")
col1, col2, col3 = st.columns(3)

with col1:
    st.info("📝 **Registrar un Examen**\n\nIngresa los datos de un nuevo paciente y documenta su ecocardiograma.")
    st.page_link("pages/estudios.py", label="Ir a Nuevo Estudio", icon="➕")

with col2:
    st.success("📊 **Ver Historial Clínico**\n\nBusca pacientes existentes, analiza tendencias y descarga PDFs históricos.")
    st.page_link("pages/historial.py", label="Ir a Historial", icon="🔍")

with col3:
    st.warning("⚙️ **Configuración**\n\nAdministra las variables ecocardiográficas, médicos y bases de datos.")
    # st.page_link("pages/configuracion.py", label="Ir a Ajustes", icon="⚙️") 

st.divider()

# 5. Panel de Resumen / Dashboard (CON DATOS REALES)
st.subheader("📈 Resumen del Sistema")
m1, m2, m3, m4 = st.columns(4)

m1.metric(
    label="Pacientes Registrados", 
    value=f"{total_pacientes:,}".replace(",", ".")
)
m2.metric(
    label="Estudios Realizados", 
    value=f"{total_estudios:,}".replace(",", "."), 
    delta=f"{estudios_este_mes} este mes",
    delta_color="normal"
)
m3.metric(
    label="Informes Generados", 
    value=f"{total_estudios:,}".replace(",", ".") # Coincide con los estudios si todos tienen informe
)
m4.metric(
    label="Médicos Activos", 
    value=medicos_activos
)

# 6. Mensaje en la barra lateral
with st.sidebar:
    st.markdown("### Navegación")
    st.success("👆 Selecciona un módulo en el menú superior para comenzar.")
    st.caption(f"© {hoy.year} EcoCardioNet")