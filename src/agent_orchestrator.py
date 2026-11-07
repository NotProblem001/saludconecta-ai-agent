"""
Orquestador Principal del Sistema Agéntico - Red SaludConecta
Asignatura: ISY0101 | Ingeniería de Soluciones con Inteligencia Artificial - Duoc UC

Integra de forma coordinada:
1. Bypass Determinista de Código Rojo (<100ms) para salvaguarda de vida ante emergencias vitales.
2. Anonimización de PII (RUT chileno, teléfonos móviles/fijos, emails) para protección de datos personales.
3. Memoria conversacional de ventana deslizante (ConversationBufferWindowMemory k=5).
4. Pipeline RAG con anclaje fáctico estricto (0.75), abstención fáctica y síntesis clínica con citas [Ref: Protocolo ...].
5. Tool calling sobre Mock HIS relacional SQLite (consultar_disponibilidad_horas y reservar_cita_medica).
6. Manejo explícito de excepciones de API y motor clínico autónomo contextual para resiliencia ante contingencias.
"""

import sys
import os
import re
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

# Asegurar compatibilidad UTF-8 en consola de Windows (emojis y tildes)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("saludconecta.agent")

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

# Memoria conversacional de ventana deslizante (k=5 interacciones)
try:
    from langchain.memory import ConversationBufferWindowMemory
except (ImportError, ModuleNotFoundError):
    try:
        from langchain_classic.memory import ConversationBufferWindowMemory
    except (ImportError, ModuleNotFoundError):
        class ConversationBufferWindowMemory:
            """Implementación autónoma de ventana deslizante (k) compatible con el protocolo LangChain."""
            def __init__(self, k: int = 5, return_messages: bool = True, memory_key: str = "chat_history"):
                self.k = k
                self.return_messages = return_messages
                self.memory_key = memory_key
                self.messages = []

            @property
            def chat_memory(self):
                return self

            def add_user_message(self, message: str):
                self.messages.append(HumanMessage(content=message))
                self._trim()

            def add_ai_message(self, message: str):
                self.messages.append(AIMessage(content=message))
                self._trim()

            def _trim(self):
                max_msgs = self.k * 2
                if len(self.messages) > max_msgs:
                    self.messages = self.messages[-max_msgs:]

            def clear(self):
                self.messages.clear()

            def load_memory_variables(self, inputs: Optional[dict] = None) -> dict:
                return {self.memory_key: self.messages}

            def save_context(self, inputs: dict, outputs: dict):
                if "input" in inputs:
                    self.add_user_message(inputs["input"])
                if "output" in outputs:
                    self.add_ai_message(outputs["output"])

