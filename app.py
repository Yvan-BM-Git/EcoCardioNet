# Archivo principal: app.py
import streamlit as st
from datetime import date
from werkzeug.security import check_password_hash
from database.database import SessionLocal, asegurar_bd
from database.models import Usuario, Rol
from menu import generar_menu
from utils.login_ui import mostrar_login
from utils.indicadores import mostrar_resumen
from utils import legal

st.set_page_config(page_title="EcoCardioNet", page_icon="🫀", layout="wide")
asegurar_bd()  # crea tablas/migraciones una vez; si la BD no responde, mensaje claro

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False

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


# Aceptación de Términos y Política (Ley 21.719): entre el login y la app.
if not st.session_state["autenticado"] and st.session_state.get("usuario_pendiente"):
    pendiente = st.session_state["usuario_pendiente"]
    respuesta = legal.pantalla_aceptacion(pendiente, st.session_state.get("legal_faltan", []))
    if respuesta == "aceptado":
        legal.registrar(pendiente["rut"], st.session_state.get("legal_faltan", []))
        st.session_state["autenticado"] = True
        st.session_state["usuario_actual"] = pendiente
    if respuesta:
        st.session_state.pop("usuario_pendiente", None)
        st.session_state.pop("legal_faltan", None)
        st.rerun()
    st.stop()

if not st.session_state["autenticado"]:
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
                st.session_state.pop("login_error", None)
                st.session_state.pop("login_rut_previo", None)
                faltan = legal.pendientes(usuario["rut"])
                if faltan:
                    st.session_state["usuario_pendiente"] = usuario
                    st.session_state["legal_faltan"] = faltan
                else:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_actual"] = usuario
            else:
                st.session_state["login_error"] = error
                st.session_state["login_rut_previo"] = rut
        st.rerun()
    st.stop()


# ==========================================
# 2. PANEL DE CONTROL (Si SÍ está autenticado)
# ==========================================
usuario_actual = st.session_state["usuario_actual"]
rol = usuario_actual["rol"]

st.title("🫀 EcoCardioNet")
st.markdown("**Sistema integral de registro, análisis y seguimiento ecocardiográfico.**")
st.divider()

st.subheader("🚀 Accesos Rápidos")
col1, col2, col3 = st.columns(3)

with col1:
    st.info("🩺 **Registrar un Examen**\n\nIngresa los datos del paciente y documenta su ecocardiograma.")
    st.page_link("pages/estudios.py", label="Ir a Nuevo Estudio", icon="➕")
with col2:
    st.success("📁 **Ver Historial Clínico**\n\nBusca pacientes, analiza tendencias y descarga PDFs históricos.")
    st.page_link("pages/historial.py", label="Ir a Historial", icon="🔍")
with col3:
    if rol in ["Administrador", "Investigador"]:
        st.warning("📊 **Exportar Base de Datos**\n\nDescarga los datos anonimizados en CSV o Excel.")
        st.page_link("pages/exportar.py", label="Ir a Exportar", icon="📤")
    else:
        st.success("🔒 **Acceso Clínico**\n\nSu perfil está habilitado para el registro y consulta de estudios.")

st.divider()

st.subheader("📈 Resumen del Sistema")
mostrar_resumen(usuario_actual.get("nombre"))

st.markdown("<br>", unsafe_allow_html=True)
st.caption(f"© {date.today().year} EcoCardioNet · Sesión iniciada como: {usuario_actual['nombre']}")
