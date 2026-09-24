# ESPECIFICACIÓN TÉCNICA DE IMPLEMENTACIÓN: SISTEMA AGÉNTICO SALUDCONECTA

**Proyecto:** Sistema Agéntico de Orientación, Triaje y Gestión de Pacientes  
**Asignatura:** ISY0101 – Ingeniería de Soluciones con Inteligencia Artificial  
**Autor:** Matias Alejandro Araos Urra  
**Institución:** Duoc UC – Escuela de Informática y Telecomunicaciones  
**Versión:** 1.0.0  
**Fecha:** Septiembre 2026  

---

## 1. Árbol de Directorios del Repositorio

```text
saludconecta-ai-agent/
├── README.md                      # Instrucciones de despliegue, ejecución y validación
├── IMPLEMENTATION_SPEC.md         # Documento de arquitectura técnica y especificación
├── requirements.txt               # Dependencias del proyecto (incluye streamlit)
├── app.py                         # Interfaz gráfica web interactiva (Streamlit)
├── .env.example                   # Plantilla de variables de entorno (GitHub Models / OpenAI)
├── .gitignore                     # Exclusión de entornos virtuales, bases locales y caché
├── docs/
│   └── bocetos_diseno.md          # Bocetos de diseño, wireframes ASCII y especificación UX/a11y
├── data/
│   ├── manual_preparacion.md      # Corpus de protocolos de laboratorio e imagenología (RAG)
│   ├── catalogo_especialidades.md # Matriz de 45 especialidades y prerrequisitos (RAG)
│   └── citas_disponibles.csv      # Dataset sintético de 25 cupos médicos para Mock HIS
├── src/
│   ├── __init__.py
│   ├── config.py                  # Conexión LLM compatible con GitHub Models y OpenAI API
│   ├── security_guardrails.py     # Bypass Código Rojo (<100ms) y anonimizador de PII
│   ├── rag_engine.py              # Chunking semántico, ChromaDB y Retriever con umbral
│   ├── prompts.py                 # System Prompts con CoT, Few-Shot y Esquemas JSON
│   ├── tools_agenda.py            # Tool calling sobre SQLite (Mock HIS)
│   └── agent_orchestrator.py      # Agente orquestador con memoria de ventana deslizante (k=5)
└── tests/
    ├── __init__.py
    ├── TEST_EVIDENCE.md           # Registro formal de pruebas PyTest y matriz de trazabilidad
    ├── test_agent_orchestrator.py # Test unitario: Síntesis RAG, memoria, desambiguación y tool calling
    ├── test_emergency_bypass.py   # Test unitario: Bypass Código Rojo ante riesgo vital
    ├── test_rag_grounding.py      # Test unitario: Recuperación fáctica y abstención
    └── test_tool_calling.py       # Test unitario: Búsqueda y agendamiento transaccional
```

---

## 2. Arquitectura de la Solución y Flujo de Datos

El sistema está estructurado bajo un diseño desacoplado de 5 capas de servicio:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        CAPA 1: CANALES Y PACIENTES                     │
│                [ Portal Web ]    [ App Móvil ]    [ Call Center ]       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTPS / REST API / CLI
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│               CAPA 2: SEGURIDAD, GATEWAY Y GUARDRAILS                  │
│   • Anonimizador PII (RUT chileno, Teléfonos móviles/fijos, Emails)    │
│   • Bypass Código Rojo (<100ms - Detección heurística de riesgo vital) │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │ Consulta Anonimizada            │ ¿Es Código Rojo?
                   │                                 └────────► [SAMU 131]
                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│             CAPA 3: NÚCLEO ORQUESTADOR AGÉNTICO (LANGCHAIN)            │
│   • Modelo: GPT-4o-mini (GitHub Models / OpenAI API)                   │
│   • Prompt Engineering: Role Setting + Chain-of-Thought (CoT)          │
│   • Memoria Conversacional: ConversationBufferWindowMemory (k=5)       │
│   • Salida Estructurada: Forzado JSON Schema (Pydantic)                │
└──────────────┬───────────────────────────────────────────┬─────────────┘
               │                                           │
  ¿Consulta Preparación/Convenio?             ¿Gestión de Horas Médicas?
               ▼                                           ▼
