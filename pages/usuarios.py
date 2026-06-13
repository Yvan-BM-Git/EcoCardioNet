import streamlit as st

st.title("Usuarios")

with st.form("nuevo_usuario"):

    rut = st.text_input("RUT")

    nombre = st.text_input("Nombre")

    email = st.text_input("Email")

    password = st.text_input(
        "Contraseña",
        type="password"
    )

    rol = st.selectbox(
        "Rol",
        [
            "Administrador",
            "Cardiólogo",
            "Investigador"
        ]
    )

    guardar = st.form_submit_button(
        "Guardar"
    )

if guardar:

    st.success(
        "Usuario creado"
    )