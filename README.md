# 🫀 EcoCardioNet

**EcoCardioNet** es un sistema integral para el registro, análisis y seguimiento ecocardiográfico. Diseñado para optimizar el flujo de trabajo clínico, permite documentar exámenes médicos, gestionar datos de pacientes, capturar mediciones estructuradas contra un catálogo dinámico de variables, importar informes PDF ya existentes, analizar tendencias clínicas —individuales y globales— y generar reportes profesionales en PDF de manera ágil, centralizada y segura.

Actualmente, el sistema está completamente preparado para producción, utilizando una arquitectura moderna con persistencia en la nube.

---

## 🚀 Accesos Rápidos

### 👤 Gestionar Pacientes
Agrega nuevos pacientes al sistema o actualiza sus antecedentes demográficos (incluida previsión y teléfono fijo) para comenzar a vincular sus respectivos estudios ecocardiográficos.

**Acceso en la App:** *Ir a Pacientes* (`pages/pacientes.py`)

### 🩺 Registrar un Examen
Ingresa los datos clínicos detallados, antecedentes de interés y documenta las mediciones del ecocardiograma mediante un formulario dinámico generado a partir del catálogo de variables. Permite generar e imprimir el informe en PDF al finalizar.

**Acceso en la App:** *Ir a Nuevo Estudio* (`pages/estudios.py`)

### 📁 Ver Historial Clínico
Busca pacientes existentes a través de filtros inteligentes, **importa informes PDF previos** (extracción automática de datos del paciente y mediciones), analiza la evolución longitudinal de sus métricas con gráficos interactivos y revisa exámenes anteriores.

**Acceso en la App:** *Ir a Historial* (`pages/historial.py`)

### 📤 Exportar Datos de Investigación
Genera una matriz de datos estructurada (una fila por estudio, una columna por variable) lista para análisis estadístico, descargable en CSV o Excel. Incluye eliminación segura de estudios para administradores.

**Acceso en la App:** *Ir a Exportar* (`pages/exportar.py`)

### 👥 Gestión de Usuarios
Administración de cuentas y roles del sistema, disponible exclusivamente para el rol **Administrador**.

**Acceso en la App:** *Ir a Usuarios* (`pages/usuarios.py`)

---

## 🛠️ Características Principales

- **Persistencia Confiable en la Nube:** PostgreSQL para garantizar la permanencia de los datos en entornos de despliegue como Streamlit Community Cloud.
- **Autenticación Avanzada y Segura:** Pantallas de Inicio de Sesión y Auto-recuperación de contraseñas con encriptación robusta (`Werkzeug`), más soporte para gestores de contraseñas del navegador.
- **Formateo Dinámico de RUT en Vivo:** Normalización y autocompletado automático de puntos y guión en tiempo real mediante callbacks de Streamlit.
- **Catálogo Dinámico de Variables Ecocardiográficas:** Las variables clínicas (numéricas, categóricas, booleanas o de texto), sus rangos normales, unidades y agrupación analítica se definen centralizadamente en `variables_ecocardio.xlsx` y se cargan a la base de datos, generando automáticamente los formularios de captura por categoría/subsección.
- **Registro Estructurado de Estudios:** Cada medición se guarda de forma normalizada (tabla `Medicion`, vinculada a `Estudio` y `Variable`), evitando pérdida de datos entre variables con nombres repetidos.
- **Importación Inteligente de Informes PDF:** Extracción automática de datos generales del paciente y de mediciones desde informes ecocardiográficos en PDF ya existentes, para poblar el historial sin reingreso manual.
- **Historial Clínico Integrado con Tendencias Interactivas:** Visualización cronológica de estudios previos y gráficos de tendencia por variable (Plotly), incluyendo una vista de **tendencia global** de una variable entre todos los pacientes con línea de ajuste LOWESS.
- **Exportación para Investigación:** Generación de una matriz ancha (estudios × variables) descargable en CSV/Excel, con desambiguación automática de nombres de variables repetidos y cálculo de edad al momento del estudio.
- **Eliminación Segura de Estudios:** Los administradores pueden marcar y eliminar estudios (y sus mediciones asociadas) desde el módulo de exportación, con confirmación explícita.
- **Reportes Profesionales en PDF:** Generación de informes clínicos listos para impresión o distribución digital directamente desde el registro del estudio.
- **Gestión de Usuarios y Roles (RBAC):** Módulo exclusivo para Administradores, con creación de cuentas y asignación de roles.
- **Inicialización Automática de Esquema:** El sistema crea de forma autónoma las tablas en la base de datos durante su primer arranque mediante SQLAlchemy.
- **Script de Siembra Inicial (`create_db.py`):** Crea los roles esenciales (`Administrador`, `Cardiólogo`, `Investigador`), un usuario administrador por defecto y carga/actualiza el catálogo completo de variables desde `variables_ecocardio.xlsx`, validando columnas requeridas y códigos duplicados.