┌─────────────────────────────────────────┐ ┌───────────────────────────┐
│          CAPA 4: PIPELINE RAG           │ │  CAPA 5: SERVICIOS Y HIS  │
│  • Base Vectorial ChromaDB             │ │  • Base Relacional SQLite │
│  • text-embedding-3-small (1536 dims)  │ │  • Tool Calling Consulta  │
│  • Top-3 Chunks con umbral >= 0.75     │ │  • Tool Calling Reserva   │
│  • Regla de Oro: Abstención Fáctica    │ │  • Control Transaccional  │
└─────────────────────────────────────────┘ └───────────────────────────┘
```

### Diagrama de Secuencia del Procesamiento

```text
Paciente                  Guardrails               RAG Engine               LLM / Agent               Mock HIS
   │                           │                        │                        │                        │
   │── 1. Enviar mensaje ─────►│                        │                        │                        │
   │                           │                        │                        │                        │
   │                           │── 2. Chequeo Código    │                        │                        │
   │                           │      Rojo (<100ms)     │                        │                        │
   │                           │   (Si es Vital:        │                        │                        │
   │◄── Alerta SAMU 131 ───────│    Bypass y Retorno)   │                        │                        │
   │                           │                        │                        │                        │
   │                           │── 3. Anonimizar PII ──►│                        │                        │
   │                           │                        │── 4. Retrieve Chunks   │                        │
   │                           │                        │      Similitud >= 0.75 │                        │
   │                           │                        │───────────────────────►│                        │
   │                           │                        │   (Contexto o          │                        │
   │                           │                        │    Abstención Fáctica) │                        │
   │                           │                        │                        │                        │
   │                           │                        │                        │── 5. ¿Requiere Tool? ─►│
   │                           │                        │                        │   (Consultar/Reservar) │
   │                           │                        │                        │◄── Confirmación ───────│
   │                           │                        │                        │                        │
   │◄── 6. Respuesta Empática, Fáctica y Triage ESI ─────────────────────────────│                        │
```

---

## 3. Capa de Seguridad y Guardrails Heurísticos (`security_guardrails.py`)

### 3.1 Bypass Determinista de Código Rojo
* **Objetivo de Latencia:** Ejecución determinista inferior a $100$ ms (rendimiento real $<1$ ms) evaluada antes de invocar cualquier modelo generativo.
* **Banderas Rojas Clínicas Detectadas:**
  1. `DOLOR_TORACICO_CORONARIO`: Dolor u opresión precordial irradiada a brazo izquierdo, cuello o mandíbula.
  2. `SOSPECHA_ACV_NEURO`: Asimetría facial súbita, pérdida de fuerza en hemicuerpo o extremidad, alteración aguda del lenguaje (Escala FAST).
  3. `COMPROMISO_RESPIRATORIO_SEVERO`: Asfixia, cianosis, imposibilidad de respirar o estridor.
  4. `SHOCK_ANAFILACTICO`: Edema de glotis, hinchazón de labios/lengua, compromiso de vía aérea.
  5. `HEMORRAGIA_SEVERA_Y_TRAUMA`: Sangrado arterial masivo, politraumatismo con inconsciencia o convulsión activa.
  6. `RIESGO_VITAL_PSIQUIATRICO`: Ideación suicida activa con plan o ingesta aguda de tóxicos.
* **Acción de Derivación:** Emisión inmediata de mensaje protocolar con redirección prioritaria a la línea de urgencia vital **SAMU 131** y traslado inmediato a centro de urgencias.

### 3.2 Anonimizador de Datos Sensibles (PII)
* **RUT Chileno:** Expresiones regulares que identifican formatos `12.345.678-9`, `12345678-k`, sustituyéndolos por `[RUT_PROTEGIDO]`.
* **Teléfonos:** Detección de numeración móvil (+569, 9xxxxxxxx) y red fija (22xxxxxxx, +56 2), sustituyéndolos por `[TELEFONO_PROTEGIDO]`.
* **Correos Electrónicos:** Enmascaramiento de direcciones estándar reemplazándolas por `[EMAIL_PROTEGIDO]`.

---

## 4. Motor RAG y Grounding Fáctico (`rag_engine.py`)

### 4.1 Estrategia de Chunking Semántico
* **Segmentación:** Basada en jerarquía estructural Markdown (`MarkdownHeaderTextSplitter`) por encabezados de sección (`## Examen...`, `## Especialidad...`).
* **Sub-chunking recursivo:** División de resguardo con tamaño de fragmento de 1200 caracteres y traslape (*overlap*) de 150 caracteres.
* **Metadatos de Trazabilidad:** Inyección de metadatos fácticos en cada chunk (`source`, `categoria`, `Seccion`, `Documento`).

### 4.2 Base Vectorial y Métrica de Similitud
* **Almacenamiento:** Base vectorial persistente **ChromaDB**.
* **Espacio Vectorial:** Configuración explícita de métrica de distancia coseno (`collection_metadata={"hnsw:space": "cosine"}`).
* **Modelo de Embeddings:** Integración nativa con `text-embedding-3-small` (1536 dimensiones) y función determinista desacoplada de respaldo para validación offline y entornos de prueba.

### 4.3 Control de Umbral y Regla de Abstención Fáctica
* **Umbral de Corte:** $\ge 0.75$ de similitud coseno.
* **Política de Abstención Fáctica:** Si ningún fragmento de la base de conocimiento alcanza el umbral de corte, el sistema activa automáticamente la directriz de abstención institucional: declara no disponer del protocolo en sus manuales oficiales y canaliza al usuario a la Central Telefónica (600 000 1234), prohibiendo cualquier conjetura o alucinación médica.

---

## 5. Prompt Engineering y Esquemas Estructurados (`prompts.py`)

### 5.1 Role Setting Institucional
Establece la identidad del asistente `SaludConecta AI` y sus restricciones bioéticas:
* Prohibición absoluta de emitir diagnósticos médicos definitivos o prescribir dosis farmacológicas.
* Realización de triaje preliminar no vinculante conforme a la escala ESI.

