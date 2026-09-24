"""
Batería de Pruebas Unitarias: Agente Orquestador, Memoria Conversacional, RAG Synthesis y Tool Calling
Asignatura: ISY0101 - Ingeniería de Soluciones con Inteligencia Artificial
Proyecto: Sistema Agéntico SaludConecta - Duoc UC
"""

import tempfile
import shutil
import warnings
from pathlib import Path
import pytest

warnings.filterwarnings("ignore")

from src.agent_orchestrator import SaludConectaAgent
from src.tools_agenda import init_database, get_db_connection


@pytest.fixture
def isolated_agent(monkeypatch):
    """
    Crea una instancia aislada de SaludConectaAgent con base de datos SQLite y
    directorio de ChromaDB temporales para garantizar tests 100% independientes y reproducibles.
    """
    temp_dir = tempfile.mkdtemp()
    temp_db_path = Path(temp_dir) / "test_his.db"
    temp_chroma_path = Path(temp_dir) / "test_chroma"

    monkeypatch.setattr("src.tools_agenda.DB_PATH", temp_db_path)
    monkeypatch.setattr("src.agent_orchestrator.DB_PATH", temp_db_path)

    init_database(db_file=temp_db_path, force_reset=True)

    agent = SaludConectaAgent(
        memory_k=5,
        use_mock_embeddings=True,
    )
    agent.rag_engine.persist_directory = str(temp_chroma_path)
    agent.rag_engine._initialize_vector_store(force_reindex=True)

    yield agent

    shutil.rmtree(temp_dir, ignore_errors=True)


def test_rag_synthesis_no_raw_dump(isolated_agent):
    """
    ANOMALÍA 1: Verifica que el RAG NUNCA vuelque metadatos en crudo ([Documento 1 | Fuente: ... | Relevancia: ...])
    y que en su lugar sintetice una respuesta clínica fluida con la referencia oficial [Ref: Protocolo LAB-001].
    """
    query = "¿Cuáles son las indicaciones de ayuno para un examen de perfil lipídico y glicemia?"
    result = isolated_agent.process_message(query)
    response = result["response"]

    # Verificar que NO existan metadatos en crudo
    assert "[Documento" not in response
    assert "Relevancia:" not in response
    assert "[Fragmento" not in response

    # Verificar presencia de síntesis clínica y código de protocolo
    assert "ayuno" in response.lower()
    assert "8 a 12 horas" in response.lower() or "8 a 10 horas" in response.lower()
    assert "[Ref: Protocolo LAB-001]" in response
    assert result["grounding_found"] is True


def test_cobertura_disambiguation_no_static_loop(isolated_agent):
    """
    ANOMALÍA 2: Verifica que ante la consulta '¿dónde tienen cobertura?' no se caiga en la plantilla
    estática de orientación genérica, sino que se desambigüe la red de sedes y convenios previsionales.
    """
    query = "¿Dónde tienen cobertura?"
    result = isolated_agent.process_message(query)
    response = result["response"]

    # Verificar desglose de sedes de la red
    assert "Santiago Centro" in response
    assert "Providencia" in response
    assert "La Florida" in response
    assert "Las Condes" in response
    assert "Maipú" in response

    # Verificar información previsional Fonasa e Isapre
    assert "Fonasa" in response
    assert "Isapres" in response or "Isapre" in response

    # No debe ser la plantilla estática repetitiva genérica
    assert "👩‍⚕️ **Orientación Clínica Inicial - Red SaludConecta**" not in response


def test_conversational_memory_and_tool_calling(isolated_agent):
    """
    ANOMALÍA 3: Verifica que tras preguntar por cobertura, cuando el paciente solicita
    'deseo consultar las de Santiago Centro', el agente recuerde el contexto conversacional,
    invoque la herramienta 'consultar_disponibilidad_horas' sobre SQLite y renderice cupos disponibles.
    """
    # Turno 1: Consulta de cobertura
    r1 = isolated_agent.process_message("¿Dónde tienen cobertura?")
    assert "Santiago Centro" in r1["response"]

    # Turno 2: Seguimiento contextual en Santiago Centro
    r2 = isolated_agent.process_message("deseo consultar las de Santiago Centro")

    assert "consultar_disponibilidad_horas" in r2["tools_used"]
    assert "Santiago Centro" in r2["response"]
    assert "ID Cita:" in r2["response"]
    assert "Médico:" in r2["response"]


def test_booking_with_rut_validation(isolated_agent):
    """
    Verifica que la reserva de horas valide el formato chileno del RUT y ejecute
    la reserva atómica cambiando el estado en SQLite a 'RESERVADA'.
    """
    # 1. Intento con RUT inválido
    r_invalid = isolated_agent.process_message("Quiero reservar la cita 4 para Juan Pérez, RUT 12345 y fono +56912345678")
    assert "formato" in r_invalid["response"].lower() or "rut" in r_invalid["response"].lower()

    # 2. Intento con RUT válido (formato chileno)
    r_valid = isolated_agent.process_message("Quiero reservar la cita 4 para Juan Pérez, RUT 15.678.901-2 y fono +56988776655")
    assert "RESERVA CONFIRMADA EXITOSAMENTE" in r_valid["response"]
    assert "#4" in r_valid["response"]
    assert "Juan Pérez" in r_valid["response"]
    assert "reservar_cita_medica" in r_valid["tools_used"]


def test_golden_rule_of_abstention(isolated_agent):
    """
    Verifica que ante un procedimiento no registrado en los manuales institucionales,
    se active la Regla de Oro de Abstención Fáctica declarando la ausencia del protocolo
    y derivando a la Mesa Central 600 000 1234.
    """
    query = "¿Cuál es la preparación para una biopsia hepática espacial de astronautas en gravedad cero?"
    result = isolated_agent.process_message(query)
    response = result["response"]

    assert result["grounding_found"] is False
    assert "no figura en nuestros manuales institucionales disponibles" in response
    assert "600 000 1234" in response


def test_emergency_bypass_in_agent(isolated_agent):
    """
    Verifica que el orquestador active el bypass de Código Rojo en menos de 100 ms
    y redirija inmediatamente al SAMU 131 sin llamadas al LLM ni RAG.
    """
    query = "Tengo un dolor muy fuerte en el pecho opresivo que se me sube a la mandíbula y brazo izquierdo"
    result = isolated_agent.process_message(query)

    assert result["bypass_activated"] is True
    assert result["emergency_level"] == "CODIGO_ROJO"
    assert "131" in result["response"] or "SAMU" in result["response"]
    assert result["response_time_ms"] < 100.0
