"""
Grafo de estados del agente (LangGraph) - Red SaludConecta
Cada turno recorre: guardrail -> contexto -> plan -> pasos -> respuesta -> persistencia.
Las herramientas se invocan solo desde `ejecutar_paso`, de modo que reintentos, logging,
resolución de PII y bloqueo de escrituras queden en un único punto.
"""

import logging
import sqlite3
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from src.decision_trace import sin_pii
from src.memory import cargar_contexto, describir_cita
from src.planner import (
    ESPECIALIDAD_POR_DEFECTO,
    PASOS_INTERNOS,
    Paso,
    crear_plan,
    desiste,
    es_confirmacion,
    es_negativa,
    extraer_datos,
    replanificar,
)
from src.tools import REGISTRO
from src.tools.razonamiento import clasificar_texto

if TYPE_CHECKING:
    from src.agent_orchestrator import SaludConectaAgent

logger = logging.getLogger("saludconecta.graph")

DATOS_PACIENTE = ("rut", "nombre", "telefono", "farmacos", "alergias")
MENSAJE_SIN_CUPOS = (
    "⚠️ No encontré cupos disponibles para **{especialidad}** en la red. "
    "Por favor comuníquese con la **Mesa Central al 600 000 1234** para gestionar una alternativa."
)
ETIQUETA_DATO = {
    "rut": "**RUT en formato chileno válido** (ejemplo: 12.345.678-9 o 12345678-K)",
    "nombre": "**Nombre Completo**",
    "telefono": "**Teléfono de contacto**",
    "cita_id": "**ID de la cita**",
    "cita_actual": "**ID de la cita**",
}


class EstadoTurno(TypedDict, total=False):
    entrada: str
    sanitizado: str
    pii: List[Dict[str, str]]
    emergencia: Any
    extraido: Dict[str, Any]
    siguiente: str
    ultimo_paso: Optional[str]
    motivo_replan: Optional[str]
    salida_fallida: Any
    avisos: List[str]
    recordatorio: Optional[str]
    lateral: bool
    respuesta: Optional[str]
    tools_used: List[str]
    tiempo_guardrail_ms: float
    grounding_found: Optional[bool]
    rag_context: Optional[str]
    api_notice: Optional[str]


