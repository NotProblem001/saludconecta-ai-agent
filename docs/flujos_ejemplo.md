# Flujos de ejemplo con traza del agente

Conversaciones ejecutadas con el planificador por reglas (sin LLM), sobre una BD temporal. Las columnas de cada tabla resumen los eventos de la traza real. En la UI se ven en el panel "Traza de decisiones".

Tipos de evento: `PLAN_INICIAL`, `HERRAMIENTA`, `DECISION`, `REPLAN`, `PASO_INTERNO`, `REANUDACION`, `CODIGO_ROJO`, `ABORTO`, `ABSTENCION`, `DEGRADACION`, `MEMORIA`, `PREFERENCIA`.

## Flujo 1: agendamiento con dos replanificaciones

**Paciente:** PAC-001, con metformina registrada en su ficha.

**Turno 1:** *"Necesito un TAC de abdomen con contraste en Maipú"*

| Pensamiento | Herramienta | Observación | Decisión |
|---|---|---|---|
| Identificar qué necesita | `clasificar_solicitud` | Agendar, TAC con contraste, IMG-102 | Continuar |
| Buscar en la sede pedida | `consultar_disponibilidad_horas` | 0 cupos | **Replanificar: SIN_CUPOS** |
| Quitar la restricción de sede | `consultar_disponibilidad_horas` | 3 cupos | Continuar |
| El paciente debe elegir | `elegir_cupo` | Falta el cupo | Esperar |

Respuesta: "Sin cupos en Maipú: se amplía a otras sedes", seguida de los cupos 26, 27 y 28.

**Turno 2:** *"la cita 26"*

| Pensamiento | Herramienta | Observación | Decisión |
|---|---|---|---|
| Datos personales ya están en la ficha | `solicitar_datos` | Completos | Continuar |
| Validar antes de escribir | `validar_reglas` | Conflicto `FARMACO_CONTRASTE` | **Replanificar: CONFLICTO_PREPARACION** |
| La escritura queda bloqueada | `advertir_y_confirmar` | Sin confirmación | Esperar |

Respuesta: advertencia sobre metformina, remisión al médico tratante y cita al protocolo IMG-102. La cita sigue `DISPONIBLE`.

**Turno 3:** *"confirmo"*

| Pensamiento | Herramienta | Observación | Decisión |
|---|---|---|---|
| Confirmación recibida | `advertir_y_confirmar` | Confirmado | Continuar |
| Escribir en el HIS | `reservar_cita_medica` | Reserva confirmada | Continuar |
| Entregar indicaciones | `generar_comprobante` | Archivo generado | Continuar |
| Dejar registro para el futuro | `registrar_atencion` | Atención registrada | Finalizar |

## Flujo 2: el paciente vuelve otro día

**Paciente:** PAC-001, en un agente nuevo que solo comparte la BD con el flujo anterior.

**Al iniciar sesión:**

```text
t1 MEMORIA  Contexto cargado: 1 cita(s) pendiente(s), 1 atención(es), 2 preferencia(s)
```

Recordatorio: cita #26 pendiente, con la preparación entregada (metformina y ayuno de 6 horas).

**Turno:** *"Quiero reprogramar mi cita"*

| Pensamiento | Herramienta | Observación | Decisión |
|---|---|---|---|
| Aplicar la preferencia guardada | Memoria | Sede Santiago Centro, franja mañana | Plan de reprogramación |
| Hay una sola cita pendiente | `solicitar_datos` | Cita #26 deducida de la memoria | Continuar |
| Buscar según preferencias | `consultar_disponibilidad_horas` | 0 cupos en la mañana | **Replanificar: SIN_CUPOS** |
| Quitar la franja | `consultar_disponibilidad_horas` | Cupo 27 | Esperar elección |

Con *"la cita 27"* el agente vuelve a validar y advierte de nuevo. Con *"confirmo"* ejecuta `reprogramar_cita`, que mueve ambos cupos en una sola transacción.

## Flujo 3: riesgo vital durante un agendamiento

**Paciente:** PAC-002.

**Turno 1:** *"Necesito hora de medicina general en La Florida"*: el agente propone los cupos 6 y 7 y espera.

**Turno 2:** *"Quiero la cita 6, pero me duele mucho el pecho"*

```text
t2 CODIGO_ROJO  Se detectaron banderas rojas de riesgo vital: DOLOR_TORACICO_CORONARIO
t2 ABORTO       Riesgo vital durante el plan: no se ejecutan escrituras
```

| Pensamiento | Herramienta | Observación | Decisión |
|---|---|---|---|
| El guardrail corre antes que todo lo demás | Ninguna | Bandera roja | **Abortar plan** |

Respuesta: instrucciones de Código Rojo y SAMU 131. No hay llamadas al LLM en ese turno y la cita 6 sigue `DISPONIBLE`.

## Flujo 4: abstención por falta de respaldo

**Mensaje:** *"¿Cuál es la preparación para una biopsia hepática espacial de astronautas en gravedad cero?"*

| Pensamiento | Herramienta | Observación | Decisión |
|---|---|---|---|
| Consulta de preparación | `clasificar_solicitud` | Intención `preparacion` | Continuar |
| Buscar en los manuales | `buscar_protocolo_rag` | Ningún fragmento supera 0.75 | **Abstener** |

Respuesta: declara que la información no figura en los manuales y deriva al 600 000 1234. El LLM no redacta esta respuesta.

## Flujo 5: falla de la base de datos

**Mensaje con el HIS caído:** *"Necesito una hora de cardiología"*

| Pensamiento | Herramienta | Observación | Decisión |
|---|---|---|---|
| Identificar la solicitud | `clasificar_solicitud` | Cardiología Adulto | Continuar |
| Buscar cupos | `consultar_disponibilidad_horas` | 3 intentos fallidos, `BD_NO_DISPONIBLE` | **Degradar** |

Respuesta: agenda temporalmente no disponible, sin cambios en la agenda, derivación a Mesa Central. La traza queda en el log y en la sesión. Se persiste cuando la BD vuelve a estar disponible en esa sesión.
