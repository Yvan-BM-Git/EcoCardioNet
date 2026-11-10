"""
Casos clínicos publicados (PDF en Papers/), de punta a punta: se ingresan en
Nuevo Estudio como lo haría un usuario, se guarda el informe y se genera el
PDF desde la base. Se verifica que:
  - todas las cifras se aceptan tal como se escriben;
  - el informe contiene los diagnósticos que reportan los autores;
  - las conclusiones de la pantalla y del PDF coinciden.

Son las pruebas más lentas: python -m pytest tests -m "not lento" las omite.
"""
import io

import pdfplumber
import pytest

from database.database import SessionLocal
from database.models import Estudio, Medicion, Paciente, Variable
from tests.conftest import abrir_estudio, sin_excepciones
from tests.datos.casos_publicados import CASOS
from utils.pdf_informe import generar_pdf_desde_historial

pytestmark = pytest.mark.lento


@pytest.fixture(scope="module", autouse=True)
def pacientes_de_los_casos():
    s = SessionLocal()
    for c in CASOS:
        if not s.get(Paciente, c["rut"]):
            s.add(Paciente(rut=c["rut"], nombres=c["nombre"], apellido_paterno="Publicado",
                           apellido_materno="Paper", sexo=c["sexo"], fecha_nacimiento=c["nac"]))
    s.commit()
    s.close()
    from utils import catalogos
    catalogos.limpiar_pacientes()


@pytest.mark.parametrize("caso", CASOS, ids=[f'{c["id"]}-{c["titulo"][:40]}' for c in CASOS])
def test_caso_publicado(caso):
    at = abrir_estudio(caso["rut"])
    assert not sin_excepciones(at)
    at.selectbox(key="medico_seleccionado_estudio").set_value("Dr. Eric Fuentes Latorre").run()
    if caso["ritmo"]:
        at.selectbox(key="ritmo").set_value(caso["ritmo"]).run()
    for k, val in (("pas", caso["pas"]), ("pad", caso["pad"]), ("fcia", caso["fc"])):
        if val is not None:
            at.text_input(key=k).input(str(val)).run()

    for cod, val in caso["v"].items():
        k = f"var_{cod}"
        ti = [w for w in at.text_input if w.key == k]
        if ti:
            ti[0].input(str(val)).run()
            assert str(at.text_input(key=k).value) == str(val).replace(",", "."), cod
        else:
            sb = [w for w in at.selectbox if w.key == k]
            assert sb, f"{cod}: campo no encontrado"
            assert val in sb[0].options, f"{cod}: opción {val!r} no existe"
            sb[0].set_value(val).run()

    [b for b in at.button if "Regenerar" in (b.label or "")][0].click().run()
    areas = {t.key: t.value for t in at.text_area}
    texto = areas.get("hallazgos_editables", "") + "\n" + areas.get("conclusiones_editables", "")
    faltan = [k for k in caso["clave_esperada"] if k.lower() not in texto.lower()]
    assert not faltan, f"el informe no menciona {faltan}"

    [b for b in at.button if "Guardar informe" in (b.label or "")][0].click().run()
    assert any("guardado" in x.value for x in at.success), [e.value for e in at.error]

    s = SessionLocal()
    est = s.query(Estudio).filter(Estudio.paciente_rut == caso["rut"]).order_by(Estudio.id.desc()).first()
    meds = (s.query(Medicion, Variable).outerjoin(Variable, Medicion.variable_id == Variable.id)
            .filter(Medicion.estudio_id == est.id).all())
    pdf = generar_pdf_desde_historial(est, s.get(Paciente, caso["rut"]), meds)
    s.close()
    texto_pdf = " ".join("\n".join(p.extract_text() or "" for p in pdfplumber.open(io.BytesIO(pdf)).pages).split())
    for linea in areas.get("conclusiones_editables", "").splitlines():
        if linea.strip():
            assert linea.split(". ", 1)[-1][:40] in texto_pdf, linea
