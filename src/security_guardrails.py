"""
Módulo de Seguridad y Guardrails Heurísticos - Red SaludConecta
Implementa:
1. Bypass Determinista de Código Rojo (<100ms) para detección instantánea de emergencias vitales.
2. Anonimizador de PII (RUT chileno, teléfonos móviles/fijos, emails) para protección de datos sensibles.
"""

import re
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class EmergencyCheckResult:
    """Resultado del chequeo determinista de emergencia vital."""
    is_emergency: bool
    emergency_level: str  # "CODIGO_ROJO", "CODIGO_NARANJA", "NO_EMERGENCIA"
    reason: Optional[str]
    action_message: str
    response_time_ms: float
    detected_patterns: List[str] = field(default_factory=list)


@dataclass
class PIIAnonymizationResult:
    """Resultado de la anonimización de datos de identificación personal."""
    sanitized_text: str
    detected_entities: List[Dict[str, str]]
    rut_count: int
    phone_count: int
    email_count: int


class EmergencyBypassGuardrail:
    """
    Guardrail determinista de ultra baja latencia (<50ms).
    Evalúa la presencia de banderas rojas de riesgo vital (ESI 1 y ESI 2 crítico)
    antes de cualquier interacción con el modelo de lenguaje (LLM).
    """

    # Diccionario de categorías críticas y sus expresiones regulares optimizadas
    RED_FLAG_PATTERNS = {
        "DOLOR_TORACICO_CORONARIO": [
            r"\b(dolor|opresi[oó]n|puntada|pesadez)(\s+[\w]+){0,3}\s+(en\s+el\s+|de\s+)?(pecho|t[oó]rax|pecho\s+opresivo)\b",
            r"\b(infarto|preinfarto|ataque\s+al\s+coraz[oó]n|paro\s+card[ií]aco)\b",
            r"\bdolor(\s+[\w]+){0,3}\s+(de\s+pecho|tor[aá]cico|en\s+el\s+pecho).*(brazo\s+izquierdo|mand[ií]bula|cuello|espalda)\b",
            r"\b(pecho|t[oó]rax).*(\s+[\w]+){0,3}\s+(brazo\s+izquierdo|mand[ií]bula)\b",
            r"\bduele(\s+[\w]+){0,2}\s+(el\s+)?(pecho|t[oó]rax)\b",
        ],
        "SOSPECHA_ACV_NEURO": [
            r"\b(asimetr[ií]a\s+facial|boca\s+torcida|cara\s+ca[ií]da|cara\s+chueca)\b",
            r"\b(no\s+puedo\s+hablar|dificultad\s+para\s+hablar|habla\s+traposa|balbuceo|lengua\s+trabada)\b",
            r"\b(par[aá]lisis|p[eé]rdida\s+de\s+fuerza|se\s+me\s+durmi[oó])(\s+[\w]+){0,2}\s+(medio\s+cuerpo|un\s+lado|brazo|pierna)\b",
            r"\b(derrame\s+cerebral|acv|ictus|isquemia\s+cerebral)\b",
            r"\b(no\s+siento|se\s+me\s+adormeci[oó])(\s+[\w]+){0,2}\s+(medio\s+cuerpo|un\s+lado|brazo|pierna)\b",
        ],
        "COMPROMISO_RESPIRATORIO_SEVERO": [
            r"\b(no\s+puedo\s+respirar|me\s+ahogo|falta\s+el\s+aire|dificultad\s+severa\s+para\s+respirar|asfixia|me\s+estoy\s+ahogando)\b",
            r"\b(labios\s+azules|morados|cianosis)\b",
            r"\b(estridor|silbido\s+intenso\s+al\s+respirar\s+con\s+ahogo)\b",
        ],
        "SHOCK_ANAFILACTICO": [
            r"\b(edema\s+de\s+glotis|se\s+me\s+cierra\s+la\s+garganta|hinchaz[oó]n\s+de\s+lengua)\b",
            r"\b(alergia\s+grave|reacci[oó]n\s+anafil[aá]ctica)\b",
        ],
        "HEMORRAGIA_SEVERA_Y_TRAUMA": [
            r"\b(hemorragia\s+masiva|sangrado\s+incontrolable|sangre\s+a\s+chorros)\b",
            r"\b(trauma\s+grave|p[eé]rdida\s+de\s+conciencia\s+con\s+golpe|inconsciente|desmayo\s+sin\s+reacci[oó]n)\b",
            r"\b(convulsi[oó]n\s+activa|convulsionando|convulsiona|convulsion[oó])\b",
            r"\b(sangrado\s+(abundante|masivo|profuso)|me\s+desmay[eé])\b",
        ],
        "RIESGO_VITAL_PSIQUIATRICO": [
            r"\b(quiero\s+matarme|voy\s+a\s+suicidarme|intent[eé]\s+matarme|plan\s+de\s+suicidio)\b",
            r"\b(acabo\s+de\s+tomarme\s+(todas\s+las\s+pastillas|veneno)|intoxicaci[oó]n\s+voluntaria)\b",
            r"\b(quiero\s+morir(me)?|me\s+quiero\s+(morir|matar)|no\s+quiero\s+seguir\s+viviendo)\b",
            r"\bme\s+tom[eé]\s+todas\s+las\s+pastillas\b",
        ],
    }

    # Mensaje protocolar estandarizado de respuesta inmediata
    EMERGENCY_DISPATCH_MESSAGE = (
        "🚨 ALERTA DE CÓDIGO ROJO - RIESGO VITAL DETECTADO 🚨\n\n"
        "Su consulta describe síntomas de máxima urgencia clínica que requieren intervención médica inmediata.\n"
        "NO ESPERE UNA HORA MÉDICA AMBULATORIA NI SE TRASLADE POR SUS PROPIOS MEDIOS SIN ASISTENCIA.\n\n"
        "INSTRUCCIONES CRÍTICAS:\n"
        "1. Llame INMEDIATAMENTE al SAMU marcando el 131 desde cualquier teléfono (llamada gratuita).\n"
        "2. Acuda al Servicio de Urgencia Hospitalaria más cercano.\n"
        "3. Si está acompañado, solicite a alguien que permanezca a su lado y mantenga la calma.\n"
        "4. En caso de dolor torácico o sospecha de infarto, permanezca en reposo semisentado."
    )

    def __init__(self):
        # Precompilar regex con flags de optimización para garantizar ejecución < 1ms
        self._compiled_rules = []
        for category, patterns in self.RED_FLAG_PATTERNS.items():
            combined_pattern = "|".join(f"(?:{p})" for p in patterns)
            regex = re.compile(combined_pattern, re.IGNORECASE)
            self._compiled_rules.append((category, regex))

    def evaluate(self, text: str) -> EmergencyCheckResult:
        """
        Analiza el texto del paciente en busca de criterios de riesgo vital.
        Garantiza tiempo de respuesta inferior a 100 ms (típicamente < 5 ms).
        """
        start_time = time.perf_counter()
        normalized_text = text.lower().strip()

        detected_categories = []
        for category, regex in self._compiled_rules:
            if regex.search(normalized_text):
                detected_categories.append(category)

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        if detected_categories:
            reason = f"Se detectaron banderas rojas de riesgo vital: {', '.join(detected_categories)}"
            return EmergencyCheckResult(
                is_emergency=True,
                emergency_level="CODIGO_ROJO",
                reason=reason,
                action_message=self.EMERGENCY_DISPATCH_MESSAGE,
                response_time_ms=elapsed_ms,
                detected_patterns=detected_categories,
            )

        return EmergencyCheckResult(
            is_emergency=False,
            emergency_level="NO_EMERGENCIA",
            reason=None,
            action_message="",
            response_time_ms=elapsed_ms,
            detected_patterns=[],
        )


