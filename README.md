# 🏥 Sistema Agéntico de Orientación, Triaje y Gestión de Pacientes - Red "SaludConecta"

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangChain](https://img.shields.io/badge/LangChain-v0.2.6+-green.svg)](https://python.langchain.com/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-v0.5.3+-orange.svg)](https://www.trychroma.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-v1.35.0+-red.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🏛️ Identificación Institucional y Académica

* **Institución:** Duoc UC – Escuela de Informática y Telecomunicaciones
* **Asignatura:** ISY0101 – Ingeniería de Soluciones con Inteligencia Artificial
* **Evaluación:** Evaluación Parcial N°1 (EP1) – Encargo Escrito y Repositorio Digital (Ponderación 30%)
* **Estudiante:** Matias Alejandro Araos Urra
* **Resultado de Aprendizaje (RA):**
  * **RA1:** Diseña soluciones basadas en modelos de lenguaje (LLM), aplicando técnicas de Prompt Engineering y RAG, que resuelvan requerimientos de información complejos en entornos organizacionales.
* **Indicadores de Evaluación Homologados (IE1 a IE5):**
  * **IE 1.1:** Caracteriza la problemática organizacional del sector salud y define los requerimientos funcionales y KPIs de impacto de la solución.
  * **IE 1.2:** Diseña una arquitectura de software desacoplada en 5 capas que integra modelos de lenguaje, guardrails de seguridad y sistemas hospitalarios.
  * **IE 1.3:** Aplica técnicas avanzadas de Prompt Engineering (*Role Setting*, *Chain-of-Thought* en 4 pasos, *Few-Shot Learning* y esquemas Pydantic).
  * **IE 1.4:** Implementa un pipeline RAG con segmentación semántica, indexación vectorial en ChromaDB ($\ge 0.75$ similitud coseno) y regla de abstención institucional.
  * **IE 1.5:** Desarrolla agentes con capacidades de Tool Calling transaccional sobre base relacional SQLite y valida su funcionamiento mediante pruebas unitarias exhaustivas.

---

## 📌 1. Caso Organizacional y KPIs de Impacto

### 1.1 Contexto de la Red de Salud Metropolitana "SaludConecta"
La red de salud **SaludConecta** gestiona 5 sedes ambulatorias y hospitalarias en la Región Metropolitana de Santiago (Santiago Centro, Providencia, La Florida, Las Condes y Maipú). La institución enfrentaba tres cuellos de botella operacionales críticos:
1. **Saturación en Mesones y Canales Telefónicos:** Largas filas de espera para agendamiento y consultas repetitivas de preparación de exámenes.
2. **Pérdida de Horas Médicas y Exámenes Suspendidos:** Pacientes que se presentan a exámenes complejos (endoscopías, TAC con contraste, curvas de tolerancia) sin cumplir el ayuno adecuado o sin suspender fármacos incompatibles (como metformina).
3. **Riesgo Vital Inadvertido:** Pacientes que consultan por canales digitales convencionales describiendo síntomas coronarios o neurológicos agudos y quedan en cola de espera sin priorización clínica.

### 1.2 Los 4 KPIs de Impacto de la Solución

| KPI | Métrica Operacional | Línea Base (Previa) | Meta con SaludConecta AI | Mecanismo de Implementación |
|---|---|:---:|:---:|---|
| **KPI-01: Tiempo de Respuesta en Triaje Asistencial** | Latencia de primera orientación preliminar al paciente. | ~15 a 20 minutos (espera presencial / call center). | **< 2 segundos** en canal web/móvil digital. | Orquestador agéntico LangChain y memoria conversacional de ventana ($k=5$). |
| **KPI-02: Latencia de Detección de Riesgo Vital (Código Rojo)** | Tiempo transcurrido hasta la derivación al SAMU 131 ante síntomas ESI 1 y 2. | Indeterminado / minutos (dependiente de operador humano). | **< 100 ms determinista** (meta real $<5$ ms). | `EmergencyBypassGuardrail`: Regex precompiladas que interceptan el flujo antes del LLM. |
| **KPI-03: Reducción de Exámenes Clínicos Suspendidos** | Porcentaje de procedimientos cancelados por incumplimiento de preparación/ayuno. | ~22% de pérdida de cupos en laboratorio e imagenología. | **Reducción de al menos un 40%** (< 13% de rechazo). | Pipeline RAG sobre manuales oficiales (`manual_preparacion.md`) con síntesis y citas protocolarias. |
| **KPI-04: Tasa de Precisión en Derivación y Agendamiento HIS** | Asignación correcta de especialidad médica y reserva sin sobreventa de cupos. | ~68% de citas agendadas en especialidad errónea o con doble reserva. | **> 90% de derivaciones correctas y 0% de colisiones**. | Clasificación guiada por catálogo oficial y tool calling transaccional atómico sobre SQLite (`tools_agenda.py`). |

---

## 🏗️ 2. Arquitectura de la Solución en 5 Capas

El sistema implementa una arquitectura desacoplada y modular orientada a garantizar resiliencia diagnóstica, protección de datos sensibles y anclaje fáctico estricto:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        CAPA 1: CANALES Y PACIENTES                     │
│        [ Interfaz Web Streamlit (app.py) ]    [ Consola CLI ]          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Entrada de texto del paciente
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               CAPA 2: SEGURIDAD, GATEWAY Y GUARDRAILS                  │
│   • Bypass Código Rojo (<100ms): Detección determinista ESI 1 y 2      │
│   • Anonimizador PII: Enmascaramiento de RUT, teléfonos y emails       │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │ Consulta Anonimizada            │ ¿Es Código Rojo?
                   │                                 └────────► [🚨 SAMU 131]
                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│             CAPA 3: NÚCLEO ORQUESTADOR AGÉNTICO (LANGCHAIN)            │
│   • Conexión: GitHub Models (gpt-4o-mini) / OpenAI API estándar        │
│   • Prompt Engineering: Role Setting + Chain-of-Thought (4 pasos)      │
│   • Memoria Conversacional: ConversationBufferWindowMemory (k=5)       │
│   • Esquemas de Salida: JSON Schema estructurado con Pydantic          │
└──────────────┬───────────────────────────────────────────┬─────────────┘
               │                                           │
  ¿Consulta Preparación/Convenio?             ¿Gestión de Horas Médicas?
               ▼                                           ▼
┌─────────────────────────────────────────┐ ┌───────────────────────────┐
│          CAPA 4: PIPELINE RAG           │ │  CAPA 5: SERVICIOS Y HIS  │
│  • Base Vectorial ChromaDB             │ │  • Base Relacional SQLite │
│  • Distancia Coseno (hnsw:space:cosine)│ │  • Tool Calling Consulta  │
│  • Filtro Umbral (score >= 0.75)       │ │  • Tool Calling Reserva   │
│  • Regla de Oro: Abstención Fáctica    │ │  • Transacción Atómica    │
│  • Citas Oficiales [Ref: Protocolo ...]│ │  • Prevención Colisiones  │
└─────────────────────────────────────────┘ └───────────────────────────┘
```

---

## 📁 3. Estructura del Repositorio

```text
saludconecta-ai-agent/
├── README.md                      # Documentación maestra, despliegue y guía del evaluador
├── IMPLEMENTATION_SPEC.md         # Especificación técnica detallada de la arquitectura
├── requirements.txt               # Dependencias del proyecto (LangChain, ChromaDB, Streamlit, etc.)
├── app.py                         # Aplicación Web interactiva en Streamlit
├── .env.example                   # Plantilla de variables de entorno (GitHub Models / OpenAI)
├── .gitignore                     # Exclusión de credenciales (.env), venv, bases locales y caché
├── docs/
│   └── bocetos_diseno.md          # Flujograma de triaje, wireframes ASCII y especificación UX/a11y
├── data/
│   ├── manual_preparacion.md      # Corpus de protocolos de laboratorio e imagenología (RAG)
│   ├── catalogo_especialidades.md # Matriz de 45 especialidades y prerrequisitos de derivación
│   └── citas_disponibles.csv      # Dataset sintético de 25 cupos médicos para Mock HIS
├── src/
│   ├── __init__.py
│   ├── config.py                  # Fábrica LLM (get_chat_model, get_embeddings_model)
│   ├── security_guardrails.py     # Bypass Código Rojo (<100ms) y anonimizador PII
│   ├── rag_engine.py              # Chunking semántico, ChromaDB y Retriever con umbral >=0.75
│   ├── prompts.py                 # System Prompt maestro con CoT, Few-Shot y Pydantic Schemas
│   ├── tools_agenda.py            # Herramientas de tool calling sobre Mock HIS (SQLite)
│   └── agent_orchestrator.py      # Agente orquestador con memoria de ventana deslizante (k=5)
└── tests/
    ├── __init__.py
    ├── TEST_EVIDENCE.md           # Registro formal de pruebas PyTest y matriz de trazabilidad
    ├── test_agent_orchestrator.py # Pruebas de síntesis RAG, memoria, desambiguación y agenda
    ├── test_emergency_bypass.py   # Pruebas de latencia (<100ms) y detección de banderas rojas
    ├── test_rag_grounding.py      # Pruebas de anclaje documental y regla de abstención
    └── test_tool_calling.py       # Pruebas de consulta, reserva atómica y colisiones en HIS
```

---

## 🚀 4. Instrucciones Paso a Paso de Despliegue Local

### Requisitos Previos
* **Python 3.10 o superior** (verificado en Python 3.12.10).
* Git instalado.
* Conexión a internet para la primera descarga de dependencias.
* Token de acceso personal de GitHub (`GITHUB_TOKEN`) o API Key de OpenAI (`OPENAI_API_KEY`).

### Paso 1: Clonar el Repositorio
```bash
git clone https://github.com/NotProblem001/saludconecta-ai-agent.git
cd saludconecta-ai-agent
```

### Paso 2: Crear y Activar el Entorno Virtual
```powershell
# En Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1

# En Linux o macOS (Bash):
python3 -m venv venv
source venv/bin/activate
```

### Paso 3: Instalar las Dependencias del Proyecto
```bash
pip install -r requirements.txt
```

### Paso 4: Configurar el Archivo de Variables de Entorno (`.env`)
Copie la plantilla oficial `.env.example` para crear su archivo de configuración `.env`:

```powershell
# En Windows (PowerShell):
Copy-Item .env.example .env

# En Linux o macOS:
cp .env.example .env
```

Abra el archivo `.env` en su editor y configure sus credenciales (Opción A recomendada para Duoc UC con GitHub Models):

```ini
# ==============================================================================
# CONFIGURACIÓN SALUDCONECTA - GITHUB MODELS (Opción A - Gratuita)
# ==============================================================================
GITHUB_TOKEN=ghp_tu_token_personal_de_github_aqui
GITHUB_BASE_URL=https://models.inference.ai.azure.com
MODEL_NAME=gpt-4o-mini

# ==============================================================================
# PARÁMETROS RAG Y BASE DE DATOS LOCAL
# ==============================================================================
EMBEDDING_MODEL_NAME=text-embedding-3-small
RAG_SIMILARITY_THRESHOLD=0.75
CHROMA_PERSIST_DIRECTORY=./chroma_db
DB_PATH=./saludconecta_his.db
```

> **Nota de Resiliencia:** El sistema cuenta con embeddings deterministas desacoplados de respaldo (`DeterministicFallbackEmbeddings`) y motor clínico autónomo, permitiendo ejecutar el 100% de la suite de pruebas y funcionalidades de agenda incluso de forma offline o ante interrupciones de red.

---

## 💻 5. Comandos de Ejecución

### 5.1 Interfaz Gráfica Web Interactiva (Streamlit)
```bash
streamlit run app.py
```
* **Acceso:** Abra su navegador en `http://localhost:8501`.
* **Funcionalidades:** Chat asistencial en tiempo real, botones de prueba rápida para los 4 escenarios críticos, badges de telemetría (latencia, herramientas invocadas y PII protegido) e historial persistente.

### 5.2 Consola Interactiva por Terminal (CLI)
```bash
python -m src.agent_orchestrator
```
* Permite interactuar directamente con SaludBot desde la línea de comandos. Admite los comandos especiales `ayuda`, `limpiar` (reiniciar memoria $k=5$) y `salir`.

### 5.3 Suite Completa de Pruebas Automatizadas (PyTest)
```bash
pytest tests/ -v
```
* Ejecuta las **32 pruebas unitarias e integrales** cubriendo bypass vital, anonimización PII, RAG con umbral de abstención, tool calling transaccional y memoria conversacional. (Evidencia detallada en [`tests/TEST_EVIDENCE.md`](tests/TEST_EVIDENCE.md)).

---

## 🧪 6. Casos de Uso de Prueba Documentados

La siguiente tabla resume los 5 escenarios canónicos exigidos para la evaluación técnica del sistema:

| N° | Escenario Clínico | Mensaje del Paciente (Entrada) | Comportamiento del Sistema y Módulos Activos | Resultado Verificado |
|:---:|---|---|---|---|
| **1** | **Bypass Vital Inmediato (Código Rojo)** | *"Tengo un dolor muy fuerte en el pecho que se me va al brazo izquierdo y a la mandíbula"* | `EmergencyBypassGuardrail` intercepta el texto antes del LLM en $<1$ ms. No consulta RAG ni consume tokens. Activa Código Rojo y emite instrucciones de reposo semisentado con derivación urgente a SAMU 131. | 🚨 Alerta SAMU 131 emitida en tiempo récord ($<100$ ms). |
| **2** | **Consulta RAG Válida (Grounding Fáctico)** | *"¿Cuáles son las indicaciones de ayuno para un perfil lipídico y glicemia? ¿Puedo tomar agua?"* | RAG recupera el chunk de `manual_preparacion.md` con similitud $\ge 0.75$. Sintetiza 8-12 hrs de ayuno, prohíbe café/té/leche y autoriza hasta 250 ml de agua sin gas. Cita formalmente `[Ref: Protocolo LAB-001]`. | 📋 Síntesis fluida con código oficial sin volcado crudo. |
| **3** | **Consulta Fuera de Dominio (Abstención Fáctica)** | *"¿Cuál es la preparación para una biopsia hepática espacial de astronautas en gravedad cero?"* | El retriever vectorial evalúa la consulta; ningún documento alcanza el umbral de similitud ($0.75$). Se activa la **Regla de Oro de Abstención Fáctica**, declarando no poseer el protocolo y derivando al 600 000 1234. | ⚠️ Abstención institucional estricta (cero alucinación). |
| **4** | **Desambiguación y Consulta de Agenda HIS** | *"¿Dónde tienen cobertura? Deseo consultar las de Santiago Centro"* | Turno 1: Desambigua sedes físicas y convenios previsionales. Turno 2: Recupera contexto de la memoria ($k=5$), invoca `consultar_disponibilidad_horas` sobre SQLite y despliega cupos médicos con ID y doctor. | 🛠️ Tool calling preciso y retención contextual de memoria. |
| **5** | **Reserva Atómica con Validación de RUT** | *"Quiero reservar la cita 1 para Juan Pérez, RUT 15.678.901-2 y fono +56988776655"* | Valida sintaxis de RUT chileno con guion. Abre transacción en SQLite (`BEGIN TRANSACTION`), valida cupo `DISPONIBLE` y actualiza atómicamente a `RESERVADA`, previniendo colisiones concurrentes. | ✅ Confirmación con código #1 y bloqueo contra doble reserva. |

---

## 📄 7. Documentación Complementaria del Repositorio

* [Bocetos de Diseño, Arquitectura de Información y UX/a11y (`docs/bocetos_diseno.md`)](docs/bocetos_diseno.md)
* [Registro de Evidencia de Pruebas Automatizadas y Matriz de Trazabilidad (`tests/TEST_EVIDENCE.md`)](tests/TEST_EVIDENCE.md)
* [Especificación Técnica de Implementación (`IMPLEMENTATION_SPEC.md`)](IMPLEMENTATION_SPEC.md)

---
*Red de Salud Metropolitana SaludConecta – Proyecto Académico Duoc UC (ISY0101).*
