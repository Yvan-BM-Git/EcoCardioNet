# 🫀 EcoCardioNet

**EcoCardioNet** es un sistema integral para el registro, análisis y seguimiento ecocardiográfico. Diseñado para optimizar el flujo de trabajo clínico, permite documentar exámenes médicos, gestionar datos de pacientes, calcular variables en tiempo real, analizar tendencias clínicas y generar reportes históricos automatizados en formato PDF de manera ágil, centralizada y segura.

---

## 🚀 Accesos Rápidos

### 📝 Registrar un Examen
Ingresa los datos de un nuevo paciente de forma dinámica o búscalo directamente en la base de datos para documentar su ecocardiograma de manera estructurada.

**Acceso:** *Ir a Nuevo Estudio*

### 📊 Ver Historial Clínico
Busca pacientes existentes a través de filtros inteligentes (RUT, Nombre o Apellido), analiza la evolución de sus métricas a lo largo del tiempo y descarga PDFs históricos firmados.

**Acceso:** *Ir a Historial*

### ⚙️ Configuración
Panel de administración avanzada para gestionar los rangos de las variables ecocardiográficas, credenciales de médicos de la institución y el estado de la base de datos.

**Acceso:** *Ir a Configuración*

---

## 🛠️ Características Principales

- **Gestión In-App de Pacientes:** Registro e inserción inteligente de pacientes mediante formularios y ventanas modales sin interrumpir el flujo de trabajo.
- **Formateo Dinámico de Datos:** Normalización automática de RUT y números telefónicos durante el ingreso de información.
- **Registro Estructurado de Estudios:** Almacenamiento organizado de mediciones ecocardiográficas y antecedentes clínicos.
- **Historial Clínico Integrado:** Visualización cronológica de estudios previos y seguimiento de la evolución del paciente.
- **Reportes Profesionales en PDF:** Generación automática de informes clínicos listos para impresión o distribución digital.
- **Arquitectura Robusta:** Persistencia de datos mediante SQLAlchemy con una estructura preparada para múltiples motores de bases de datos.
- **Interfaz Web Intuitiva:** Implementada con Streamlit para facilitar el uso clínico diario.

---

## 📦 Tecnologías Utilizadas

- **Frontend / Interfaz:** Streamlit
- **Procesamiento de Datos:** Pandas
- **Base de Datos / ORM:** SQLAlchemy
- **Generación de Documentos:** ReportLab
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

### 4. Crear la base de datos

La base de datos SQLite no se distribuye a través del repositorio. Para crear automáticamente la estructura inicial de la aplicación, ejecute:

```bash
python create_db.py
```

Este comando generará el archivo:

```text
data/ecocardionet.db
```

### 5. Ejecutar la aplicación

```bash
streamlit run app.py
```

La aplicación estará disponible en:

```text
http://localhost:8501
```

---

## 📁 Estructura del Proyecto

```text
EcoCardioNet/
├── app.py
├── create_db.py
├── requirements.txt
├── security.py
├── variables_ecocardio.xlsx
│
├── assets/
│
├── data/
│   └── ecocardionet.db
│
├── database/
│   ├── database.py
│   └── models.py
│
├── pages/
│   ├── estudios.py
│   ├── exportar.py
│   ├── historial.py
│   ├── login.py
│   ├── pacientes.py
│   └── usuarios.py
│
└── README.md
```

### Descripción de los Componentes

| Archivo / Carpeta | Descripción |
|-------------------|-------------|
| `app.py` | Punto de entrada principal de la aplicación Streamlit. |
| `create_db.py` | Inicializa la base de datos y crea las tablas necesarias. |
| `database/database.py` | Configuración de conexión a la base de datos. |
| `database/models.py` | Definición de los modelos ORM mediante SQLAlchemy. |
| `pages/estudios.py` | Registro y edición de estudios ecocardiográficos. |
| `pages/historial.py` | Consulta y seguimiento histórico de pacientes. |
| `pages/pacientes.py` | Gestión de pacientes. |
| `pages/usuarios.py` | Administración de usuarios. |
| `pages/login.py` | Sistema de autenticación. |
| `pages/exportar.py` | Generación y exportación de informes PDF. |
| `variables_ecocardio.xlsx` | Plantilla de variables ecocardiográficas utilizadas por la aplicación. |
| `data/ecocardionet.db` | Base de datos SQLite generada localmente. |

---

## 🗄️ Base de Datos

EcoCardioNet utiliza una base de datos SQLite para almacenar:

- Información demográfica de pacientes.
- Estudios ecocardiográficos.
- Historial clínico.
- Configuración de usuarios.
- Parámetros y variables ecocardiográficas.

La base de datos se genera automáticamente mediante:

```bash
python create_db.py
```

Por razones de portabilidad y seguridad, el archivo `ecocardionet.db` no forma parte del repositorio Git y debe ser generado localmente por cada instalación.

---

## 📄 Generación de Reportes

El sistema permite generar informes clínicos en formato PDF que incluyen:

- Identificación del paciente.
- Datos clínicos relevantes.
- Mediciones ecocardiográficas.
- Interpretación médica.
- Firma y credenciales profesionales.

Los documentos son generados utilizando la biblioteca **ReportLab**.

---

## 🔒 Seguridad

EcoCardioNet incorpora:

- Autenticación de usuarios.
- Gestión de credenciales.
- Persistencia segura de datos clínicos.
- Separación entre lógica de aplicación y almacenamiento.

Se recomienda complementar la instalación con mecanismos institucionales de respaldo y control de acceso cuando se utilice en entornos clínicos reales.

---

## 👨‍⚕️ Uso Previsto

EcoCardioNet está orientado a:

- Cardiólogos.
- Ecocardiografistas.
- Centros médicos.
- Hospitales.
- Instituciones académicas vinculadas a la formación en ciencias de la salud.

Su objetivo es facilitar la gestión, documentación y análisis longitudinal de estudios ecocardiográficos.

---

## 🚧 Estado del Proyecto

Proyecto en desarrollo activo.

Las funcionalidades y la estructura interna pueden evolucionar conforme se incorporen nuevas herramientas de análisis, visualización y gestión clínica.

---

## 🤝 Contribuciones

Las contribuciones son bienvenidas.

Para colaborar:

1. Realice un fork del repositorio.
2. Cree una rama para su funcionalidad.
3. Realice los cambios correspondientes.
4. Envíe un Pull Request para revisión.

---

## 📄 Licencia

Este proyecto se distribuye con fines académicos, de investigación y apoyo a la práctica clínica.

Consulte el repositorio para futuras actualizaciones relacionadas con la licencia de distribución.