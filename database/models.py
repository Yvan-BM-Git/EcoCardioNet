# Archivo: database/models.py
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Date,
    DateTime,
    Boolean,
    ForeignKey,
    Text
)

from datetime import datetime
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Rol(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    nombre = Column(String, unique=True)


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    rut = Column(String, unique=True)
    nombre = Column(String)
    email = Column(String)
    password_hash = Column(String)
    rol_id = Column(Integer, ForeignKey("roles.id"))
    activo = Column(Boolean, default=True)


class Paciente(Base):
    __tablename__ = "pacientes"

    rut = Column(String, primary_key=True)
    nombres = Column(String)
    apellido_paterno = Column(String)
    apellido_materno = Column(String)
    fecha_nacimiento = Column(Date)
    sexo = Column(String)
    telefono = Column(String) # Aquí estamos guardando el Celular
    email = Column(String)

    # --- NUEVOS CAMPOS AGREGADOS ---
    prevision = Column(String, nullable=True)
    fono_fijo = Column(String, nullable=True)
    
    fecha_creacion = Column(DateTime, default=datetime.utcnow)


class Estudio(Base):
    __tablename__ = "estudios"

    id = Column(Integer, primary_key=True)
    paciente_rut = Column(String, ForeignKey("pacientes.rut"), nullable=False)
    fecha_estudio = Column(Date, nullable=False)
    tipo_estudio = Column(String, default="Ecocardiograma")
    medico = Column(String)
    motivo = Column(String)
    observaciones = Column(Text)
    dicom_study_uid = Column(String, unique=True, nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    estado = Column(String, default="Validado")

    # --- NUEVOS CAMPOS GENERALES DEL ECOCARDIOGRAMA ---
    diagnostico = Column(String, nullable=True)
    procedencia = Column(String, nullable=True)
    ficha_clinica = Column(String, nullable=True)
    peso = Column(Float, nullable=True)
    talla = Column(Float, nullable=True)
    asc_valor = Column(Float, nullable=True)
    pas = Column(Integer, nullable=True)
    pad = Column(Integer, nullable=True)
    ritmo = Column(String, nullable=True)
    fcia = Column(Integer, nullable=True)

    mediciones = relationship("Medicion", back_populates="estudio")


class Variable(Base):
    __tablename__ = "variables"

    id = Column(Integer, primary_key=True)
    codigo = Column(String)
    categoria = Column(String)
    nombre = Column(String)
    descripcion = Column(String)
    unidad = Column(String)
    tipo = Column(String)
    opciones = Column(String)
    rangos_normales = Column(String)
    metodo = Column(String)
    derivada_de = Column(String)
    obligatoria = Column(String)
    grupo_analitico = Column(String)


class Medicion(Base):
    __tablename__ = "mediciones"

    id = Column(Integer, primary_key=True)
    estudio_id = Column(Integer, ForeignKey("estudios.id"))
    variable_id = Column(Integer, ForeignKey("variables.id"))
    codigo_variable = Column(String, nullable=False, index=True)
    valor_num = Column(Float)
    valor_texto = Column(String)

    variable = relationship("Variable")
    estudio = relationship("Estudio", back_populates="mediciones")