class PIIAnonymizer:
    """
    Anonimizador determinista de Información de Identificación Personal (PII).
    Especializado en formatos chilenos: RUT (con y sin puntos), teléfonos móviles (+569),
    fijos y correos electrónicos.
    """

    # Patrón RUT chileno: 7 u 8 dígitos, separador de miles opcional, guion y dígito verificador (0-9 o K)
    RUT_PATTERN = re.compile(
        r"\b\d{1,2}(?:\.\d{3}\.\d{3}|\d{6,7})[-‐‑‒–—][0-9kK]\b"
    )

    # Patrón Teléfono chileno: +56 9, +569, 9xxxxxxxx, 22xxxxxxx
    PHONE_PATTERN = re.compile(
        r"(?:\+?56\s?9\s?\d{4}\s?\d{4}|\b9\s?\d{4}\s?\d{4}\b|\b\+?56\s?[2-9]\s?\d{4}\s?\d{4}\b|\b2\s?\d{7,8}\b)"
    )

    # Patrón Correo Electrónico estándar
    EMAIL_PATTERN = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"
    )

    def anonymize(self, text: str) -> PIIAnonymizationResult:
        """
        Enmascara RUTs, teléfonos y correos presentes en el texto reemplazándolos
        por identificadores seguros ([RUT_PROTEGIDO], [TELEFONO_PROTEGIDO], [EMAIL_PROTEGIDO]).
        """
        detected_entities = []

        # 1. Anonimizar RUTs
        def _replace_rut(match):
            val = match.group(0)
            detected_entities.append({"type": "RUT", "original": val})
            return "[RUT_PROTEGIDO]"

        text_no_rut, rut_count = self.RUT_PATTERN.subn(_replace_rut, text)

        # 2. Anonimizar Emails
        def _replace_email(match):
            val = match.group(0)
            detected_entities.append({"type": "EMAIL", "original": val})
            return "[EMAIL_PROTEGIDO]"

        text_no_email, email_count = self.EMAIL_PATTERN.subn(_replace_email, text_no_rut)

        # 3. Anonimizar Teléfonos
        def _replace_phone(match):
            val = match.group(0)
            detected_entities.append({"type": "PHONE", "original": val})
            return "[TELEFONO_PROTEGIDO]"

        sanitized_text, phone_count = self.PHONE_PATTERN.subn(_replace_phone, text_no_email)

        return PIIAnonymizationResult(
            sanitized_text=sanitized_text,
            detected_entities=detected_entities,
            rut_count=rut_count,
            phone_count=phone_count,
            email_count=email_count,
        )
