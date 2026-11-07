# Arquitectura del agente SaludConecta (EP2)

Todos los diagramas describen el código actual. El grafo de la sección 3 corresponde a `GrafoAgente._construir` en `src/agent_graph.py`.

## 1. Arquitectura por capas

```mermaid
flowchart TB
    subgraph C1["Capa 1: Canales"]
        UI["Streamlit: app.py"]
        CLI["CLI: src.agent_orchestrator"]
        DEMO["scripts/run_demo_scenarios.py"]
    end

    subgraph C2["Capa 2: Seguridad"]
        GR["EmergencyBypassGuardrail<br/>Código Rojo antes del LLM"]
        PII["PIIAnonymizer<br/>RUT, teléfono, correo"]
    end

    subgraph C3["Capa 3: Orquestación (LangGraph)"]
        FACHADA["SaludConectaAgent<br/>fachada de sesión"]
        GRAFO["GrafoAgente: StateGraph"]
        PLAN["planner.py<br/>plan LLM o reglas + invariantes"]
        TRAZA["decision_trace.py"]
    end

    subgraph C4["Capa 4: Herramientas"]
        CONS["Consulta"]
        ESC["Escritura"]
        RAZ["Razonamiento"]
    end

    subgraph C5["Capa 5: Memoria"]
        CP["Corto plazo<br/>ventana k=5 + EstadoTarea"]
        LP["Largo plazo<br/>MemoriaLargoPlazo"]
    end

    subgraph C6["Capa 6: Datos y modelos"]
        SQLITE[("SQLite<br/>Mock HIS, memoria, traza")]
        CHROMA[("ChromaDB<br/>manuales")]
        LLM["LLM compatible con OpenAI<br/>opcional"]
        FILES["comprobantes/*.txt"]
    end

    C1 --> FACHADA --> GRAFO
    GRAFO --> GR
    GRAFO --> PII
    GRAFO --> PLAN
    GRAFO --> TRAZA
    GRAFO --> C4
    GRAFO --> C5
    PLAN -.-> LLM
    CONS --> SQLITE
    CONS --> CHROMA
    ESC --> SQLITE
    ESC --> FILES
    RAZ --> SQLITE
    LP --> SQLITE
    TRAZA --> SQLITE
```

### Herramientas por categoría

| Categoría | Herramienta | Módulo | Función |
|---|---|---|---|
| Consulta | `buscar_protocolo_rag` | `src/tools/consulta.py` | Preparación y convenios en los manuales, con umbral |
| Consulta | `consultar_catalogo_especialidad` | `src/tools/consulta.py` | Prerrequisito clínico de una especialidad |
| Consulta | `consultar_disponibilidad_horas` | `src/tools/consulta.py` | Cupos por especialidad, sede, fecha y franja |
| Consulta | `consultar_historial_paciente` | `src/tools/consulta.py` | Citas, atenciones, indicaciones y preferencias |
| Escritura | `reservar_cita_medica` | `src/tools/escritura.py` | Reserva atómica |
| Escritura | `cancelar_cita_medica` | `src/tools/escritura.py` | Cancelación con verificación del titular |
| Escritura | `reprogramar_cita` | `src/tools/escritura.py` | Traslado de cupo en una sola transacción |
| Escritura | `registrar_atencion` | `src/tools/escritura.py` | Resumen de la atención en el HIS |
| Escritura | `generar_comprobante` | `src/tools/escritura.py` | Archivo `.txt` sin RUT ni teléfono, más registro de indicaciones |
| Razonamiento | `clasificar_solicitud` | `src/tools/razonamiento.py` | Intención, especialidad, protocolo y ESI preliminar |
| Razonamiento | `validar_reglas` | `src/tools/razonamiento.py` | Cupo vigente, colisión horaria, fármacos, alergias y ayuno |
| Razonamiento | `seleccionar_siguiente_accion` | `src/tools/razonamiento.py` | Política determinista de la siguiente acción |

Cada herramienta tiene esquema de entrada y salida en `src/tools/schemas.py`. El decorador de `src/tools/base.py` aporta logging, reintentos ante fallas de BD y errores tipados.

## 2. Secuencia de un flujo completo

Agendamiento de TAC con contraste para un paciente en tratamiento con metformina, sin cupos en la sede pedida.

```mermaid
sequenceDiagram
    actor P as Paciente
    participant G as Grafo
    participant S as Guardrail y PII
    participant M as Memoria
    participant PL as Planificador
    participant T as Herramientas
    participant H as Mock HIS

    P->>G: Necesito un TAC con contraste en Maipú
    G->>S: Evaluar riesgo vital y anonimizar
    S-->>G: Sin emergencia, texto sanitizado
    G->>M: Cargar contexto del paciente
    M-->>G: Fármacos: metformina
    G->>PL: Crear plan
    PL-->>G: Plan v1 validado por invariantes
    G->>T: consultar_disponibilidad_horas (Maipú)
    T->>H: Consulta de cupos
    H-->>T: 0 cupos
    T-->>G: total=0
    G->>PL: Replanificar por SIN_CUPOS
    PL-->>G: Plan v2 sin filtro de sede
    G->>T: consultar_disponibilidad_horas
    T-->>G: 3 cupos
    G-->>P: Propone cupos y queda esperando

    P->>G: la cita 26
    G->>S: Evaluar riesgo vital y anonimizar
    G->>T: validar_reglas
    T-->>G: Conflicto FARMACO_CONTRASTE
    G->>PL: Replanificar por CONFLICTO_PREPARACION
    PL-->>G: Plan v3 con advertir_y_confirmar
    G-->>P: Advierte y pide confirmar

    P->>G: confirmo
    G->>S: Evaluar riesgo vital y anonimizar
    G->>T: reservar_cita_medica
    T->>H: Transacción atómica
    G->>T: generar_comprobante y registrar_atencion
    G->>M: Guardar preferencias y traza
    G-->>P: Reserva, indicaciones y comprobante
```

