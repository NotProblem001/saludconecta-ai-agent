# Estructura propuesta para la presentación

**Formato:** 20 minutos: 10 de exposición y 10 de preguntas.
**Reparto:** 5 minutos para cada integrante. I1 = Matias Araos. I2 = `[NOMBRE INTEGRANTE 2]`.

| # | Diapositiva | Min | Quién | Contenido | Fuente en el repo |
|---|---|---:|:---:|---|---|
| 1 | Problema organizacional | 1:00 | I1 | Saturación, exámenes suspendidos y riesgo inadvertido. De chatbot a agente | `README.md` |
| 2 | Arquitectura | 1:00 | I1 | Diagrama por capas y tres categorías de herramientas | `docs/arquitectura_ep2.md` §1 |
| 3 | Justificación de la orquestación | 1:15 | I1 | Comparación con Haystack y AutoGen. Evidencia: ejecutor único e invariantes | ADR-001 y ADR-002 |
| 4 | Memoria | 1:00 | I2 | Corto y largo plazo, qué se guarda y qué no | `docs/arquitectura_ep2.md` §4, ADR-003 |
| 5 | Planificación adaptativa | 1:00 | I2 | Grafo de estados y disparadores de replanificación | `docs/arquitectura_ep2.md` §3 |
| 6 | Demo en vivo | 3:30 | I1 conduce, I2 narra | Actos 1 a 3. Se alternan para repartir 1:45 cada uno | `docs/guion_demo.md` |
| 7 | Métricas y KPIs | 0:45 | I2 | Evidencia medida frente a metas | `tests/TEST_EVIDENCE.md` |
| 8 | Cierre | 0:30 | I2 | Conclusiones y aprendizajes del equipo | Redacción propia |

Tiempos por integrante: I1 = 1:00 + 1:00 + 1:15 + 1:45 = 5:00. I2 = 1:00 + 1:00 + 1:45 + 0:45 + 0:30 = 5:00. Ajusten al ensayar.

## Diapositiva 7: datos para mostrar

| Indicador | Valor | Tipo |
|---|---|---|
| Pruebas automatizadas | Ver `tests/TEST_EVIDENCE.md` | Medido |
| Cobertura de `src/` | Ver `tests/TEST_EVIDENCE.md` | Medido |
| Escenarios adaptativos | 6 de 6 en `run_demo_scenarios.py` | Medido, en entorno controlado |
| Latencia del bypass Código Rojo | Se muestra en el mensaje durante la demo | Medido en vivo |
| Exámenes suspendidos, de 22 % a menos de 13 % | Línea base y meta de EP1 | **Simulado, sin medición real** |
| Derivación correcta, de 68 % a más de 90 % | Línea base y meta de EP1 | **Simulado, sin medición real** |

No presenten los KPIs de EP1 como resultados. El sistema no se probó con pacientes reales, y los escenarios demuestran comportamiento, no impacto.

## Preguntas probables

Preparen estas respuestas con sus propias palabras:

1. ¿Por qué el LLM no ejecuta las herramientas directamente?
2. ¿Qué pasa si el LLM propone un plan peligroso?
3. ¿Por qué SQLite y no memoria vectorial?
4. ¿Qué tan confiable es el umbral 0.75 con los embeddings actuales?
5. ¿Qué emergencias podría no detectar el guardrail?
6. ¿Qué datos personales se guardan y dónde?
7. ¿Cómo usaron IA en el desarrollo?

<!-- A COMPLETAR POR EL EQUIPO: conclusiones, justificación crítica y reflexiones individuales -->
