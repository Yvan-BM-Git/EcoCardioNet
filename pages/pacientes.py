# Archivo: pages/pacientes.py
import streamlit as st
import pandas as pd
from datetime import date

from database.database import SessionLocal
from database.models import Paciente

# Configuración del título
st.title("👤 Gestión de Pacientes")

# ==================================================
# ESTILOS CSS COMPACTOS
# ==================================================
st.markdown("""
<style>
section[data-testid="stMain"] > div:first-child {
    max-width: 1100px;
    margin: 0 auto;
}
div[data-testid="stVerticalBlock"] { gap: 0.1rem !important; }
div[data-testid="stMarkdownContainer"] p { margin-bottom: 0px !important; }
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] > div {
    max-width: 100% !important;
    min-height: 36px !important;
    padding-top: 4px !important;
    padding-bottom: 4px !important;
}
</style>
""", unsafe_allow_html=True)


# ==================================================
# CALLBACKS DINÁMICOS DE FORMATEO Y HELPERS
# ==================================================
def formatear_busqueda_callback():
    busqueda_actual = st.session_state.get("busqueda_input_pacientes", "")
    if not busqueda_actual: return
    limpio = busqueda_actual.replace(".", "").replace("-", "").strip().upper()
    if 7 <= len(limpio) <= 9:
        cuerpo = limpio[:-1]
        dv = limpio[-1]
        if cuerpo.isdigit() and (dv.isdigit() or dv == "K"):
            cuerpo_formateado = f"{int(cuerpo):,}".replace(",", ".")
            st.session_state.busqueda_input_pacientes = f"{cuerpo_formateado}-{dv}"

def formatear_rut_dinamico(k):
    rut_actual = st.session_state.get(k, "")
    if not rut_actual:
        return

    # Mantener solo números y K
    rut_limpio = "".join(c for c in rut_actual.upper() if c.isdigit() or c == "K")

    # Máximo 9 caracteres: 8 del cuerpo + DV
    rut_limpio = rut_limpio[:9]

    if len(rut_limpio) < 2:
        st.session_state[k] = rut_limpio
        return

    cuerpo = rut_limpio[:-1]
    dv = rut_limpio[-1]

    if cuerpo.isdigit():
        cuerpo_formateado = f"{int(cuerpo):,}".replace(",", ".")
        st.session_state[k] = f"{cuerpo_formateado}-{dv}"

def formatear_telefono_dinamico(k):
    telf_actual = st.session_state.get(k, "")

    if not telf_actual:
        return

    # Mantener solo números
    numeros = "".join(c for c in str(telf_actual) if c.isdigit())

    # Restringir estrictamente a un máximo de 9 dígitos
    numeros = numeros[:9]

    # Formateo progresivo en bloques de 3 (sin prefijo)
    if len(numeros) <= 3:
        st.session_state[k] = numeros
    elif len(numeros) <= 6:
        st.session_state[k] = f"{numeros[:3]} {numeros[3:]}"
    else:
        st.session_state[k] = f"{numeros[:3]} {numeros[3:6]} {numeros[6:]}"

def separar_prefijo_numero(tel_str):
    """Separa el prefijo del número base para rellenar los inputs al editar"""
    if not tel_str: 
        return "+56", ""
    tel_str = tel_str.strip()
    if tel_str.startswith("+") and " " in tel_str:
        partes = tel_str.split(" ", 1)
        return partes[0], partes[1]
    elif tel_str.startswith("+56"): # Porc si hay registros antiguos sin espacio
        return "+56", tel_str[3:].strip()
    return "+56", tel_str

# ==================================================
# SELECCIÓN Y BÚSQUEDA DE PACIENTE
# ==================================================
st.subheader("Selección de Paciente")

opcion_paciente = st.radio("", ["Ingresar nuevo paciente", "Buscar paciente existente"], horizontal=True, label_visibility="collapsed")

paciente_existente = None

