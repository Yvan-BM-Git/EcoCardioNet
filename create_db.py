# create_db.py
"""
Inicializa la base de datos: tablas, roles, administrador y catálogo de
variables (desde variables_ecocardio.xlsx).

Uso:
    python create_db.py

La contraseña del administrador NO está en el código. Se toma de la
variable de entorno ECOCARDIONET_ADMIN_PASSWORD o se pide por consola.
"""
import os
import sys
from getpass import getpass
from pathlib import Path

import pandas as pd
from werkzeug.security import generate_password_hash

from database.database import SessionLocal, init_db
from database.models import Rol, Usuario, Variable

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

# El login formatea el RUT con puntos y guion (12.345.678-9).
ADMIN_RUT = "11.111.111-1"
ADMIN_RUT_ANTIGUO = "11111111-1"   # formato usado por versiones anteriores
LARGO_MINIMO_CLAVE = 8


def pedir_clave_admin():
    clave = os.environ.get("ECOCARDIONET_ADMIN_PASSWORD")
    if clave:
        if len(clave) < LARGO_MINIMO_CLAVE:
            sys.exit(f"ECOCARDIONET_ADMIN_PASSWORD debe tener al menos {LARGO_MINIMO_CLAVE} caracteres.")
        return clave
    while True:
        clave = getpass(f"Contraseña para el administrador ({ADMIN_RUT}): ")
        if len(clave) < LARGO_MINIMO_CLAVE:
            print(f"  La contraseña debe tener al menos {LARGO_MINIMO_CLAVE} caracteres.")
            continue
        if getpass("Repita la contraseña: ") != clave:
            print("  Las contraseñas no coinciden.")
            continue
        return clave


def es_hash_antiguo(password_hash):
    """Hash de security.py (salt$sha256): incompatible con el login (werkzeug)."""
    return bool(password_hash) and password_hash.count("$") == 1


# ==================================================
# CREAR TABLAS, MIGRAR COLUMNAS Y ROLES
# ==================================================

print("\nCreando tablas y roles...")
init_db()
print("✓ Tablas y roles listos")

session = SessionLocal()

# ==================================================
# ADMINISTRADOR
# ==================================================

print("\nVerificando administrador...")

admin = (
    session.query(Usuario)
    .filter(Usuario.rut.in_([ADMIN_RUT, ADMIN_RUT_ANTIGUO]))
    .first()
)

if not admin:
    rol_admin = session.query(Rol).filter(Rol.nombre == "Administrador").first()
    session.add(
        Usuario(
            rut=ADMIN_RUT,
            nombre="Administrador",
            email="admin@ecocardionet.cl",
            password_hash=generate_password_hash(pedir_clave_admin()),
            rol_id=rol_admin.id,
        )
    )
    session.commit()
    print(f"✓ Administrador creado (RUT {ADMIN_RUT})")

elif es_hash_antiguo(admin.password_hash) or admin.rut == ADMIN_RUT_ANTIGUO:
    # El administrador creado por versiones anteriores no podía iniciar
    # sesión: hash incompatible y RUT sin puntos.
    print("! El administrador existente usa un formato antiguo; se actualizará.")
    admin.rut = ADMIN_RUT
    if es_hash_antiguo(admin.password_hash):
        admin.password_hash = generate_password_hash(pedir_clave_admin())
    session.commit()
    print(f"✓ Administrador actualizado (RUT {ADMIN_RUT})")

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

def leer_limite(row, columna, codigo):
    """Lee ValorMinimo/ValorMaximo; acepta coma o punto decimal."""
    if columna not in row.index or pd.isna(row[columna]):
        return None
    texto = str(row[columna]).strip().replace(",", ".")
    if texto == "":
        return None
    try:
        return float(texto)
    except ValueError:
        raise Exception(
            f"{columna} no numérico en la variable {codigo}: {row[columna]!r}"
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

    # Límites de plausibilidad (opcionales; vacíos = sin límite)
    orden = (
        int(row["Orden"])
        if "Orden" in row.index and pd.notna(row["Orden"])
        else None
    )

    valor_minimo = leer_limite(row, "ValorMinimo", codigo)
    valor_maximo = leer_limite(row, "ValorMaximo", codigo)
    if (
        valor_minimo is not None
        and valor_maximo is not None
        and valor_minimo > valor_maximo
    ):
        raise Exception(
            f"ValorMinimo > ValorMaximo en la variable {codigo}"
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
        existe.orden = orden
        existe.valor_minimo = valor_minimo
        existe.valor_maximo = valor_maximo

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

        grupo_analitico=grupo_analitico,
        orden=orden,
        valor_minimo=valor_minimo,
        valor_maximo=valor_maximo
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