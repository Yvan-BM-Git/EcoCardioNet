# # Archivo: migrar_orden_variables.py
# # Ejecutar UNA sola vez para:

# migrar_columnas_pdf.py
from sqlalchemy import text
from database.database import engine

with engine.connect() as conn:
    conn.execute(text("ALTER TABLE estudios ADD COLUMN IF NOT EXISTS pdf_original BYTEA"))
    conn.execute(text("ALTER TABLE estudios ADD COLUMN IF NOT EXISTS pdf_nombre_archivo VARCHAR"))
    conn.commit()

print("Columnas 'pdf_original' y 'pdf_nombre_archivo' agregadas correctamente.")



# migrar_columna_imc.py
# from sqlalchemy import text
# from database.database import engine

# with engine.connect() as conn:
#     conn.execute(text("ALTER TABLE estudios ADD COLUMN IF NOT EXISTS imc FLOAT"))
#     conn.commit()

# print("Columna 'imc' agregada correctamente a la tabla 'estudios'.")

# # 1. Agregar la columna 'orden' a la tabla de variables (si no existe)
# # 2. Cargar los valores de orden desde el Excel actualizado (variables_ecocardio_con_orden.xlsx)



# import pandas as pd
# from sqlalchemy import text
# from database.database import SessionLocal, engine
# from database.models import Variable

# # --- 1. Agregar la columna si no existe (seguro re-ejecutar, no falla si ya existe) ---
# with engine.connect() as conn:
#     conn.execute(text("ALTER TABLE variables ADD COLUMN IF NOT EXISTS orden INTEGER"))
#     conn.commit()

# print("✅ Columna 'orden' verificada/creada.")

# # --- 2. Cargar los valores desde el Excel ---
# df = pd.read_excel("variables_ecocardio.xlsx")  # ajusta la ruta si es necesario

# session = SessionLocal()
# try:
#     actualizadas = 0
#     for _, fila in df.iterrows():
#         var = session.query(Variable).filter(Variable.codigo == fila["Codigo"]).first()
#         if var:
#             var.orden = int(fila["Orden"])
#             actualizadas += 1
#     session.commit()
#     print(f"✅ Se actualizó el campo 'orden' en {actualizadas} variables.")
# except Exception as e:
#     session.rollback()
#     print(f"❌ Error actualizando: {e}")
# finally:
#     session.close()