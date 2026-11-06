# Archivo: database/database.py
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from database.models import Base, Rol

# 1. Obtener la URL desde los secretos de Streamlit (Protegido en la nube)
DATABASE_URL = st.secrets["DATABASE_URL"]

# Corrección obligatoria si la URL llegase a empezar con postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 2. Crear el motor de conexión para PostgreSQL
engine = create_engine(
    DATABASE_URL,
    pool_size=10,             # Número máximo de conexiones simultáneas persistentes
    max_overflow=10,         # Conexiones extra permitidas en picos de tráfico
    pool_recycle=180,        # Reciclar conexiones cada 3 minutos (Evita el cierre de Neon)
    pool_pre_ping=True       # Verifica si la conexión sigue viva antes de usarla
)

# 3. Configurar la fábrica de sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. Asegurar que las tablas existan en Neon
Base.metadata.create_all(bind=engine)

# 4b. Migración: create_all() NO agrega columnas a tablas que ya existen,
#     por eso se agrega aquí la columna de enteros si aún no está.
try:
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE mediciones ADD COLUMN IF NOT EXISTS valor_entero INTEGER"
        ))
except Exception as e:
    print(f"Aviso al migrar la tabla mediciones: {e}")

# =========================================================
# CONFIGURACIÓN INICIAL DE ROLES (No es información sensible)
# =========================================================
session = SessionLocal()
try:
    # Aseguramos que los roles del sistema existan siempre en la base de datos
    roles_sistema = ["Administrador", "Cardiólogo", "Investigador"]
    
    for nombre_rol in roles_sistema:
        existe = session.query(Rol).filter(Rol.nombre == nombre_rol).first()
        if not existe:
            nuevo_rol = Rol(nombre=nombre_rol)
            session.add(nuevo_rol)
            
    session.commit()
except Exception as e:
    session.rollback()
    print(f"Aviso al inicializar roles: {e}")
finally:
    session.close()