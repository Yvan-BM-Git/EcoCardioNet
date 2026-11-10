"""
Pruebas de las páginas con AppTest (Streamlit sin navegador): ingreso,
aceptación legal, permisos por rol y los flujos principales.
"""
from datetime import date

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from database.database import SessionLocal
from database.models import AceptacionLegal, Estudio, Medicion, Rol, Usuario
from tests.conftest import (
    CLAVE_ADMIN, RAIZ, RUT_ADMIN, AppTest, abrir_estudio, abrir_pagina, sin_excepciones,
)

PAGINAS = ["app.py", "pages/estudios.py", "pages/historial.py", "pages/exportar.py",
           "pages/usuarios.py", "pages/legal.py"]


# ======================================================================
# Ingreso + Términos y Privacidad
# ======================================================================
def _estado(at, clave, defecto=None):
    """El session_state de AppTest no tiene .get()."""
    return at.session_state[clave] if clave in at.session_state else defecto


def _login(at, rut, clave):
    at.text_input(key="puente_rut").input(rut)
    at.text_input(key="puente_clave").input(clave)
    at.button[0].click().run()   # botón del formulario puente
    return at


@pytest.fixture
def usuario_nuevo():
    """Cardiólogo que nunca ha aceptado los documentos legales."""
    rut = "16.000.000-1"
    s = SessionLocal()
    rol = s.query(Rol).filter(Rol.nombre == "Cardiólogo").one()
    s.add(Usuario(rut=rut, nombre="Dra. Nueva", password_hash=generate_password_hash("ClaveNueva123"),
                  rol_id=rol.id, activo=True))
    s.commit()
    yield rut, "ClaveNueva123"
    s.query(AceptacionLegal).filter(AceptacionLegal.usuario_rut == rut).delete()
    s.query(Usuario).filter(Usuario.rut == rut).delete()
    s.commit()
    s.close()


def test_login_clave_incorrecta():
    at = AppTest.from_file(str(RAIZ / "app.py")).run()
    _login(at, "111111111", "mala")
    assert not at.session_state["autenticado"]
    assert at.session_state["login_error"] == "RUT o contraseña incorrectos."
    assert at.session_state["login_rut_previo"] == RUT_ADMIN       # RUT formateado y conservado


def test_login_campos_vacios():
    at = AppTest.from_file(str(RAIZ / "app.py")).run()
    _login(at, "", "")
    assert at.session_state["login_error"] == "Ingresa tu RUT y tu contraseña."


def test_login_pide_aceptacion_y_luego_entra(usuario_nuevo):
    rut, clave = usuario_nuevo
    at = AppTest.from_file(str(RAIZ / "app.py")).run()
    _login(at, rut, clave)
    assert not at.session_state["autenticado"]
    assert any("Antes de continuar" in t.value for t in at.title)
    aceptar = [b for b in at.button if b.label == "Aceptar y continuar"][0]
    assert aceptar.disabled                                          # sin marcar las casillas
    at.checkbox(key="acepta_terminos").check()
    at.checkbox(key="acepta_privacidad").check().run()
    [b for b in at.button if b.label == "Aceptar y continuar"][0].click().run()
    assert at.session_state["autenticado"]
    assert at.session_state["usuario_actual"]["rol"] == "Cardiólogo"
    assert not sin_excepciones(at)
    s = SessionLocal()
    assert {a.documento for a in s.query(AceptacionLegal).filter(AceptacionLegal.usuario_rut == rut)} == \
        {"terminos", "privacidad"}
    s.close()
    # Segundo ingreso: ya no se pide aceptar
    at2 = AppTest.from_file(str(RAIZ / "app.py")).run()
    _login(at2, rut, clave)
    assert at2.session_state["autenticado"]


def test_rechazar_terminos_vuelve_al_login(usuario_nuevo):
    rut, clave = usuario_nuevo
    at = AppTest.from_file(str(RAIZ / "app.py")).run()
    _login(at, rut, clave)
    [b for b in at.button if b.label == "Rechazar y salir"][0].click().run()
    assert not at.session_state["autenticado"]
    assert "usuario_pendiente" not in at.session_state


def test_usuario_desactivado_no_entra(usuario_nuevo):
    rut, clave = usuario_nuevo
    s = SessionLocal()
    s.query(Usuario).filter(Usuario.rut == rut).update({"activo": False})
    s.commit()
    s.close()
    at = AppTest.from_file(str(RAIZ / "app.py")).run()
    _login(at, rut, clave)
    assert "desactivada" in at.session_state["login_error"]


def test_admin_creado_por_create_db_entra():
    at = AppTest.from_file(str(RAIZ / "app.py")).run()
    _login(at, RUT_ADMIN, CLAVE_ADMIN)
    assert _estado(at, "autenticado") or _estado(at, "usuario_pendiente")