---

## 📦 Tecnologías Utilizadas

- **Frontend / Interfaz:** Streamlit
- **Procesamiento de Datos:** Pandas, NumPy
- **Visualización y Tendencias:** Plotly (incluye regresión LOWESS para tendencias globales)
- **Análisis Estadístico:** SciPy, statsmodels
- **Base de Datos / ORM:** SQLAlchemy & PostgreSQL (Alojado en Neon.tech)
- **Conector de Base de Datos:** Psycopg2-binary
- **Generación de Documentos PDF:** ReportLab
- **Lectura/Extracción de PDF:** pdfplumber, pdfminer.six, pypdfium2
- **Manejo de Excel:** openpyxl
- **Seguridad:** Werkzeug (hash de contraseñas)
- **Lenguaje:** Python 3.10+

---

## 🔧 Instalación y Configuración

### 1. Clonar el repositorio

```bash
git clone https://github.com/Yvan-BM-Git/EcoCardioNet.git
cd EcoCardioNet
```

### 2. Crear un entorno virtual

#### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

#### Windows (PowerShell)

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

### 3. Instalar las dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar las Variables de Entorno (Secrets)

Por motivos de seguridad, las credenciales de la base de datos no se suben al repositorio. Debes configurar la cadena de conexión utilizando el sistema de secretos de Streamlit.

Crea una carpeta llamada `.streamlit` en la raíz del proyecto (si no existe) y, dentro de ella, un archivo llamado `secrets.toml`:

```toml
# .streamlit/secrets.toml
DATABASE_URL = "postgresql://usuario:contraseña@servidor-en-la-nube.com/neondb?sslmode=require"
```

> ⚠️ **Nota:** Asegúrate de que el archivo `.streamlit/secrets.toml` se encuentre incluido en tu `.gitignore` (ya está excluido por defecto). Si despliegas en **Streamlit Community Cloud**, deberás configurar esta misma variable en la sección *Advanced Settings -> Secrets* de tu panel de control.

### 5. Inicializar roles, administrador y catálogo de variables

La primera vez que se conecta a la base de datos, SQLAlchemy crea automáticamente el esquema de tablas. Para poblar los **roles del sistema**, un **usuario administrador por defecto** y el **catálogo completo de variables ecocardiográficas** (desde `variables_ecocardio.xlsx`), ejecuta:

```bash
python create_db.py
```

Este script valida que el Excel contenga las columnas requeridas (`Codigo`, `Categoria`, `Variable`, `Descripcion`, `Unidad`, `Tipo`, `Opciones`, `RangosNormales`, `Metodo`, `DerivadaDe`, `Obligatoria`, `GrupoAnalitico`) y que no existan códigos de variable duplicados antes de cargarlos.

> 🔑 El administrador por defecto se crea con RUT `11111111-1`. Cambia su contraseña inmediatamente después del primer inicio de sesión, tanto en entornos locales como en producción.

### 6. Ejecutar la aplicación

```bash
streamlit run app.py
```

La aplicación estará disponible localmente en:

```text
http://localhost:8501
```

---

## 📁 Estructura del Proyecto

```text
EcoCardioNet/
├── app.py
├── create_db.py
├── menu.py
├── requirements.txt
├── security.py
├── variables_ecocardio.xlsx
│
├── .streamlit/
│   └── config.toml
│
├── database/
│   ├── database.py
│   └── models.py
│
├── pages/
│   ├── estudios.py
│   ├── exportar.py
│   ├── historial.py
│   ├── pacientes.py
│   └── usuarios.py
│
└── README.md
```

## 📊 Diagrama de Flujo de la Aplicación

