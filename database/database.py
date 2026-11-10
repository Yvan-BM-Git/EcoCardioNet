# Archivo: database/database.py
"""
Conexión a la base de datos.

Importar este módulo NO abre ninguna conexión: create_engine() es
perezoso. La creación de tablas, las migraciones de columnas y los
roles del sistema se ejecutan en init_db(), que se llama una sola vez
por proceso a través de asegurar_bd() al inicio de cada página.
"""
import streamlit as st
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from database.models import Base, Rol

# 1. Obtener la URL desde los secretos de Streamlit (Protegido en la nube)
DATABASE_URL = st.secrets["DATABASE_URL"]

# Corrección obligatoria si la URL llegase a empezar con postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

ES_POSTGRES = DATABASE_URL.startswith("postgresql")

# 2. Crear el motor de conexión
_opciones_motor = {"pool_pre_ping": True}  # Verifica si la conexión sigue viva antes de usarla
if ES_POSTGRES:
    _opciones_motor.update(
        pool_size=10,           # Conexiones simultáneas persistentes
        max_overflow=10,        # Conexiones extra permitidas en picos de tráfico
        pool_recycle=180,       # Reciclar cada 3 minutos (Neon cierra conexiones inactivas)
        connect_args={"connect_timeout": 10},  # Falla en 10 s en vez de colgarse minutos
    )

engine = create_engine(DATABASE_URL, **_opciones_motor)

# 3. Configurar la fábrica de sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

ROLES_SISTEMA = ["Administrador", "Cardiólogo", "Investigador"]

# Columnas agregadas después de crear las tablas. create_all() NO agrega
# columnas a tablas que ya existen, por eso se agregan aquí si faltan.
#   (tabla, columna, tipo SQL)
COLUMNAS_MIGRADAS = [
    ("mediciones", "valor_entero", "INTEGER"),
    ("variables", "valor_minimo", "DOUBLE PRECISION" if ES_POSTGRES else "REAL"),
    ("variables", "valor_maximo", "DOUBLE PRECISION" if ES_POSTGRES else "REAL"),
]


def _migrar_columnas():
    inspector = inspect(engine)
    tablas = set(inspector.get_table_names())
    with engine.begin() as conn:
        for tabla, columna, tipo_sql in COLUMNAS_MIGRADAS:
            if tabla not in tablas:
                continue
            existentes = {c["name"] for c in inspector.get_columns(tabla)}
            if columna not in existentes:
                conn.execute(text(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo_sql}"))


def _asegurar_roles():
    session = SessionLocal()
    try:
        for nombre_rol in ROLES_SISTEMA:
            if not session.query(Rol).filter(Rol.nombre == nombre_rol).first():
                session.add(Rol(nombre=nombre_rol))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@st.cache_resource(show_spinner="Conectando con la base de datos...")
def init_db():
    """
    Crea tablas, agrega columnas nuevas y asegura los roles del sistema.
    Se cachea: corre una vez por proceso. Si falla, no queda en caché y
    se reintenta en la siguiente ejecución.
    """
    Base.metadata.create_all(bind=engine)
    _migrar_columnas()
    _asegurar_roles()
    return True


def asegurar_bd():
    """
    Llamar al inicio de cada página. Si la base de datos no responde,
    muestra un mensaje claro y detiene la página en vez de mostrar un
    traceback.
    """
    try:
        init_db()
    except Exception as e:
        st.error(
            "❌ No se pudo conectar con la base de datos. Revise su conexión a "
            "internet (algunas redes institucionales bloquean el puerto 5432) "
            "y vuelva a cargar la página."
        )
        with st.expander("Detalle técnico"):
            st.code(str(e))
        st.stop()
