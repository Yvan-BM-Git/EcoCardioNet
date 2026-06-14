# Archivo principal: app.py 
import streamlit as st
import time
from datetime import datetime
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash
from database.database import SessionLocal
# Importamos todas las tablas necesarias
from database.models import Usuario, Rol, Paciente, Estudio 
from menu import generar_menu

# Configuración de la página (debe ir al principio)
st.set_page_config(page_title="EcoCardioNet", page_icon="🫀", layout="wide")

# Inicializamos las variables de sesión necesarias
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if "vista_actual" not in st.session_state:
    st.session_state["vista_actual"] = "login" # Puede ser 'login' o 'recuperar'

# Llamamos a nuestro menú (que estará oculto si no hay sesión)
generar_menu()

# ==================================================
# CALLBACK DINÁMICO PARA AUTOCOMPLETAR RUT EN VIVO
# ==================================================
def formatear_rut_callback(key_destino):
    rut_actual = st.session_state.get(key_destino, "")
    if not rut_actual:
        return

    # Limpiar: dejar solo números y la letra K
    limpio = "".join(c for c in rut_actual.upper() if c.isdigit() or c == "K")
    limpio = limpio[:9]

    if len(limpio) < 2:
        st.session_state[key_destino] = limpio
        return

    cuerpo = limpio[:-1]
    dv = limpio[-1]

    if cuerpo.isdigit():
        cuerpo_formateado = f"{int(cuerpo):,}".replace(",", ".")
        st.session_state[key_destino] = f"{cuerpo_formateado}-{dv}"


# ==========================================
# 1. PANTALLA DE INICIO DE SESIÓN / RECUPERACIÓN (Si no está autenticado)
# ==========================================
if not st.session_state["autenticado"]:
    col1, col2, col3 = st.columns([1, 1.2, 1])
    
    with col2:
        st.markdown("<h1 style='text-align: center;'>🫀 EcoCardioNet</h1>", unsafe_allow_html=True)
        
        # --- SUB-PANTALLA: FORMULARIO DE LOGIN ---
        if st.session_state["vista_actual"] == "login":
            st.markdown("<h4 style='text-align: center; color: gray;'>Iniciar Sesión</h4>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            with st.container(border=True): 
                # Campo de RUT con autocompletado en vivo
                key_rut_login = "rut_login_input"
                rut = st.text_input(
                    "RUT", 
                    placeholder="Ej: 12.345.678-9",
                    key=key_rut_login,
                    on_change=formatear_rut_callback,
                    args=(key_rut_login,)
                )
                
                password = st.text_input("Contraseña", type="password")
                
                if st.button("Ingresar", type="primary", use_container_width=True):
                    if not rut or not password:
                        st.warning("⚠️ Ingresa RUT y contraseña.")
                    else:
                        session = SessionLocal()
                        try:
                            usuario = session.query(Usuario).filter(Usuario.rut == rut.strip()).first()
                            if usuario and check_password_hash(usuario.password_hash, password):
                                if not usuario.activo:
                                    st.error("❌ Cuenta desactivada.")
                                else:
                                    rol_obj = session.query(Rol).filter(Rol.id == usuario.rol_id).first()
                                    nombre_rol = rol_obj.nombre if rol_obj else "Sin Rol"

                                    st.session_state["autenticado"] = True
                                    st.session_state["usuario_actual"] = {
                                        "rut": usuario.rut, 
                                        "nombre": usuario.nombre, 
                                        "rol": nombre_rol
                                    }
                                    st.success("✅ Acceso concedido")
                                    time.sleep(0.5)
                                    st.rerun()
                            else:
                                st.error("❌ RUT o contraseña incorrectos.")
                        except Exception as e:
                            st.error(f"Error de base de datos: {e}")
                        finally:
                            session.close()
                
                # Enlace dinámico para cambiar de pantalla
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🔑 ¿Olvidaste tu contraseña? Recupérala aquí", use_container_width=True):
                    st.session_state["vista_actual"] = "recuperar"
                    st.rerun()

        # --- SUB-PANTALLA: AUTO-RECUPERACIÓN POR CORREO ---
        elif st.session_state["vista_actual"] == "recuperar":
            st.markdown("<h4 style='text-align: center; color: gray;'>Recuperar Contraseña</h4>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            with st.container(border=True):
                st.info("💡 Introduce tus datos registrados para validar tu identidad y asignar una nueva clave.")
                
                # Campo de RUT con autocompletado en vivo
                key_rut_recup = "rut_recuperar_input"
                rut_recup = st.text_input(
                    "Ingresa tu RUT registrado",
                    placeholder="Ej: 12.345.678-9",
                    key=key_rut_recup,
                    on_change=formatear_rut_callback,
                    args=(key_rut_recup,)
                )
                
                email_recup = st.text_input("Ingresa tu Correo Electrónico registrado")
                nueva_password = st.text_input("Escribe tu NUEVA Contraseña", type="password")
                
                col_btn1, col_btn2 = st.columns(2)
                
                with col_btn1:
                    if st.button("🔄 Cambiar Contraseña", type="primary", use_container_width=True):
                        if not rut_recup or not email_recup or not nueva_password:
                            st.error("❌ Todos los campos son obligatorios.")
                        else:
                            session = SessionLocal()
                            try:
                                # Buscamos al usuario que coincida estrictamente con RUT y Email (quitando espacios vacíos)
                                usuario = session.query(Usuario).filter(
                                    Usuario.rut == rut_recup.strip(),
                                    Usuario.email == email_recup.strip()
                                ).first()
                                
                                if usuario:
                                    # Modificamos la contraseña encriptándola al vuelo
                                    usuario.password_hash = generate_password_hash(nueva_password)
                                    session.commit()
                                    st.success("✅ ¡Contraseña actualizada con éxito!")
                                    time.sleep(1.5)
                                    # Lo devolvemos al login de forma automática
                                    st.session_state["vista_actual"] = "login"
                                    st.rerun()
                                else:
                                    st.error("❌ Los datos ingresados no coinciden con ningún usuario registrado.")
                            except Exception as e:
                                session.rollback()
                                st.error(f"Error en el proceso: {e}")
                            finally:
                                session.close()
                                
                with col_btn2:
                    if st.button("❌ Cancelar", use_container_width=True):
                        st.session_state["vista_actual"] = "login"
                        st.rerun()
                        
    st.stop() # Detiene la ejecución aquí para que no dibuje el panel central si no se ha logueado


# ==========================================
# 2. PANEL DE CONTROL (Si SÍ está autenticado)
# ==========================================

# --- A. OBTENER DATOS REALES DE LA BASE DE DATOS ---
session = SessionLocal()
try:
    hoy = datetime.now()
    total_pacientes = session.query(Paciente).count()
    total_estudios = session.query(Estudio).count()
    
    # Versión limpia y segura para PostgreSQL usando rangos de fecha del mes actual
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


# --- B. DIBUJAR LA INTERFAZ ---
st.title("🫀 EcoCardioNet")
st.markdown("**Sistema integral de registro, análisis y seguimiento ecocardiográfico.**")
st.divider()

# Sección de Accesos Rápidos
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
with col4:
    st.warning("📊 **Exportar Base de Datos**\n\nExporta los datos del sistema en formato PDF o Excel.")
    st.page_link("pages/exportar.py", label="Ir a Exportar", icon="📤")

st.divider()

# Panel de Resumen / Dashboard (AHORA CON DATOS DINÁMICOS)
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