if opcion_paciente == "Buscar paciente existente":
    _session = SessionLocal()
    try:
        pacientes_db = _session.query(Paciente).order_by(Paciente.apellido_paterno, Paciente.nombres).all()
        if pacientes_db:
            df_pacientes_todos = pd.DataFrame([
                {
                    "RUT": p.rut,
                    "Nombre completo": f"{p.apellido_paterno} {p.apellido_materno or ''} {p.nombres}".strip(),
                }
                for p in pacientes_db
            ])
        else:
            df_pacientes_todos = pd.DataFrame(columns=["RUT", "Nombre completo"])  # DataFrame vacío con columnas
    finally:
        _session.close()

    col_search, col_seleccion = st.columns([1, 1])

    with col_search:
        busqueda = st.text_input(
            "🔎 Buscar paciente en la base de datos", 
            value="", placeholder="Ej: Nombre, Apellido o RUT",
            key="busqueda_input_pacientes",
            on_change=formatear_busqueda_callback
        )

    with col_seleccion:
        if df_pacientes_todos.empty:
            st.info("No hay pacientes registrados en la base de datos.")
            rut_seleccionado = None
        else:
            opciones_todos = df_pacientes_todos["RUT"].tolist()
            rut_seleccionado = st.selectbox(
                "✅ Seleccionar un paciente existente",
                options=opciones_todos,
                index=None,
                placeholder="Seleccionar 👇",
                format_func=lambda r: f"{df_pacientes_todos[df_pacientes_todos['RUT'] == r]['Nombre completo'].iloc[0]} ({r})",
                key="selectbox_todos_pacientes",
            )

    # Selector adicional que aparece SOLO si hay búsqueda y hay datos
    if busqueda and not df_pacientes_todos.empty:
        mask = (
            df_pacientes_todos["Nombre completo"].str.contains(busqueda, case=False, na=False) |
            df_pacientes_todos["RUT"].str.contains(busqueda, case=False, na=False)
        )
        df_filtrado = df_pacientes_todos[mask]

        if not df_filtrado.empty:
            st.markdown("---")
            rut_filtrado = st.selectbox(
                "🔍 Seleccione el paciente de la búsqueda",
                options=df_filtrado["RUT"].tolist(),
                index=None,
                placeholder="Resultados de búsqueda 👇",
                format_func=lambda r: f"{df_filtrado[df_filtrado['RUT'] == r]['Nombre completo'].iloc[0]} ({r})",
                key="selectbox_busqueda_pacientes",
            )
            if rut_filtrado:
                rut_seleccionado = rut_filtrado
        else:
            st.warning("No se encontraron pacientes que coincidan con la búsqueda.")

    # Carga segura del paciente seleccionado
    if rut_seleccionado:
        _session = SessionLocal()
        try:
            paciente_existente = _session.query(Paciente).filter(Paciente.rut == rut_seleccionado).first()
            st.success(f"✏️ Modo edición: Modificando a **{paciente_existente.nombres} {paciente_existente.apellido_paterno} {paciente_existente.apellido_materno or ''}**")
        finally:
            _session.close()
    else:
        if not busqueda and not df_pacientes_todos.empty:
            st.info("🔍 Escribe en el campo de búsqueda para encontrar un paciente, o selecciona uno de la lista.")
        elif df_pacientes_todos.empty:
            st.info("No hay pacientes registrados. Use la opción 'Ingresar nuevo paciente'.")

# ==================================================
# VARIABLES PRE-CARGADAS DEL FORMULARIO
# ==================================================
v_rut = paciente_existente.rut if paciente_existente else ""
v_nom = paciente_existente.nombres if paciente_existente else ""
v_ap = paciente_existente.apellido_paterno if paciente_existente else ""
v_am = paciente_existente.apellido_materno if paciente_existente and paciente_existente.apellido_materno else ""
v_fn = paciente_existente.fecha_nacimiento if paciente_existente and paciente_existente.fecha_nacimiento else date(2000, 1, 1)

opts_prev = ["", "Fonasa", "Isapre", "Otra"]
v_prev = getattr(paciente_existente, 'prevision', "") if paciente_existente else ""
idx_prev = opts_prev.index(v_prev) if v_prev in opts_prev else 0

