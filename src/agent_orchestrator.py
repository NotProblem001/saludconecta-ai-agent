"""
Orquestador Principal del Sistema Agéntico - Red SaludConecta
Asignatura: ISY0101 | Ingeniería de Soluciones con Inteligencia Artificial - Duoc UC

Fachada del agente: mantiene la sesión (memoria y tarea en curso) y delega cada turno en el
grafo de estados de src/agent_graph.py. También conserva el motor clínico autónomo, que
responde los turnos generales cuando el LLM remoto no está disponible.
"""

import argparse
import sys
import os
import re
import logging
import sqlite3
import uuid
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

# Asegurar compatibilidad UTF-8 en consola de Windows (emojis y tildes)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("saludconecta.agent")

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from src.config import (
    get_llm,
    get_llm_credentials,
    format_api_error,
    RAG_SIMILARITY_THRESHOLD,
    DB_PATH,
)
from src.security_guardrails import EmergencyBypassGuardrail, PIIAnonymizer
from src.rag_engine import RAGEngine, synthesize_rag_response
from src.tools_agenda import init_database, consultar_disponibilidad_horas
from src.prompts import SYSTEM_PROMPT_SALUDCONECTA, FEW_SHOT_EXAMPLES, format_user_prompt
from src.memory import ContextoPaciente, EstadoTarea, MemoriaLargoPlazo, MemoriaVentana, cargar_contexto
from src.decision_trace import TrazaDecisiones, formatear_traza
from src.tools.consulta import configurar_rag
from src.agent_graph import GrafoAgente


def _has_word(text: str, keywords: List[str]) -> bool:
    """Verifica la presencia de palabras clave completas delimitadas por fronteras de palabra."""
    for kw in keywords:
        pattern = r'\b' + re.escape(kw) + r'\b'
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


