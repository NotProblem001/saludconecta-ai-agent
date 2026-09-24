"""
Batería de Pruebas Unitarias: Grounding Fáctico y Abstención Institucional RAG
Asignatura: ISY0101 - Ingeniería de Soluciones con Inteligencia Artificial
Proyecto: Sistema Agéntico SaludConecta
"""

import shutil
import tempfile
import pytest
from src.rag_engine import RAGEngine


@pytest.fixture(scope="module")
def temp_rag_engine():
    """
    Crea una instancia aislada del motor RAG utilizando un directorio temporal
    y embeddings deterministas para asegurar ejecución 100% reproducible y offline.
    """
    temp_dir = tempfile.mkdtemp()
    engine = RAGEngine(
        persist_directory=temp_dir,
        force_reindex=True,
        use_mock_embeddings=True
    )
    yield engine
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_rag_corpus_loaded_correctly(temp_rag_engine):
    """
    Verifica que el corpus institucional de manual_preparacion.md y catalogo_especialidades.md
    haya sido cargado y chunked en la base vectorial.
    """
    collection = temp_rag_engine.vector_store._collection
    count = collection.count()
    assert count > 0, "La base vectorial ChromaDB debe contener fragmentos indexados."


def test_rag_grounding_perfil_lipidico(temp_rag_engine):
    """
    Verifica la recuperación fáctica de indicaciones de ayuno para el Perfil Lipídico (LAB-001).
    """
    query = "ayuno para examen de perfil lipidico y glicemia"
    # Usar umbral moderado para embeddings deterministas
    result = temp_rag_engine.retrieve_with_threshold(query, top_k=3, threshold=0.50)

    assert result["grounding_found"] is True
    assert len(result["documents"]) > 0

    combined_text = result["context_text"].lower()
    assert "ayuno" in combined_text
    assert "8 a 12 horas" in combined_text or "perfil lipídico" in combined_text


def test_rag_grounding_tac_abdomen_contraste(temp_rag_engine):
    """
    Verifica la recuperación de prerrequisitos de función renal y metformina para TAC con contraste (IMG-102).
    """
    query = "tomografía computarizada tac abdomen contraste creatinina y metformina"
    result = temp_rag_engine.retrieve_with_threshold(query, top_k=3, threshold=0.50)

    assert result["grounding_found"] is True
    combined_text = result["context_text"].lower()
    assert "creatinina" in combined_text or "metformina" in combined_text


def test_rag_grounding_especialidad_cardiologia(temp_rag_engine):
    """
    Verifica la recuperación de prerrequisitos clínicos para consulta de Cardiología Adulto.
    """
    query = "prerrequisito electrocardiograma cardiologia adulto"
    result = temp_rag_engine.retrieve_with_threshold(query, top_k=3, threshold=0.50)

    assert result["grounding_found"] is True
    combined_text = result["context_text"].lower()
    assert "electrocardiograma" in combined_text or "ecg" in combined_text


def test_rag_abstention_on_unknown_procedure(temp_rag_engine):
    """
    Verifica la REGLA DE ORO DE ABSTENCIÓN FÁCTICA:
    Ante una consulta sobre un procedimiento totalmente inexistente en los manuales
    (ej: biopsia cerebral marciana extraterrestre), el retriever debe declarar grounding_found=False
    y emitir la directriz de abstención para evitar alucinaciones clínicas.
    """
    query = "preparación para biopsia hepática espacial de astronautas en gravedad cero"
    result = temp_rag_engine.retrieve_with_threshold(query, top_k=3, threshold=0.75)

    assert result["grounding_found"] is False
    assert len(result["documents"]) == 0
    assert "REGLA DE ABSTENCIÓN ACTIVA" in result["context_text"]
    assert "600 000 1234" in result["context_text"]
