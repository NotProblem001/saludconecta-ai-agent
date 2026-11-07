"""
Configuración común de PyTest: garantiza una suite determinista y sin red.
Aunque exista una API key real en .env, ningún test llega al proveedor LLM.
"""

import pytest


@pytest.fixture(autouse=True)
def sin_credenciales_llm(monkeypatch):
    """Fuerza el modo sin credenciales; los tests que necesitan LLM inyectan un modelo falso."""
    credenciales_mock = lambda: ("mock-token", "http://localhost")
    monkeypatch.setattr("src.agent_orchestrator.get_llm_credentials", credenciales_mock)
    monkeypatch.setattr("src.rag_engine.get_llm_credentials", credenciales_mock)
