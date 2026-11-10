# Archivo: pages/legal.py
"""Términos de Servicio y Política de Privacidad. Página pública (no exige sesión)."""
import streamlit as st

st.set_page_config(page_title="Términos y Privacidad · EcoCardioNet", page_icon="📄", layout="centered")

from menu import generar_menu
from utils import legal

generar_menu()

if not st.session_state.get("autenticado", False):
    st.page_link("app.py", label="Volver al inicio de sesión", icon="⬅️")

legal.mostrar_documentos()