class GrafoAgente:
    """Construye y ejecuta el grafo; el estado entre turnos vive en el agente (sesión)."""

    def __init__(self, agente: "SaludConectaAgent"):
        self.a = agente
        self.grafo = self._construir()

    def _construir(self):
        g = StateGraph(EstadoTurno)
        for nombre in ("guardrail", "abortar_plan", "cargar_contexto", "planificar", "ejecutar_paso",
                       "evaluar", "replanificar", "responder", "persistir"):
            g.add_node(nombre, getattr(self, f"_{nombre}"))

        g.add_edge(START, "guardrail")
        g.add_conditional_edges("guardrail", lambda s: "abortar_plan" if s.get("emergencia") else "cargar_contexto")
        g.add_edge("abortar_plan", "persistir")
        g.add_edge("cargar_contexto", "planificar")
        g.add_conditional_edges("planificar", lambda s: s["siguiente"], ["ejecutar_paso", "responder"])
        g.add_edge("ejecutar_paso", "evaluar")
        g.add_conditional_edges("evaluar", lambda s: s["siguiente"], ["ejecutar_paso", "replanificar", "responder"])
        g.add_conditional_edges("replanificar", lambda s: s["siguiente"], ["ejecutar_paso", "responder"])
        g.add_edge("responder", "persistir")
        g.add_edge("persistir", END)
        return g.compile()

    def invocar(self, entrada: str) -> EstadoTurno:
        inicial: EstadoTurno = {"entrada": entrada, "tools_used": [], "avisos": []}
        return self.grafo.invoke(inicial, {"recursion_limit": 80})

    # --------------------------------------------------------------------------
    # Nodos de entrada
    # --------------------------------------------------------------------------

    def _guardrail(self, s: EstadoTurno) -> EstadoTurno:
        """Se ejecuta primero en todos los turnos, también con un plan en curso."""
        chequeo = self.a.emergency_guardrail.evaluate(s["entrada"])
        self.a.traza.turno += 1
        anonimizado = self.a.pii_anonymizer.anonymize(s["entrada"])
        return {
            "emergencia": chequeo if chequeo.is_emergency else None,
            "tiempo_guardrail_ms": chequeo.response_time_ms,
            "sanitizado": anonimizado.sanitized_text,
            "pii": anonimizado.detected_entities,
        }

    def _abortar_plan(self, s: EstadoTurno) -> EstadoTurno:
        chequeo = s["emergencia"]
        tarea = self.a.tarea
        self.a.traza.registrar("CODIGO_ROJO", chequeo.reason, ms=round(chequeo.response_time_ms, 2))
        if tarea.activa:
            omitidos = [p.herramienta for p in tarea.plan.pasos if p.estado in ("pendiente", "esperando")]
            for paso in tarea.plan.pasos:
                if paso.estado in ("pendiente", "esperando"):
                    paso.estado = "omitido"
            tarea.plan.estado = "abortado"
            self.a.traza.registrar("ABORTO", "Riesgo vital durante el plan: no se ejecutan escrituras", omitidos=omitidos)
            self.a.ultimo_plan = tarea.plan
            tarea.cerrar(conservar=DATOS_PACIENTE)
        if self.a.paciente_id:
            REGISTRO["registrar_atencion"].invoke({
                "paciente_id": self.a.paciente_id, "tipo": "codigo_rojo",
                "resumen": "Código Rojo activado; derivación a SAMU 131.",
            })
        return {"respuesta": chequeo.action_message}

    def _cargar_contexto(self, s: EstadoTurno) -> EstadoTurno:
        tarea = self.a.tarea
        recordatorio = None
        if self.a.traza.turno == 1 and self.a.paciente_id:
            recordatorio = self.a.cargar_memoria_paciente()

        paso = tarea.plan.siguiente if tarea.activa else None
        extraido = extraer_datos(s["entrada"], self.a.pii_anonymizer, paso.herramienta if paso else None)

        for clave in ("rut", "nombre", "telefono", "cita_id", "comuna", "franja"):
            if clave in extraido:
                tarea.datos[clave] = extraido[clave]
        for clave in ("farmacos", "alergias"):
            if clave in extraido:
                tarea.datos[clave] = sorted(set(tarea.datos.get(clave, [])) | set(extraido[clave]))
        if self.a.paciente_id and extraido.get("farmacos_declarados"):
            for farmaco in extraido["farmacos"]:
                self._memoria_segura(self.a.memoria.agregar_farmaco, self.a.paciente_id, farmaco)
        return {"extraido": extraido, "recordatorio": recordatorio, "sanitizado": self._sin_nombre(s["sanitizado"])}

    def _planificar(self, s: EstadoTurno) -> EstadoTurno:
        tarea, traza = self.a.tarea, self.a.traza

        if tarea.activa:
            paso = tarea.plan.siguiente
            if desiste(s["entrada"]) or (paso.herramienta == "advertir_y_confirmar" and es_negativa(s["entrada"])):
                self._cerrar_plan("abortado")
                traza.registrar("PLAN_CANCELADO", "El paciente desistió; no se ejecutan escrituras")
                return {"siguiente": "responder", "respuesta": (
                    "De acuerdo, detuve la solicitud y no se realizó ninguna reserva. "
                    "¿Le puedo orientar en algo más?"
                )}
            if self._aporta(paso, s):
                self._reanudar(paso, s)
                traza.registrar("REANUDACION", "El paciente entregó lo solicitado", paso=paso.herramienta)
                return {"siguiente": "ejecutar_paso"}
            if clasificar_texto(s["sanitizado"]).intencion in ("preparacion", "general", "historial"):
                traza.registrar("CONSULTA_LATERAL", "Se responde sin perder el plan en curso", paso=paso.herramienta)
                return {"siguiente": "responder", "lateral": True}
            traza.registrar("PLAN_REEMPLAZADO", "El paciente inició otra solicitud")
            self.a.ultimo_plan = tarea.plan
            tarea.cerrar(conservar=DATOS_PACIENTE + ("cita_id", "comuna", "franja"))

        plan, aviso = crear_plan(self.a.llm, s["sanitizado"], self._contexto_planificador(), tarea.datos, self.a.paciente_id)
        if aviso:
            traza.registrar("PLAN_LLM_DESCARTADO", aviso)
        tarea.plan = plan
        tarea.resultados = {}
        self._preparar_busqueda(s)
        traza.registrar(
            "PLAN_INICIAL", f"{plan.objetivo} (origen: {plan.origen})",
            pasos=plan.resumen(), busqueda=tarea.datos.get("busqueda"),
        )
        return {"siguiente": "ejecutar_paso"}

    def _sin_nombre(self, texto: str) -> str:
        """El anonimizador no reconoce nombres: se enmascara el nombre conocido de la tarea."""
        nombre = self.a.tarea.datos.get("nombre")
        return texto.replace(nombre, "[NOMBRE_PROTEGIDO]") if nombre else texto

    def _contexto_planificador(self) -> str:
        """Memoria del paciente y últimos turnos anonimizados, ambos delimitados como dato."""
        partes = [self.a.contexto.como_prompt()] if self.a.contexto else []
        recientes = self.a.memory.chat_memory.messages[-4:]
        if recientes:
            lineas = [f"{m.type}: {str(m.content)[:200]}" for m in recientes]
            partes.append("[CONVERSACION_RECIENTE]\n" + "\n".join(lineas) + "\n[/CONVERSACION_RECIENTE]")
        return "\n".join(partes)

    def _preparar_busqueda(self, s: EstadoTurno) -> None:
        """Fija los filtros de agenda; la preferencia guardada solo aplica si el paciente no indicó otra."""
        tarea = self.a.tarea
        preferencias = self.a.contexto.preferencias if self.a.contexto else {}
        if tarea.plan.intencion == "reprogramar" and tarea.datos.get("cita_id"):
            tarea.datos["cita_actual"] = tarea.datos.pop("cita_id")
        busqueda = {
            "especialidad": clasificar_texto(s["sanitizado"]).especialidad,
            "comuna": tarea.datos.get("comuna") or preferencias.get("sede"),
            "franja": tarea.datos.get("franja") or preferencias.get("franja"),
        }
        if tarea.plan.intencion == "agendar" and not busqueda["especialidad"]:
            busqueda["especialidad"] = ESPECIALIDAD_POR_DEFECTO
        tarea.datos["busqueda"] = busqueda
        usa_agenda = tarea.plan.indice("consultar_disponibilidad_horas") is not None
        if usa_agenda and not tarea.datos.get("comuna") and preferencias.get("sede"):
            self.a.traza.registrar("PREFERENCIA", f"Se usa la sede preferida: {preferencias['sede']}")

    def _aporta(self, paso: Paso, s: EstadoTurno) -> bool:
        """Indica si el mensaje responde a lo que el paso en espera necesita."""
        extraido = s["extraido"]
        if paso.herramienta == "advertir_y_confirmar":
            return es_confirmacion(s["entrada"])
        if paso.herramienta == "elegir_cupo":
            return any(k in extraido for k in ("cita_id", "comuna", "franja"))
        if paso.herramienta == "solicitar_datos":
            return any(k in extraido for k in ("rut", "nombre", "telefono", "cita_id"))
        return False

    def _reanudar(self, paso: Paso, s: EstadoTurno) -> None:
        tarea = self.a.tarea
        tarea.plan.estado = "en_curso"
        paso.estado = "pendiente"
        if paso.herramienta == "advertir_y_confirmar":
            tarea.datos["confirmado"] = True
        if paso.herramienta == "elegir_cupo" and "cita_id" not in s["extraido"]:
            # El paciente cambió de sede u horario: se repite la búsqueda con el nuevo filtro
            busqueda = tarea.datos["busqueda"]
            busqueda.update({k: s["extraido"][k] for k in ("comuna", "franja") if k in s["extraido"]})
            tarea.plan.pasos[tarea.plan.indice("consultar_disponibilidad_horas")].estado = "pendiente"

    # --------------------------------------------------------------------------
    # Ejecución y evaluación de pasos
    # --------------------------------------------------------------------------

    def _ejecutar_paso(self, s: EstadoTurno) -> EstadoTurno:
        tarea, traza = self.a.tarea, self.a.traza
        paso = tarea.plan.siguiente

        if paso.herramienta in PASOS_INTERNOS:
            self._paso_interno(paso)
            traza.registrar("PASO_INTERNO", paso.descripcion, paso=paso.herramienta, estado=paso.estado)
            return {"ultimo_paso": paso.herramienta, "salida_fallida": None}

        # Los argumentos salen del estado de la tarea: los del plan no deben pisar una búsqueda ya relajada
        args = self._resolver_args(paso.herramienta, s)
        salida = REGISTRO[paso.herramienta].invoke(args)
        tarea.resultados[paso.herramienta] = salida
        if salida.ok:
            paso.estado = "hecho"
        traza.registrar(
            "HERRAMIENTA", f"ok={salida.ok} error={salida.error}", paso=paso.herramienta, args=sin_pii(args),
        )
        return {
            "ultimo_paso": paso.herramienta,
            "tools_used": s["tools_used"] + [paso.herramienta],
            "salida_fallida": None if salida.ok else salida,
        }

    def _paso_interno(self, paso: Paso) -> None:
        datos = self.a.tarea.datos
        if paso.herramienta == "elegir_cupo":
            listo = bool(datos.get("cita_id"))
        elif paso.herramienta == "solicitar_datos":
            listo = not self._faltantes()
        elif paso.herramienta == "advertir_y_confirmar":
            listo = bool(datos.get("confirmado"))
        else:
            listo = True
        paso.estado = "hecho" if listo else "esperando"

    def _faltantes(self) -> List[str]:
        """Datos que faltan para la intención en curso; la cita se deduce de la memoria si hay una sola."""
        tarea = self.a.tarea
        datos = tarea.datos
        intencion = tarea.plan.intencion
        if intencion == "agendar":
            return [c for c in ("rut", "nombre", "telefono") if not datos.get(c)]

        clave = "cita_actual" if intencion == "reprogramar" else "cita_id"
        if intencion == "reprogramar" and datos.get("cita_id") and not datos.get("cita_actual"):
            datos["cita_actual"] = datos.pop("cita_id")
        if not datos.get("rut"):
            return ["rut"] if datos.get(clave) else ["rut", clave]

        pendientes = self._memoria_segura(self.a.memoria.citas_pendientes, datos["rut"]) or []
        if not datos.get(clave) and len(pendientes) == 1:
            datos[clave] = pendientes[0]["id"]
        if not datos.get(clave):
            return [clave]
        if intencion == "reprogramar":
            cita = next((c for c in pendientes if c["id"] == datos[clave]), None)
            if cita:
                datos["busqueda"]["especialidad"] = cita["especialidad"]
        return []

    def _resolver_args(self, herramienta: str, s: EstadoTurno) -> Dict[str, Any]:
        """El plan nunca lleva PII: aquí se completan los argumentos desde el estado de la tarea."""
        datos = self.a.tarea.datos
        persona = {
            "paciente_rut": datos.get("rut"), "paciente_nombre": datos.get("nombre"),
            "paciente_telefono": datos.get("telefono"),
        }
        if herramienta == "clasificar_solicitud":
            return {"texto": s["sanitizado"]}
        if herramienta == "buscar_protocolo_rag":
            return {"consulta": s["sanitizado"]}
        if herramienta == "consultar_catalogo_especialidad":
            return {"especialidad": datos["busqueda"].get("especialidad") or ESPECIALIDAD_POR_DEFECTO}
        if herramienta == "consultar_disponibilidad_horas":
            return dict(datos["busqueda"])
        if herramienta == "consultar_historial_paciente":
            return {"paciente_id": self.a.paciente_id}
        if herramienta == "validar_reglas":
            return {
                "cita_id": datos.get("cita_id"), "paciente_rut": datos.get("rut"),
                "farmacos": datos.get("farmacos", []), "alergias": datos.get("alergias", []),
            }
        if herramienta == "reservar_cita_medica":
            return {"cita_id": datos.get("cita_id"), **persona}
        if herramienta == "cancelar_cita_medica":
            return {"cita_id": datos.get("cita_id"), "paciente_rut": datos.get("rut")}
        if herramienta == "reprogramar_cita":
            return {
                "cita_actual": datos.get("cita_actual"), "cita_id": datos.get("cita_id"),
                "paciente_rut": datos.get("rut"),
            }
        if herramienta == "generar_comprobante":
            return {
                "cita_id": datos.get("cita_id"), "paciente_id": self.a.paciente_id,
                "indicaciones": self._indicaciones(),
            }
        if herramienta == "registrar_atencion":
            intencion = self.a.tarea.plan.intencion
            return {
                "paciente_id": self.a.paciente_id, "tipo": intencion, "cita_id": datos.get("cita_id"),
                "resumen": f"{self.a.tarea.plan.objetivo} (cita #{datos.get('cita_id')}, "
                           f"{datos.get('busqueda', {}).get('especialidad') or 'sin especialidad'})",
            }
        return {}

    def _indicaciones(self) -> List[str]:
        resultados = self.a.tarea.resultados
        validacion = resultados.get("validar_reglas")
        catalogo = resultados.get("consultar_catalogo_especialidad")
        textos: List[str] = []
        if validacion:
            textos += [c.mensaje for c in validacion.conflictos] + validacion.indicaciones
        if catalogo and catalogo.prerrequisito:
            textos.append(f"Prerrequisito: {catalogo.prerrequisito}")
        return textos

    def _evaluar(self, s: EstadoTurno) -> EstadoTurno:
        """Traduce la última observación a una decisión mediante la herramienta de razonamiento."""
        tarea, traza = self.a.tarea, self.a.traza
        plan = tarea.plan
        ultimo = s["ultimo_paso"]
        salida = tarea.resultados.get(ultimo)
        en_espera = plan.siguiente is not None and plan.siguiente.estado == "esperando"
        observacion: Dict[str, Any] = {
            "ultimo_paso": ultimo, "pasos_restantes": plan.pendientes, "esperando_paciente": en_espera,
        }
        if ultimo not in PASOS_INTERNOS and salida is not None:
            observacion.update(ok=salida.ok, error=salida.error)
            if ultimo == "consultar_disponibilidad_horas" and salida.ok:
                observacion["total_cupos"] = salida.total
            if ultimo == "buscar_protocolo_rag" and salida.ok:
                observacion["grounding_found"] = salida.grounding_found
            if ultimo == "validar_reglas" and salida.ok and plan.indice("advertir_y_confirmar") is None:
                observacion["conflictos_sin_confirmar"] = len(salida.conflictos)

        decision = REGISTRO["seleccionar_siguiente_accion"].invoke(observacion)
        traza.registrar("DECISION", f"{decision.accion}: {decision.motivo}", paso=ultimo)

        if decision.accion == "continuar":
            return {"siguiente": "ejecutar_paso"}
        if decision.accion == "replanificar":
            return {"siguiente": "replanificar", "motivo_replan": decision.motivo}
        plan.estado = {
            "esperar": "esperando_paciente", "abstener": "abstencion",
            "degradar": "degradado", "finalizar": "completado",
        }[decision.accion]
        return {"siguiente": "responder"}

    def _replanificar(self, s: EstadoTurno) -> EstadoTurno:
        tarea, traza = self.a.tarea, self.a.traza
        motivo = s["motivo_replan"]
        explicacion = replanificar(tarea.plan, motivo, tarea.datos)
        if explicacion is None:
            traza.registrar("SIN_ALTERNATIVAS", f"{motivo}: se deriva a Mesa Central")
            tarea.plan.estado = "completado"
            especialidad = tarea.datos.get("busqueda", {}).get("especialidad", "su solicitud")
            return {"siguiente": "responder", "respuesta": MENSAJE_SIN_CUPOS.format(especialidad=especialidad)}
        traza.registrar(
            "REPLAN", explicacion, paso=s["ultimo_paso"], motivo_codigo=motivo,
            version=tarea.plan.version, pasos=tarea.plan.resumen(),
        )
        return {"siguiente": "ejecutar_paso", "avisos": s["avisos"] + [explicacion]}

    # --------------------------------------------------------------------------
    # Respuesta y persistencia
    # --------------------------------------------------------------------------

    def _responder(self, s: EstadoTurno) -> EstadoTurno:
        cambios: EstadoTurno = {}
        tarea = self.a.tarea
        plan = tarea.plan
        respuesta = s.get("respuesta")

        rag = tarea.resultados.get("buscar_protocolo_rag")
        if rag is not None:
            cambios.update(grounding_found=rag.grounding_found, rag_context=rag.contexto)

        if respuesta:
            pass
        elif s.get("lateral"):
            directa = self.a.responder_directo(s["entrada"], s["sanitizado"], s["tools_used"])
            cambios.update(directa["estado"])
            respuesta = f"{directa['respuesta']}\n\n⏳ *Su solicitud sigue pendiente: {plan.objetivo.lower()}.*"
        elif plan.estado == "esperando_paciente":
            respuesta = self._pedir_al_paciente(plan.siguiente, s)
        elif plan.estado == "abstencion":
            self.a.traza.registrar("ABSTENCION", "Sin respaldo documental: se deriva a un humano")
            respuesta = rag.sintesis
        elif plan.estado == "degradado":
            respuesta = self._mensaje_degradado()
        elif s.get("salida_fallida") is not None:
            respuesta = f"⚠️ {s['salida_fallida'].mensaje}"
        else:
            respuesta, adicionales = self._respuesta_final(s, plan.intencion, rag)
            cambios.update(adicionales)

        if s.get("recordatorio"):
            respuesta = f"{s['recordatorio']}\n\n{respuesta}"
        return cambios | {"respuesta": respuesta}

    def _respuesta_final(self, s: EstadoTurno, intencion: str, rag: Any) -> tuple:
        resultados = self.a.tarea.resultados
        if intencion == "preparacion":
            texto, aviso = self.a.invocar_llm(s["sanitizado"], rag.contexto, True)
            return texto or rag.sintesis, {"api_notice": aviso}
        if intencion == "historial":
            return self._texto_historial(resultados["consultar_historial_paciente"]), {}
        if intencion in ("agendar", "cancelar", "reprogramar"):
            escritura = next(
                resultados[h] for h in ("reservar_cita_medica", "cancelar_cita_medica", "reprogramar_cita")
                if h in resultados
            )
            partes = [escritura.mensaje]
            indicaciones = self._indicaciones()
            if indicaciones and intencion != "cancelar":
                partes.append("🧾 **Indicaciones registradas:**\n" + "\n".join(f"• {i}" for i in indicaciones))
            comprobante = resultados.get("generar_comprobante")
            if comprobante and comprobante.ok:
                partes.append(f"📄 {comprobante.mensaje}")
            return "\n\n".join(partes), {}
        directa = self.a.responder_directo(s["entrada"], s["sanitizado"], s["tools_used"])
        return directa["respuesta"], directa["estado"]

    def _pedir_al_paciente(self, paso: Paso, s: EstadoTurno) -> str:
        tarea = self.a.tarea
        if paso.herramienta == "elegir_cupo":
            consulta = tarea.resultados["consultar_disponibilidad_horas"]
            lineas = [f"• **ID {c.id}** | {describir_cita(c.model_dump())} | {c.prevision}" for c in consulta.cupos]
            encabezado = "🩺 **Cupos disponibles:**"
            if s["avisos"]:
                aviso = s["avisos"][-1]
                encabezado = f"🔄 {aviso[0].upper()}{aviso[1:]}.\n\n{encabezado}"
            catalogo = tarea.resultados.get("consultar_catalogo_especialidad")
            nota = f"\n\n💡 *Prerrequisito:* {catalogo.prerrequisito}" if catalogo and catalogo.prerrequisito else ""
            return f"{encabezado}\n" + "\n".join(lineas) + nota + "\n\n*Indique el ID del cupo que prefiere.*"
        if paso.herramienta == "solicitar_datos":
            etiquetas = [ETIQUETA_DATO[c] for c in self._faltantes()]
            faltantes = " y ".join(filter(None, [", ".join(etiquetas[:-1]), etiquetas[-1]]))
            cita = tarea.datos.get("cita_id")
            return f"Para continuar{f' con el cupo #{cita}' if cita else ''} necesito su {faltantes}."
        conflictos = tarea.resultados["validar_reglas"].conflictos
        lineas = [f"• {c.mensaje} [Ref: Protocolo {c.protocolo}]" for c in conflictos]
        return (
            "⚠️ **Advertencia antes de confirmar:**\n" + "\n".join(lineas) +
            "\n\nResponda **confirmo** para mantener el agendamiento o **no** para detenerlo."
        )

    def _mensaje_degradado(self) -> str:
        resultados = self.a.tarea.resultados
        escritura = next(
            (resultados[h] for h in ("reservar_cita_medica", "cancelar_cita_medica", "reprogramar_cita")
             if h in resultados and resultados[h].ok),
            None,
        )
        if escritura:
            return (
                f"{escritura.mensaje}\n\n⚠️ La operación quedó registrada, pero el sistema no pudo completar "
                "el comprobante. Puede solicitarlo a la **Mesa Central al 600 000 1234**."
            )
        return (
            "⚠️ **Sistema de agenda temporalmente no disponible.** Reintenté la operación y no fue posible "
            "completarla; no se realizó ningún cambio en su agenda. Intente nuevamente en unos minutos o "
            "comuníquese con la **Mesa Central al 600 000 1234**."
        )

    def _texto_historial(self, historial: Any) -> str:
        if not historial.ok:
            return f"⚠️ {historial.mensaje}"
        lineas = [f"• Cita #{c.id}: {describir_cita(c.model_dump())}" for c in historial.citas_pendientes]
        lineas += [f"• {a['fecha'][:10]}: {a['resumen']}" for a in historial.atenciones[:3]]
        return "🗂️ **Su historial en SaludConecta:**\n" + "\n".join(lineas) if lineas else "No registra citas ni atenciones."

    def _persistir(self, s: EstadoTurno) -> EstadoTurno:
        a = self.a
        a.memory.chat_memory.add_user_message(self._sin_nombre(s["sanitizado"]))
        a.memory.chat_memory.add_ai_message(self._sin_nombre(a.pii_anonymizer.anonymize(s["respuesta"]).sanitized_text))

        tarea = a.tarea
        if tarea.plan is not None:
            a.ultimo_plan = tarea.plan
            if a.paciente_id and tarea.plan.intencion in ("agendar", "reprogramar"):
                self._guardar_preferencias()
            if tarea.plan.estado in ("completado", "abortado", "abstencion", "degradado"):
                tarea.cerrar(conservar=DATOS_PACIENTE)
            if a.paciente_id:
                a.contexto = self._memoria_segura(cargar_contexto, a.paciente_id, a.memoria) or a.contexto
        a.traza.persistir()
        return {}

    def _guardar_preferencias(self) -> None:
        tarea = self.a.tarea
        hecha = any(
            tarea.resultados.get(h) is not None and tarea.resultados[h].ok
            for h in ("reservar_cita_medica", "reprogramar_cita")
        )
        cita = self._memoria_segura(self.a.memoria.obtener_cita, tarea.datos.get("cita_id")) if hecha else None
        if cita:
            franja = "mañana" if int(cita["hora"][:2]) < 13 else "tarde"
            self._memoria_segura(self.a.memoria.guardar_preferencia, self.a.paciente_id, "sede", cita["comuna"])
            self._memoria_segura(self.a.memoria.guardar_preferencia, self.a.paciente_id, "franja", franja)

    def _memoria_segura(self, operacion: Callable, *args: Any) -> Any:
        """La memoria enriquece la atención, pero su falla no puede interrumpirla."""
        try:
            return operacion(*args)
        except sqlite3.Error as e:
            self.a.traza.registrar("DEGRADACION", f"Memoria no disponible: {type(e).__name__}")
            logger.warning("Memoria no disponible: %s", e)
            return None

    def _cerrar_plan(self, estado: Literal["abortado"]) -> None:
        tarea = self.a.tarea
        for paso in tarea.plan.pasos:
            if paso.estado in ("pendiente", "esperando"):
                paso.estado = "omitido"
        tarea.plan.estado = estado
        self.a.ultimo_plan = tarea.plan
        tarea.cerrar(conservar=DATOS_PACIENTE)
