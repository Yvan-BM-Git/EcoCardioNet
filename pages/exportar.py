# Archivo: pages/exportar.py
import streamlit as st

# ==================================================
# CONFIGURACIÓN DE PÁGINA (Debe ser la primera instrucción)
# ==================================================
st.set_page_config(page_title="Exportar Datos", page_icon="📊", layout="wide")

from menu import generar_menu

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

# ==================================================
# PERMISOS: SOLO ADMINISTRADOR E INVESTIGADOR
# ==================================================
rol_actual = st.session_state.get("usuario_actual", {}).get("rol", "")

if rol_actual not in ["Administrador", "Investigador"]:
    st.error("🚫 Acceso denegado.")
    st.stop()

import pandas as pd
import numpy as np
import io
from datetime import date, datetime

from database.database import SessionLocal
from database.models import Paciente, Estudio, Medicion, Variable

st.title("📥 Exportación de Base de Datos para Investigación")

st.markdown("""
Esta herramienta extrae toda la información clínica de la base de datos y genera una matriz estructurada. 
Cada fila representa un **estudio ecocardiográfico**. Las primeras columnas contienen los datos del paciente, seguidas de **todas las variables** (las celdas sin datos quedarán como `NaN`).
""")

session = SessionLocal()

try:
    with st.spinner("Extrayendo y procesando datos desde la base de datos..."):
        
        # ==========================================
        # PASO 1: RESCATAR DATOS ESTÁTICOS (Estudios + Pacientes)
        # ==========================================
        estudios_db = session.query(Estudio, Paciente).join(Paciente, Estudio.paciente_rut == Paciente.rut).all()
        
        datos_base = []
        for est, pac in estudios_db:
            # Calcular edad de forma segura
            edad = np.nan
            if pac.fecha_nacimiento and est.fecha_estudio:
                try:
                    f_nac = pac.fecha_nacimiento.date() if isinstance(pac.fecha_nacimiento, datetime) else pac.fecha_nacimiento
                    f_est = est.fecha_estudio.date() if isinstance(est.fecha_estudio, datetime) else est.fecha_estudio
                    edad = (f_est - f_nac).days // 365
                except Exception:
                    pass
            
            # Formatear fechas a texto seguro
            f_nac_str = pac.fecha_nacimiento.strftime('%d/%m/%Y') if pac.fecha_nacimiento else ""
            f_est_str = est.fecha_estudio.strftime('%d/%m/%Y') if est.fecha_estudio else ""

            datos_base.append({
                'estudio_id': est.id,
                'rut': pac.rut,
                'fecha_estudio': f_est_str,
                'nombres': pac.nombres,
                'apellido_paterno': pac.apellido_paterno,
                'apellido_materno': pac.apellido_materno,
                # 'apellidos': f"{pac.apellido_paterno} {pac.apellido_materno or ''}".strip(),
                # 'fecha_nacimiento': f_nac_str,
                'edad_calculada': edad,
                'prevision': getattr(pac, 'prevision', None),
                'sexo': pac.sexo,
                # 'fono_fijo': getattr(pac, 'fono_fijo', None),
                # 'celular': pac.telefono,
                # 'email': pac.email,
                'medico_responsable': est.medico,
                'tipo_estudio': est.tipo_estudio,
                # 'ficha_clinica': getattr(est, 'ficha_clinica', None),
                'patologia_de_base': getattr(est, 'diagnostico', None),
                'servicio_origen': getattr(est, 'procedencia', None),
                'servicio_destino': getattr(est, 'destino', None),
                'peso_kg': getattr(est, 'peso', None),
                'talla_cm': getattr(est, 'talla', None),
                'asc': getattr(est, 'asc_valor', None),
                'imc': getattr(est, 'imc_valor', None),  
                'pas': getattr(est, 'pas', None),
                'pad': getattr(est, 'pad', None),
                'ritmo': getattr(est, 'ritmo', None),
                'fcia': getattr(est, 'fcia', None),
                # 'eco_3d': getattr(est, 'eco_3d', None),
                # 'eco_estres': getattr(est, 'eco_estres', None)
            })
            
        df_base = pd.DataFrame(datos_base)

        if df_base.empty:
            st.warning("No hay estudios registrados en la base de datos.")
        else:
            # ==========================================
            # PASO 2: RESCATAR MEDICIONES Y PIVOTAR POR CÓDIGO (ÚNICO)
            # ==========================================
            # IMPORTANTE: pivotamos por 'codigo_variable' (siempre único), NO por el nombre
            # visible de la variable. Dos variables clínicamente distintas pueden compartir
            # el mismo nombre (ej. "Onda E" en Válvula Mitral y en Válvula Tricúspide);
            # pivotar por nombre las mezclaría en una sola columna y perdería datos.
            mediciones_db = session.query(
                Medicion.estudio_id, Medicion.codigo_variable, Medicion.valor_num, Medicion.valor_texto
            ).all()

            if mediciones_db:
                df_med = pd.DataFrame(mediciones_db)
                df_med['valor_final'] = df_med['valor_num'].astype(object).fillna(df_med['valor_texto'])

                df_ancha_mediciones = df_med.pivot_table(
                    index='estudio_id',
                    columns='codigo_variable',
                    values='valor_final',
                    aggfunc='first'
                ).reset_index()
            else:
                df_ancha_mediciones = pd.DataFrame(columns=['estudio_id'])

            # ==========================================
            # PASO 3: UNIR BASE ESTÁTICA + VARIABLES (aún indexado por código)
            # ==========================================
            df_final = pd.merge(df_base, df_ancha_mediciones, on='estudio_id', how='left')

            # ==========================================
            # PASO 4: INYECTAR TODAS LAS COLUMNAS RESTANTES Y CONSTRUIR NOMBRES LEGIBLES
            # ==========================================
            todas_las_variables_db = session.query(Variable.codigo, Variable.nombre, Variable.categoria).all()

            # Contamos cuántas veces se repite cada nombre visible (limpiando espacios)
            conteo_nombres = {}
            for cod, nom, cat in todas_las_variables_db:
                nom_limpio = (nom or cod).strip()
                conteo_nombres[nom_limpio] = conteo_nombres.get(nom_limpio, 0) + 1

            # Mapeo codigo -> nombre a mostrar en la columna final.
            # Si el nombre está repetido, lo desambiguamos agregando la categoría.
            mapeo_codigo_a_nombre = {}
            for cod, nom, cat in todas_las_variables_db:
                nom_limpio = (nom or cod).strip()
                if conteo_nombres[nom_limpio] > 1:
                    cat_limpia = (cat or "").strip()
                    mapeo_codigo_a_nombre[cod] = f"{nom_limpio} ({cat_limpia})" if cat_limpia else f"{nom_limpio} [{cod}]"
                else:
                    mapeo_codigo_a_nombre[cod] = nom_limpio

            codigos_ordenados = sorted(mapeo_codigo_a_nombre.keys(), key=lambda c: mapeo_codigo_a_nombre[c])

            for cod in codigos_ordenados:
                if cod not in df_final.columns:
                    df_final[cod] = np.nan

            # Ordenar columnas (todavía por código)
            columnas_estaticas = list(df_base.columns)
            columnas_codigos_presentes = [c for c in codigos_ordenados if c in df_final.columns]
            df_final = df_final[columnas_estaticas + columnas_codigos_presentes]

            # Renombramos las columnas de variables a su nombre legible (ya desambiguado)
            df_final = df_final.rename(columns=mapeo_codigo_a_nombre)

            st.success(f"✅ Se han procesado exitosamente **{len(df_final)} filas**.")

            # Vista previa
            with st.expander("👁️ Ver vista previa de la matriz de datos", expanded=True):
                st.dataframe(df_final.head(50), use_container_width=True)

            st.divider()
            col1, col2 = st.columns(2)

            # DESCARGAS
            csv_data = df_final.to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig')
            with col1:
                st.download_button("📄 Descargar Dataset CSV", csv_data, f"Dataset_EcoCardioNet_{date.today().strftime('%Y%m%d')}.csv", "text/csv", use_container_width=True)

            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False, sheet_name='Base_Investigacion')
            with col2:
                st.download_button("📊 Descargar Dataset Excel", buffer.getvalue(), f"Dataset_EcoCardioNet_{date.today().strftime('%Y%m%d')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

            # ==========================================
            # PASO 5: ELIMINAR ESTUDIOS (SOLO ADMINISTRADOR)
            # ==========================================
            # Ajusta este valor si el nombre del rol de administrador en tu tabla Rol es distinto
            NOMBRE_ROL_ADMIN = "Administrador"

            rol_actual = st.session_state.get("usuario_actual", {}).get("rol", "")
            es_admin = rol_actual.strip().lower() == NOMBRE_ROL_ADMIN.lower()

            if es_admin:
                st.divider()
                st.subheader("🗑️ Eliminar Estudios (solo Administrador)")
                st.caption(
                    "Marca las filas que deseas eliminar. Esta acción borra el estudio y "
                    "**todas sus mediciones asociadas** de forma permanente, tanto de la base "
                    "de datos como de esta tabla de exportación."
                )

                columnas_id = ["estudio_id", "fecha_estudio", "rut", 'nombres', 'apellido_paterno', 'apellido_materno', "medico_responsable"]
                columnas_id_presentes = [c for c in columnas_id if c in df_final.columns]

                df_seleccion = df_final[columnas_id_presentes].copy()
                df_seleccion.insert(0, "Eliminar", False)

                df_editado = st.data_editor(
                    df_seleccion,
                    hide_index=True,
                    use_container_width=True,
                    disabled=columnas_id_presentes,
                    key="editor_eliminar_estudios"
                )

                filas_marcadas = df_editado[df_editado["Eliminar"] == True]

                if not filas_marcadas.empty:
                    st.warning(f"⚠️ Has seleccionado **{len(filas_marcadas)}** estudio(s) para eliminar.")
                    confirmar_borrado = st.checkbox(
                        "Entiendo que esta acción es irreversible y eliminará también todas las mediciones asociadas.",
                        key="confirmar_borrado_estudios"
                    )

                    if confirmar_borrado:
                        if st.button("🗑️ Eliminar definitivamente", type="primary"):
                            ids_a_borrar = filas_marcadas["estudio_id"].tolist()
                            session_del = SessionLocal()
                            try:
                                # Primero las mediciones (dependen del estudio), luego el estudio
                                session_del.query(Medicion).filter(
                                    Medicion.estudio_id.in_(ids_a_borrar)
                                ).delete(synchronize_session=False)
                                session_del.query(Estudio).filter(
                                    Estudio.id.in_(ids_a_borrar)
                                ).delete(synchronize_session=False)
                                session_del.commit()
                                st.success(f"✅ Se eliminaron {len(ids_a_borrar)} estudio(s) correctamente.")
                                st.rerun()
                            except Exception as e:
                                session_del.rollback()
                                st.error(f"❌ Error al eliminar: {e}")
                            finally:
                                session_del.close()

            # ==========================================
            # PASO 6: ELIMINAR PACIENTES (SOLO ADMINISTRADOR)
            # ==========================================
            if es_admin:
                st.divider()
                st.subheader("🗑️ Eliminar Pacientes (solo Administrador)")

                st.caption(
                    "Eliminar un paciente borrará permanentemente todos sus estudios "
                    "y todas las mediciones asociadas."
                )

                pacientes_db=session.query(Paciente).all()

                datos_pacientes=[]

                for pac in pacientes_db:

                    n_estudios=session.query(Estudio).filter(
                        Estudio.paciente_rut==pac.rut
                    ).count()

                    datos_pacientes.append({

                        "Eliminar":False,
                        "RUT":pac.rut,
                        "Nombres":pac.nombres,
                        "Apellido paterno":pac.apellido_paterno,
                        "Apellido materno":pac.apellido_materno,
                        "Sexo":pac.sexo,
                        "N° Estudios":n_estudios

                    })

                df_pacientes=pd.DataFrame(datos_pacientes)

                df_pacientes_editado=st.data_editor(

                    df_pacientes,

                    hide_index=True,

                    use_container_width=True,

                    disabled=[
                        "RUT",
                        "Nombres",
                        "Apellido paterno",
                        "Apellido materno",
                        "Sexo",
                        "N° Estudios"
                    ],

                    key="editor_eliminar_pacientes"

                )

                pacientes_eliminar=df_pacientes_editado[
                    df_pacientes_editado["Eliminar"]
                ]

                if not pacientes_eliminar.empty:

                    st.error(
                        f"Se eliminarán {len(pacientes_eliminar)} paciente(s) "
                        "con todos sus estudios."
                    )

                    confirmar=st.checkbox(
                        "Confirmo la eliminación permanente de los pacientes seleccionados.",
                        key="confirmar_borrado_pacientes"
                    )

                    if confirmar:

                        if st.button(
                            "🗑 Eliminar pacientes definitivamente",
                            type="primary"
                        ):

                            session_del=SessionLocal()

                            try:

                                ruts=pacientes_eliminar["RUT"].tolist()

                                estudios=session_del.query(Estudio.id).filter(
                                    Estudio.paciente_rut.in_(ruts)
                                ).all()

                                ids_estudios=[x[0] for x in estudios]

                                if ids_estudios:

                                    session_del.query(Medicion).filter(
                                        Medicion.estudio_id.in_(ids_estudios)
                                    ).delete(
                                        synchronize_session=False
                                    )

                                    session_del.query(Estudio).filter(
                                        Estudio.id.in_(ids_estudios)
                                    ).delete(
                                        synchronize_session=False
                                    )

                                session_del.query(Paciente).filter(
                                    Paciente.rut.in_(ruts)
                                ).delete(
                                    synchronize_session=False
                                )

                                session_del.commit()

                                st.success(
                                    f"Se eliminaron {len(ruts)} paciente(s)."
                                )

                                st.rerun()

                            except Exception as e:

                                session_del.rollback()

                                st.error(e)

                            finally:

                                session_del.close()                                

except Exception as e:
    st.error(f"Error procesando la exportación: {e}")
finally:
    session.close()