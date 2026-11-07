"""
Traza de decisiones del agente - Red SaludConecta
Registra plan inicial, replanificaciones y su motivo en el log y en SQLite. Nunca guarda PII.
"""

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.tools_agenda import get_db_connection

logger = logging.getLogger("saludconecta.traza")

CAMPOS_SENSIBLES = {"paciente_rut", "paciente_nombre", "paciente_telefono", "rut", "nombre", "telefono"}


def sin_pii(detalle: Dict[str, Any]) -> Dict[str, Any]:
    """Enmascara los campos personales de un diccionario de argumentos."""
    return {k: ("***" if k in CAMPOS_SENSIBLES else v) for k, v in detalle.items()}


@dataclass
class EventoTraza:
    turno: int
    ts: str
    tipo: str
    motivo: str
    paso: Optional[str] = None
    detalle: Dict[str, Any] = field(default_factory=dict)


class TrazaDecisiones:
    """Acumula los eventos de una sesión; cada turno se vuelca a SQLite."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.turno = 0
        self.eventos: List[EventoTraza] = []
        self._persistidos = 0

    def registrar(self, tipo: str, motivo: str, paso: Optional[str] = None, **detalle: Any) -> None:
        evento = EventoTraza(
            turno=self.turno, ts=datetime.now().strftime("%H:%M:%S"), tipo=tipo,
            motivo=motivo, paso=paso, detalle=sin_pii(detalle),
        )
        self.eventos.append(evento)
        logger.info("[%s t%d] %s | %s | %s", self.session_id, self.turno, tipo, paso or "-", motivo)

    def del_turno(self) -> List[Dict[str, Any]]:
        return [asdict(e) for e in self.eventos if e.turno == self.turno]

    def persistir(self) -> None:
        """Una falla de la BD no debe impedir responder al paciente: se conserva en memoria y en el log."""
        pendientes = self.eventos[self._persistidos:]
        if not pendientes:
            return
        try:
            conn = get_db_connection()
            conn.executemany(
                """INSERT INTO traza_decisiones (session_id, turno, ts, tipo, paso, motivo, detalle)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (self.session_id, e.turno, e.ts, e.tipo, e.paso, e.motivo, json.dumps(e.detalle, ensure_ascii=False))
                    for e in pendientes
                ],
            )
            conn.commit()
            conn.close()
            self._persistidos = len(self.eventos)
        except sqlite3.Error as e:
            logger.warning("No se pudo persistir la traza: %s", e)


def formatear_traza(eventos: List[Dict[str, Any]]) -> str:
    """Representación legible para la CLI y el script de demo."""
    lineas = []
    for e in eventos:
        paso = f" [{e['paso']}]" if e.get("paso") else ""
        lineas.append(f"  t{e['turno']} {e['tipo']:<13}{paso} {e['motivo']}")
    return "\n".join(lineas)


def leer_traza(session_id: str) -> List[Dict[str, Any]]:
    """Consulta posterior de la traza persistida de una sesión."""
    conn = get_db_connection()
    filas = conn.execute(
        "SELECT turno, ts, tipo, paso, motivo, detalle FROM traza_decisiones WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    conn.close()
    return [dict(f) | {"detalle": json.loads(f["detalle"] or "{}")} for f in filas]
