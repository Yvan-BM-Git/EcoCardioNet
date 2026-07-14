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

import pandas as pd
import numpy as np
import io
from datetime import date, datetime

from database.database import SessionLocal
from database.models import Paciente, Estudio, Medicion, Variable

# st.set_page_config(page_title="Exportar Datos", layout="wide")
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
                # 'nombres': pac.nombres,
                # 'apellidos': f"{pac.apellido_paterno} {pac.apellido_materno or ''}".strip(),
                'fecha_nacimiento': f_nac_str,
                'edad_calculada': edad,
                'prevision': getattr(pac, 'prevision', None),
                'sexo': pac.sexo,
                'fono_fijo': getattr(pac, 'fono_fijo', None),
                'celular': pac.telefono,
                'email': pac.email,
                'fecha_estudio': f_est_str,
                'medico_responsable': est.medico,
                'tipo_estudio': est.tipo_estudio,
                'ficha_clinica': getattr(est, 'ficha_clinica', None),
                'patologia_de_base': getattr(est, 'diagnostico', None),
                'servicio_origen': getattr(est, 'procedencia', None),
                'servicio_destino': getattr(est, 'destino', None),
                'peso_kg': getattr(est, 'peso', None),
                'talla_cm': getattr(est, 'talla', None),
                'asc': getattr(est, 'asc_valor', None),
                'pas': getattr(est, 'pas', None),
                'pad': getattr(est, 'pad', None),
                'ritmo': getattr(est, 'ritmo', None),
                'fcia': getattr(est, 'fcia', None),
                'eco_3d': getattr(est, 'eco_3d', None),
                'eco_estres': getattr(est, 'eco_estres', None)
            })
            
        df_base = pd.DataFrame(datos_base)

        if df_base.empty:
            st.warning("No hay estudios registrados en la base de datos.")
        else:
            # ==========================================
            # PASO 2: RESCATAR MEDICIONES Y PIVOTAR
            # ==========================================
            mediciones_db = session.query(
                Medicion.estudio_id, Variable.nombre.label('variable'), Medicion.valor_num, Medicion.valor_texto
            ).join(Variable, Medicion.codigo_variable == Variable.codigo).all()
            
            if mediciones_db:
                df_med = pd.DataFrame(mediciones_db)
                df_med['valor_final'] = df_med['valor_num'].astype(object).fillna(df_med['valor_texto'])
                
                # Al pivotar SOLO por estudio_id evitamos que Pandas elimine filas por datos demográficos vacíos
                df_ancha_mediciones = df_med.pivot_table(
                    index='estudio_id', 
                    columns='variable', 
                    values='valor_final', 
                    aggfunc='first'
                ).reset_index()
            else:
                df_ancha_mediciones = pd.DataFrame(columns=['estudio_id'])

            # ==========================================
            # PASO 3: UNIR BASE ESTÁTICA + VARIABLES
            # ==========================================
            df_final = pd.merge(df_base, df_ancha_mediciones, on='estudio_id', how='left')

            # ==========================================
            # PASO 4: INYECTAR TODAS LAS COLUMNAS RESTANTES
            # ==========================================
            todas_las_variables_db = session.query(Variable.nombre).all()
            nombres_todas_variables = sorted([v[0] for v in todas_las_variables_db if v[0]])

            for var in nombres_todas_variables:
                if var not in df_final.columns:
                    df_final[var] = np.nan

            # Ordenar columnas
            columnas_estaticas = list(df_base.columns)
            columnas_variables_presentes = [c for c in nombres_todas_variables if c in df_final.columns]
            df_final = df_final[columnas_estaticas + columnas_variables_presentes]

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

except Exception as e:
    st.error(f"Error procesando la exportación: {e}")
finally:
    session.close()