# Archivo: menu.py
import streamlit as st

def generar_menu():
    # 1. Si el usuario NO ha iniciado sesión, no mostramos el menú en absoluto.
    # Así forzamos a que solo vean la pantalla de login principal.
    if not st.session_state.get("autenticado", False):
        return

    # 2. Si ya inició sesión, construimos el menú profesional
    with st.sidebar:
        # Información del usuario
        st.markdown(f"👤 **{st.session_state['usuario_actual']['nombre']}**")
        st.markdown(f"🏷️ *{st.session_state['usuario_actual']['rol']}*")

        # Botón para cerrar sesión corregido
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state["autenticado"] = False
            st.session_state["usuario_actual"] = None
            st.session_state["vista_actual"] = "login" # Asegura que regrese a la vista de ingreso
            
            # Navegar explícitamente a la raíz del proyecto donde se gestiona el Login
            st.switch_page("app.py")     
        
        st.divider()            

        # Navegación Principal
        st.markdown("### 📌 Navegación")
        
        # OJO: Cambiamos el login por un acceso a la página principal (Dashboard)
        st.page_link("app.py", label="Inicio", icon="🏠")
        
        # Pestañas visibles para TODOS los usuarios logueados
        st.page_link("pages/pacientes.py", label="Pacientes", icon="🧑‍⚕️")
        st.page_link("pages/estudios.py", label="Estudios", icon="🩺")
        st.page_link("pages/historial.py", label="Historial", icon="📁")
        st.page_link("pages/exportar.py", label="Exportar Datos", icon="📊")

        # Pestañas exclusivas para el Administrador
        if st.session_state["usuario_actual"]["rol"] == "Administrador":
            st.divider()
            st.markdown("### ⚙️ Administración")
            st.page_link("pages/usuarios.py", label="Gestión de Usuarios", icon="👥")

        st.divider()