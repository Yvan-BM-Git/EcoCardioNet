# Archivo principal: app.py
import streamlit as st
import streamlit.components.v1 as components
import time
from datetime import datetime
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash
from database.database import SessionLocal
from database.models import Usuario, Rol, Paciente, Estudio
from menu import generar_menu

st.set_page_config(page_title="EcoCardioNet", page_icon="🫀", layout="wide")

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
if "vista_actual" not in st.session_state:
    st.session_state["vista_actual"] = "login"

generar_menu()


def formatear_rut_callback(key_destino):
    rut_actual = st.session_state.get(key_destino, "")
    if not rut_actual:
        return
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


def inyectar_soporte_password_manager(exito_login=False, rut="", password="", nombre=""):
    guardar_cred_js = ""
    if exito_login:
        rut_js = rut.replace("'", "\\'")
        pass_js = password.replace("'", "\\'")
        nombre_js = nombre.replace("'", "\\'")
        guardar_cred_js = f"""
        try {{
            if (window.PasswordCredential && navigator.credentials) {{
                const cred = new PasswordCredential({{
                    id: '{rut_js}',
                    password: '{pass_js}',
                    name: '{nombre_js}'
                }});
                navigator.credentials.store(cred).catch(function(e) {{
                    console.log('No se pudo guardar credencial:', e);
                }});
            }}
        }} catch (e) {{ console.log('Credential API no disponible:', e); }}
        """

    js = f"""
    <script>
    (function() {{
        function aplicarAutocomplete() {{
            try {{
                const doc = window.parent.document;
                const inputs = doc.querySelectorAll('input');
                inputs.forEach(function(inp) {{
                    const label = (inp.getAttribute('aria-label') || '').toLowerCase();
                    if (label.includes('rut')) {{
                        inp.setAttribute('autocomplete', 'username');
                        inp.setAttribute('name', 'username');
                    }}
                    if (inp.type === 'password') {{
                        inp.setAttribute('autocomplete', 'current-password');
                        inp.setAttribute('name', 'current-password');
                    }}
                }});
            }} catch (e) {{ console.log('No se pudo ajustar autocomplete:', e); }}
        }}
        aplicarAutocomplete();
        setTimeout(aplicarAutocomplete, 300);
        setTimeout(aplicarAutocomplete, 800);
        {guardar_cred_js}
    }})();
    </script>
    """
    components.html(js, height=0, width=0)


if not st.session_state["autenticado"]:
    col1, col2, col3 = st.columns([1, 1.2, 1])

    with col2:
        st.markdown("<h1 style='text-align: center;'>🫀 EcoCardioNet</h1>", unsafe_allow_html=True)

        if st.session_state["vista_actual"] == "login":
            st.markdown("<h4 style='text-align: center; color: gray;'>Iniciar Sesión</h4>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            with st.container(border=True):
                # El campo RUT queda FUERA del st.form porque usa on_change
                # (Streamlit no permite callbacks on_change en widgets dentro de un form,
                # solo en st.form_submit_button). Sigue leyéndose normalmente al enviar.
                key_rut_login = "rut_login_input"
                rut = st.text_input(
                    "RUT",
                    placeholder="Ej: 12.345.678-9",
                    key=key_rut_login,
                    on_change=formatear_rut_callback,
                    args=(key_rut_login,)
                )

                with st.form(key="form_login", clear_on_submit=False):
                    password = st.text_input("Contraseña", type="password", key="password_login_input")
                    submitted = st.form_submit_button("Ingresar", type="primary", use_container_width=True)

            inyectar_soporte_password_manager()

            if submitted:
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
                                inyectar_soporte_password_manager(
                                    exito_login=True,
                                    rut=rut.strip(),
                                    password=password,
                                    nombre=usuario.nombre
                                )
                                st.success("✅ Acceso concedido")
                                time.sleep(1.0)
                                st.rerun()
                        else:
                            st.error("❌ RUT o contraseña incorrectos.")
                    except Exception as e:
                        st.error(f"Error de base de datos: {e}")
                    finally:
                        session.close()

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔑 ¿Olvidaste tu contraseña? Recupérala aquí", use_container_width=True):
                st.session_state["vista_actual"] = "recuperar"
                st.rerun()

        elif st.session_state["vista_actual"] == "recuperar":
            st.markdown("<h4 style='text-align: center; color: gray;'>Recuperar Contraseña</h4>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            with st.container(border=True):
                st.info("💡 Introduce tus datos registrados para validar tu identidad y asignar una nueva clave.")

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
                                usuario = session.query(Usuario).filter(
                                    Usuario.rut == rut_recup.strip(),
                                    Usuario.email == email_recup.strip()
                                ).first()
                                if usuario:
                                    usuario.password_hash = generate_password_hash(nueva_password)
                                    session.commit()
                                    st.success("✅ ¡Contraseña actualizada con éxito!")
                                    time.sleep(1.5)
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
with col4:
    st.warning("📊 **Exportar Base de Datos**\n\nExporta los datos del sistema en formato PDF o Excel.")
    st.page_link("pages/exportar.py", label="Ir a Exportar", icon="📤")

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