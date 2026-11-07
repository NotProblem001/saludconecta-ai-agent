"""
Configuración común de PyTest: garantiza una suite determinista y sin red.
Aunque exista una API key real en .env, ningún test llega al proveedor LLM.
"""

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from src.agent_orchestrator import SaludConectaAgent
from src.tools_agenda import get_db_connection, init_database


@pytest.fixture(autouse=True)
def sin_credenciales_llm(monkeypatch):
    """Fuerza el modo sin credenciales; los tests que necesitan LLM inyectan un modelo falso."""
    credenciales_mock = lambda: ("mock-token", "http://localhost")
    monkeypatch.setattr("src.agent_orchestrator.get_llm_credentials", credenciales_mock)
    monkeypatch.setattr("src.rag_engine.get_llm_credentials", credenciales_mock)


class LLMFalso:
    """Modelo determinista: responde en orden y registra todo lo que recibe."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.recibido = []

    @property
    def llamadas(self):
        return len(self.recibido)

    def invoke(self, messages):
        self.recibido.append(" ".join(str(m.content) for m in messages))
        return AIMessage(content=self.respuestas.pop(0) if self.respuestas else "Sin guion")


def plan_json(intencion, *herramientas, **args_por_paso):
    """Plan con el formato que devolvería el LLM."""
    return json.dumps({
        "intencion": intencion,
        "objetivo": "Plan de prueba",
        "pasos": [{"herramienta": h, "args": args_por_paso.get(h, {})} for h in herramientas],
    })


@pytest.fixture(scope="session")
def chroma_compartido(tmp_path_factory):
    """El índice de manuales no cambia entre tests: se construye una sola vez."""
    return str(tmp_path_factory.mktemp("chroma"))


@pytest.fixture
def entorno(monkeypatch, tmp_path, chroma_compartido):
    """HIS y comprobantes temporales, y una forma de crear agentes sobre ellos."""
    ruta_bd = tmp_path / "his.db"
    monkeypatch.setattr("src.tools_agenda.DB_PATH", ruta_bd)
    monkeypatch.setattr("src.config.COMPROBANTES_DIR", tmp_path / "comprobantes")
    monkeypatch.setattr("src.tools.base.ESPERA_BASE_S", 0)
    init_database(db_file=ruta_bd, force_reset=True)

    def crear_agente(paciente_id=None, llm=None):
        return SaludConectaAgent(
            use_mock_embeddings=True, paciente_id=paciente_id, llm=llm, persist_directory=chroma_compartido
        )

    def estado_cita(cita_id):
        conn = get_db_connection()
        fila = conn.execute("SELECT estado FROM citas WHERE id = ?", (cita_id,)).fetchone()
        conn.close()
        return fila["estado"]

    def tumbar_bd():
        monkeypatch.setattr("src.tools_agenda.DB_PATH", tmp_path / "no_existe" / "his.db")

    return SimpleNamespace(
        crear_agente=crear_agente, estado_cita=estado_cita, tumbar_bd=tumbar_bd,
        comprobantes=tmp_path / "comprobantes",
    )


def eventos(resultado, tipo):
    return [e for e in resultado["traza"] if e["tipo"] == tipo]
