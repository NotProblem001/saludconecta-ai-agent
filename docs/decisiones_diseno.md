# Registro de decisiones de diseño (ADR)

Cada registro entrega contexto, decisión, alternativas y consecuencias técnicas. La justificación crítica final es responsabilidad del equipo y queda marcada para completar sin IA.

## ADR-001: Framework de agentes

**Contexto.** El agente debe combinar herramientas, memoria y replanificación, con intercepción garantizada antes del LLM y una traza consultable.

**Decisión.** LangGraph `StateGraph` sobre componentes de LangChain.

| Criterio | LangGraph | LangChain con tool calling | Haystack Agents | AutoGen |
|---|---|---|---|---|
| Modelo de ejecución | Grafo de estados explícito | Bucle agente-herramientas | Componente Agent dentro de pipelines | Conversación entre agentes |
| Nodo obligatorio antes del LLM | Se modela como arista de entrada | Requiere middleware o envoltura | Requiere componer el pipeline | Requiere un agente o interceptor adicional |
| Reutilización de lo construido en EP1 | Alta: ya usa LangChain y ChromaDB | Alta | Baja: exige portar el RAG | Baja: exige rediseñar el flujo |
| Dependencia en el proyecto | Ya instalada con LangChain 1.x | Ya instalada | Nueva | Nueva |
| Ajuste al caso | Un agente con flujo controlado | Un agente con flujo decidido por el LLM | Fuerte en RAG y pipelines | Fuerte en colaboración multiagente |

**Consecuencias.** El flujo es verificable y cada rama se prueba sin LLM. A cambio hay más código propio que en un agente prefabricado, y las rutas nuevas deben declararse en el grafo.

<!-- A COMPLETAR POR EL EQUIPO: justificación crítica de la elección -->

## ADR-002: Estrategia de planificación

**Contexto.** Hay decisiones que no pueden depender de un modelo probabilístico: Código Rojo, abstención, bloqueo de escrituras y degradación.

**Decisión.** Plan-and-Execute. El LLM propone un plan JSON, las invariantes lo validan y un ejecutor determinista lo corre. Si falta el LLM o el plan es inválido, se usa un plan por reglas.

| Alternativa | Ventaja | Limitación en este caso |
|---|---|---|
| ReAct con `bind_tools` | Máxima flexibilidad del modelo | El LLM decide cada escritura y necesita ver sus argumentos, incluido el RUT |
| Plan-and-Execute (elegida) | Punto único de control y plan visible | Menor flexibilidad ante pedidos no previstos |
| Solo reglas | Totalmente determinista | Sin capacidad de planificar fuera de los casos programados |

**Consecuencias.** Se eliminó `bind_tools` de EP1. El agente opera sin LLM y sin perder las garantías de seguridad. Cuando el LLM propone un plan, solo puede elegir entre pasos permitidos.

<!-- A COMPLETAR POR EL EQUIPO: justificación crítica de la elección -->

## ADR-003: Tipo de memoria

**Contexto.** La pauta pide corto plazo, largo plazo por paciente y recuperación al iniciar sesión. La persistencia puede ser SQLite y/o una colección vectorial.

**Decisión.** Corto plazo con ventana k=5 y `EstadoTarea`. Largo plazo en SQLite, indexado por `paciente_id` simulado.

| Alternativa | Ventaja | Limitación en este caso |
|---|---|---|
| SQLite estructurado (elegida) | Consultas exactas: la cita pendiente se recupera sin ambigüedad | Sin búsqueda semántica sobre texto libre |
| Colección vectorial separada | Recuperación por similitud sobre episodios | Con los embeddings de respaldo sería coincidencia léxica; aporta poco a datos ya estructurados |
| Guardar la transcripción completa | Contexto total | Conserva PII y crece sin control |
| Resumen conversacional por LLM | Comprime la historia | Depende del LLM y agrega costo |

**Consecuencias.** No se guardan transcripciones. Los datos de memoria inyectados al prompt van delimitados como dato. No se implementó el borrado de datos a pedido del paciente.

<!-- A COMPLETAR POR EL EQUIPO: justificación crítica de la elección -->

## ADR-004: Umbral RAG de 0.75

**Contexto.** El umbral viene de EP1. La evaluación de EP2 reveló cómo se comporta en la práctica.

**Decisión.** Mantener 0.75 y hacer determinista la abstención: bajo el umbral, el LLM no redacta.

**Hallazgo técnico.** `get_embeddings` solo usa embeddings remotos si existe `OPENAI_API_KEY`. Con OpenRouter o sin credenciales se usa `DeterministicFallbackEmbeddings`, una representación léxica basada en hash, no semántica. Sus puntajes parten de un piso cercano a 0.68 por un vector base compartido.

| Consulta (embeddings de respaldo) | Similitud máxima | Resultado con 0.75 |
|---|---:|---|
| `resonancia magnetica de cerebro` | 0.881 | Recupera |
| `tomo metformina y tengo un tac de abdomen con contraste` | 0.827 | Recupera |
| `ayuno perfil lipidico` | 0.819 | Recupera |
| `que necesito para cardiologia` | 0.773 | Recupera |
| `hola quiero una hora al dentista` | 0.713 | Se abstiene |
| `biopsia hepatica espacial gravedad cero` | 0.686 | Se abstiene |

**Consecuencias.** El valor 0.75 está calibrado para los embeddings de respaldo y no se puede transferir a `text-embedding-3-small` sin medirlo de nuevo. Cambiar de embeddings exige reindexar: `python scripts/init_data.py --reset`. Esta evaluación usa 10 consultas de prueba, no un conjunto etiquetado.

<!-- A COMPLETAR POR EL EQUIPO: justificación crítica del umbral -->

## ADR-005: Guardrails

**Contexto.** En EP1, el texto crudo llegaba al LLM aunque RNF-01 indicaba lo contrario. Además, el Código Rojo no detectaba formas coloquiales.

**Decisión.**

1. El Código Rojo es el primer nodo de todos los turnos, también con un plan activo.
2. El LLM, la memoria y la traza reciben solo texto anonimizado. Los datos personales quedan en `EstadoTarea` y el ejecutor los resuelve.
3. Se agregaron patrones coloquiales de riesgo vital, sin quitar ninguno.
4. Toda escritura exige validación previa y, si hay conflicto, confirmación explícita.
5. El agente advierte y remite al médico tratante. No suspende ni ajusta tratamientos.

| Alternativa | Limitación |
|---|---|
| Clasificar el riesgo con LLM | Agrega latencia y dependencia externa en el caso más crítico |
| Anonimizar solo el mensaje actual | El historial reintroduce el PII en el siguiente turno |
| Dar el RUT al LLM para usar tool calling | Contradice la protección de datos declarada |

**Consecuencias.** La detección por expresiones regulares favorece no perder emergencias y acepta falsos positivos: "dolor de pecho leve hace un año, quiero control" activa el Código Rojo. Sigue habiendo frases que no detecta. Las reglas clínicas transcriben `data/manual_preparacion.md` y **requieren revisión del equipo antes de cualquier uso fuera del contexto académico**.

<!-- A COMPLETAR POR EL EQUIPO: justificación crítica de los guardrails -->

## ADR-006: Datos de demostración

**Decisión.** Fechas del CSV desplazadas 70 días, 5 cupos de examen nuevos y 3 pacientes simulados.

**Consecuencias.** Los pacientes son ficticios. Las bases locales creadas antes de este cambio conservan las fechas antiguas hasta ejecutar `python scripts/init_data.py --reset`, comando que borra reservas y memoria.
