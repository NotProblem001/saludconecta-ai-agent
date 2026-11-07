# 🏥 SaludConecta: agente inteligente de orientación, triaje y agendamiento

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-green.svg)](https://docs.langchain.com/docs/langgraph/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-RAG-orange.svg)](https://docs.trychroma.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-UI-red.svg)](https://docs.streamlit.io)

## Identificación

| | |
|---|---|
| **Institución** | Duoc UC, Escuela de Informática y Telecomunicaciones |
| **Asignatura** | ISY0101, Ingeniería de Soluciones con Inteligencia Artificial |
| **Evaluación** | Evaluación Parcial N°2 (EP2) |
| **Integrantes** | Matias Alejandro Araos Urra y `[NOMBRE INTEGRANTE 2]` |

## Qué hace

Convierte el asistente de la EP1 en un agente que resuelve un flujo organizacional de punta a punta: entiende la solicitud, planifica, consulta el HIS simulado, valida reglas clínicas, escribe la reserva y recuerda al paciente en la siguiente sesión. Si las condiciones cambian, replanifica.

La red simulada **SaludConecta** tiene 5 sedes en la Región Metropolitana. El agente apunta a tres problemas: saturación de canales de atención, exámenes suspendidos por mala preparación y riesgo vital inadvertido en canales digitales.

> Proyecto académico con datos ficticios. No constituye orientación médica real.

## Requisitos previos

- Python 3.10 o superior (verificado con 3.12.10).
- Git.
- Credencial de LLM **opcional**. Sin ella, el agente funciona con planificador por reglas y motor autónomo.

## Instalación

**Windows (PowerShell)**

```powershell
git clone https://github.com/NotProblem001/saludconecta-ai-agent.git
cd saludconecta-ai-agent
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

**Linux o macOS**

```bash
git clone https://github.com/NotProblem001/saludconecta-ai-agent.git
cd saludconecta-ai-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Para usar LLM, edite `.env` y configure una opción: `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `GITHUB_TOKEN` o `GROQ_API_KEY`. El sistema las evalúa en ese orden.

## Comandos

| Tarea | Comando |
|---|---|
| Crear lo que falte en BD e índice | `python scripts/init_data.py` |
| Reiniciar datos (**borra reservas, memoria y traza**) | `python scripts/init_data.py --reset` |
| Levantar la interfaz web | `streamlit run app.py` |
| Usar la CLI | `python -m src.agent_orchestrator` |
| Usar la CLI con memoria de paciente | `python -m src.agent_orchestrator --paciente PAC-001` |
| Correr las pruebas | `pytest -v` |
| Correr las pruebas con cobertura | `pytest -v --cov=src` |
| Demo de escenarios, sin LLM ni BD local | `python scripts/run_demo_scenarios.py` |
| Demo con el LLM configurado | `python scripts/run_demo_scenarios.py --llm real` |

**Orden recomendado para evaluar:** `python scripts/init_data.py --reset`, `pytest -v`, `python scripts/run_demo_scenarios.py` y `streamlit run app.py` (abre `http://localhost:8501`).

Pacientes simulados: `PAC-001` (metformina), `PAC-002` (sin fármacos) y `PAC-003` (alergia al yodo).

## Herramientas

Cada herramienta tiene esquema Pydantic de entrada y salida, docstring, manejo de errores y logging.

| Categoría | Herramientas |
|---|---|
| **Consulta** | `buscar_protocolo_rag`, `consultar_catalogo_especialidad`, `consultar_disponibilidad_horas`, `consultar_historial_paciente` |
| **Escritura** | `reservar_cita_medica`, `cancelar_cita_medica`, `reprogramar_cita`, `registrar_atencion`, `generar_comprobante` |
| **Razonamiento** | `clasificar_solicitud`, `validar_reglas`, `seleccionar_siguiente_accion` |

## Memoria

- **Corto plazo:** ventana de 5 turnos con texto anonimizado y estado de la tarea (plan, paso actual y datos recolectados).
- **Largo plazo:** por paciente, en SQLite: preferencias de sede y horario, atenciones previas e indicaciones entregadas. No guarda transcripciones.
- **Recuperación:** al iniciar sesión, el agente carga y resume el contexto, avisa de las citas pendientes con su preparación y lo inyecta al prompt como dato delimitado.

## Planificación

Plan-and-Execute sobre un `StateGraph` de LangGraph. El LLM propone un plan JSON, las invariantes de seguridad lo validan y un ejecutor determinista lo corre. Sin LLM, se usa un plan por reglas.

| Condición | Comportamiento |
|---|---|
| Sin cupos en la sede preferida | Replanifica: otro horario, otra sede o Mesa Central |
| Síntoma de riesgo vital con un plan activo | Aborta el plan y activa el Código Rojo antes del LLM |
| RAG bajo el umbral 0.75 | Se abstiene y deriva a un humano |
| Conflicto de preparación | Agrega una advertencia y bloquea la escritura hasta confirmar |
| Falla de herramienta | Reintenta y degrada con mensaje controlado |

La traza de decisiones se ve en el panel de Streamlit y en la CLI, y queda en el log y en la tabla `traza_decisiones`.

## Estructura del repositorio

```text
saludconecta-ai-agent/
├── app.py                     # Interfaz Streamlit
├── requirements.txt
├── .env.example
├── IMPLEMENTATION_SPEC.md     # Especificación técnica de EP1
├── data/                      # Manuales, catálogo, cupos y pacientes simulados
├── docs/
│   ├── arquitectura_ep2.md    # Diagramas de arquitectura, secuencia, grafo y memoria
│   ├── decisiones_diseno.md   # Registro de decisiones (ADR)
│   ├── flujos_ejemplo.md      # Conversaciones con su traza
│   ├── bocetos_diseno.md      # Flujos y wireframes de la interfaz
│   ├── guion_demo.md          # Guion de la demo en vivo
│   ├── estructura_ppt.md      # Propuesta de diapositivas
│   └── referencias.md         # Referencias APA 7
├── scripts/
│   ├── init_data.py           # Inicializa SQLite y ChromaDB
│   └── run_demo_scenarios.py  # Escenarios de punta a punta
├── src/
│   ├── agent_orchestrator.py  # Fachada de sesión, motor autónomo y CLI
│   ├── agent_graph.py         # Grafo de estados
│   ├── planner.py             # Planes, invariantes y replanificación
│   ├── decision_trace.py      # Traza de decisiones
│   ├── security_guardrails.py # Código Rojo y anonimización
│   ├── rag_engine.py          # RAG con umbral
│   ├── tools_agenda.py        # Mock HIS en SQLite
│   ├── prompts.py, config.py
│   ├── memory/                # short_term, long_term, context
│   └── tools/                 # consulta, escritura, razonamiento, schemas, base
└── tests/                     # Suite PyTest y TEST_EVIDENCE.md
```

## Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `Activate.ps1 cannot be loaded` | Política de ejecución de PowerShell | `Set-ExecutionPolicy -Scope Process RemoteSigned` |
| `ModuleNotFoundError: langgraph` | Dependencias sin instalar o venv inactivo | Active el venv y ejecute `pip install -r requirements.txt` |
| Los cupos muestran fechas antiguas o no aparecen los de TAC | BD creada antes de EP2 | `python scripts/init_data.py --reset` |
| Un cupo aparece ocupado | Reservas de pruebas anteriores | `python scripts/init_data.py --reset` |
| La traza muestra `PLAN_LLM_DESCARTADO` con `AuthenticationError` | Credencial inválida o expirada | Renueve la key. Mientras tanto, el agente opera por reglas |
| Las respuestas tardan varios segundos | Red lenta hacia el LLM | Deje la credencial vacía para operar sin LLM |
| El RAG se abstiene en todo tras configurar `OPENAI_API_KEY` | Índice construido con otros embeddings | `python scripts/init_data.py --reset` y recalibre el umbral |
| Caracteres extraños en la consola de Windows | Codificación de la terminal | `$env:PYTHONIOENCODING="utf-8"` |

## Limitaciones conocidas

- Con OpenRouter, GitHub Models o sin credenciales, el RAG usa embeddings léxicos de respaldo. Ver ADR-004 en [`docs/decisiones_diseno.md`](docs/decisiones_diseno.md).
- La detección de Código Rojo usa expresiones regulares: puede generar falsos positivos y no detectar todas las formas de expresar una emergencia.
- Las reglas clínicas y los pacientes son material académico sin revisión profesional.
- La disponibilidad no filtra por previsión del paciente.
- En turnos generales sin plan, la abstención depende del prompt y no de una regla determinista.
- Con LLM real, los turnos con planificación tardan cerca de 2 a 7 segundos, sobre la meta de 2 s de KPI-01.
- El anonimizador no reconoce nombres: solo se enmascara el nombre conocido por la tarea.

## Documentación

- [Arquitectura](docs/arquitectura_ep2.md)
- [Decisiones de diseño](docs/decisiones_diseno.md)
- [Flujos de ejemplo](docs/flujos_ejemplo.md)
- [Bocetos de diseño](docs/bocetos_diseno.md)
- [Guion de la demo](docs/guion_demo.md)
- [Estructura de la presentación](docs/estructura_ppt.md)
- [Referencias](docs/referencias.md)
- [Evidencia de pruebas](tests/TEST_EVIDENCE.md)

## Declaración de uso de IA

<!-- A COMPLETAR POR EL EQUIPO: describir cómo usaron Claude Code, qué partes revisaron y qué decisiones tomaron ustedes -->

## Conclusiones y reflexiones

<!-- A COMPLETAR POR EL EQUIPO: conclusiones, justificación crítica y reflexiones individuales, sin uso de IA -->