opts_sexo = ["", "Masculino", "Femenino"]
v_sexo = paciente_existente.sexo if paciente_existente and paciente_existente.sexo else ""
idx_sexo = opts_sexo.index(v_sexo) if v_sexo in opts_sexo else 0

# Separación de prefijos para los teléfonos
v_fono_completo = getattr(paciente_existente, 'fono_fijo', "") if paciente_existente else ""
v_cel_completo = paciente_existente.telefono if paciente_existente and paciente_existente.telefono else ""

pref_fono_ext, base_fono_ext = separar_prefijo_numero(v_fono_completo)
pref_cel_ext, base_cel_ext = separar_prefijo_numero(v_cel_completo)

v_email = paciente_existente.email if paciente_existente and paciente_existente.email else ""

prefijo_key = paciente_existente.rut if paciente_existente else "nuevo"
key_rut = f"rut_input_{prefijo_key}"
key_fono_base = f"fono_base_input_{prefijo_key}"      
key_celular_base = f"cel_base_input_{prefijo_key}"

# Diccionario de prefijos
dic_prefijos = {
    "+56": "🇨🇱 +56",
    "+54": "🇦🇷 +54",
    "+51": "🇵🇪 +51",
    "+57": "🇨🇴 +57",
    "+52": "🇲🇽 +52",
    "+58": "🇻🇪 +58",
    "+593": "🇪🇨 +593",
    "+591": "🇧🇴 +591",
    "+595": "🇵🇾 +595",
    "+598": "🇺🇾 +598",
    "+55": "🇧🇷 +55",
    "+1":  "🇺🇸/🇨🇦 +1",
    "+34": "🇪🇸 +34",
    "OTRO": "🌍 Otro..."
}
lista_prefijos = list(dic_prefijos.keys())


