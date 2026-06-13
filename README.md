# 🫀 EcoCardioNet

**EcoCardioNet** es un sistema integral para el registro, análisis y seguimiento ecocardiográfico. Diseñado para optimizar el flujo de trabajo clínico, permite documentar exámenes médicos, gestionar datos de pacientes, calcular variables en tiempo real, analizar tendencias clínicas y generar reportes históricos automatizados en formato PDF de manera ágil, centralizada y segura.

---

## 🚀 Accesos Rápidos

### 📝 Registrar un Examen
Ingresa los datos de un nuevo paciente de forma dinámica o búscalo directamente en la base de datos para documentar su ecocardiograma de manera estructurada.
* *Acceso:* **Ir a Nuevo Estudio**

### 📊 Ver Historial Clínico
Busca pacientes existentes a través de filtros inteligentes (RUT, Nombre o Apellido), analiza la evolución de sus métricas a lo largo del tiempo y descarga PDFs históricos firmados.
* *Acceso:* **Ir a Historial**

### ⚙️ Configuración
Panel de administración avanzada para gestionar los rangos de las variables ecocardiográficas, credenciales de médicos de la institución y el estado de la base de datos.
* *Acceso:* **Ir a Configuración**

---

## 🛠️ Características Principales

- **Gestión In-App de Pacientes:** Formulario de registro e inserción inteligente *inline* y *modals* sin perder el progreso ni cambiar de pestaña.
- **Formateo Dinámico de Datos:** Normalización automática en tiempo real de RUT (formato chileno) y números telefónicos durante la escritura.
- **Reportes Profesionales (PDF):** Generación automática de informes clínicos listos para imprimir o enviar, maquetados con `ReportLab`.
- **Arquitectura Robusta:** Persistencia de datos gestionada eficientemente a través de `SQLAlchemy` con soporte para múltiples motores relacionales.

---

## 📦 Tecnologías Utilizadas

- **Frontend / Interfaz:** [Streamlit](https://streamlit.io/)
- **Procesamiento de Datos:** [Pandas](https://pandas.pydata.org/)
- **Base de Datos / ORM:** [SQLAlchemy](https://www.sqlalchemy.org/)
- **Generación de Documentos:** [ReportLab](https://www.reportlab.com/)
- **Lenguaje:** Python 3.10+

---

## 🔧 Instalación y Configuración

1. **Clonar el repositorio:**
   ```bash
   git clone [https://github.com/Yvan-BM-Git/EcoCardioNet.git](https://github.com/Yvan-BM-Git/EcoCardioNet.git)
   cd EcoCardioNet