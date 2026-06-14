# 🫀 EcoCardioNet

**EcoCardioNet** es un sistema integral para el registro, análisis y seguimiento ecocardiográfico. Diseñado para optimizar el flujo de trabajo clínico, permite documentar exámenes médicos, gestionar datos de pacientes, calcular variables en tiempo real, analizar tendencias clínicas y generar reportes históricos automatizados en formato PDF de manera ágil, centralizada y segura.

Actualmente, el sistema está completamente preparado para producción, utilizando una arquitectura moderna con persistencia en la nube.

---

## 🚀 Accesos Rápidos

### 👤 Gestionar Pacientes
Agrega nuevos pacientes al sistema o actualiza sus antecedentes demográficos para comenzar a vincular sus respectivos estudios ecocardiográficos.

**Acceso en la App:** *Ir a Pacientes* (`pages/pacientes.py`)

### 🩺 Registrar un Examen
Ingresa los datos clínicos detallados, antecedentes de interés y documenta las mediciones del ecocardiograma del paciente de manera estructurada.

**Acceso en la App:** *Ir a Nuevo Estudio* (`pages/estudios.py`)

### 📁 Ver Historial Clínico
Busca pacientes existentes a través de filtros inteligentes, analiza la evolución longitudinal de sus métricas a lo largo del tiempo y revisa exámenes anteriores.

**Acceso en la App:** *Ir a Historial* (`pages/historial.py`)

### 📤 Exportar Reportes y Datos
Módulo especializado para la generación formal de informes clínicos en formato PDF listos para distribución y la exportación de registros consolidados.

**Acceso en la App:** *Ir a Exportar* (`pages/exportar.py`)

---

## 🛠️ Características Principales

- **Persistencia Confiable en la Nube:** Migrado a PostgreSQL para garantizar la permanencia de los datos en entornos de despliegue como Streamlit Community Cloud.
- **Autenticación Avanzada y Segura:** Pantallas de Inicio de Sesión y Auto-recuperación de contraseñas con encriptación robusta (`Werkzeug`).
- **Formateo Dinámico de RUT en Vivo:** Normalización y autocompletado automático de puntos y guión en tiempo real mediante callbacks de Streamlit.
- **Gestión In-App de Pacientes:** Registro e inserción inteligente de pacientes mediante formularios y ventanas modales sin interrumpir el flujo de trabajo.
- **Registro Estructurado de Estudios:** Almacenamiento organizado de mediciones ecocardiográficas y antecedentes clínicos.
- **Historial Clínico Integrado:** Visualización cronológica de estudios previos y seguimiento de la evolución del paciente.
- **Reportes Profesionales en PDF:** Generación automática de informes clínicos listos para impresión o distribución digital.
- **Inicialización Automática:** El sistema crea de forma autónoma las tablas y los roles esenciales (`Administrador`, `Cardiólogo`, `Investigador`) en la base de datos durante su primer arranque.

---

## 📦 Tecnologías Utilizadas

- **Frontend / Interfaz:** Streamlit
- **Procesamiento de Datos:** Pandas
- **Base de Datos / ORM:** SQLAlchemy & PostgreSQL (Alojado en Neon.tech)
- **Conector de Base de Datos:** Psycopg2-binary
- **Generación de Documentos:** ReportLab
- **Lenguaje:** Python 3.10+

---

## 🔧 Instalación y Configuración

### 1. Clonar el repositorio