# ==================================================
# FORMULARIO DE PACIENTE
# ==================================================
if opcion_paciente == "Ingresar nuevo paciente" or paciente_existente:
    st.divider()
    st.markdown("#### 👤 Registrar Nuevo Paciente" if not paciente_existente else "#### 👤 Editar Paciente")
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1: 
        rut = st.text_input(
            "RUT del paciente",
            value=v_rut,
            placeholder="Ej: 12.345.678-9",
            max_chars=12,
            key=key_rut,
            on_change=formatear_rut_dinamico,
            args=(key_rut,)
        )        
    with col2: nombres = st.text_input("Nombres", value=v_nom)
    with col3: apellido_paterno = st.text_input("Apellido paterno", value=v_ap)
    with col4: apellido_materno = st.text_input("Apellido materno", value=v_am)

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        fecha_nacimiento = st.date_input("Fecha nacimiento", value=v_fn, min_value=date(1900, 1, 1), max_value=date.today(), format="DD/MM/YYYY")
    with col6:
        hoy = date.today()
        edad_paciente = hoy.year - fecha_nacimiento.year - ((hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))
        st.text_input("Edad calculada", value=f"{edad_paciente} años", disabled=True)
    with col7:
        prevision = st.selectbox("Previsión", opts_prev, index=idx_prev)
    with col8:
        sexo = st.selectbox("Sexo", opts_sexo, index=idx_sexo)        

    col9, col10, col11 = st.columns(3)
    
    with col9: 
        c_pref1, c_num1 = st.columns([1, 2])
        with c_pref1:
            idx_p_fono = lista_prefijos.index(pref_fono_ext) if pref_fono_ext in lista_prefijos else lista_prefijos.index("OTRO")
            sel_pref_fono = st.selectbox("Cód.", options=lista_prefijos, index=idx_p_fono, format_func=lambda x: dic_prefijos[x], key=f"p_fono_{prefijo_key}")
            
            if sel_pref_fono == "OTRO":
                prefijo_fono = st.text_input("Escriba Cód.", value=pref_fono_ext if pref_fono_ext not in lista_prefijos else "+", key=f"m_fono_{prefijo_key}")
            else:
                prefijo_fono = sel_pref_fono

        with c_num1:
            fono_base = st.text_input(
                "Fono fijo",
                value=base_fono_ext,
                placeholder="22 123 4567",
                max_chars=11,
                key=key_fono_base,
                on_change=formatear_telefono_dinamico,
                args=(key_fono_base,)
            )
        # Reconstruimos el teléfono fijo
        fono_fijo_final = f"{prefijo_fono} {fono_base.strip()}" if fono_base.strip() else ""

    with col10: 
        c_pref2, c_num2 = st.columns([1, 2])
        with c_pref2:
            idx_p_cel = lista_prefijos.index(pref_cel_ext) if pref_cel_ext in lista_prefijos else lista_prefijos.index("OTRO")
            sel_pref_cel = st.selectbox("Cód.", options=lista_prefijos, index=idx_p_cel, format_func=lambda x: dic_prefijos[x], key=f"p_cel_{prefijo_key}")
            
            if sel_pref_cel == "OTRO":
                prefijo_cel = st.text_input("Escriba Cód.", value=pref_cel_ext if pref_cel_ext not in lista_prefijos else "+", key=f"m_cel_{prefijo_key}")
            else:
                prefijo_cel = sel_pref_cel

        with c_num2:
            celular_base = st.text_input(
                "Celular",
                value=base_cel_ext,
                placeholder="987 654 321",
                max_chars=11,
                key=key_celular_base,
                on_change=formatear_telefono_dinamico,
                args=(key_celular_base,)
            )
        # Reconstruimos el celular
        celular_final = f"{prefijo_cel} {celular_base.strip()}" if celular_base.strip() else ""
            
    with col11: 
        email = st.text_input("Email", value=v_email, placeholder="ejemplo@correo.com")

    st.markdown("<br>", unsafe_allow_html=True)
    
    texto_boton = "💾 Actualizar datos del paciente" if paciente_existente else "💾 Guardar nuevo paciente"
    
    if st.button(texto_boton, type="primary"):
        if not rut or not nombres or not apellido_paterno:
            st.error("❌ Debe completar al menos: RUT, Nombres y Apellido paterno.")
        else:
            session = SessionLocal()
            try:
                if paciente_existente:
                    p = session.query(Paciente).filter(Paciente.rut == paciente_existente.rut).first()
                    p.rut = rut.strip()
                    p.nombres = nombres
                    p.apellido_paterno = apellido_paterno
                    p.apellido_materno = apellido_materno
                    p.fecha_nacimiento = fecha_nacimiento
                    p.sexo = sexo if sexo else None
                    p.telefono = celular_final if celular_final else None
                    p.email = email if email else None
                    
                    if hasattr(p, 'prevision'): p.prevision = prevision
                    if hasattr(p, 'fono_fijo'): p.fono_fijo = fono_fijo_final
                    
                    session.commit()
                    st.success(f"✅ Paciente **{nombres} {apellido_paterno} {apellido_materno or ''}** actualizado correctamente.")
                
                else:
                    existe = session.query(Paciente).filter(Paciente.rut == rut.strip()).first()
                    if existe:
                        st.error(f"⚠️ Ya existe un paciente registrado con el RUT {rut}")
                    else:
                        nuevo_p = Paciente(
                            rut=rut.strip(),
                            nombres=nombres,
                            apellido_paterno=apellido_paterno,
                            apellido_materno=apellido_materno,
                            fecha_nacimiento=fecha_nacimiento,
                            sexo=sexo if sexo else None,
                            telefono=celular_final if celular_final else None,
                            email=email if email else None
                        )
                        
                        if hasattr(nuevo_p, 'prevision'): nuevo_p.prevision = prevision
                        if hasattr(nuevo_p, 'fono_fijo'): nuevo_p.fono_fijo = fono_fijo_final
                        
                        session.add(nuevo_p)
                        session.commit()
                        st.success(f"✅ Paciente **{nombres} {apellido_paterno} {apellido_materno or ''}** registrado correctamente.")
                        st.balloons()
            except Exception as e:
                session.rollback()
                st.error(f"❌ Error al guardar en la base de datos: {e}")
            finally:
                session.close()