# ======================================================================
# Carga y permisos de cada página
# ======================================================================
@pytest.mark.parametrize("ruta", PAGINAS)
@pytest.mark.parametrize("rol", ["Administrador", "Cardiólogo", "Investigador"])
def test_paginas_cargan_sin_errores(ruta, rol):
    at = abrir_pagina(ruta, rol=rol).run()
    assert not sin_excepciones(at)


@pytest.mark.parametrize("ruta", ["pages/estudios.py", "pages/historial.py", "pages/exportar.py", "pages/usuarios.py"])
def test_paginas_protegidas_sin_sesion(ruta):
    at = abrir_pagina(ruta, autenticado=False).run()
    assert any("iniciar sesión" in w.value.lower() for w in at.warning)


def test_legal_es_publica():
    at = abrir_pagina("pages/legal.py", autenticado=False).run()
    assert not sin_excepciones(at)
    assert [t.label for t in at.tabs] == ["Términos de Servicio", "Política de Privacidad"]


@pytest.mark.parametrize("ruta, rol", [("pages/exportar.py", "Cardiólogo"), ("pages/usuarios.py", "Cardiólogo"),
                                       ("pages/usuarios.py", "Investigador")])
def test_acceso_denegado_por_rol(ruta, rol):
    at = abrir_pagina(ruta, rol=rol).run()
    assert at.error and "denegado" in at.error[0].value.lower() or any("acceso" in e.value.lower() for e in at.error)


def test_inicio_sin_tarjeta_de_paciente_nuevo():
    at = abrir_pagina("app.py").run()
    textos = " ".join(x.value for grupo in (at.info, at.success, at.warning, at.error) for x in grupo)
    assert "Ingresar un Paciente Nuevo" not in textos
    assert "Registrar un Examen" in textos


# ======================================================================
# Nuevo Estudio
# ======================================================================
@pytest.mark.parametrize("key, entrada, esperado", [
    ("var_FEVI", "abc", ""),
    ("var_FEVI", "66,5", "66.5"),
    ("var_STRAIN_LONGITUDINAL_GLOBAL_VI", "-14", "-14"),   # strain admite negativos
    ("pas", "120.5", ""),                                   # PAS es entera
    ("pas", "104", "104"),
    ("peso_input", "70,5", "70.5"),
    ("talla_input", "1e3", ""),
])
def test_estudio_valida_campos_numericos(key, entrada, esperado):
    at = abrir_estudio("14.111.222-3")
    at.text_input(key=key).input(entrada).run()
    assert at.text_input(key=key).value == esperado
    assert not sin_excepciones(at)


def test_estudio_negativo_rechazado_conserva_valor_previo():
    at = abrir_estudio("14.111.222-3")
    at.text_input(key="var_DIAMETRO_VI_DIASTOLICO").input("50").run()
    at.text_input(key="var_DIAMETRO_VI_DIASTOLICO").input("-61").run()
    assert at.text_input(key="var_DIAMETRO_VI_DIASTOLICO").value == "50"
    assert any("negativo" in t.value for t in at.toast)


def test_estudio_asc_mosteller():
    at = abrir_estudio("14.111.222-3")
    at.text_input(key="peso_input").input("70").run()
    at.text_input(key="talla_input").input("170").run()
    assert round(float(at.session_state["asc_val"]), 2) == 1.82


def _boton(at, texto):
    return [b for b in at.button if texto in (b.label or "")][0]


def test_estudio_exige_medico_y_guarda_con_pdf_y_destino():
    rut = "15.222.333-4"
    at = abrir_estudio(rut)
    at.text_input(key="var_FEVI").input("22").run()
    at.text_input(key="peso_input").input("70").run()
    at.text_input(key="talla_input").input("170").run()
    at.text_input(key="destino").input("UCI Coronaria").run()
    _boton(at, "Guardar informe").click().run()
    assert any("médico responsable" in e.value for e in at.error)

    s = SessionLocal()
    antes = s.query(Estudio).filter(Estudio.paciente_rut == rut).count()
    at.selectbox(key="medico_seleccionado_estudio").set_value("Dr. Eric Fuentes Latorre").run()
    _boton(at, "Guardar informe").click().run()
    assert any("guardado" in x.value for x in at.success)
    assert not sin_excepciones(at)

    est = s.query(Estudio).filter(Estudio.paciente_rut == rut).order_by(Estudio.id.desc()).first()
    assert s.query(Estudio).filter(Estudio.paciente_rut == rut).count() == antes + 1
    assert est.destino == "UCI Coronaria"
    assert est.pdf_original[:5] == b"%PDF-"                 # el PDF se genera al guardar
    import io as _io, pdfplumber as _pp
    cab = " ".join((_pp.open(_io.BytesIO(est.pdf_original)).pages[0].extract_text() or "").split())
    assert "Talla 170 cm" in cab and "Peso 70 kg" in cab     # antes salían como "—"
    fevi = s.query(Medicion).filter(Medicion.estudio_id == est.id, Medicion.codigo_variable == "FEVI").one()
    assert fevi.valor_entero == 22 and fevi.valor_num is None
    s.close()


