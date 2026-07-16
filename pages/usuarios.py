# Archivo: pages/usuarios.py
import streamlit as st
import pandas as pd
import time

# ==================================================
# CONFIGURACIÓN DE PÁGINA (Debe ser la primera instrucción)
# ==================================================
st.set_page_config(page_title="Gestión de Usuarios", page_icon="👥", layout="wide")

from menu import generar_menu
from werkzeug.security import generate_password_hash
from database.database import SessionLocal
from database.models import Usuario, Rol

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

# 3. 🔒 CANDADO ESPECÍFICO: Solo Administradores
if st.session_state.get("usuario_actual", {}).get("rol") != "Administrador":
    st.error("🚫 Acceso denegado. Solo los Administradores pueden gestionar usuarios.")
    st.stop()


# ==================================================
# CALLBACK DINÁMICO PARA AUTOCOMPLETAR RUT EN VIVO
# ==================================================
def formatear_rut_usuario_callback(key_destino):
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
# CÓDIGO DE LA PÁGINA
# ==========================================

st.title("👥 Gestión de Usuarios")

# tab1, tab2, tab3 = st.tabs(["➕ Registrar Nuevo Usuario", "📋 Usuarios Registrados", "🔑 Restablecer Contraseña"])

tab1, tab2, tab3, tab4 = st.tabs([
    "➕ Registrar Nuevo Usuario",
    "📋 Usuarios Registrados",
    "🔑 Restablecer Contraseña",
    "✏️ Modificar Usuario"
])

# --- PESTAÑA 1: CREAR USUARIO (SIN FORMULARIO) ---
with tab1:
    ROLES_SISTEMA = ["Administrador", "Cardiólogo", "Investigador"]
    
    st.markdown("### Crear Cuenta")
    
    # 🧹 RUTINA DE LIMPIEZA: Se ejecuta antes de dibujar los campos
    if st.session_state.get("limpiar_form_usuarios", False):
        for k in ["rut_usuario_nuevo", "nombre_nuevo", "email_nuevo", "password_nuevo"]:
            st.session_state[k] = ""
        st.session_state["limpiar_form_usuarios"] = False
    
    # Dibujamos los campos libres, asignando una 'key' a cada uno
    key_rut_nuevo = "rut_usuario_nuevo"
    rut_visible = st.text_input(
        "RUT", 
        placeholder="Ej: 123456789 o 12.345.678-9",
        key=key_rut_nuevo,
        on_change=formatear_rut_usuario_callback,
        args=(key_rut_nuevo,)
    )

    nombre = st.text_input("Nombre", key="nombre_nuevo")
    email = st.text_input("Email", key="email_nuevo")
    password = st.text_input("Contraseña", type="password", key="password_nuevo")
    rol_seleccionado = st.selectbox("Rol", ROLES_SISTEMA)

    guardar = st.button("Guardar Usuario", type="primary")

    if guardar:
        rut_limpio_db = rut_visible.strip()
        
        if not rut_limpio_db or not nombre or not password:
            st.error("❌ RUT, Nombre y Contraseña son obligatorios.")
        else:
            session = SessionLocal()
            try:
                existe = session.query(Usuario).filter(Usuario.rut == rut_limpio_db).first()
                if existe:
                    st.error(f"⚠️ El RUT {rut_limpio_db} ya tiene una cuenta registrada.")
                else:
                    rol_db = session.query(Rol).filter(Rol.nombre == rol_seleccionado).first()
                    if not rol_db:
                        rol_db = Rol(nombre=rol_seleccionado)
                        session.add(rol_db)
                        session.flush() 
                    
                    hash_pw = generate_password_hash(password)
                    nuevo_user = Usuario(
                        rut=rut_limpio_db,
                        nombre=nombre.strip(),
                        email=email.strip(),
                        password_hash=hash_pw,
                        rol_id=rol_db.id,
                        activo=True
                    )
                    session.add(nuevo_user)
                    session.commit()
                    st.success(f"✅ Usuario {nombre} ({rol_seleccionado}) creado correctamente.")
                    st.balloons()
                    
                    time.sleep(1)
                    # 🚩 Levantamos la bandera de limpieza y reiniciamos
                    st.session_state["limpiar_form_usuarios"] = True
                    st.rerun()
                    
            except Exception as e:
                session.rollback()
                st.error(f"❌ Error al guardar: {e}")
            finally:
                session.close()

