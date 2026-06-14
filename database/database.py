# Archivo: database/database.py
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base, Usuario, Rol
from werkzeug.security import generate_password_hash

# 1. Obtener la URL desde los secretos de Streamlit
DATABASE_URL = st.secrets["DATABASE_URL"]

# Corrección obligatoria si la URL llegase a empezar con postgres://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 2. Crear el motor de conexión para PostgreSQL
engine = create_engine(DATABASE_URL)

# 3. Configurar la fábrica de sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# =========================================================
# MÁGIA DE POSTGRESQL: CREACIÓN Y SIEMBRA INICIAL
# =========================================================
# Crea las tablas en Neon de forma automática si no existen
Base.metadata.create_all(bind=engine)

# Rutina para crear el primer Administrador en la nube si la DB está vacía
session = SessionLocal()
try:
    # Asegurar que el rol Administrador exista en Postgres
    rol_admin = session.query(Rol).filter(Rol.nombre == "Administrador").first()
    if not rol_admin:
        rol_admin = Rol(nombre="Administrador")
        session.add(rol_admin)
        session.flush()

    # Si no hay ningún usuario registrado en la nube, creamos el tuyo de prueba
    if session.query(Usuario).count() == 0:
        primer_admin = Usuario(
            rut="26.154.665-5",  # Tu RUT de la captura de pantalla
            nombre="Yvan Baldera Moreno",
            email="yvan.baldera@example.com", # Puedes cambiarlo luego
            password_hash=generate_password_hash("6289yvanbm"), # Tu clave temporal de la captura
            rol_id=rol_admin.id,
            activo=True
        )
        session.add(primer_admin)
        session.commit()
except Exception as e:
    session.rollback()
    print(f"Aviso de inicialización: {e}")
finally:
    session.close()