def test_estudio_descarga_pdf_diferida():
    """El PDF ya no se arma en cada recarga: el botón recibe una función."""
    at = abrir_estudio("14.111.222-3")
    botones = [e for e in at.get("download_button")]
    assert botones, "debe existir el botón de descarga del PDF"


def test_estudio_crear_paciente_inline():
    rut = "19.876.543-2"
    at = abrir_pagina("pages/estudios.py").run()
    _boton(at, "Registrar Nuevo Paciente").click().run()
    at.text_input(key="rut_inline_nuevo").input(rut).run()
    at.text_input(key="nom_inline").input("Pedro").run()
    at.text_input(key="ap_inline").input("Inline").run()
    _boton(at, "Guardar y seleccionar paciente").click().run()
    assert not sin_excepciones(at)
    from utils import catalogos
    assert rut in {p["rut"] for p in catalogos.pacientes()}    # el buscador lo ve de inmediato


# ======================================================================
# Historial
# ======================================================================
def test_historial_paciente_con_estudios():
    at = abrir_pagina("pages/historial.py").run()
    at.selectbox(key="selectbox_historial_paciente").set_value("15.222.333-4").run()
    assert not sin_excepciones(at)
    assert any("Historial Clínico" in x.value for x in at.subheader)
    etiquetas = [b.proto.label for b in at.get("download_button")]
    assert any("Re-generar" in e for e in etiquetas)


def test_historial_pdf_regenerado_y_original():
    import importlib.util
    spec = importlib.util.spec_from_file_location("hist", RAIZ / "pages" / "historial.py")
    src = (RAIZ / "pages" / "historial.py").read_text()
    inicio, fin = src.index("def _pdf_regenerado"), src.index("def formatear_busqueda_callback")
    ns = {}
    exec("from database.database import SessionLocal\nfrom database.models import *\n"
         "from utils.pdf_informe import generar_pdf_desde_historial\n" + src[inicio:fin], ns)
    s = SessionLocal()
    est = s.query(Estudio).filter(Estudio.pdf_original.isnot(None)).first()
    s.close()
    assert ns["_pdf_regenerado"](est.id)()[:5] == b"%PDF-"
    assert ns["_pdf_original"](est.id)()[:5] == b"%PDF-"


# ======================================================================
# Exportar
# ======================================================================
def test_exportar_investigador_solo_anonimizado():
    at = abrir_pagina("pages/exportar.py", rol="Investigador").run()
    assert not sin_excepciones(at)
    assert any("anonimizada" in i.value for i in at.info)
    assert not any("identificada" in e.label for e in at.expander)
    assert "rut" not in at.dataframe[0].value.columns


def test_exportar_admin_identificada_requiere_confirmacion():
    at = abrir_pagina("pages/exportar.py").run()
    assert any("identificada" in e.label for e in at.expander)
    n = len(at.get("download_button"))
    at.checkbox(key="ok_export_identificada").check().run()
    assert len(at.get("download_button")) == n + 2              # CSV y Excel identificados


# ======================================================================
# Usuarios
# ======================================================================
def test_usuarios_crear_validar_y_cambiar_clave():
    rut = "17.555.444-3"
    at = abrir_pagina("pages/usuarios.py").run()
    at.text_input(key="rut_usuario_nuevo").input("175554443").run()
    assert at.text_input(key="rut_usuario_nuevo").value == rut     # formateado
    at.text_input(key="nombre_nuevo").input("Dr. Test")
    at.text_input(key="password_nuevo").input("corta")
    at.button(key="btn_guardar_usuario").click().run()
    assert any("al menos 8" in e.value for e in at.error)

    at.text_input(key="password_nuevo").input("ClaveLarga123")
    at.button(key="btn_guardar_usuario").click().run()
    assert not sin_excepciones(at)
    s = SessionLocal()
    u = s.query(Usuario).filter(Usuario.rut == rut).one()
    assert check_password_hash(u.password_hash, "ClaveLarga123")

    at.selectbox(key="rut_cambiar_clave").set_value(rut)
    at.text_input(key="nueva_clave").input("Nueva12345")
    [b for b in at.button if b.label == "Actualizar Contraseña"][0].click().run()
    s.expire_all()
    assert check_password_hash(s.query(Usuario).filter(Usuario.rut == rut).one().password_hash, "Nueva12345")
    s.query(Usuario).filter(Usuario.rut == rut).delete()
    s.commit()
    s.close()
