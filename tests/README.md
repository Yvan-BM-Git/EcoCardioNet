# Pruebas de EcoCardioNet

Pruebas automáticas de todas las funciones de la app. **No tocan la base de
producción (Neon):** `conftest.py` crea en cada ejecución una base SQLite
temporal con `create_db.py` (tablas, roles, administrador y variables del Excel)
y la app la usa a través de la variable `ECOCARDIONET_DATABASE_URL`.

## Cómo ejecutarlas

Desde la carpeta del proyecto, con el entorno virtual activo:

```bash
pip install -r requirements-dev.txt
python -m pytest                       # todas (≈2 min)
python -m pytest -m "not lento"        # rápidas (≈1 min): sin casos publicados ni navegador
python -m pytest --cov=utils --cov=database --cov-report=term-missing   # con cobertura
python -m pytest tests/test_motor_informe.py -k fevi                     # un tema puntual
```

Las pruebas de navegador (`test_navegador.py`) se omiten solas si no está
Playwright. Para incluirlas: `pip install playwright && python -m playwright install chromium`.

## Qué cubre cada archivo

| Archivo | Qué prueba |
|---|---|
| `test_validacion.py` | Campos numéricos: coma→punto, negativos solo en strain, máximo 2 decimales, enteros, avisos de rango. |
| `test_utilidades.py` | Formato de RUT y teléfono, formulario de login, catálogos cacheados, textos legales y registro de aceptación por versión. |
| `test_importar_pdf.py` | Lectura de informes PDF: alias de variables, nombres, RUT, peso/talla, médico y extracción de texto. |
| `test_indicadores_exportacion.py` | Indicadores del inicio (períodos, comparación, tendencia) y exportación anonimizada (Ley 21.719). |
| `test_motor_informe.py` | Motor del informe: 28 casos límite y las 7 decisiones clínicas basadas en guías ASE. |
| `test_valvulopatias_pdf.py` | Graduación de valvulopatías y prótesis, discordancias y generación del PDF (igual a pantalla). |
| `test_ramas_clinicas.py` | Aurícula izquierda, presión de llenado en FA, válvulas derechas, imágenes del PDF. |
| `test_base_de_datos.py` | `create_db.py`, migraciones de columnas, error de conexión y menú/cierre de sesión. |
| `test_paginas.py` | Login, aceptación de Términos, permisos por rol, Nuevo Estudio, Historial, Exportar y Usuarios. |
| `test_casos_publicados.py` | 7 casos clínicos publicados de punta a punta (`lento`). |
| `test_navegador.py` | JavaScript en Chrome real: login para gestores de claves y bloqueo de texto en campos numéricos (`lento`). |

## Agregar pruebas

- Funciones puras: importar el módulo y probarlo directamente.
- Páginas: `abrir_pagina("pages/x.py", rol="Cardiólogo")` o `abrir_estudio(rut)` de `conftest.py`.
- Un caso clínico nuevo: agregarlo a `datos/casos_publicados.py`; la prueba lo toma sola.
