from pathlib import Path

import pandas as pd

from database.database import (
    engine,
    SessionLocal
)

from database.models import (
    Base,
    Rol,
    Usuario,
    Variable
)

from security import hash_password

# ==================================================
# CONFIGURACIÓN
# ==================================================

TIPOS_VALIDOS = {
    "numero",
    "categoria",
    "texto",
    "booleano"
}

OBLIGATORIOS_VALIDOS = {
    "SI",
    "NO"
}

# ==================================================
# CREAR TABLAS
# ==================================================

Base.metadata.create_all(bind=engine)

session = SessionLocal()

# ==================================================
# ROLES
# ==================================================

print("\nCreando roles...")

roles = [
    "Administrador",
    "Cardiólogo",
    "Investigador"
]

for nombre in roles:

    existe = (
        session.query(Rol)
        .filter(
            Rol.nombre == nombre
        )
        .first()
    )

    if not existe:

        session.add(
            Rol(
                nombre=nombre
            )
        )

session.commit()

print("✓ Roles creados")

# ==================================================
# ADMINISTRADOR
# ==================================================

print("\nVerificando administrador...")

admin = (
    session.query(Usuario)
    .filter(
        Usuario.rut == "11111111-1"
    )
    .first()
)

if not admin:

    rol_admin = (
        session.query(Rol)
        .filter(
            Rol.nombre == "Administrador"
        )
        .first()
    )

    nuevo_admin = Usuario(
        rut="11111111-1",
        nombre="Administrador",
        email="admin@ecocardionet.cl",
        password_hash=hash_password("admin123"),
        rol_id=rol_admin.id
    )

    session.add(
        nuevo_admin
    )

    session.commit()

    print("✓ Administrador creado")

else:

    print("✓ Administrador ya existe")

# ==================================================
# VARIABLES ECOCARDIOGRÁFICAS
# ==================================================

print("\nCargando variables...")

archivo_excel = (
    Path(__file__).parent
    /
    "variables_ecocardio.xlsx"
)

if not archivo_excel.exists():

    raise FileNotFoundError(
        f"No se encontró:\n{archivo_excel}"
    )

df = pd.read_excel(
    archivo_excel
)

columnas_requeridas = [

    "Codigo",

    "Categoria",

    "Variable",

    "Descripcion",

    "Unidad",

    "Tipo",

    "Opciones",

    "RangosNormales",

    "Metodo",

    "DerivadaDe",

    "Obligatoria",

    "GrupoAnalitico"
]

faltantes = [

    c

    for c in columnas_requeridas

    if c not in df.columns
]

if len(faltantes) > 0:

    raise Exception(
        f"Faltan columnas: {faltantes}"
    )

# ==================================================
# VALIDAR DUPLICADOS
# ==================================================

duplicados = df[
    df["Codigo"]
    .astype(str)
    .duplicated()
]

if len(duplicados) > 0:

    raise Exception(
        f"""
Códigos duplicados encontrados:

{duplicados['Codigo'].tolist()}
"""
    )

# ==================================================
# CARGA VARIABLES
# ==================================================

nuevas = 0
actualizadas = 0

for _, row in df.iterrows():

    codigo = (
        str(row["Codigo"]).strip()
        if pd.notna(row["Codigo"])
        else ""
    )

    nombre = (
        str(row["Variable"]).strip()
        if pd.notna(row["Variable"])
        else ""
    )

    if codigo == "":

        raise Exception(
            f"Variable sin código: {nombre}"
        )

    categoria = (
        str(row["Categoria"]).strip()
        if pd.notna(row["Categoria"])
        else ""
    )

    descripcion = (
        str(row["Descripcion"]).strip()
        if pd.notna(row["Descripcion"])
        else ""
    )

    unidad = (
        str(row["Unidad"]).strip()
        if pd.notna(row["Unidad"])
        else ""
    )

    tipo = (
        str(row["Tipo"]).strip()
        if pd.notna(row["Tipo"])
        else "texto"
    )

    opciones = (
        str(row["Opciones"]).strip()
        if pd.notna(row["Opciones"])
        else ""
    )

    rangos_normales = (
        str(row["RangosNormales"]).strip()
        if pd.notna(row["RangosNormales"])
        else ""
    )

    metodo = (
        str(row["Metodo"]).strip()
        if pd.notna(row["Metodo"])
        else ""
    )

    derivada_de = (
        str(row["DerivadaDe"]).strip()
        if pd.notna(row["DerivadaDe"])
        else ""
    )

    obligatoria = (
        str(row["Obligatoria"]).strip()
        if pd.notna(row["Obligatoria"])
        else "NO"
    )

    grupo_analitico = (
        str(row["GrupoAnalitico"]).strip()
        if pd.notna(row["GrupoAnalitico"])
        else ""
    )

    # --------------------------------------
    # VALIDAR TIPO
    # --------------------------------------

    if tipo not in TIPOS_VALIDOS:

        raise Exception(
            f"""
Tipo inválido:

Código: {codigo}
Variable: {nombre}
Tipo: {tipo}
"""
        )

    # --------------------------------------
    # VALIDAR OBLIGATORIA
    # --------------------------------------

    if obligatoria not in OBLIGATORIOS_VALIDOS:

        obligatoria = "NO"

    existe = (
        session.query(Variable)
        .filter(
            Variable.codigo == codigo
        )
        .first()
    )

    # --------------------------------------
    # ACTUALIZAR
    # --------------------------------------

    if existe:

        existe.categoria = categoria
        existe.nombre = nombre
        existe.descripcion = descripcion
        existe.unidad = unidad
        existe.tipo = tipo
        existe.opciones = opciones
        existe.rangos_normales = rangos_normales
        existe.metodo = metodo
        existe.derivada_de = derivada_de
        existe.obligatoria = obligatoria
        existe.grupo_analitico = grupo_analitico

        actualizadas += 1

        continue

    # --------------------------------------
    # NUEVA VARIABLE
    # --------------------------------------

    variable = Variable(

        codigo=codigo,

        categoria=categoria,

        nombre=nombre,

        descripcion=descripcion,

        unidad=unidad,

        tipo=tipo,

        opciones=opciones,

        rangos_normales=rangos_normales,

        metodo=metodo,

        derivada_de=derivada_de,

        obligatoria=obligatoria,

        grupo_analitico=grupo_analitico
    )

    session.add(
        variable
    )

    nuevas += 1

# ==================================================
# GUARDAR
# ==================================================

session.commit()

total = (
    session.query(Variable)
    .count()
)

print("\nResumen")

print(
    f"✓ Variables nuevas: {nuevas}"
)

print(
    f"✓ Variables actualizadas: {actualizadas}"
)

print(
    f"✓ Total variables: {total}"
)

# ==================================================
# CERRAR
# ==================================================

session.close()

print(
    "\n✓ EcoCardioNet inicializado correctamente"
)