El siguiente diagrama representa el flujo principal de navegación y procesos de EcoCardioNet, desde la autenticación hasta la generación de reportes y la exportación de datos.

```mermaid
flowchart TD
    A([Inicio]) --> B[Pantalla de Login]
    B --> C{¿Autenticación correcta?}
    C -->|No| D[Mostrar error y reintentar]
    D --> B
    C -->|Sí| E[Dashboard principal]

    E --> F[Menú de navegación]
    F --> G[Gestión de Pacientes]
    F --> H[Registro de Estudios]
    F --> I[Historial Clínico]
    F --> J[Exportar Datos de Investigación]
    F --> M[Gestión de Usuarios]
    F --> K[Cerrar sesión]

    G --> G1[Lista de pacientes]
    G1 --> G2[Búsqueda/Filtro de pacientes]
    G2 --> G3[Seleccionar paciente]
    G3 --> G4[Ver/Editar datos del paciente]
    G4 --> G5{¿Guardar cambios?}
    G5 -->|Sí| G6[Actualizar BD]
    G5 -->|No| G1
    G6 --> G1

    H --> H1[Seleccionar paciente]
    H1 --> H2[Formulario dinámico según catálogo de Variables]
    H2 --> H3[Validar datos]
    H3 -->|Error| H4[Mostrar errores]
    H4 --> H2
    H3 -->|OK| H5[Guardar estudio y mediciones en BD]
    H5 --> H6[Generar PDF del informe]
    H6 --> H7[Ofrecer descarga]

    I --> I1[Ver estudios previos]
    I1 --> I2[Detalle de cada estudio]
    I2 --> I3{¿Importar PDF existente?}
    I3 -->|Sí| I4[Extraer datos y mediciones del PDF]
    I4 --> I5[Precargar/Guardar en BD]
    I3 -->|No| I6[Graficar tendencias por paciente]
    I1 --> I7[Tendencia global entre pacientes - LOWESS]

    J --> J1[Construir matriz estudios x variables]
    J1 --> J2[Descargar CSV / Excel]
    J1 --> J3{¿Rol Administrador?}
    J3 -->|Sí| J4[Seleccionar y eliminar estudios]
    J4 --> J5[Confirmar eliminación]
    J5 --> J1

    M --> M1{¿Rol Administrador?}
    M1 -->|No| M2[Acceso denegado]
    M1 -->|Sí| M3[Crear/editar usuarios y roles]

    K --> L([Fin de sesión])
```

---

### Descripción de los Componentes

