# Guion de la demo en vivo

**Duración objetivo:** 6 minutos dentro de los 10 de exposición.
**Caso organizacional:** la red SaludConecta automatiza un agendamiento de imagenología, donde un examen mal preparado se pierde.
**Muestra:** autonomía, 3 replanificaciones (2 en la primera sesión, 1 en la segunda), memoria entre sesiones y Código Rojo.

Todos los inputs de este guion se ejecutaron con el planificador por reglas y con LLM real, y producen el resultado descrito. Con LLM activo, la redacción de algunas respuestas puede variar.

## Preparación (antes de presentar)

```powershell
.\venv\Scripts\Activate.ps1
python scripts/init_data.py --reset
streamlit run app.py
```

> `--reset` borra reservas, memoria y traza locales. Es necesario para que los cupos estén libres.

Dejen abierta una segunda terminal con el plan B listo. Abran el primer mensaje del panel "Traza de decisiones" una vez antes de presentar, para confirmar que carga.

## Acto 1: agendamiento con conflicto (2 min 30 s)

En la barra lateral, seleccionen **PAC-001 · Juan Pérez Soto**. Muestren el panel "Memoria del paciente": metformina registrada.

| # | Copiar y pegar | Qué mostrar |
|---|---|---|
| 1 | `Necesito un TAC de abdomen con contraste en Maipú` | Abrir la traza. **Replanificación 1:** `REPLAN` por `SIN_CUPOS`, plan v2 |
| 2 | `la cita 26` | **Replanificación 2:** `CONFLICTO_PREPARACION`. No pidió datos: los tomó de la memoria. La cita aún no se reserva |
| 3 | `confirmo` | Reserva, indicaciones y comprobante. El panel de memoria ya muestra la cita |

## Acto 2: continuidad (1 min 30 s)

Presionen **Reiniciar Conversación**. Esto borra el corto plazo y conserva el largo plazo. Expliquen la diferencia.

| # | Copiar y pegar | Qué mostrar |
|---|---|---|
| — | (El recordatorio aparece solo) | El agente recuerda la cita #26 y su preparación |
| 4 | `Quiero reprogramar mi cita` | Dedujo la cita desde la memoria y aplicó la sede preferida. **Replanificación 3:** no hay cupos de mañana |
| 5 | `la cita 27` | Vuelve a validar y a advertir |
| 6 | `confirmo` | Reprogramación atómica |

## Acto 3: seguridad (2 min)

Seleccionen **PAC-002 · María González Rojas**.

| # | Copiar y pegar | Qué mostrar |
|---|---|---|
| 7 | `Necesito hora de medicina general en La Florida` | Plan activo, cupos 6 y 7 |
| 8 | `Quiero la cita 6, pero me duele mucho el pecho` | `CODIGO_ROJO` y `ABORTO`. Latencia del guardrail y reserva no ejecutada |
| 9 | `¿Cuál es la preparación para una biopsia hepática espacial de astronautas en gravedad cero?` | `ABSTENCION`: no inventa y deriva a un humano |

Activen **5. Simular caída del HIS**.

| # | Copiar y pegar | Qué mostrar |
|---|---|---|
| 10 | `Necesito hora de medicina general` | `degradar`: mensaje controlado, sin excepción |

Desactiven el interruptor al terminar.

## Plan B: falla la API o la red

La demo no depende de la API. Sin credenciales válidas, el agente usa el planificador por reglas y el motor autónomo, y el recorrido anterior funciona igual. Si la red está lenta, cada turno puede esperar el tiempo límite del LLM. En ese caso dejen `OPENROUTER_API_KEY` vacía en `.env` y reinicien Streamlit.

Si falla Streamlit, ejecuten en la terminal:

```powershell
python scripts/run_demo_scenarios.py
```

Imprime los 6 escenarios con su traza y un resumen OK/FALLA, sin tocar la BD local. Los mismos turnos se pueden hacer a mano:

```powershell
python -m src.agent_orchestrator --paciente PAC-001
```

## Antes de presentar

- [ ] Ensayar el guion completo con cronómetro.
- [ ] Confirmar que la key de `.env` sigue activa si van a mostrar el modo con LLM real.
- [ ] Avisar que, con LLM real, los turnos con planificación tardan cerca de 2 a 7 segundos.
- [ ] Definir quién conduce la demo y quién narra.
<!-- A COMPLETAR POR EL EQUIPO: reparto de la demo y frase de cierre -->