```bash
git clone [https://github.com/Yvan-BM-Git/EcoCardioNet.git](https://github.com/Yvan-BM-Git/EcoCardioNet.git)
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

Crea una carpeta llamada `.streamlit` en la raíz del proyecto y, dentro de ella, un archivo llamado `secrets.toml`:

```toml
# .streamlit/secrets.toml
DATABASE_URL = "postgresql://usuario:contraseña@servidor-en-la-nube.com/neondb?sslmode=require"
```

> ⚠️ **Nota:** Asegúrate de que el archivo `.streamlit/secrets.toml` se encuentre incluido en tu `.gitignore`. Si despliegas en **Streamlit Community Cloud**, deberás configurar esta misma variable en la sección *Advanced Settings -> Secrets* de tu panel de control.

### 5. Ejecutar la aplicación

Al iniciar la aplicación por primera vez, SQLAlchemy detectará la base de datos en la nube y creará automáticamente toda la estructura de tablas y roles necesarios. No requiere scripts de inicialización externos.

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
├── menu.py
├── requirements.txt
├── security.py
├── variables_ecocardio.xlsx
│
├── assets/
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

### Descripción de los Componentes

| Archivo / Carpeta | Descripción |
| --- | --- |
| `app.py` | Punto de entrada principal, manejo de sesión, login con formateo de RUT y panel de control. |
| `menu.py` | Generador dinámico del menú de navegación lateral. |
| `database/database.py` | Conexión a PostgreSQL en la nube y rutina de inicialización de tablas/roles. |
| `database/models.py` | Definición de los modelos y entidades ORM mediante SQLAlchemy. |
| `pages/estudios.py` | Registro, edición y documentación de mediciones ecocardiográficas. |
| `pages/historial.py` | Consulta, filtros inteligentes y seguimiento longitudinal de pacientes. |
| `pages/pacientes.py` | Gestión y registro demográfico de pacientes. |
| `pages/usuarios.py` | Administración avanzada de cuentas de usuarios y roles del sistema. |
| `pages/exportar.py` | Módulo encargado de estructurar y exportar reportes clínicos en PDF. |
| `variables_ecocardio.xlsx` | Plantilla base con los rangos y variables ecocardiográficas de la aplicación. |

---

## 🗄️ Base de Datos

EcoCardioNet utiliza un motor **PostgreSQL** (alojado de forma gratuita en la región de baja latencia de São Paulo a través de **Neon.tech**) para asegurar la persistencia a largo plazo de:

* Información demográfica de pacientes.
* Estudios ecocardiográficos completos.
* Historial clínico longitudinal.
* Credenciales encriptadas de usuarios y asignación de roles.

La base de datos se autogestiona en su primer inicio a través del ORM de SQLAlchemy definido en `database/database.py`.

---

## 📄 Generación de Reportes

El sistema permite generar informes clínicos profesionales en formato PDF listos para impresión o distribución digital mediante la biblioteca **ReportLab**, incluyendo:

* Identificación completa del paciente.
* Datos y antecedentes clínicos relevantes.
* Mediciones ecocardiográficas estructuradas.
* Conclusiones e interpretación médica.
* Firma digitalizada y credenciales del profesional responsable.

---

## 🔒 Seguridad

EcoCardioNet incorpora altos estándares de seguridad para el manejo de datos de salud:

* **Aislamiento de Credenciales:** Uso estricto de `st.secrets` para evitar la exposición de credenciales de bases de datos en repositorios públicos.
* **Cifrado de Contraseñas:** Encriptación de contraseñas en tránsito y almacenamiento mediante hashes seguros con `Werkzeug`.
* **Control de Acceso (RBAC):** Restricción de vistas y operaciones basada en roles preestablecidos (*Administrador*, *Cardiólogo*, *Investigador*).

---

## 👨‍⚕️ Uso Previsto

EcoCardioNet está orientado a:

* Cardiólogos clínicos.
* Ecocardiografistas y tecnólogos médicos.
* Centros médicos de especialidad y hospitales.
* Instituciones académicas vinculadas a la formación en cardiología.

---

## 🚧 Estado del Proyecto

Proyecto en desarrollo activo.

Las funcionalidades y la estructura interna pueden evolucionar conforme se incorporen nuevas herramientas de análisis estadístico, visualizaciones de tendencias y gestión avanzada de fichas clínicas.

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