| Archivo / Carpeta          | Descripción                                                                                                                                              |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app.py`                    | Punto de entrada principal, manejo de sesión, login con formateo de RUT, soporte para gestores de contraseñas y panel de control.                       |
| `create_db.py`               | Script de siembra inicial: crea roles y usuario administrador por defecto, y carga/actualiza el catálogo de variables desde `variables_ecocardio.xlsx`. |
| `menu.py`                    | Generador dinámico del menú de navegación lateral.                                                                                                       |
| `security.py`                | Utilidades de hash y verificación de contraseñas.                                                                                                        |
| `database/database.py`      | Conexión a PostgreSQL en la nube (pool de conexiones, reciclado y ping automático) e inicialización automática del esquema y roles base.                |
| `database/models.py`        | Modelos ORM: `Rol`, `Usuario`, `Paciente`, `Estudio`, `Variable` (catálogo de variables) y `Medicion` (mediciones estructuradas por estudio).           |
| `pages/estudios.py`         | Registro de estudios mediante formulario dinámico basado en el catálogo de variables; genera el informe PDF del estudio.                                |
| `pages/historial.py`        | Consulta, filtros inteligentes, **importación y extracción automática de datos desde PDFs**, y gráficos de tendencia individuales/globales con Plotly.  |
| `pages/pacientes.py`        | Gestión y registro demográfico de pacientes.                                                                                                              |
| `pages/usuarios.py`         | Administración de cuentas de usuarios y roles del sistema (solo Administrador).                                                                          |
| `pages/exportar.py`         | Exportación de la base de datos completa como matriz estudios × variables (CSV/Excel) para investigación, con eliminación segura de estudios.           |
| `variables_ecocardio.xlsx`  | Plantilla base con los códigos, categorías, rangos y tipos de las variables ecocardiográficas de la aplicación.                                          |
| `.streamlit/config.toml`    | Configuración de Streamlit (navegación de la barra lateral deshabilitada; se reemplaza por `menu.py`).                                                  |

---

## 🗄️ Base de Datos

EcoCardioNet utiliza un motor **PostgreSQL** (alojado de forma gratuita en la región de baja latencia de São Paulo a través de **Neon.tech**) para asegurar la persistencia a largo plazo de:

- Información demográfica de pacientes (incluye previsión y teléfono fijo).
- Estudios ecocardiográficos completos, con datos clínicos generales (diagnóstico, procedencia, ficha clínica, antropometría, signos vitales) y el PDF original importado, cuando corresponde.
- Catálogo de variables ecocardiográficas y sus mediciones estructuradas por estudio (tablas `Variable` y `Medicion`).
- Historial clínico longitudinal.
- Credenciales encriptadas de usuarios y asignación de roles.

La base de datos se autogestiona en su primer inicio a través del ORM de SQLAlchemy definido en `database/database.py`; la siembra de roles, administrador y catálogo de variables se completa ejecutando `create_db.py`.

---

## 📄 Informes y Análisis de Datos

- **Generación de Reportes PDF:** Desde el registro de un estudio (`pages/estudios.py`) se genera un informe clínico profesional con ReportLab, listo para impresión o distribución digital, incluyendo identificación del paciente, mediciones agrupadas por categoría, conclusiones y credenciales del profesional responsable.
- **Importación de Informes PDF Existentes:** Desde el historial clínico (`pages/historial.py`) es posible cargar un PDF de un informe previo; el sistema extrae automáticamente los datos generales del paciente y las mediciones reconocidas para agilizar la digitalización de registros antiguos.
- **Tendencias Clínicas Interactivas:** Gráficos de evolución por paciente y por variable, más una vista de tendencia global de una variable a través de todos los pacientes con línea de ajuste LOWESS (Plotly).
- **Exportación para Investigación:** Matriz de datos estudios × variables descargable en CSV o Excel desde `pages/exportar.py`, con nombres de columnas desambiguados automáticamente cuando dos variables comparten nombre visible.

---

## 🔒 Seguridad

EcoCardioNet incorpora altos estándares de seguridad para el manejo de datos de salud:

- **Aislamiento de Credenciales:** Uso estricto de `st.secrets` para evitar la exposición de credenciales de bases de datos en repositorios públicos.
- **Cifrado de Contraseñas:** Encriptación de contraseñas en tránsito y almacenamiento mediante hashes seguros con `Werkzeug`.
- **Control de Acceso (RBAC):** Restricción de vistas y operaciones basada en roles preestablecidos (*Administrador*, *Cardiólogo*, *Investigador*); páginas como Usuarios y la eliminación de estudios están restringidas exclusivamente al rol Administrador.
- **Credenciales por Defecto:** El usuario administrador creado por `create_db.py` debe tener su contraseña cambiada de inmediato en cualquier entorno más allá de pruebas locales.

---

## 👨‍⚕️ Uso Previsto

EcoCardioNet está orientado a:

- Cardiólogos clínicos.
- Ecocardiografistas y tecnólogos médicos.
- Centros médicos de especialidad y hospitales.
- Instituciones académicas vinculadas a la formación en cardiología.
- Investigadores que requieran datasets estructurados de estudios ecocardiográficos.

---

## 🚧 Estado del Proyecto

Proyecto en desarrollo activo.

Las funcionalidades y la estructura interna pueden seguir evolucionando conforme se incorporen nuevas herramientas de análisis estadístico, visualizaciones de tendencias y gestión avanzada de fichas clínicas.

---

## 🤝 Contribuciones

Las contribuciones son bienvenidas.

Para colaborar:

1. Realice un fork del repositorio.
2. Cree una rama para su funcionalidad (`git checkout -b feature/nueva-funcion`).
3. Realice los cambios correspondientes y haga un commit limpio.
4. Envíe un Pull Request para revisión.

---

## 📄 Licencia

Este proyecto se distribuye con fines académicos, de investigación y apoyo a la práctica clínica. Consulte el repositorio para futuras actualizaciones relacionadas con las licencias de uso institucional.