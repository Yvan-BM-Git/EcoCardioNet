import streamlit as st

st.title("Login")

rut = st.text_input("RUT")

password = st.text_input(
    "Contraseña",
    type="password"
)

if st.button("Ingresar"):

    st.success(
        f"Bienvenido {rut}"
    )