# --- PESTAÑA 2: LISTAR Y ELIMINAR USUARIOS ---
with tab2:
    st.markdown("### Listado de Credenciales y Accesos")
    st.caption("💡 Para dar de baja a un usuario, selecciónalo en la lista desplegable inferior y presiona 'Eliminar Usuario'.")
    
    session = SessionLocal()
    try:
        usuarios_db = session.query(Usuario, Rol).join(Rol, Usuario.rol_id == Rol.id).all()
        
        if usuarios_db:
            lista_usuarios = []
            todos_los_ruts = []
            # 🔥 Obtener el RUT del usuario que ha iniciado sesión
            usuario_actual_rut = st.session_state.get("usuario_actual", {}).get("rut")
            
            for user, rol in usuarios_db:
                # Determinar si este usuario es el que está usando la app
                if usuario_actual_rut and user.rut == usuario_actual_rut:
                    estado_sesion = "🟢 Activo"
                else:
                    estado_sesion = "🔴 Inactivo"
                
                lista_usuarios.append({
                    "RUT": user.rut,
                    "Nombre Completo": user.nombre,
                    "Email": user.email if user.email else "No registrado",
                    "Rol asignado": rol.nombre,
                    "Estado de sesión": estado_sesion,
                    "Cuenta habilitada": "✅ Sí" if user.activo else "❌ No"
                })
                todos_los_ruts.append(user.rut)
            
            df_usuarios = pd.DataFrame(lista_usuarios)
            
            # Buscador interno
            busqueda = st.text_input("🔍 Buscar usuario en esta lista", placeholder="Escribe RUT o Nombre...")
            if busqueda:
                df_usuarios = df_usuarios[
                    df_usuarios["Nombre Completo"].str.contains(busqueda, case=False, na=False) |
                    df_usuarios["RUT"].str.contains(busqueda, case=False, na=False)
                ]
            
            st.dataframe(df_usuarios, use_container_width=True, hide_index=True)
            st.caption(f"Total de cuentas en el sistema: {len(lista_usuarios)} usuarios.")
            
            st.divider()
            
            # --- SECCIÓN DE ELIMINACIÓN SEGURA ---
            st.markdown("### 🗑️ Zona de Eliminación")
            
            col_sel, col_btn = st.columns([2, 1])
            
            with col_sel:
                rut_a_eliminar = st.selectbox(
                    "Selecciona el RUT del usuario que deseas remover permanentemente:",
                    options=todos_los_ruts,
                    index=None,
                    placeholder="Elegir RUT del usuario..."
                )
                
            with col_btn:
                st.markdown("<div style='padding-top: 24px;'></div>", unsafe_allow_html=True)
                btn_eliminar = st.button("❌ Eliminar Usuario", type="primary", use_container_width=True)
                
            if btn_eliminar:
                if not rut_a_eliminar:
                    st.warning("⚠️ Por favor, selecciona un RUT de la lista antes de presionar eliminar.")
                elif rut_a_eliminar == st.session_state["usuario_actual"]["rut"]:
                    st.error("🚫 No puedes eliminar tu propia cuenta de Administrador mientras mantengas la sesión activa.")
                else:
                    usuario_a_borrar = session.query(Usuario).filter(Usuario.rut == rut_a_eliminar).first()
                    if usuario_a_borrar:
                        nombre_eliminado = usuario_a_borrar.nombre
                        session.delete(usuario_a_borrar)
                        session.commit()
                        st.success(f"✅ El usuario **{nombre_eliminado}** (RUT: {rut_a_eliminar}) fue removido con éxito del sistema.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ El usuario no pudo ser encontrado en la base de datos.")
            
        else:
            st.info("No hay usuarios registrados.")
            todos_los_ruts = []
            
    except Exception as e:
        st.error(f"❌ Error en la gestión de datos: {e}")
    finally:
        session.close()

