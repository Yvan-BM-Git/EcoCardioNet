# Archivo: menu.py

import streamlit as st


def generar_menu():
    # Si el usuario no ha iniciado sesión, no mostrar el menú
    if not st.session_state.get("autenticado", False):
        return

    usuario = st.session_state["usuario_actual"]
    rol = usuario["rol"]

    with st.sidebar:

        # Información del usuario
        st.markdown(f"👤 **{usuario['nombre']}**")
        st.markdown(f"🏷️ *{rol}*")

        # Cerrar sesión
        if st.button("🚪 Cerrar Sesión", width="stretch"):
            st.session_state["autenticado"] = False
            st.session_state["usuario_actual"] = None

            # Regresar al login
            st.switch_page("app.py")

        st.divider()

        # ==========================
        # Navegación
        # ==========================
        st.markdown("### 📌 Navegación")

        # Visible para todos los usuarios autenticados
        st.page_link("app.py", label="Inicio", icon="🏠")
        st.page_link("pages/estudios.py", label="Estudios", icon="🩺")
        st.page_link("pages/historial.py", label="Historial", icon="📁")

        # Visible para Administrador e Investigador
        if rol in ["Administrador", "Investigador"]:
            st.page_link("pages/exportar.py", label="Exportar Datos", icon="📊")

        # Menú exclusivo del Administrador
        if rol == "Administrador":
            st.divider()
            st.markdown("### ⚙️ Administración")

            st.page_link("pages/usuarios.py", label="Gestión de Usuarios", icon="👥")

        st.divider()
        st.page_link("pages/legal.py", label="Términos y Privacidad", icon="📄")
