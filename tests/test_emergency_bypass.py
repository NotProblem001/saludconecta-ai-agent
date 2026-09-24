"""
Batería de Pruebas Unitarias: Bypass Determinista de Código Rojo y Anonimizador PII
Asignatura: ISY0101 - Ingeniería de Soluciones con Inteligencia Artificial
Proyecto: Sistema Agéntico SaludConecta
"""

import time
import pytest
from src.security_guardrails import EmergencyBypassGuardrail, PIIAnonymizer


@pytest.fixture
def guardrail():
    return EmergencyBypassGuardrail()


@pytest.fixture
def anonymizer():
    return PIIAnonymizer()


# ==============================================================================
# 1. Pruebas de Latencia (<100ms) y Detección de Código Rojo
# ==============================================================================

def test_emergency_bypass_latency_benchmark(guardrail):
    """
    Verifica que el tiempo de evaluación determinista sea estrictamente inferior a 100ms
    (típicamente < 5ms), garantizando protección previa a cualquier llamada LLM.
    """
    sample_text = "Siento una opresión en el pecho terrible y me duele el brazo izquierdo"
    start = time.perf_counter()
    result = guardrail.evaluate(sample_text)
    duration_ms = (time.perf_counter() - start) * 1000.0

    assert duration_ms < 100.0, f"Latencia excedida: {duration_ms:.2f} ms >= 100.0 ms"
    assert result.is_emergency is True
    assert result.emergency_level == "CODIGO_ROJO"
    assert result.response_time_ms < 100.0


@pytest.mark.parametrize("emergency_prompt,expected_category", [
    (
        "Tengo un dolor en el pecho opresivo muy fuerte que se me sube a la mandíbula y brazo izquierdo",
        "DOLOR_TORACICO_CORONARIO"
    ),
    (
        "Mi abuela tiene la boca torcida de repente y no puede hablar bien, se le cayó el brazo",
        "SOSPECHA_ACV_NEURO"
    ),
    (
        "Me falta el aire grave, no puedo respirar y tengo los labios morados",
        "COMPROMISO_RESPIRATORIO_SEVERO"
    ),
    (
        "Comí maní y tengo edema de glotis, se me cierra la garganta y me asfixio",
        "SHOCK_ANAFILACTICO"
    ),
    (
        "Hay una hemorragia masiva tras un accidente y el paciente está inconsciente",
        "HEMORRAGIA_SEVERA_Y_TRAUMA"
    ),
    (
        "Siento que no doy más y quiero matarme hoy mismo",
        "RIESGO_VITAL_PSIQUIATRICO"
    ),
])
def test_emergency_red_flags_detection(guardrail, emergency_prompt, expected_category):
    """
    Verifica que las distintas banderas rojas de riesgo vital sean detectadas correctamente.
    """
    result = guardrail.evaluate(emergency_prompt)
    assert result.is_emergency is True
    assert result.emergency_level == "CODIGO_ROJO"
    assert "131" in result.action_message or "SAMU" in result.action_message
    assert any(expected_category in pattern for pattern in result.detected_patterns)


@pytest.mark.parametrize("routine_prompt", [
    "Hola, necesito agendar una hora para control de medicina general con la Dra. Andrea Morales.",
    "¿Cuáles son las indicaciones de ayuno para un examen de sangre de perfil lipídico?",
    "Tengo dolor en la espalda baja desde hace dos meses y quiero ver a un traumatólogo.",
    "¿Atienden por Fonasa nivel B en la sucursal de Providencia?",
    "Buenas tardes, quisiera saber el precio de una consulta dental para limpieza.",
])
def test_non_emergency_queries_pass_through(guardrail, routine_prompt):
    """
    Verifica que las consultas ambulatorias rutinarias NO activen falsos positivos en el bypass.
    """
    result = guardrail.evaluate(routine_prompt)
    assert result.is_emergency is False
    assert result.emergency_level == "NO_EMERGENCIA"
    assert result.reason is None
    assert result.action_message == ""


# ==============================================================================
# 2. Pruebas del Anonimizador de PII
# ==============================================================================

def test_pii_anonymizer_rut(anonymizer):
    """
    Verifica la detección y enmascaramiento de RUTs chilenos con y sin puntos.
    """
    text = "Mi nombre es Juan Pérez y mi RUT es 18.234.567-8 o 12345678-k."
    result = anonymizer.anonymize(text)

    assert "18.234.567-8" not in result.sanitized_text
    assert "12345678-k" not in result.sanitized_text
    assert "[RUT_PROTEGIDO]" in result.sanitized_text
    assert result.rut_count == 2


def test_pii_anonymizer_phone_and_email(anonymizer):
    """
    Verifica la detección y enmascaramiento de teléfonos y correos electrónicos.
    """
    text = "Contáctenme al teléfono +569 9876 5432 o al correo paciente.test@gmail.com para mi hora."
    result = anonymizer.anonymize(text)

    assert "+569 9876 5432" not in result.sanitized_text
    assert "paciente.test@gmail.com" not in result.sanitized_text
    assert "[TELEFONO_PROTEGIDO]" in result.sanitized_text
    assert "[EMAIL_PROTEGIDO]" in result.sanitized_text
    assert result.phone_count >= 1
    assert result.email_count == 1
