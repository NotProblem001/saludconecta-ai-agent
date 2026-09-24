# 🧪 Registro de Evidencia de Pruebas Automatizadas (PyTest)
## Red de Salud Metropolitana "SaludConecta"

> **Asignatura:** ISY0101 – Ingeniería de Soluciones con Inteligencia Artificial  
> **Evaluación Parcial N°1 (EP1):** Encargo Escrito y Repositorio Digital (Ponderación 30%)  
> **Resultado de Aprendizaje (RA):** RA1 – Diseña soluciones basadas en modelos de lenguaje (LLM), aplicando técnicas de Prompt Engineering y RAG, que resuelvan requerimientos de información complejos en entornos organizacionales.  
> **Alumno:** Matias Alejandro Araos Urra  
> **Institución:** Duoc UC – Escuela de Informática y Telecomunicaciones  
> **Fecha de Ejecución:** Septiembre 2026  
> **Estado de la Suite:** ✅ **100% PASSED (32/32 pruebas exitosas)**  

---

## 1. Resumen del Entorno de Ejecución

| Parámetro | Valor Verificado en Ejecución |
|---|---|
| **Sistema Operativo** | Windows 11 (Plataforma `win32`) |
| **Intérprete de Python** | Python 3.12.10 (`win_amd64`) |
| **Ruta del Ejecutable** | `C:\Users\Matias\AppData\Local\Programs\Python\Python312\python.exe` |
| **Framework de Pruebas** | `pytest 9.1.1` (con `pluggy 1.6.0`, `anyio 4.15.1`, `langsmith 0.14.0`) |
| **Librerías Core IA** | `langchain>=0.2.6`, `langchain-openai>=0.1.14`, `chromadb>=0.5.3`, `pydantic>=2.7.4` |
| **Total de Tests Ejecutados** | **32 pruebas unitarias e integrales** |
| **Tasa de Aprobación** | **100.0% (32 pasados, 0 fallidos, 0 omitidos)** |
| **Tiempo Total de Ejecución** | **26.60 segundos** |

---

## 2. Salida Completa y Textual de la Consola de PyTest

A continuación se transcribe de forma literal la salida generada por el comando `pytest tests/ -v`:

