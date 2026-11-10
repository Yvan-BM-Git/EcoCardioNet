"""
Armado de la base de investigación y su anonimización (Ley 21.719).
Sin Streamlit: se prueba en tests/test_exportacion.py.
"""
import numpy as np
import pandas as pd

from database.models import Estudio, Medicion, Paciente, Variable


# Columnas que identifican al paciente: nunca salen en la exportación anonimizada.
COLUMNAS_IDENTIFICADORAS = ["estudio_id", "rut", "nombres", "apellido_paterno", "apellido_materno", "fecha_estudio"]


def _edad(f_nac, f_est):
    if not f_nac or not f_est:
        return np.nan
    return f_est.year - f_nac.year - ((f_est.month, f_est.day) < (f_nac.month, f_nac.day))


def construir_dataset(session) -> pd.DataFrame:
    """Una fila por estudio: datos del paciente/estudio + todas las variables (identificado)."""
    filas = session.query(
        Estudio.id, Estudio.fecha_estudio, Estudio.medico, Estudio.tipo_estudio, Estudio.diagnostico,
        Estudio.procedencia, Estudio.destino, Estudio.peso, Estudio.talla, Estudio.asc_valor, Estudio.imc, Estudio.pas,
        Estudio.pad, Estudio.ritmo, Estudio.fcia,
        Paciente.rut, Paciente.nombres, Paciente.apellido_paterno, Paciente.apellido_materno,
        Paciente.fecha_nacimiento, Paciente.sexo, Paciente.prevision,
    ).join(Paciente, Estudio.paciente_rut == Paciente.rut).all()
    if not filas:
        return pd.DataFrame()

    df = pd.DataFrame([{
        "estudio_id": f.id,
        "rut": f.rut,
        "nombres": f.nombres,
        "apellido_paterno": f.apellido_paterno,
        "apellido_materno": f.apellido_materno,
        "fecha_estudio": f.fecha_estudio,
        "edad": _edad(f.fecha_nacimiento, f.fecha_estudio),
        "sexo": f.sexo,
        "prevision": f.prevision,
        "medico_responsable": f.medico,
        "tipo_estudio": f.tipo_estudio,
        "patologia_de_base": f.diagnostico,
        "servicio_origen": f.procedencia,
        "servicio_destino": f.destino,
        "peso_kg": f.peso,
        "talla_cm": f.talla,
        "asc": f.asc_valor,
        "imc": f.imc,
        "pas": f.pas,
        "pad": f.pad,
        "ritmo": f.ritmo,
        "fcia": f.fcia,
    } for f in filas])

    # Mediciones pivotadas por código (único); enteros se mantienen enteros.
    med = session.query(Medicion.estudio_id, Medicion.codigo_variable, Medicion.valor_entero,
                        Medicion.valor_num, Medicion.valor_texto).all()
    if med:
        df_med = pd.DataFrame([{
            "estudio_id": m.estudio_id,
            "codigo": m.codigo_variable,
            "valor": (int(m.valor_entero) if m.valor_entero is not None
                      else m.valor_num if m.valor_num is not None else m.valor_texto),
        } for m in med])
        ancha = df_med.pivot_table(index="estudio_id", columns="codigo", values="valor",
                                   aggfunc="first").reset_index()
        df = df.merge(ancha, on="estudio_id", how="left")

    # Nombres legibles; si dos variables comparten nombre, se agrega la categoría.
    variables = session.query(Variable.codigo, Variable.nombre, Variable.categoria).all()
    conteo = pd.Series([(n or c).strip() for c, n, _ in variables]).value_counts()
    nombres = {}
    for cod, nom, cat in variables:
        n = (nom or cod).strip()
        nombres[cod] = f"{n} ({(cat or '').strip() or cod})" if conteo[n] > 1 else n
    codigos = sorted(nombres, key=nombres.get)
    for cod in codigos:
        if cod not in df.columns:
            df[cod] = np.nan
    base = [c for c in df.columns if c not in nombres]
    return df[base + codigos].rename(columns=nombres)


def anonimizar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Quita RUT, nombres y fecha exacta. Agrega:
      · id_paciente: código correlativo (P0001…) que agrupa los estudios de una persona;
      · anio_estudio y dias_desde_primer_estudio: permiten seguimiento sin la fecha;
      · medico_responsable: reemplazado por un código (M01…).
    También se quita estudio_id, que permitiría volver a la ficha en la base.
    El código no se guarda en ninguna parte, por lo que no se puede revertir.
    """
    out = df.copy()
    fechas = pd.to_datetime(out["fecha_estudio"])
    orden = out.assign(_f=fechas).sort_values(["_f", "estudio_id"])
    codigos_pac = {rut: f"P{i:04d}" for i, rut in enumerate(orden["rut"].drop_duplicates(), start=1)}
    out.insert(0, "id_paciente", out["rut"].map(codigos_pac))
    out.insert(2, "anio_estudio", fechas.dt.year)
    primera = fechas.groupby(out["rut"]).transform("min")
    out.insert(3, "dias_desde_primer_estudio", (fechas - primera).dt.days)
    medicos = sorted(m for m in out["medico_responsable"].dropna().unique() if str(m).strip())
    out["medico_responsable"] = out["medico_responsable"].map({m: f"M{i:02d}" for i, m in enumerate(medicos, 1)})
    out = out.drop(columns=COLUMNAS_IDENTIFICADORAS)
    return out.sort_values(["id_paciente", "dias_desde_primer_estudio"]).reset_index(drop=True)