### 5.2 Metodología Chain-of-Thought (CoT)
Obligatoriedad de razonamiento secuencial en cuatro etapas antes de formular la respuesta final:
* **Paso 1 (Evaluación de Riesgo):** Discriminación de emergencia vital y ESI 1-2.
* **Paso 2 (Grounding Fáctico):** Verificación de evidencia documental en RAG y evaluación de necesidad de abstención.
* **Paso 3 (Planificación Transaccional):** Identificación de parámetros para invocación de herramientas de agenda.
* **Paso 4 (Síntesis y Empatía):** Redacción clínica clara, cálida y tranquilizadora.

### 5.3 Modelos Pydantic de Salida Estructurada
* `TriageClassification`:
  - `nivel_esi`: Entero del 1 al 5.
  - `justificacion_clinica`: Fundamento clínico del triaje.
  - `especialidad_sugerida`: Especialidad recomendada.
  - `prerrequisitos_requeridos`: Lista de exámenes basales obligatorios.
* `AgentStructuredOutput`:
  - `tipo_interaccion`: `triaje` | `preparacion_examen` | `agendamiento` | `orientacion_general` | `emergencia`
  - `analisis_cot`: Texto del pensamiento clínico paso a paso.
  - `clasificacion_triaje`: Objeto opcional `TriageClassification`.
  - `respuesta_paciente`: Mensaje redactado al usuario.
  - `acciones_tomadas`: Lista de operaciones ejecutadas.
  - `requiere_atencion_urgente`: Booleano de derivación a Urgencia.

---

## 6. Capa Transaccional Mock HIS (`tools_agenda.py`)

* **Motor de Persistencia:** Base de datos relacional SQLite (`saludconecta_his.db`).
* **Tabla `citas`:**
  - `id`: Identificador único (INTEGER PRIMARY KEY).
  - `especialidad`, `medico`, `sucursal`, `comuna`, `fecha`, `hora`, `prevision`.
  - `estado`: Estado del cupo (`DISPONIBLE` o `RESERVADA`).
  - `paciente_rut`, `paciente_nombre`, `paciente_telefono`, `fecha_reserva`.
* **Herramientas Expuestas vía `@tool`:**
  1. `consultar_citas_disponibles`: Búsqueda multicriterio insensible a mayúsculas/minúsculas por especialidad, comuna, sucursal o fecha.
  2. `reservar_cita_medica`: Operación atómica (`BEGIN TRANSACTION`) que verifica que el cupo esté disponible y lo actualiza a `RESERVADA`, previniendo colisiones concurrentes y dobles agendamientos.
  3. `cancelar_cita_medica`: Liberación de cupo con autenticación del RUT del paciente titular.

---

## 7. Orquestador Agéntico (`agent_orchestrator.py`)

* **Control de Contexto:** Integración de `ConversationBufferWindowMemory` con tamaño de ventana $k=5$ para mantener las últimas 5 interacciones sin saturar la ventana de contexto del LLM.
* **Enlace Dinámico de Herramientas:** Vinculación de `AGENDA_TOOLS` mediante `bind_tools()` para ejecución autónoma de consultas y reservas.
* **Interfaz de Usuario:** CLI interactiva por consola con soporte para comandos de control de sesión (`salir`, `limpiar`, `ayuda`).

---

## 8. Batería de Pruebas Automatizadas PyTest

La suite de pruebas contiene **32 pruebas unitarias e integrales** estructuradas en cuatro módulos:

| Módulo de Prueba | Archivo | Casos de Prueba | Cobertura |
|---|---|:---:|---|
| **Orquestador y Memoria** | `tests/test_agent_orchestrator.py` | 6 | Síntesis RAG sin volcado crudo, desambiguación de cobertura (sedes y convenios), memoria de ventana ($k=5$), reserva con validación de RUT chileno, abstención institucional y bypass de Código Rojo en agente. |
| **Bypass y PII** | `tests/test_emergency_bypass.py` | 14 | Benchmarking de latencia ($<100$ ms), banderas rojas coronarias, ACV, disnea, anafilaxia, trauma, suicidio, paso de consultas rutinarias, anonimización de RUT, teléfonos y correos. |
| **Grounding y RAG** | `tests/test_rag_grounding.py` | 5 | Carga de corpus, anclaje en Perfil Lipídico (LAB-001), TAC con contraste (IMG-102), Cardiología Adulto (ESP-CARD-01) y activación de la regla de abstención institucional ante exámenes ficticios. |
| **Tool Calling HIS** | `tests/test_tool_calling.py` | 7 | Búsqueda por especialidad y comuna, manejo de búsquedas vacías, reserva atómica exitosa, rechazo de colisiones por doble reserva, manejo de IDs inexistentes y cancelación autenticada. |

**Resultado de Ejecución Verificado:** `32 passed in 26.60s` (100% de éxito, 0 fallos).  
Para más detalles de trazabilidad de requerimientos RF-01 a RF-04 y RNF-01 a RNF-03, consulte [`tests/TEST_EVIDENCE.md`](tests/TEST_EVIDENCE.md).