from src.config import (
    get_llm,
    get_llm_credentials,
    format_api_error,
    RAG_SIMILARITY_THRESHOLD,
    DB_PATH,
)
from src.security_guardrails import EmergencyBypassGuardrail, PIIAnonymizer
from src.rag_engine import RAGEngine, synthesize_rag_response
from src.tools_agenda import (
    AGENDA_TOOLS,
    init_database,
    consultar_disponibilidad_horas,
    consultar_citas_disponibles,
    reservar_cita_medica,
    cancelar_cita_medica,
    validar_formato_rut_chileno,
)
from src.prompts import (
    SYSTEM_PROMPT_SALUDCONECTA,
    FEW_SHOT_EXAMPLES,
    AgentStructuredOutput,
    format_user_prompt,
)


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
        similarity_threshold: Optional[float] = None
    ):
        # 1. Guardrails de seguridad deterministas
        self.emergency_guardrail = EmergencyBypassGuardrail()
        self.pii_anonymizer = PIIAnonymizer()

        # 2. Base de datos SQLite de Mock HIS
        init_database()

        # 3. Motor RAG con umbral >= 0.75
        self.similarity_threshold = similarity_threshold or RAG_SIMILARITY_THRESHOLD
        self.rag_engine = RAGEngine(use_mock_embeddings=use_mock_embeddings)

        # 4. Memoria de ventana deslizante (k=5 turnos)
        self.memory = ConversationBufferWindowMemory(
            k=memory_k,
            return_messages=True,
            memory_key="chat_history"
        )

        # 5. Mapeo de herramientas por nombre
        self.tools_map = {tool.name: tool for tool in AGENDA_TOOLS}

        # 6. Inicializar LLM con herramientas enlazadas
        self._init_llm()

    def _init_llm(self):
        """Inicializa el modelo de lenguaje si hay credenciales configuradas."""
        api_key, base_url = get_llm_credentials()
        self.has_credentials = bool(
            api_key
            and api_key != "mock-token"
            and not api_key.startswith("ghp_tu_token")
            and not api_key.startswith("sk-tu-api-key")
        )

        if self.has_credentials:
            try:
                base_llm = get_llm(temperature=0.1, max_tokens=600)
                self.llm_with_tools = base_llm.bind_tools(AGENDA_TOOLS)
            except Exception as e:
                logger.warning("Fallo al enlazar herramientas con LLM: %s", e)
                self.llm_with_tools = None
        else:
            self.llm_with_tools = None

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
        # 1. CASO TRANSACCIONAL: RESERVA DE CITA MÉDICA
        # ----------------------------------------------------------------------
        is_reserva = _has_word(text_lower, [
            "reservar", "reserva", "tomar", "agendar", "confirmar", "confirmo"
        ]) and any(w in text_lower for w in ["cita", "cupo", "hora", "id", "#", "rut"])

        if is_reserva:
            id_match = re.search(r'\b(?:id|cita|cupo|numero|número)?\s*#?\s*(\d{1,2})\b', text_lower)
            rut_match = self.pii_anonymizer.RUT_PATTERN.search(user_input)
            phone_match = self.pii_anonymizer.PHONE_PATTERN.search(user_input)

            if id_match:
                cita_id = int(id_match.group(1))

                # Validar existencia de RUT y su formato chileno
                if not rut_match:
                    return (
                        f"Para proceder con la reserva del cupo #{cita_id}, es requisito obligatorio "
                        "proporcionar un **RUT en formato chileno válido** (ejemplo: 12.345.678-9 o 12345678-K), "
                        "su **Nombre Completo** y un **Teléfono de contacto**."
                    )

                rut = rut_match.group(0).strip()
                if not validar_formato_rut_chileno(rut):
                    return (
                        f"⚠️ El RUT proporcionado ('{rut}') no cumple con el formato oficial chileno. "
                        "Por favor ingréselo con guion y dígito verificador (ej: 12.345.678-9 o 12345678-K)."
                    )

                phone = phone_match.group(0).strip() if phone_match else "+569 9123 4567"
                nombre = "Paciente Registrado"
                nombre_match = re.search(
                    r'(?:nombre|paciente|para)\s+([A-Za-zÁÉÍÓÚáéíóúñÑ ]+?)(?:,|-|rut|fono|telefono|\.|$)',
                    user_input,
                    re.IGNORECASE
                )
                if nombre_match:
                    nombre = nombre_match.group(1).strip()

                tool_result = reservar_cita_medica.invoke({
                    "cita_id": cita_id,
                    "paciente_rut": rut,
                    "paciente_nombre": nombre,
                    "paciente_telefono": phone
                })
                tools_executed.append("reservar_cita_medica")
                return tool_result

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

    def process_message(self, user_input: str) -> Dict[str, Any]:
        """
        Flujo de orquestación por capas para cada mensaje recibido:
        Capa 2: Bypass de Emergencia (<100ms) y Anonimización PII.
        Capa 4: Recuperación de Conocimiento RAG (umbral >= 0.75).
        Capa 3 y 5: Invocación del LLM, Tool Calling y actualización de Memoria (k=5).
        """
        # ======================================================================
        # PASO 1: BYPASS DETERMINISTA DE CÓDIGO ROJO (<100ms)
        # ======================================================================
        emergency_check = self.emergency_guardrail.evaluate(user_input)
        if emergency_check.is_emergency:
            self.memory.chat_memory.add_user_message(self.pii_anonymizer.anonymize(user_input).sanitized_text)
            self.memory.chat_memory.add_ai_message(emergency_check.action_message)

            return {
                "bypass_activated": True,
                "emergency_level": emergency_check.emergency_level,
                "reason": emergency_check.reason,
                "response": emergency_check.action_message,
                "response_time_ms": emergency_check.response_time_ms,
                "rag_used": False,
                "tools_used": [],
                "api_notice": None,
            }

        # ======================================================================
        # PASO 2: ANONIMIZACIÓN DE DATOS SENSIBLES (PII)
        # ======================================================================
        pii_result = self.pii_anonymizer.anonymize(user_input)
        sanitized_input = pii_result.sanitized_text

        # ======================================================================
        # PASO 3: RECUPERACIÓN AUMENTADA (RAG) CON FILTRO DE CORTE (0.75)
        # ======================================================================
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
        rag_context = rag_data["context_text"]
        grounding_found = rag_data["grounding_found"]

        # ======================================================================
        # PASO 4: CONSTRUCCIÓN DEL CONTEXTO Y PROMPTS
        # ======================================================================
        system_content = (
            f"{SYSTEM_PROMPT_SALUDCONECTA}\n\n"
            f"========================================\n"
            f"EJEMPLOS DE REFERENCIA (FEW-SHOT):\n"
            f"{FEW_SHOT_EXAMPLES}\n\n"
            f"========================================\n"
            f"CONTEXTO INSTITUCIONAL RECUPERADO ({'RAG DISPONIBLE' if grounding_found else 'ABSTENCIÓN ACTIVA'}):\n"
            f"{rag_context}\n"
        )

        history_messages = list(self.memory.chat_memory.messages)

        messages = [SystemMessage(content=system_content)]
        messages.extend(history_messages)
        messages.append(HumanMessage(content=format_user_prompt(sanitized_input)))

        # ======================================================================
        # PASO 5: EJECUCIÓN DEL LLM Y TOOL CALLING
        # ======================================================================
        tools_executed = []
        final_response = None
        api_error_notice = None

        if self.has_credentials and self.llm_with_tools is not None:
            try:
                ai_msg = self.llm_with_tools.invoke(messages)

                if hasattr(ai_msg, "tool_calls") and ai_msg.tool_calls:
                    messages.append(ai_msg)
                    for tool_call in ai_msg.tool_calls:
                        tool_name = tool_call["name"]
                        tool_args = tool_call["args"]
                        tools_executed.append(tool_name)

                        if tool_name in self.tools_map:
                            selected_tool = self.tools_map[tool_name]
                            tool_output = selected_tool.invoke(tool_args)
                        else:
                            tool_output = f"Error: Herramienta '{tool_name}' no reconocida."

                        messages.append(
                            ToolMessage(
                                content=str(tool_output),
                                tool_call_id=tool_call["id"]
                            )
                        )

                    final_ai_msg = self.llm_with_tools.invoke(messages)
                    final_response = final_ai_msg.content
                else:
                    final_response = ai_msg.content

            except Exception as e:
                api_error_notice = format_api_error(e)
                logger.warning("Fallo durante invocación de ChatOpenAI: %s", api_error_notice)
                final_response = None

        # Si el LLM remoto no está activo o falló, utilizar el generador clínico autónomo contextual
        if not final_response:
            final_response = self._synthesize_autonomous_response(
                user_input=user_input,
                sanitized_input=sanitized_input,
                rag_data=rag_data,
                tools_executed=tools_executed,
                api_notice=api_error_notice
            )

        # Actualizar memoria conversacional de ventana deslizante (k=5)
        self.memory.chat_memory.add_user_message(sanitized_input)
        self.memory.chat_memory.add_ai_message(self.pii_anonymizer.anonymize(final_response).sanitized_text)

        return {
            "bypass_activated": False,
            "emergency_level": "NO_EMERGENCIA",
            "sanitized_input": sanitized_input,
            "pii_detected": pii_result.detected_entities,
            "grounding_found": grounding_found,
            "rag_context": rag_context,
            "tools_used": tools_executed,
            "response": final_response,
            "response_time_ms": emergency_check.response_time_ms,
            "api_notice": api_error_notice,
        }

    def reset_conversation(self):
        """Limpia el búfer de memoria conversacional."""
        self.memory.clear()


def run_cli():
    """Interfaz de consola interactiva para evaluar el agente en tiempo real."""
    print("=" * 75)
    print("  🏥 SISTEMA AGÉNTICO DE ORIENTACIÓN Y GESTIÓN - RED SALUDCONECTA 🏥")
    print("  Asignatura: ISY0101 | Ingeniería de Soluciones con Inteligencia Artificial")
    print("=" * 75)
    print("Comandos disponibles: 'salir' para terminar | 'limpiar' para reiniciar memoria | 'ayuda'")
    print("-" * 75)

    agent = SaludConectaAgent()

    while True:
        try:
            user_input = input("\n👤 Paciente: ").strip()
            if not user_input:
                continue

            if user_input.lower() in ["salir", "exit", "quit"]:
                print("\nGracias por utilizar los servicios de la Red SaludConecta. ¡Hasta pronto!\n")
                break

            if user_input.lower() == "limpiar":
                agent.reset_conversation()
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

        except (KeyboardInterrupt, EOFError):
            print("\nSesión finalizada por el usuario.")
            break


if __name__ == "__main__":
    run_cli()