# --- PESTAÑA 3: RESTABLECER CONTRASEÑA ---
with tab3:
    st.markdown("### 🔑 Cambiar Contraseña de un Usuario")
    st.markdown("Como las contraseñas se guardan encriptadas por seguridad, si olvidas una puedes sobreescribirla aquí directamente.")
    
    if not todos_los_ruts:
        st.info("No hay usuarios disponibles para modificar.")
    else:
        with st.form("cambiar_password_form"):
            rut_a_cambiar = st.selectbox("Selecciona el RUT del usuario", options=todos_los_ruts)
            nueva_password = st.text_input("Escribe la NUEVA Contraseña", type="password", placeholder="Mínimo 6 caracteres")
            confirmar_btn = st.form_submit_button("Actualizar Contraseña", type="primary")
            
        if confirmar_btn:
            if not nueva_password:
                st.error("❌ Debes ingresar una nueva contraseña.")
            else:
                session = SessionLocal()
                try:
                    usuario_db = session.query(Usuario).filter(Usuario.rut == rut_a_cambiar).first()
                    if usuario_db:
                        usuario_db.password_hash = generate_password_hash(nueva_password)
                        session.commit()
                        st.success(f"✅ La contraseña para el RUT {rut_a_cambiar} ha sido actualizada con éxito.")
                    else:
                        st.error("❌ Usuario no encontrado.")
                except Exception as e:
                    session.rollback()
                    st.error(f"❌ Error al actualizar la contraseña: {e}")
                finally:
                    session.close()

# ==================================================
# PESTAÑA 4: MODIFICAR USUARIO
# ==================================================
with tab4:

    st.markdown("### ✏️ Modificar Datos de un Usuario")

    if not todos_los_ruts:
        st.info("No existen usuarios registrados.")
    else:

        session = SessionLocal()

        try:
            usuarios_dict = {
                u.rut: u.nombre
                for u in session.query(Usuario).all()
            }            

            rut_modificar = st.selectbox(
                "Seleccione el usuario",
                options=todos_los_ruts,
                format_func=lambda rut: f"{usuarios_dict.get(rut, '')} ({rut})",
                key="usuario_modificar"
            )

            usuario = (
                session.query(Usuario)
                .filter(Usuario.rut == rut_modificar)
                .first()
            )

            roles = session.query(Rol).order_by(Rol.nombre).all()
            nombres_roles = [r.nombre for r in roles]

            indice = 0
            for i, r in enumerate(roles):
                if r.id == usuario.rol_id:
                    indice = i
                    break

            with st.form("form_modificar_usuario"):

                rut = st.text_input(
                    "RUT",
                    value=usuario.rut,
                    disabled=True
                )

                nombre = st.text_input(
                    "Nombre completo",
                    value=usuario.nombre
                )

                email = st.text_input(
                    "Email",
                    value=usuario.email or ""
                )

                rol = st.selectbox(
                    "Rol",
                    nombres_roles,
                    index=indice
                )

                activo = st.checkbox(
                    "Cuenta habilitada",
                    value=usuario.activo
                )

                guardar = st.form_submit_button(
                    "💾 Guardar Cambios",
                    type="primary"
                )

            if guardar:

                usuario.nombre = nombre.strip()
                usuario.email = email.strip()

                rol_db = (
                    session.query(Rol)
                    .filter(Rol.nombre == rol)
                    .first()
                )

                usuario.rol_id = rol_db.id
                usuario.activo = activo

                session.commit()

                st.success("✅ Usuario actualizado correctamente.")
                time.sleep(1)
                st.rerun()

        except Exception as e:
            session.rollback()
            st.error(f"❌ Error al actualizar el usuario: {e}")

        finally:
            session.close()                    