## 3. Grafo del planificador

```mermaid
stateDiagram-v2
    [*] --> guardrail
    guardrail --> abortar_plan: riesgo vital
    guardrail --> cargar_contexto: sin emergencia
    abortar_plan --> persistir
    cargar_contexto --> planificar
    planificar --> ejecutar_paso: plan nuevo o reanudado
    planificar --> responder: consulta lateral o paciente desiste
    ejecutar_paso --> evaluar
    evaluar --> ejecutar_paso: continuar
    evaluar --> replanificar: SIN_CUPOS, CONFLICTO_PREPARACION, CUPO_NO_DISPONIBLE, COLISION_HORARIO
    evaluar --> responder: esperar, abstener, degradar o finalizar
    replanificar --> ejecutar_paso: plan corregido
    replanificar --> responder: sin alternativas
    responder --> persistir
    persistir --> [*]
```

Cada turno recorre el grafo desde `guardrail`. El estado entre turnos vive en la sesión (`EstadoTarea`), de modo que un plan en espera siempre vuelve a pasar por el Código Rojo.

### Disparadores de replanificación

| Motivo | Origen | Cambio en el plan |
|---|---|---|
| `SIN_CUPOS` | `total_cupos == 0` | Quita la franja y luego la sede. Sin filtros, deriva a Mesa Central |
| `CONFLICTO_PREPARACION` | `validar_reglas` con conflictos | Inserta `advertir_y_confirmar` antes de escribir |
| `CUPO_NO_DISPONIBLE` | Cupo tomado por otro paciente | Descarta el cupo y la confirmación; busca de nuevo |
| `COLISION_HORARIO` | El paciente ya tiene otra cita a esa hora | Igual que el anterior |

Fuera de la replanificación, `abstener` cierra el plan sin LLM y `degradar` entrega un mensaje controlado.

### Invariantes del plan

`asegurar_invariantes` en `src/planner.py` se aplica a todo plan, venga del LLM o de las reglas:

1. Solo herramientas registradas o pasos internos conocidos.
2. Sin RUT, nombre ni teléfono en los argumentos.
3. Toda reserva o reprogramación va precedida de `solicitar_datos` y `validar_reglas`.
4. Toda cancelación va precedida de `solicitar_datos`.
5. Una consulta de preparación siempre pasa por `buscar_protocolo_rag`.
6. La intención declarada debe tener su paso clave, y `elegir_cupo` exige una búsqueda previa.
7. El plan del LLM debe concordar con la intención reconocida por las reglas (`_concuerda_con_reglas`). Si las reglas no reconocen la solicitud, el LLM puede proponer lecturas o una búsqueda de cupos, pero nunca cancelar, reprogramar ni reservar un cupo directo.

Un plan que no se puede corregir se descarta y se usa el plan por reglas. Los argumentos de cada herramienta los resuelve el ejecutor desde el estado de la tarea: los que proponga el LLM se ignoran.

## 4. Flujo de memoria

```mermaid
flowchart LR
    subgraph Lectura["Recuperación"]
        L1["Primer turno de la sesión"] --> L2["cargar_contexto"]
        L2 --> L3["ContextoPaciente"]
        L3 --> L4["Recordatorio al paciente"]
        L3 --> L5["[MEMORIA_PACIENTE] en el prompt"]
        L3 --> L6["Datos y filtros de la tarea"]
    end

    subgraph Corto["Corto plazo (sesión)"]
        C1["MemoriaVentana k=5<br/>solo texto anonimizado"]
        C2["EstadoTarea<br/>plan, paso, datos"]
    end

    subgraph Escritura["Escritura"]
        E1["Nodo persistir"] --> E2["Ventana conversacional"]
        E1 --> E3["Preferencias de sede y franja"]
        E1 --> E4["Traza de decisiones"]
        E5["registrar_atencion"] --> E6["Tabla atenciones"]
        E7["generar_comprobante"] --> E8["Tabla indicaciones"]
    end

    DB[("SQLite")]
    DB --> L2
    E3 --> DB
    E4 --> DB
    E6 --> DB
    E8 --> DB
    L6 --> C2
    E2 --> C1
```

| Dato | Dónde se guarda | Vigencia | Llega al LLM |
|---|---|---|---|
| Conversación anonimizada | `MemoriaVentana` | Sesión, últimos 5 turnos | Sí |
| Plan y datos recolectados | `EstadoTarea` | Hasta cerrar la tarea | RUT, teléfono y nombre conocido: no |
| Fármacos, alergias y prerrequisitos | Tablas `pacientes` e `indicaciones` | Entre sesiones | Fármacos y alergias: sí |
| Sede y franja preferidas | Tabla `preferencias` | Entre sesiones | Sí |
| Atenciones previas | Tabla `atenciones` | Entre sesiones | Sí, resumidas |
| RUT y teléfono | Tablas `pacientes` y `citas` | Entre sesiones | No |

Una cita se considera pendiente si está `RESERVADA`. No se compara con el reloj porque el Mock HIS es un calendario simulado.