```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\Matias\AppData\Local\Programs\Python\Python312\python.exe
cachedir: .pytest_cache
rootdir: C:\Workspace\saludconecta-ai-agent
plugins: anyio-4.15.1, langsmith-0.14.0
collecting ... collected 32 items

tests/test_agent_orchestrator.py::test_rag_synthesis_no_raw_dump PASSED  [  3%]
tests/test_agent_orchestrator.py::test_cobertura_disambiguation_no_static_loop PASSED [  6%]
tests/test_agent_orchestrator.py::test_conversational_memory_and_tool_calling PASSED [  9%]
tests/test_agent_orchestrator.py::test_booking_with_rut_validation PASSED [ 12%]
tests/test_agent_orchestrator.py::test_golden_rule_of_abstention PASSED  [ 15%]
tests/test_agent_orchestrator.py::test_emergency_bypass_in_agent PASSED  [ 18%]
tests/test_emergency_bypass.py::test_emergency_bypass_latency_benchmark PASSED [ 21%]
tests/test_emergency_bypass.py::test_emergency_red_flags_detection[Tengo un dolor en el pecho opresivo muy fuerte que se me sube a la mand\xedbula y brazo izquierdo-DOLOR_TORACICO_CORONARIO] PASSED [ 25%]
tests/test_emergency_bypass.py::test_emergency_red_flags_detection[Mi abuela tiene la boca torcida de repente y no puede hablar bien, se le cay\xf3 el brazo-SOSPECHA_ACV_NEURO] PASSED [ 28%]
tests/test_emergency_bypass.py::test_emergency_red_flags_detection[Me falta el aire grave, no puedo respirar y tengo los labios morados-COMPROMISO_RESPIRATORIO_SEVERO] PASSED [ 31%]
tests/test_emergency_bypass.py::test_emergency_red_flags_detection[Com\xed man\xed y tengo edema de glotis, se me cierra la garganta y me asfixio-SHOCK_ANAFILACTICO] PASSED [ 34%]
tests/test_emergency_bypass.py::test_emergency_red_flags_detection[Hay una hemorragia masiva tras un accidente y el paciente est\xe1 inconsciente-HEMORRAGIA_SEVERA_Y_TRAUMA] PASSED [ 37%]
tests/test_emergency_bypass.py::test_emergency_red_flags_detection[Siento que no doy m\xe1s y quiero matarme hoy mismo-RIESGO_VITAL_PSIQUIATRICO] PASSED [ 40%]
tests/test_emergency_bypass.py::test_non_emergency_queries_pass_through[Hola, necesito agendar una hora para control de medicina general con la Dra. Andrea Morales.] PASSED [ 43%]
tests/test_emergency_bypass.py::test_non_emergency_queries_pass_through[\xbfCu\xe1les son las indicaciones de ayuno para un examen de sangre de perfil lip\xeddico?] PASSED [ 46%]
tests/test_emergency_bypass.py::test_non_emergency_queries_pass_through[Tengo dolor en la espalda baja desde hace dos meses y quiero ver a un traumat\xf3logo.] PASSED [ 50%]
tests/test_emergency_bypass.py::test_non_emergency_queries_pass_through[\xbfAtienden por Fonasa nivel B en la sucursal de Providencia?] PASSED [ 53%]
tests/test_emergency_bypass.py::test_non_emergency_queries_pass_through[Buenas tardes, quisiera saber el precio de una consulta dental para limpieza.] PASSED [ 56%]
tests/test_emergency_bypass.py::test_pii_anonymizer_rut PASSED           [ 59%]
tests/test_emergency_bypass.py::test_pii_anonymizer_phone_and_email PASSED [ 62%]
tests/test_rag_grounding.py::test_rag_corpus_loaded_correctly PASSED     [ 65%]
tests/test_rag_grounding.py::test_rag_grounding_perfil_lipidico PASSED   [ 68%]
tests/test_rag_grounding.py::test_rag_grounding_tac_abdomen_contraste PASSED [ 71%]
tests/test_rag_grounding.py::test_rag_grounding_especialidad_cardiologia PASSED [ 75%]
tests/test_rag_grounding.py::test_rag_abstention_on_unknown_procedure PASSED [ 78%]
tests/test_tool_calling.py::test_consultar_citas_filtro_especialidad PASSED [ 81%]
tests/test_tool_calling.py::test_consultar_citas_filtro_comuna PASSED    [ 84%]
tests/test_tool_calling.py::test_consultar_citas_sin_resultados PASSED   [ 87%]
tests/test_tool_calling.py::test_reservar_cita_exitosa PASSED            [ 90%]
tests/test_tool_calling.py::test_prevencion_doble_agendamiento_conflicto PASSED [ 93%]
tests/test_tool_calling.py::test_reservar_cita_inexistente PASSED        [ 96%]
tests/test_tool_calling.py::test_cancelar_cita_y_liberar_cupo PASSED     [100%]

============================== warnings summary ===============================
tests/test_agent_orchestrator.py::test_rag_synthesis_no_raw_dump
  C:\Workspace\saludconecta-ai-agent\src\rag_engine.py:295: LangChainDeprecationWarning: The class `Chroma` was deprecated in LangChain 0.2.9 and will be removed in 1.0. An updated version of the class exists in the `langchain-chroma package and should be used instead. To use it run `pip install -U `langchain-chroma` and import as `from `langchain_chroma import Chroma``.
    self.vector_store = Chroma(

tests/test_agent_orchestrator.py::test_rag_synthesis_no_raw_dump
  C:\Workspace\saludconecta-ai-agent\src\agent_orchestrator.py:135: LangChainDeprecationWarning: The class `ConversationBufferWindowMemory` was deprecated in LangChain 0.3.1 and will be removed in 2.0.0. Use `langchain.agents.create_agent` instead. For agents that need to remember prior interactions, use `create_agent` with checkpointing or the `Store` API. See https://docs.langchain.com/oss/python/langchain/short-term-memory and https://docs.langchain.com/oss/python/langchain/long-term-memory
    self.memory = ConversationBufferWindowMemory(

tests/test_agent_orchestrator.py::test_rag_synthesis_no_raw_dump
  C:\Users\Matias\AppData\Local\Programs\Python\Python312\Lib\site-packages\pydantic\main.py:263: LangChainDeprecationWarning: The class `InMemoryChatMessageHistory` was deprecated in LangChain 1.6.4 and will be removed in 2.0.0 See the short-term memory documentation for recommended alternatives: https://docs.langchain.com/oss/python/langchain/short-term-memory
    validated_self = self.__pydantic_validator__.validate_python(data, self_instance=self)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 32 passed, 3 warnings in 26.60s =======================
```

---

## 3. Matriz de Cobertura y Trazabilidad de Requerimientos

La siguiente matriz homologa cada prueba unitaria e integral con los requerimientos funcionales (RF) y no funcionales (RNF) definidos en la pauta de evaluación formal de Duoc UC (ISY0101):

### 3.1 Requerimientos Funcionales (RF)

