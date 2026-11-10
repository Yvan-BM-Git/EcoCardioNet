"""utils/indicadores.py y utils/exportacion.py."""
from datetime import date, timedelta

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from database.models import Estudio, Medicion
from utils import indicadores
from utils.exportacion import COLUMNAS_IDENTIFICADORAS, anonimizar, construir_dataset


# ---------------- Indicadores: funciones puras ----------------
def test_periodos_mismo_tramo_anterior():
    hoy = date(2026, 11, 10)  # martes
    p = indicadores.periodos(hoy)
    assert p["Hoy"][0] == (hoy, hoy) and p["Hoy"][1] == (date(2026, 11, 9),) * 2
    assert p["Esta semana"][0] == (date(2026, 11, 9), hoy)
    assert p["Esta semana"][1] == (date(2026, 11, 2), date(2026, 11, 3))
    assert p["Este mes"][1] == (date(2026, 10, 1), date(2026, 10, 10))
    assert p["Este año"][1] == (date(2025, 1, 1), date(2025, 11, 10))


@pytest.mark.parametrize("hoy, previo_mes, previo_anio_fin", [
    (date(2026, 3, 31), (date(2026, 2, 1), date(2026, 2, 28)), date(2025, 3, 31)),   # febrero más corto
    (date(2026, 1, 15), (date(2025, 12, 1), date(2025, 12, 15)), date(2025, 1, 15)), # cambio de año
    (date(2028, 2, 29), (date(2028, 1, 1), date(2028, 1, 29)), date(2027, 2, 28)),   # bisiesto
])
def test_periodos_bordes(hoy, previo_mes, previo_anio_fin):
    p = indicadores.periodos(hoy)
    assert p["Este mes"][1] == previo_mes
    assert p["Este año"][1][1] == previo_anio_fin


def test_contar_y_delta():
    f = pd.Series(pd.to_datetime(["2026-11-01", "2026-11-05", "2026-11-10"]))
    assert indicadores._contar(f, date(2026, 11, 1), date(2026, 11, 5)) == 2
    assert indicadores._contar(pd.Series(dtype="datetime64[ns]"), date(2026, 1, 1), date(2026, 12, 31)) == 0
    assert indicadores._delta(5, 3, "ayer") == "+2 vs. ayer"
    assert indicadores._delta(1, 3, "ayer") == "-2 vs. ayer"
    assert indicadores._miles(12345) == "12.345"


@pytest.mark.parametrize("gran, n", [("Día", 30), ("Semana", 12), ("Mes", 12)])
def test_serie_largo_y_conteo(gran, n):
    hoy = date(2026, 11, 10)
    est = pd.DataFrame({"fecha": pd.to_datetime([hoy, hoy, hoy - timedelta(days=40)])})
    s = indicadores.serie(est, gran, hoy)
    assert len(s) == n
    assert s["Estudios"].iloc[-1] == 2
    assert s["Estudios"].sum() == (2 if gran == "Día" else 3)


def test_serie_anual_incluye_anio_actual_sin_datos():
    s = indicadores.serie(pd.DataFrame({"fecha": pd.to_datetime(["2024-05-01"])}), "Año", date(2026, 1, 1))
    assert list(s["Período"]) == ["2024", "2026"]


def test_cargar_datos_y_cache(sesion_bd):
    indicadores.limpiar_cache()
    est, pac, med = indicadores.cargar_datos()
    n = len(est)
    sesion_bd.add(Estudio(paciente_rut="14.111.222-3", fecha_estudio=date.today(), medico="Dr. Cache"))
    sesion_bd.commit()
    assert len(indicadores.cargar_datos()[0]) == n          # cacheado
    indicadores.limpiar_cache()
    assert len(indicadores.cargar_datos()[0]) == n + 1
    assert {"id", "rut", "fecha", "medico"} == set(est.columns)


def test_mostrar_resumen_sin_errores():
    def script():
        from utils.indicadores import mostrar_resumen
        mostrar_resumen("Dr. Cache")

    at = AppTest.from_function(script).run(timeout=60)
    assert not at.exception
    etiquetas = [m.label for m in at.metric]
    for e in ("Hoy", "Esta semana", "Este mes", "Este año", "Pacientes registrados",
              "Promedio diario (30 días)", "Pacientes con seguimiento", "Médicos activos (90 días)"):
        assert e in etiquetas
    hallazgos = at.dataframe[-1].value
    assert list(hallazgos["Hallazgo"]) == [e for _, e, _ in indicadores.CLINICOS]


# ---------------- Exportación anonimizada ----------------
@pytest.fixture
def dataset(sesion_bd):
    """Dos estudios del mismo paciente y uno de otro, con mediciones."""
    ids = []
    for rut, fecha, medico, fevi in [("14.111.222-3", date(2025, 1, 10), "Dr. A", 60),
                                     ("14.111.222-3", date(2025, 3, 11), "Dra. B", 45),
                                     ("15.222.333-4", date(2026, 2, 1), "Dr. A", 30)]:
        e = Estudio(paciente_rut=rut, fecha_estudio=fecha, medico=medico, destino="UCI")
        sesion_bd.add(e)
        sesion_bd.flush()
        sesion_bd.add(Medicion(estudio_id=e.id, codigo_variable="FEVI", valor_entero=fevi))
        sesion_bd.add(Medicion(estudio_id=e.id, codigo_variable="GRADO_REFLUJO_MITRAL", valor_texto="Leve"))
        ids.append(e.id)
    sesion_bd.commit()
    df = construir_dataset(sesion_bd)
    yield df[df["estudio_id"].isin(ids)].reset_index(drop=True)
    sesion_bd.query(Medicion).filter(Medicion.estudio_id.in_(ids)).delete(synchronize_session=False)
    sesion_bd.query(Estudio).filter(Estudio.id.in_(ids)).delete(synchronize_session=False)
    sesion_bd.commit()


def test_construir_dataset(dataset):
    assert len(dataset) == 3
    nombre_fevi = [c for c in dataset.columns if c.lower().startswith("frac")][0]
    assert list(dataset[nombre_fevi]) == [60, 45, 30]                    # enteros siguen enteros
    assert "servicio_destino" in dataset.columns and set(dataset["servicio_destino"]) == {"UCI"}
    assert dataset.loc[0, "edad"] == 64                                  # 1960-05-01 -> 2025-01-10


def test_anonimizar_quita_identificadores(dataset):
    anon = anonimizar(dataset)
    for c in COLUMNAS_IDENTIFICADORAS:
        assert c not in anon.columns
    texto = anon.to_csv()
    for dato in ("14.111.222-3", "Juan", "Prueba", "2025-01-10", "Dr. A", "Dra. B"):
        assert dato not in texto


def test_anonimizar_conserva_seguimiento(dataset):
    anon = anonimizar(dataset)
    assert list(anon.columns[:3]) == ["id_paciente", "anio_estudio", "dias_desde_primer_estudio"]
    juan = anon[anon["id_paciente"] == "P0001"]
    assert list(juan["dias_desde_primer_estudio"]) == [0, 60]
    assert list(juan["anio_estudio"]) == [2025, 2025]
    assert anon["id_paciente"].nunique() == 2
    assert set(anon["medico_responsable"]) == {"M01", "M02"}
