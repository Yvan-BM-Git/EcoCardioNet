"""
Indicadores del panel de inicio.

Todo sale de 3 consultas (estudios, pacientes y 3 mediciones clave) que se
cachean 2 minutos; los cálculos por período se hacen en pandas. Así el
inicio carga rápido aunque la base esté en la nube.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from database.database import SessionLocal
from database.models import Estudio, Medicion, Paciente

# Indicadores clínicos: (código, etiqueta, función de umbral)
CLINICOS = [
    ("FEVI", "FEVI < 50 %", lambda v: v < 50),
    ("PSAP", "PSAP > 35 mmHg", lambda v: v > 35),
    ("VOLUMEN_AI", "AI dilatada (> 34 mL/m²)", lambda v: v > 34),
]

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


@st.cache_data(ttl=120, show_spinner=False)
def cargar_datos() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    session = SessionLocal()
    try:
        est = pd.DataFrame(
            session.query(
                Estudio.id, Estudio.paciente_rut, Estudio.fecha_estudio,
                Estudio.medico,
            ).all(),
            columns=["id", "rut", "fecha", "medico"],
        )
        pac = pd.DataFrame(
            session.query(Paciente.rut, Paciente.fecha_creacion).all(),
            columns=["rut", "creado"],
        )
        med = pd.DataFrame(
            session.query(
                Medicion.estudio_id, Medicion.codigo_variable,
                Medicion.valor_num, Medicion.valor_entero,
            ).filter(Medicion.codigo_variable.in_([c for c, _, _ in CLINICOS])).all(),
            columns=["id", "codigo", "num", "ent"],
        )
    finally:
        session.close()

    if not est.empty:
        est["fecha"] = pd.to_datetime(est["fecha"]).dt.normalize()
        est["medico"] = est["medico"].fillna("").str.strip()
    if not pac.empty:
        pac["creado"] = pd.to_datetime(pac["creado"]).dt.normalize()
    if not med.empty:
        med["valor"] = med["num"].fillna(med["ent"])
    return est, pac, med


def limpiar_cache() -> None:
    cargar_datos.clear()


def _miles(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


def _contar(fechas: pd.Series, desde: date, hasta: date) -> int:
    """Cuenta fechas en [desde, hasta] (ambos inclusive)."""
    if fechas.empty:
        return 0
    d, h = pd.Timestamp(desde), pd.Timestamp(hasta)
    return int(((fechas >= d) & (fechas <= h)).sum())


def _delta(actual: int, previo: int, texto: str) -> str | None:
    dif = actual - previo
    signo = "+" if dif > 0 else ""
    return f"{signo}{dif} vs. {texto}"


def periodos(hoy: date) -> dict:
    """Períodos en curso y su equivalente anterior (mismo número de días transcurridos)."""
    lunes = hoy - timedelta(days=hoy.weekday())
    ini_mes = hoy.replace(day=1)
    ini_anio = hoy.replace(month=1, day=1)
    fin_mes_ant = ini_mes - timedelta(days=1)
    ini_mes_ant = fin_mes_ant.replace(day=1)
    dia_mes = min(hoy.day, fin_mes_ant.day)
    try:
        hoy_anio_ant = hoy.replace(year=hoy.year - 1)
    except ValueError:  # 29 de febrero
        hoy_anio_ant = hoy.replace(year=hoy.year - 1, day=28)
    return {
        "Hoy": ((hoy, hoy), (hoy - timedelta(days=1),) * 2, "ayer"),
        "Esta semana": ((lunes, hoy), (lunes - timedelta(days=7), hoy - timedelta(days=7)), "sem. anterior"),
        "Este mes": ((ini_mes, hoy), (ini_mes_ant, ini_mes_ant.replace(day=dia_mes)), "mes anterior"),
        "Este año": ((ini_anio, hoy), (ini_anio.replace(year=hoy.year - 1), hoy_anio_ant), "año anterior"),
    }


def serie(est: pd.DataFrame, granularidad: str, hoy: date) -> pd.DataFrame:
    """Estudios por día (30 días), semana (12), mes (12) o año (todos)."""
    f = est["fecha"] if not est.empty else pd.Series(dtype="datetime64[ns]")
    hoy_ts = pd.Timestamp(hoy)
    if granularidad == "Día":
        idx = pd.date_range(hoy_ts - pd.Timedelta(days=29), hoy_ts, freq="D")
        cuenta = f.value_counts()
        etiquetas = [d.strftime("%d/%m") for d in idx]
        valores = [int(cuenta.get(d, 0)) for d in idx]
    elif granularidad == "Semana":
        lunes = hoy_ts - pd.Timedelta(days=hoy_ts.weekday())
        idx = [lunes - pd.Timedelta(weeks=k) for k in range(11, -1, -1)]
        sem = f - pd.to_timedelta(f.dt.weekday, unit="D")
        cuenta = sem.value_counts()
        etiquetas = [d.strftime("%d/%m") for d in idx]
        valores = [int(cuenta.get(d, 0)) for d in idx]
    elif granularidad == "Mes":
        per = pd.period_range(end=hoy_ts.to_period("M"), periods=12, freq="M")
        cuenta = f.dt.to_period("M").value_counts()
        etiquetas = [f"{MESES[p.month - 1]} {str(p.year)[2:]}" for p in per]
        valores = [int(cuenta.get(p, 0)) for p in per]
    else:
        anios = sorted(set(f.dt.year.dropna().astype(int)) | {hoy.year})
        cuenta = f.dt.year.value_counts()
        etiquetas = [str(a) for a in anios]
        valores = [int(cuenta.get(a, 0)) for a in anios]
    return pd.DataFrame({"Período": etiquetas, "Estudios": valores})


def mostrar_resumen(nombre_usuario: str | None = None, hoy: date | None = None) -> None:
    hoy = hoy or date.today()
    try:
        est, pac, med = cargar_datos()
    except Exception as e:  # la página no debe caerse por los indicadores
        st.warning(f"No se pudieron cargar los indicadores ({type(e).__name__}).")
        return

    fechas = est["fecha"] if not est.empty else pd.Series(dtype="datetime64[ns]")
    per = periodos(hoy)

    # ---------- Actividad por período ----------
    st.markdown("##### Estudios realizados")
    cols = st.columns(4)
    for col, (nombre, (actual, previo, texto)) in zip(cols, per.items()):
        n_act = _contar(fechas, *actual)
        n_prev = _contar(fechas, *previo)
        col.metric(nombre, _miles(n_act), delta=_delta(n_act, n_prev, texto), border=True,
                   help="La comparación usa el mismo tramo del período anterior "
                        "(p. ej., del 1 al 10 del mes pasado si hoy es día 10).")

    # ---------- Pacientes y productividad ----------
    st.markdown("##### Pacientes y productividad")
    c1, c2, c3, c4 = st.columns(4)
    total_pac = len(pac)
    ini_mes = hoy.replace(day=1)
    creados = pac["creado"] if not pac.empty else pd.Series(dtype="datetime64[ns]")
    nuevos_mes = _contar(creados, ini_mes, hoy)
    c1.metric("Pacientes registrados", _miles(total_pac), delta=f"+{nuevos_mes} este mes" if nuevos_mes else None,
              border=True)

    ult30 = _contar(fechas, hoy - timedelta(days=29), hoy)
    c2.metric("Promedio diario (30 días)", f"{ult30 / 30:.1f}".replace(".", ","), border=True,
              help="Estudios de los últimos 30 días dividido por 30.")

    seguimiento = int((est.groupby("rut").size() >= 2).sum()) if not est.empty else 0
    pct_seg = 100 * seguimiento / total_pac if total_pac else 0
    c3.metric("Pacientes con seguimiento", _miles(seguimiento), border=True,
              delta=f"{pct_seg:.0f} % del total".replace(".", ","), delta_color="off",
              help="Pacientes con 2 o más estudios.")

    hace90 = pd.Timestamp(hoy - timedelta(days=89))
    medicos_activos = est.loc[(est["fecha"] >= hace90) & (est["medico"] != ""), "medico"].nunique() if not est.empty else 0
    c4.metric("Médicos activos (90 días)", medicos_activos, border=True)

    if nombre_usuario and not est.empty:
        mios = est[est["medico"].str.casefold() == nombre_usuario.strip().casefold()]
        if not mios.empty:
            m_mes = _contar(mios["fecha"], ini_mes, hoy)
            m_anio = _contar(mios["fecha"], hoy.replace(month=1, day=1), hoy)
            st.caption(f"Tus estudios: **{m_mes}** este mes · **{m_anio}** este año · **{len(mios)}** en total.")

    # ---------- Tendencia ----------
    st.markdown("##### Tendencia")
    gran = st.segmented_control("Agrupar por", ["Día", "Semana", "Mes", "Año"], default="Mes",
                                key="ind_granularidad", label_visibility="collapsed") or "Mes"
    datos = serie(est, gran, hoy)
    st.bar_chart(datos, x="Período", y="Estudios", color="#c62f3c", height=240,
                 x_label="", y_label="Estudios", sort=False)

    # ---------- Médicos y hallazgos ----------
    izq, der = st.columns(2)
    with izq:
        st.markdown("##### Estudios por médico (este año)")
        ini_anio = pd.Timestamp(hoy.replace(month=1, day=1))
        anio = est[(est["fecha"] >= ini_anio) & (est["medico"] != "")] if not est.empty else est
        if anio.empty:
            st.caption("Sin estudios con médico registrado este año.")
        else:
            tabla = (anio.groupby("medico").size().sort_values(ascending=False).head(8)
                     .rename("Estudios").reset_index().rename(columns={"medico": "Médico"}))
            st.dataframe(tabla, hide_index=True, width="stretch")
    with der:
        st.markdown("##### Hallazgos frecuentes (este año)")
        ids_anio = set(est.loc[est["fecha"] >= pd.Timestamp(hoy.replace(month=1, day=1)), "id"]) if not est.empty else set()
        filas = []
        for codigo, etiqueta, umbral in CLINICOS:
            vals = med.loc[(med["codigo"] == codigo) & med["id"].isin(ids_anio), "valor"].dropna() if not med.empty else pd.Series(dtype=float)
            if vals.empty:
                filas.append({"Hallazgo": etiqueta, "Estudios": "–", "%": "–"})
                continue
            n = int(vals.map(umbral).sum())
            filas.append({"Hallazgo": etiqueta, "Estudios": f"{n} de {len(vals)}",
                          "%": f"{100 * n / len(vals):.0f} %"})
        st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
        st.caption("Porcentaje sobre los estudios del año que registraron esa medición.")

    st.caption(f"Total histórico: {_miles(len(est))} estudios. "
               "Indicadores por fecha del estudio; se actualizan cada 2 minutos.")