| ID | Requerimiento Funcional | Descripción Clínica / Operativa | Tests Automatizados que lo Validan | Estado |
|---|---|---|---|:---:|
| **RF-01** | **Triaje Clínico Preliminar y Clasificación ESI** | Sugerencia no diagnóstica de severidad clínica y derivación médica basada en el *Emergency Severity Index* (niveles 1 a 5) y desambiguación de cobertura institucional. | `test_agent_orchestrator.py::test_cobertura_disambiguation_no_static_loop`<br>`test_emergency_bypass.py::test_non_emergency_queries_pass_through` [5 casos] | ✅ PASSED |
| **RF-02** | **Grounding Fáctico RAG y Regla de Abstención** | Recuperación fáctica con umbral cosine $\ge 0.75$ sobre manuales de preparación y catálogo de especialidades. Síntesis sin volcado en crudo, citas protocolarias y abstención ante procedimientos ficticios. | `test_rag_grounding.py::test_rag_corpus_loaded_correctly`<br>`test_rag_grounding.py::test_rag_grounding_perfil_lipidico`<br>`test_rag_grounding.py::test_rag_grounding_tac_abdomen_contraste`<br>`test_rag_grounding.py::test_rag_grounding_especialidad_cardiologia`<br>`test_rag_grounding.py::test_rag_abstention_on_unknown_procedure`<br>`test_agent_orchestrator.py::test_rag_synthesis_no_raw_dump`<br>`test_agent_orchestrator.py::test_golden_rule_of_abstention` | ✅ PASSED |
| **RF-03** | **Bypass Determinista de Código Rojo** | Intercepción de ultra baja latencia ante banderas rojas de riesgo vital (ESI 1-2: coronario, ACV FAST, asfixia, anafilaxia, trauma, suicidio), emitiendo derivación inmediata al SAMU 131. | `test_emergency_bypass.py::test_emergency_bypass_latency_benchmark`<br>`test_emergency_bypass.py::test_emergency_red_flags_detection` [6 casos]<br>`test_agent_orchestrator.py::test_emergency_bypass_in_agent` | ✅ PASSED |
| **RF-04** | **Tool Calling y Agendamiento Transaccional HIS** | Invocación de herramientas sobre Mock HIS SQLite para consulta de cupos por comuna/especialidad, reserva atómica con validación de RUT chileno, prevención de doble agendamiento y cancelación autenticada. | `test_tool_calling.py::test_consultar_citas_filtro_especialidad`<br>`test_tool_calling.py::test_consultar_citas_filtro_comuna`<br>`test_tool_calling.py::test_consultar_citas_sin_resultados`<br>`test_tool_calling.py::test_reservar_cita_exitosa`<br>`test_tool_calling.py::test_prevencion_doble_agendamiento_conflicto`<br>`test_tool_calling.py::test_reservar_cita_inexistente`<br>`test_tool_calling.py::test_cancelar_cita_y_liberar_cupo`<br>`test_agent_orchestrator.py::test_conversational_memory_and_tool_calling`<br>`test_agent_orchestrator.py::test_booking_with_rut_validation` | ✅ PASSED |

---

### 3.2 Requerimientos No Funcionales (RNF)

| ID | Requerimiento No Funcional | Criterio de Aceptación / Métricas de Calidad | Tests Automatizados que lo Validan | Estado |
|---|---|---|---|:---:|
| **RNF-01** | **Protección de Datos Personales (PII)** | Anonimización y enmascaramiento estricto de RUT chileno (con y sin puntos), números de teléfono móviles/fijos (+56 9) y correos electrónicos antes de invocar cualquier modelo generativo (Ley N° 20.584). | `test_emergency_bypass.py::test_pii_anonymizer_rut`<br>`test_emergency_bypass.py::test_pii_anonymizer_phone_and_email` | ✅ PASSED |
| **RNF-02** | **Rendimiento y Latencia Determinista** | El guardrail de Código Rojo debe evaluar el mensaje y responder en $<100$ ms (meta: $<5$ ms) de forma previa a cualquier llamada a API externa. | `test_emergency_bypass.py::test_emergency_bypass_latency_benchmark`<br>`test_agent_orchestrator.py::test_emergency_bypass_in_agent` | ✅ PASSED |
| **RNF-03** | **Control de Alucinaciones y Memoria Conversacional** | Prohibición absoluta de volcado de metadatos internos (`[Documento 1 | ...]`), inclusión de citas `[Ref: Protocolo XXX]`, retención de contexto en ventana deslizante ($k=5$) y regla de abstención institucional. | `test_agent_orchestrator.py::test_rag_synthesis_no_raw_dump`<br>`test_agent_orchestrator.py::test_conversational_memory_and_tool_calling`<br>`test_agent_orchestrator.py::test_golden_rule_of_abstention`<br>`test_rag_grounding.py::test_rag_abstention_on_unknown_procedure` | ✅ PASSED |

---

## 4. Conclusión Técnica de la Auditoría de Pruebas

1. **Aislamiento y Reproducibilidad:** Todas las pruebas utilizan bases de datos SQLite temporales y ChromaDB efímero con embeddings deterministas, garantizando que el 100% de la suite pueda ejecutarse en cualquier entorno sin depender de conexión a internet ni consumir tokens de API.
2. **Cero Falsos Positivos en Banderas Rojas:** Las pruebas de consultas rutinarias (`test_non_emergency_queries_pass_through`) confirmaron que solicitudes ambulatorias estándar no activan erróneamente el bypass de Código Rojo.
3. **Integridad Transaccional Comprobada:** Se verificó el rechazo exitoso de dobles reservas (`test_prevencion_doble_agendamiento_conflicto`), validando el aislamiento ACID sobre el sistema hospitalario Mock HIS.
4. **Cumplimiento Integral de la Evaluación:** La suite satisface en su totalidad los requerimientos funcionales (RF-01 a RF-04) y no funcionales (RNF-01 a RNF-03) exigidos en la pauta de evaluación Duoc UC para la asignatura ISY0101.
