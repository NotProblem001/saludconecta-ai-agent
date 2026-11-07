"""
Memoria de corto plazo por sesión - Red SaludConecta
Ventana conversacional deslizante y estado de la tarea en curso (plan, paso y datos recolectados).
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

if TYPE_CHECKING:
    from src.planner import Plan


class MemoriaVentana:
    """Conserva los últimos k turnos. Solo debe recibir texto ya anonimizado."""

    def __init__(self, k: int = 5):
        self.k = k
        self.messages: List[BaseMessage] = []

    @property
    def chat_memory(self) -> "MemoriaVentana":
        return self

    def add_user_message(self, message: str) -> None:
        self.messages.append(HumanMessage(content=message))
        self._trim()

    def add_ai_message(self, message: str) -> None:
        self.messages.append(AIMessage(content=message))
        self._trim()

    def _trim(self) -> None:
        self.messages = self.messages[-self.k * 2:]

    def clear(self) -> None:
        self.messages.clear()


@dataclass
class EstadoTarea:
    """Tarea en curso: sobrevive entre turnos de la misma sesión."""
    plan: Optional["Plan"] = None
    datos: Dict[str, Any] = field(default_factory=dict)
    resultados: Dict[str, Any] = field(default_factory=dict)

    @property
    def activa(self) -> bool:
        return self.plan is not None and self.plan.estado in ("en_curso", "esperando_paciente")

    def cerrar(self, conservar: tuple = ()) -> None:
        """Descarta plan y resultados; conserva solo los datos indicados."""
        self.plan = None
        self.resultados = {}
        self.datos = {k: v for k, v in self.datos.items() if k in conservar}
