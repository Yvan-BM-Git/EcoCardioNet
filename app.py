# Archivo principal: app.py
import streamlit as st
from datetime import datetime
from sqlalchemy import func
from werkzeug.security import check_password_hash
from database.database import SessionLocal, asegurar_bd
from database.models import Usuario, Rol, Paciente, Estudio
from menu import generar_menu
from utils.login_ui import mostrar_login

st.set_page_config(page_title="EcoCardioNet", page_icon="🫀", layout="wide")
asegurar_bd()  # crea tablas/migraciones una vez; si la BD no responde, mensaje claro

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if "vista_actual" not in st.session_state:
    st.session_state["vista_actual"] = "login"

generar_menu()


def autenticar(rut: str, password: str):
    """Devuelve (usuario_dict, None) si las credenciales son válidas; si no, (None, mensaje)."""
    session = SessionLocal()
    try:
        usuario = session.query(Usuario).filter(Usuario.rut == rut).first()
        if not usuario or not check_password_hash(usuario.password_hash, password):
            return None, "RUT o contraseña incorrectos."
        if not usuario.activo:
            return None, "La cuenta está desactivada. Contacta al Administrador."
        rol_obj = session.query(Rol).filter(Rol.id == usuario.rol_id).first()
        return {
            "rut": usuario.rut,
            "nombre": usuario.nombre,
            "rol": rol_obj.nombre if rol_obj else "Sin Rol",
        }, None
    except Exception as e:
        return None, f"No se pudo conectar con la base de datos ({type(e).__name__})."
    finally:
        session.close()


if not st.session_state["autenticado"]:
    st.session_state["vista_actual"] = "login"
    envio = mostrar_login(
        rut_previo=st.session_state.get("login_rut_previo", ""),
        error=st.session_state.get("login_error"),
    )
    if envio:
        rut, password = envio
        if not rut or not password:
            st.session_state["login_error"] = "Ingresa tu RUT y tu contraseña."
        else:
            usuario, error = autenticar(rut, password)
            if usuario:
                st.session_state["autenticado"] = True
                st.session_state["usuario_actual"] = usuario
                st.session_state.pop("login_error", None)
                st.session_state.pop("login_rut_previo", None)
            else:
                st.session_state["login_error"] = error
                st.session_state["login_rut_previo"] = rut
        st.rerun()
    st.stop()


# ==========================================
# 2. PANEL DE CONTROL (Si SÍ está autenticado)
# ==========================================
session = SessionLocal()
try:
    hoy = datetime.now()
    total_pacientes = session.query(Paciente).count()
    total_estudios = session.query(Estudio).count()

    inicio_mes = datetime(hoy.year, hoy.month, 1)
    estudios_este_mes = session.query(Estudio).filter(
        Estudio.fecha_creacion >= inicio_mes
    ).count()

    medicos_activos = session.query(Estudio.medico).filter(Estudio.medico.isnot(None)).distinct().count()

except Exception as e:
    st.error(f"Error al cargar las métricas: {e}")
    total_pacientes, total_estudios, estudios_este_mes, medicos_activos = 0, 0, 0, 0
    hoy = datetime.now()
finally:
    session.close()


st.title("🫀 EcoCardioNet")
st.markdown("**Sistema integral de registro, análisis y seguimiento ecocardiográfico.**")
st.divider()

st.subheader("🚀 Accesos Rápidos")
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.error("👤 **Ingresar un Paciente Nuevo**\n\nAgrega un nuevo paciente al sistema para comenzar a registrar sus estudios.")
    st.page_link("pages/pacientes.py", label="Ir a Pacientes", icon="➕")
with col2:
    st.info("🩺 **Registrar un Examen**\n\nIngresa los datos de un nuevo paciente y documenta su ecocardiograma.")
    st.page_link("pages/estudios.py", label="Ir a Nuevo Estudio", icon="➕")
with col3:
    st.success("📁 **Ver Historial Clínico**\n\nBusca pacientes existentes, analiza tendencias y descarga PDFs históricos.")
    st.page_link("pages/historial.py", label="Ir a Historial", icon="🔍")
# with col4:
#     st.warning("📊 **Exportar Base de Datos**\n\nExporta los datos del sistema en formato PDF o Excel.")
#     st.page_link("pages/exportar.py", label="Ir a Exportar", icon="📤")
rol = st.session_state["usuario_actual"]["rol"]

with col4:
    if rol in ["Administrador", "Investigador"]:
        st.warning(
            "📊 **Exportar Base de Datos**\n\n"
            "Exporta los datos del sistema en formato CSV o Excel."
        )
        st.page_link(
            "pages/exportar.py",
            label="Ir a Exportar",
            icon="📤"
        )
    else:
        st.success(
            "🔒 **Acceso Clínico**\n\n"
            "Su perfil está habilitado para el registro y consulta de estudios."
        )

st.divider()

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
    value=f"{total_estudios:,}".replace(",", ".")
)
m4.metric(
    label="Médicos Activos",
    value=medicos_activos
)

st.markdown("<br><br>", unsafe_allow_html=True)
st.caption(f"© {hoy.year} EcoCardioNet - Sesión iniciada como: {st.session_state['usuario_actual']['nombre']}")