class SaludConectaAgent:
    """
    Agente Orquestador Clínico y Administrativo para la Red SaludConecta.
    """

    def __init__(
        self,
        memory_k: int = 5,
        use_mock_embeddings: bool = False,
        similarity_threshold: Optional[float] = None,
        paciente_id: Optional[str] = None,
        llm: Any = None,
        persist_directory: Optional[str] = None,
    ):
        # 1. Guardrails de seguridad deterministas
        self.emergency_guardrail = EmergencyBypassGuardrail()
        self.pii_anonymizer = PIIAnonymizer()

        # 2. Base de datos SQLite de Mock HIS y memoria de largo plazo
        init_database()
        self.memoria = MemoriaLargoPlazo()

        # 3. Motor RAG con umbral >= 0.75
        self.similarity_threshold = similarity_threshold or RAG_SIMILARITY_THRESHOLD
        self.rag_engine = RAGEngine(persist_directory=persist_directory, use_mock_embeddings=use_mock_embeddings)
        configurar_rag(self.rag_engine, self.similarity_threshold)

        # 4. Memoria de corto plazo: ventana conversacional y tarea en curso
        self.memory = MemoriaVentana(k=memory_k)
        self.tarea = EstadoTarea()
        self.traza = TrazaDecisiones(uuid.uuid4().hex[:8])
        self.ultimo_plan = None

        # 5. Paciente de la sesión
        self.paciente_id = paciente_id
        self.contexto: Optional[ContextoPaciente] = None

        # 6. LLM (inyectable para pruebas deterministas)
        self.llm = llm
        self._init_llm()

        # 7. Grafo de estados
        self.grafo = GrafoAgente(self)

    def _init_llm(self):
        """Inicializa el modelo de lenguaje si hay credenciales configuradas."""
        if self.llm is not None:
            self.has_credentials = True
            return

        api_key, base_url = get_llm_credentials()
        self.has_credentials = bool(
            api_key
            and api_key != "mock-token"
            and not api_key.startswith("ghp_tu_token")
            and not api_key.startswith("sk-tu-api-key")
        )

        if self.has_credentials:
            try:
                self.llm = get_llm(temperature=0.1, max_tokens=600)
            except Exception as e:
                logger.warning("Fallo al inicializar el LLM: %s", e)
                self.has_credentials = False

    def setup(self) -> bool:
        """Verifica y prepara los subsistemas de base de datos y motor RAG."""
        init_database()
        if not self.rag_engine.vector_store:
            self.rag_engine._initialize_vector_store()
        return True

    def _synthesize_autonomous_response(
        self,
        user_input: str,
        sanitized_input: str,
        rag_data: Dict[str, Any],
        tools_executed: List[str],
        api_notice: Optional[str] = None
    ) -> str:
        """
        Generador clínico y transaccional autónomo.
        Aplica razonamiento contextual en 4 pasos (CoT), memoria histórica (k=5),
        desambiguación de 'cobertura', síntesis fáctica de RAG y tool calling contra SQLite.
        Se activa cuando el LLM remoto no está disponible o reporta fallos de conectividad/cuota.
        """
        text_lower = user_input.lower().strip()
        grounding_found = rag_data.get("grounding_found", False)

        # ----------------------------------------------------------------------
        # Contexto histórico de la memoria (Últimos turnos de diálogo)
        # ----------------------------------------------------------------------
        last_ai_text = ""
        recent_user_texts = []
        for msg in self.memory.chat_memory.messages:
            if isinstance(msg, AIMessage):
                last_ai_text = msg.content.lower()
            elif isinstance(msg, HumanMessage):
                recent_user_texts.append(msg.content.lower())

        is_previous_scheduling_offer = any(
            phrase in last_ai_text for phrase in [
                "disponibilidad de horas", "consultar cupos", "sucursales",
                "santiago centro", "providencia", "desea consultar"
            ]
        )

        # Detectar comunas de la Red SaludConecta en turno actual
        comunas_red = ["Santiago Centro", "Providencia", "La Florida", "Las Condes", "Maipú"]
        detected_comuna = None
        for com in comunas_red:
            if re.search(r'\b' + re.escape(com) + r'\b', user_input, re.IGNORECASE):
                detected_comuna = com
                break
            # Soporte para "Santiago" como Santiago Centro
            if com == "Santiago Centro" and re.search(r'\bsantiago\b', user_input, re.IGNORECASE):
                detected_comuna = com
                break

        # Detectar especialidad médica en el turno actual
        especialidades_catalogo = [
            "Cardiología Adulto", "Cardiología", "Traumatología - Columna", "Traumatología",
            "Medicina General", "Neurología Adulto", "Neurología", "Pediatría", "Dermatología",
            "Gastroenterología", "Ginecología y Obstetricia", "Ginecología", "Oftalmología",
            "Otorrinolaringología", "Broncopulmonar Adulto", "Broncopulmonar", "Urología",
            "Endocrinología", "Reumatología", "Geriatría"
        ]
        detected_especialidad = None
        for esp in especialidades_catalogo:
            if re.search(r'\b' + re.escape(esp) + r'\b', user_input, re.IGNORECASE):
                detected_especialidad = esp
                break

        # Si no se detecta especialidad en turno actual, rescatar de la memoria reciente
        if not detected_especialidad:
            for esp in especialidades_catalogo:
                if any(re.search(r'\b' + re.escape(esp) + r'\b', t, re.IGNORECASE) for t in recent_user_texts[-3:]):
                    detected_especialidad = esp
                    break

        # ----------------------------------------------------------------------
        # 2. CASO PREPARACIÓN DE EXÁMENES, PROTOCOLOS O ABSTENCIÓN FÁCTICA (RAG)
        # Prioridad alta para responder con síntesis fáctica antes de enrutar a agenda
        # ----------------------------------------------------------------------
        is_preparacion_examen = _has_word(text_lower, [
            "ayuno", "preparacion", "preparación", "examen", "examenes", "exámenes",
            "perfil", "glicemia", "tac", "resonancia", "ecografia", "ecografía",
            "endoscopia", "endoscopía", "colonoscopia", "colonoscopía", "mamografia",
            "mamografía", "orina", "urocultivo", "indicacion", "indicaciones",
            "indicación", "creatinina", "metformina", "biopsia", "muestra", "sangre"
        ])

        if is_preparacion_examen:
            if grounding_found:
                tools_executed.append("consultar_protocolo_rag")
                return self.rag_engine.synthesize_response(rag_data, query=user_input)
            else:
                return (
                    "⚠️ **Información Institucional No Disponible (Regla de Abstención Fáctica)**\n\n"
                    "La información solicitada no figura en nuestros manuales institucionales disponibles.\n\n"
                    "Por estrictas razones de seguridad clínica (Ley N° 20.584), SaludBot no especula sobre indicaciones, "
                    "preparaciones ni procedimientos no homologados en nuestra red. "
                    "Por favor comuníquese directamente con nuestra **Mesa Central de Informaciones al 600 000 1234** "
                    "o consulte en el mesón de atención presencial de su centro médico más cercano.\n\n"
                    "*Descargo Institucional (Ley N° 20.584): Red de Salud SaludConecta.*"
                )

        # ----------------------------------------------------------------------
        # 3. CASO DESAMBIGUACIÓN DE INTENCIONES: "COBERTURA"
        # ----------------------------------------------------------------------
        is_cobertura = _has_word(text_lower, [
            "cobertura", "sedes", "sucursales", "sucursal"
        ]) or any(ph in text_lower for ph in ["donde atienden", "dónde atienden", "donde estan", "dónde están", "centros medicos", "centros médicos"])

        if is_cobertura:
            is_previsional = _has_word(text_lower, [
                "fonasa", "isapre", "prevision", "previsión", "seguro", "copago",
                "bono pad", "arancel", "mle", "i-med", "imed"
            ])
            is_geografica = _has_word(text_lower, [
                "donde", "dónde", "sede", "sedes", "sucursal", "sucursales", "comuna",
                "santiago", "providencia", "florida", "condes", "maipu", "maipú"
            ])

            if is_previsional and not is_geografica:
                return (
                    "💳 **Convenios y Coberturas Previsionales - Red SaludConecta**\n\n"
                    "En toda la red SaludConecta contamos con las siguientes modalidades de cobertura:\n\n"
                    "• **Fonasa Modalidad Libre Elección (MLE):** Aplica para pacientes Fonasa tramos B, C y D. "
                    "Puede adquirir su Bono Fonasa electrónico en caja vía huella dactilar I-Med o en el sitio web de Fonasa con su orden médica.\n"
                    "• **Bono PAD Fonasa (Pago Asociado a Diagnóstico):** Cirugías programadas con precio paquete conocido y cerrado "
                    "(Colecistectomía, Hernioplastías, Cataratas, Parto), incluyendo pabellón, honorarios y días cama sin cobros sorpresa.\n"
                    "• **Isapres en Convenio:** Bonificación directa en línea por sistema I-Med con huella digital en módulos de admisión "
                    "(Banmédica, Colmena, Consalud, CruzBlanca, Vida Tres, Nueva Masvida), abonando solo su copago pactado.\n"
                    "• **Seguro Complementario:** Boleta electrónica con desglose y timbre digital para reembolso directo.\n\n"
                    "[Ref: Protocolo COB-PREV-001]\n\n"
                    "*Descargo Institucional (Ley N° 20.584): Red SaludConecta.*"
                )

            # Respuesta desambiguada geográfica + previsional
            return (
                "🏢 **Cobertura Geográfica y Sedes de Atención - Red SaludConecta**\n\n"
                "Nuestra red cuenta con atención ambulatoria y hospitalaria en 5 sedes de la Región Metropolitana:\n"
                "• **Santiago Centro:** Clínica Central (Av. Alameda)\n"
                "• **Providencia:** Centro Médico Providencia (Av. Salvador)\n"
                "• **La Florida:** Centro Médico La Florida (Av. Vicuña Mackenna)\n"
                "• **Las Condes:** Centro Médico Las Condes (Av. Apoquindo)\n"
                "• **Maipú:** Centro Médico Maipú (Av. Pajaritos)\n\n"
                "💳 **Cobertura Previsional y Convenios:**\n"
                "Todas nuestras sedes operan en convenio con **Fonasa** (Modalidad Libre Elección y Bono PAD) e "
                "**Isapres** (Banmédica, Colmena, Consalud, CruzBlanca, Vida Tres, Nueva Masvida) con bonificación electrónica en línea vía I-Med.\n\n"
                "¿Desea consultar la disponibilidad de horas médicas en alguna de nuestras sedes (por ejemplo, en **Santiago Centro** o **Providencia**)?"
            )

        # ----------------------------------------------------------------------
        # 4. CASO TRANSACCIONAL: CONSULTA DE DISPONIBILIDAD DE HORAS (TOOL CALLING)
        # ----------------------------------------------------------------------
        is_consultar_agenda = (
            _has_word(text_lower, [
                "hora", "horas", "cita", "citas", "cupo", "cupos", "agenda",
                "disponibilidad", "disponible", "disponibles", "medico", "médicos", "médico", "doctor", "doctora"
            ])
            or (detected_comuna is not None and _has_word(text_lower, ["consultar", "ver", "deseo", "quiero", "disponibles", "las de"]))
            or (is_previous_scheduling_offer and (
                detected_comuna is not None
                or _has_word(text_lower, ["si", "sí", "deseo", "consultar", "ver", "favor", "por favor", "las de"])
            ))
        )

        if is_consultar_agenda:
            comuna_query = detected_comuna
            tool_result = consultar_disponibilidad_horas.invoke({
                "especialidad": detected_especialidad,
                "comuna": comuna_query
            })
            tools_executed.append("consultar_disponibilidad_horas")

            sede_info = f" en la comuna de **{comuna_query}**" if comuna_query else ""
            resp_parts = [
                f"🩺 **Disponibilidad de Horas Médicas - Red SaludConecta**\n",
                f"He consultado nuestro sistema hospitalario Mock HIS{sede_info}:\n",
                tool_result,
                "\n*Para confirmar su reserva, proporcione el ID de la cita, RUT (ej: 12.345.678-9), Nombre Completo y Teléfono de contacto.*"
            ]

            if detected_especialidad:
                resp_parts.append(
                    f"\n💡 *Recuerde revisar los exámenes basales requeridos para {detected_especialidad} en nuestros manuales.*"
                )

            return "\n".join(resp_parts)

        # ----------------------------------------------------------------------
        # 5. CASO GROUNDING RAG ACTIVO (CONSULTA SOBRE CORPUS)
        # ----------------------------------------------------------------------
        if grounding_found:
            tools_executed.append("consultar_protocolo_rag")
            return self.rag_engine.synthesize_response(rag_data, query=user_input)

        # ----------------------------------------------------------------------
        # 6. CASO CASUAL / FUERA DE CONTEXTO CLÍNICO / SALUDOS
        # ----------------------------------------------------------------------
        is_casual_or_offtopic = not any(w in text_lower for w in [
            "dolor", "molestia", "sintoma", "síntoma", "sintomas", "síntomas",
            "enfermo", "enfermedad", "presion", "presión", "salud", "medico", "médico",
            "atencion", "atención", "urgencia", "emergencia", "fiebre", "tos",
            "pecho", "espalda", "cabeza", "estomago", "estómago", "cuerpo", "brazo", "pierna",
            "lumbar", "columna", "garganta", "ojo", "oido", "oído", "piel", "alergia"
        ])

        if is_casual_or_offtopic:
            return (
                "👋 **¡Hola! Soy SaludBot**, el asistente de orientación asistencial y agendamiento de la Red SaludConecta.\n\n"
                "Veo que tu mensaje no parece estar relacionado directamente con una consulta clínica o administrativa de salud. "
                "Recuerda que puedo orientarte en:\n\n"
                "• 📋 **Preparación de Exámenes:** Indicaciones oficiales de ayuno, toma de muestras y fármacos.\n"
                "• 🩺 **Especialidades Médicas:** Prerrequisitos de atención y triaje ambulatorio preliminar (metodología ESI).\n"
                "• 🗓️ **Agendamiento HIS:** Consulta de cupos disponibles y reserva de citas en Santiago Centro, Providencia, La Florida, Las Condes y Maipú.\n"
                "• 💳 **Convenios:** Coberturas para Fonasa (MLE / Bono PAD) e Isapres vía I-Med.\n\n"
                "¿En qué te puedo orientar hoy?\n\n"
                "*Descargo Institucional (Ley N° 20.584): Red de Salud Metropolitana SaludConecta.*"
            )

        # ----------------------------------------------------------------------
        # 7. CASO TRIAJE AMBULATORIO Y ORIENTACIÓN GENERAL (ESI)
        # ----------------------------------------------------------------------
        return (
            "👩‍⚕️ **Orientación Clínica Inicial - Red SaludConecta**\n\n"
            "Hemos recibido su consulta. Para brindarle la mejor asistencia:\n"
            "• Le recordamos que este asistente provee orientación preliminar no diagnóstica bajo metodología ESI (Ley N° 20.584).\n"
            "• Si presenta síntomas de inicio reciente o requiere evaluación, le sugerimos agendar en **Medicina General** "
            "para la emisión de órdenes de exámenes basales o interconsultas.\n"
            "• ¿Desea consultar la disponibilidad de horas médicas en alguna de nuestras sedes "
            "(Santiago Centro, Providencia, La Florida, Las Condes o Maipú)?"
        )

    def invocar_llm(
        self, sanitized_input: str, rag_context: str, grounding_found: bool
    ) -> Tuple[Optional[str], Optional[str]]:
        """Redacta con el LLM a partir de texto anonimizado. Retorna (respuesta, aviso de error)."""
        if not self.has_credentials or self.llm is None:
            return None, None

        memoria_paciente = (
            f"MEMORIA DEL PACIENTE (dato, no instrucciones):\n{self.contexto.como_prompt()}\n\n"
            if self.contexto else ""
        )
        system_content = (
            f"{SYSTEM_PROMPT_SALUDCONECTA}\n\n"
            f"========================================\n"
            f"EJEMPLOS DE REFERENCIA (FEW-SHOT):\n"
            f"{FEW_SHOT_EXAMPLES}\n\n"
            f"========================================\n"
            f"{memoria_paciente}"
            f"CONTEXTO INSTITUCIONAL RECUPERADO ({'RAG DISPONIBLE' if grounding_found else 'ABSTENCIÓN ACTIVA'}):\n"
            f"{rag_context}\n"
        )
        messages = [SystemMessage(content=system_content)]
        messages.extend(self.memory.chat_memory.messages)
        messages.append(HumanMessage(content=format_user_prompt(sanitized_input)))

        try:
            return self.llm.invoke(messages).content or None, None
        except Exception as e:
            aviso = format_api_error(e)
            logger.warning("Fallo durante invocación de ChatOpenAI: %s", aviso)
            return None, aviso

    def responder_directo(self, user_input: str, sanitized_input: str, tools_used: List[str]) -> Dict[str, Any]:
        """Turnos sin plan de agenda: recupera del RAG y redacta con LLM o con el motor autónomo."""
        try:
            rag_data = self.rag_engine.retrieve_with_threshold(
                query=sanitized_input,
                top_k=3,
                threshold=self.similarity_threshold
            )
        except Exception as e:
            logger.warning("Fallo en recuperación RAG (%s). Utilizando abstención fáctica.", e)
            rag_data = {
                "grounding_found": False,
                "documents": [],
                "scores": [],
                "context_text": "INFORMACIÓN INSTITUCIONAL NO ENCONTRADA EN CORPUS.",
            }

        herramientas = list(tools_used)
        respuesta, aviso = self.invocar_llm(sanitized_input, rag_data["context_text"], rag_data["grounding_found"])
        if not respuesta:
            try:
                respuesta = self._synthesize_autonomous_response(
                    user_input=user_input,
                    sanitized_input=sanitized_input,
                    rag_data=rag_data,
                    tools_executed=herramientas,
                    api_notice=aviso
                )
            except sqlite3.Error as e:
                self.traza.registrar("DEGRADACION", f"Agenda no disponible: {type(e).__name__}")
                respuesta = (
                    "⚠️ **Sistema de agenda temporalmente no disponible.** "
                    "Intente en unos minutos o comuníquese con la **Mesa Central al 600 000 1234**."
                )

        return {
            "respuesta": respuesta,
            "estado": {
                "grounding_found": rag_data["grounding_found"],
                "rag_context": rag_data["context_text"],
                "tools_used": herramientas,
                "api_notice": aviso,
            },
        }

    def cargar_memoria_paciente(self) -> Optional[str]:
        """Carga la memoria del paciente y prepara la tarea. Retorna el recordatorio para el paciente."""
        try:
            self.contexto = cargar_contexto(self.paciente_id, self.memoria)
            paciente = self.memoria.obtener_paciente(self.paciente_id)
        except sqlite3.Error as e:
            self.traza.registrar("DEGRADACION", f"Memoria no disponible: {type(e).__name__}")
            logger.warning("Memoria no disponible: %s", e)
            return None

        if paciente:
            datos = self.tarea.datos
            for clave, valor in (("rut", paciente["rut"]), ("nombre", paciente["nombre"]), ("telefono", paciente["telefono"])):
                datos.setdefault(clave, valor)
            datos["farmacos"] = sorted(set(datos.get("farmacos", [])) | set(paciente["farmacos"]))
            datos["alergias"] = sorted(set(datos.get("alergias", [])) | set(paciente["alergias"]))
        self.traza.registrar(
            "MEMORIA", f"Contexto cargado: {len(self.contexto.citas_pendientes)} cita(s) pendiente(s), "
                       f"{len(self.contexto.atenciones)} atención(es), {len(self.contexto.preferencias)} preferencia(s)",
        )
        return self.contexto.recordatorio()

    def iniciar_sesion(self, paciente_id: Optional[str]) -> Optional[str]:
        """Inicia una sesión nueva para el paciente y retorna su recordatorio, si existe."""
        self.reset_conversation()
        self.paciente_id = paciente_id
        self.contexto = None
        return self.cargar_memoria_paciente() if paciente_id else None

    def process_message(self, user_input: str) -> Dict[str, Any]:
        """
        Ejecuta un turno en el grafo: bypass de emergencia, anonimización, plan y respuesta.
        Las claves de retorno de EP1 se conservan; EP2 agrega `plan` y `traza`.
        """
        s = self.grafo.invocar(user_input)
        chequeo = s.get("emergencia")
        plan = self.ultimo_plan

        return {
            "bypass_activated": chequeo is not None,
            "emergency_level": chequeo.emergency_level if chequeo else "NO_EMERGENCIA",
            "reason": chequeo.reason if chequeo else None,
            "sanitized_input": s["sanitizado"],
            "pii_detected": s["pii"],
            "grounding_found": s.get("grounding_found"),
            "rag_context": s.get("rag_context"),
            "rag_used": s.get("grounding_found") is not None,
            "tools_used": s.get("tools_used", []),
            "response": s["respuesta"],
            "response_time_ms": s["tiempo_guardrail_ms"],
            "api_notice": s.get("api_notice"),
            "plan": plan.model_dump() if plan else None,
            "traza": self.traza.del_turno(),
        }

    def reset_conversation(self):
        """Limpia la memoria de corto plazo y la tarea en curso; inicia una traza nueva."""
        self.memory.clear()
        self.tarea = EstadoTarea()
        self.traza = TrazaDecisiones(uuid.uuid4().hex[:8])
        self.ultimo_plan = None


