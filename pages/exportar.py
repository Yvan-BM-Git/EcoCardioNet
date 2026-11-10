# Archivo: pages/exportar.py
import streamlit as st

st.set_page_config(page_title="Exportar Datos", page_icon="📊", layout="wide")

from menu import generar_menu

generar_menu()

if not st.session_state.get("autenticado", False):
    st.warning("🛑 Debes iniciar sesión para ver esta página.")
    if st.button("🔑 Ir a Iniciar Sesión"):
        st.switch_page("app.py")
    st.stop()

rol_actual = st.session_state.get("usuario_actual", {}).get("rol", "")
if rol_actual not in ["Administrador", "Investigador"]:
    st.error("🚫 Acceso denegado.")
    st.stop()
es_admin = rol_actual == "Administrador"

import io
from datetime import date

import pandas as pd
from sqlalchemy import func

from database.database import SessionLocal, asegurar_bd
from database.models import Estudio, Medicion, Paciente
from utils.indicadores import limpiar_cache as limpiar_indicadores

asegurar_bd()

from utils.exportacion import anonimizar, construir_dataset


def _descargas(df: pd.DataFrame, sufijo: str) -> None:
    hoy = date.today().strftime("%Y%m%d")
    c1, c2 = st.columns(2)
    c1.download_button("📄 Descargar CSV", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       f"EcoCardioNet_{sufijo}_{hoy}.csv", "text/csv", width="stretch")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Base")
    c2.download_button("📊 Descargar Excel", buffer.getvalue(), f"EcoCardioNet_{sufijo}_{hoy}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")


st.title("📥 Exportación de Base de Datos para Investigación")
st.markdown(
    "Cada fila es un **estudio ecocardiográfico**: primero los datos del paciente y del examen, "
    "luego **todas las variables** (celdas vacías si no se midieron)."
)

session = SessionLocal()
try:
    with st.spinner("Extrayendo datos..."):
        df_ident = construir_dataset(session)

    if df_ident.empty:
        st.warning("No hay estudios registrados en la base de datos.")
        st.stop()

    df_anon = anonimizar(df_ident)
    st.info(
        "🔒 **Exportación anonimizada (Ley N° 21.719).** Se quitan RUT, nombres y fechas exactas. "
        "Cada paciente aparece como un código (P0001…) que permite seguir sus estudios, con el año y "
        "los días transcurridos desde su primer examen. Los médicos aparecen como M01, M02…"
    )
    st.success(f"✅ {len(df_anon)} estudios de {df_anon['id_paciente'].nunique()} pacientes.")
    with st.expander("👁️ Vista previa", expanded=True):
        st.dataframe(df_anon.head(50), width="stretch")
    _descargas(df_anon, "anonimizada")

    # ---------------- Solo Administrador ----------------
    if es_admin:
        st.divider()
        with st.expander("🪪 Exportación identificada (solo uso clínico interno)"):
            st.warning(
                "Incluye RUT, nombres y fechas. Úsala solo para fines asistenciales o de gestión del "
                "Responsable; para investigación usa la versión anonimizada."
            )
            if st.checkbox("Entiendo que estos datos son sensibles y que debo resguardarlos.",
                           key="ok_export_identificada"):
                _descargas(df_ident, "identificada")

        st.divider()
        st.subheader("🗑️ Eliminar Estudios (solo Administrador)")
        st.caption("Borra el estudio y todas sus mediciones de forma permanente.")
        cols_id = ["estudio_id", "fecha_estudio", "rut", "nombres", "apellido_paterno",
                   "apellido_materno", "medico_responsable"]
        df_sel = df_ident[cols_id].copy()
        df_sel.insert(0, "Eliminar", False)
        editado = st.data_editor(df_sel, hide_index=True, width="stretch", disabled=cols_id,
                                 key="editor_eliminar_estudios")
        marcadas = editado[editado["Eliminar"]]
        if not marcadas.empty:
            st.warning(f"⚠️ Has seleccionado **{len(marcadas)}** estudio(s) para eliminar.")
            if st.checkbox("Entiendo que esta acción es irreversible y eliminará también todas las mediciones asociadas.",
                           key="confirmar_borrado_estudios") and \
                    st.button("🗑️ Eliminar definitivamente", type="primary"):
                ids = marcadas["estudio_id"].tolist()
                try:
                    session.query(Medicion).filter(Medicion.estudio_id.in_(ids)).delete(synchronize_session=False)
                    session.query(Estudio).filter(Estudio.id.in_(ids)).delete(synchronize_session=False)
                    session.commit()
                    limpiar_indicadores()
                    st.success(f"✅ Se eliminaron {len(ids)} estudio(s).")
                    st.rerun()
                except Exception as e:
                    session.rollback()
                    st.error(f"❌ Error al eliminar: {e}")

        st.divider()
        st.subheader("🗑️ Eliminar Pacientes (solo Administrador)")
        st.caption("Eliminar un paciente borra permanentemente todos sus estudios y mediciones.")
        n_por_rut = dict(session.query(Estudio.paciente_rut, func.count(Estudio.id))
                         .group_by(Estudio.paciente_rut).all())
        df_pac = pd.DataFrame([{
            "Eliminar": False, "RUT": p.rut, "Nombres": p.nombres, "Apellido paterno": p.apellido_paterno,
            "Apellido materno": p.apellido_materno, "Sexo": p.sexo, "N° Estudios": n_por_rut.get(p.rut, 0),
        } for p in session.query(Paciente).order_by(Paciente.apellido_paterno).all()])
        editado_p = st.data_editor(df_pac, hide_index=True, width="stretch",
                                   disabled=[c for c in df_pac.columns if c != "Eliminar"],
                                   key="editor_eliminar_pacientes")
        a_borrar = editado_p[editado_p["Eliminar"]]
        if not a_borrar.empty:
            st.error(f"Se eliminarán {len(a_borrar)} paciente(s) con todos sus estudios.")
            if st.checkbox("Confirmo la eliminación permanente de los pacientes seleccionados.",
                           key="confirmar_borrado_pacientes") and \
                    st.button("🗑 Eliminar pacientes definitivamente", type="primary"):
                ruts = a_borrar["RUT"].tolist()
                try:
                    ids = [i for (i,) in session.query(Estudio.id).filter(Estudio.paciente_rut.in_(ruts))]
                    if ids:
                        session.query(Medicion).filter(Medicion.estudio_id.in_(ids)).delete(synchronize_session=False)
                        session.query(Estudio).filter(Estudio.id.in_(ids)).delete(synchronize_session=False)
                    session.query(Paciente).filter(Paciente.rut.in_(ruts)).delete(synchronize_session=False)
                    session.commit()
                    limpiar_indicadores()
                    st.success(f"Se eliminaron {len(ruts)} paciente(s).")
                    st.rerun()
                except Exception as e:
                    session.rollback()
                    st.error(f"❌ Error al eliminar: {e}")
except Exception as e:
    st.error(f"Error procesando la exportación: {e}")
finally:
    session.close()