def run_cli():
    """Interfaz de consola interactiva para evaluar el agente en tiempo real."""
    parser = argparse.ArgumentParser(description="SaludBot por consola")
    parser.add_argument("--paciente", help="identificador simulado, ej: PAC-001")
    args = parser.parse_args()

    print("=" * 75)
    print("  🏥 SISTEMA AGÉNTICO DE ORIENTACIÓN Y GESTIÓN - RED SALUDCONECTA 🏥")
    print("  Asignatura: ISY0101 | Ingeniería de Soluciones con Inteligencia Artificial")
    print("=" * 75)
    print("Comandos disponibles: 'salir' para terminar | 'limpiar' para reiniciar memoria | 'ayuda'")
    print("-" * 75)

    agent = SaludConectaAgent()
    recordatorio = agent.iniciar_sesion(args.paciente)
    if recordatorio:
        print(f"\n{recordatorio}")

    while True:
        try:
            user_input = input("\n👤 Paciente: ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["salir", "exit", "quit"]:
                print("\nGracias por utilizar los servicios de la Red SaludConecta. ¡Hasta pronto!\n")
                break

            if user_input.lower() == "limpiar":
                agent.iniciar_sesion(args.paciente)
                print("\n🔄 Memoria conversacional reiniciada con éxito.")
                continue

            if user_input.lower() == "ayuda":
                print("\nPuede realizar consultas tales como:")
                print("1. 'Tengo un fuerte dolor en el pecho que se me va al brazo izquierdo.' (Bypass Código Rojo)")
                print("2. '¿Cómo debo prepararme para un perfil lipídico y glicemia?' (Grounding RAG con síntesis)")
                print("3. '¿Dónde tienen cobertura?' (Desambiguación geográfica y previsional)")
                print("4. 'Deseo consultar las de Santiago Centro' (Memoria y Tool Calling HIS)")
                print("5. 'Quiero reservar la cita 1 para Juan Pérez, RUT 12.345.678-9, fono +56912345678' (Reserva Atómica)")
                print("6. '¿Qué preparación necesito para una biopsia interplanetaria?' (Regla de Abstención RAG)")
                continue

            print("\n⏳ Procesando consulta con guardrails, RAG y orquestación...")
            result = agent.process_message(user_input)

            if result["bypass_activated"]:
                print(f"\n[TIEMPO BYPASS: {result['response_time_ms']:.2f} ms]")
                print(result["response"])
            else:
                if result.get("api_notice"):
                    print(f"⚠️ {result['api_notice']}")
                if result.get("pii_detected"):
                    print(f"🔒 [PII Anonimizado: {len(result['pii_detected'])} entidad(es)]")
                if result.get("tools_used"):
                    print(f"🛠️ [Herramientas invocadas: {', '.join(result['tools_used'])}]")
                print(f"\n🤖 SaludBot:\n{result['response']}")
            print(f"\n🧭 Traza del turno:\n{formatear_traza(result['traza'])}")

        except (KeyboardInterrupt, EOFError):
            print("\nSesión finalizada por el usuario.")
            break


if __name__ == "__main__":
    run_cli()
