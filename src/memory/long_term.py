"""
Memoria de largo plazo por paciente (SQLite) - Red SaludConecta
Persiste entre sesiones las preferencias, atenciones previas e indicaciones entregadas.
Se indexa por paciente_id simulado y no guarda transcripciones de la conversación.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from src.tools_agenda import get_db_connection


def _ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalizar_rut(rut: Optional[str]) -> str:
    """Quita puntos y guiones para comparar RUT escritos en formatos distintos."""
    return "".join(c for c in (rut or "") if c.isalnum()).upper()


class MemoriaLargoPlazo:
    """Interfaz de lectura y escritura de la memoria persistente de cada paciente."""

    def obtener_paciente(self, paciente_id: str) -> Optional[Dict[str, Any]]:
        conn = get_db_connection()
        fila = conn.execute("SELECT * FROM pacientes WHERE paciente_id = ?", (paciente_id,)).fetchone()
        conn.close()
        if not fila:
            return None
        paciente = dict(fila)
        paciente["farmacos"] = [f for f in paciente["farmacos"].split(",") if f]
        paciente["alergias"] = [a for a in paciente["alergias"].split(",") if a]
        return paciente

    def agregar_farmaco(self, paciente_id: str, farmaco: str) -> None:
        """Agrega a la ficha un fármaco declarado por el paciente, sin duplicarlo."""
        paciente = self.obtener_paciente(paciente_id)
        if not paciente or farmaco in paciente["farmacos"]:
            return
        conn = get_db_connection()
        conn.execute(
            "UPDATE pacientes SET farmacos = ? WHERE paciente_id = ?",
            (",".join(paciente["farmacos"] + [farmaco]), paciente_id),
        )
        conn.commit()
        conn.close()

    def guardar_preferencia(self, paciente_id: str, clave: str, valor: str) -> None:
        conn = get_db_connection()
        conn.execute(
            """INSERT INTO preferencias (paciente_id, clave, valor, actualizado_en) VALUES (?, ?, ?, ?)
               ON CONFLICT(paciente_id, clave) DO UPDATE SET valor = excluded.valor,
               actualizado_en = excluded.actualizado_en""",
            (paciente_id, clave, valor, _ahora()),
        )
        conn.commit()
        conn.close()

    def preferencias(self, paciente_id: str) -> Dict[str, str]:
        conn = get_db_connection()
        filas = conn.execute("SELECT clave, valor FROM preferencias WHERE paciente_id = ?", (paciente_id,)).fetchall()
        conn.close()
        return {f["clave"]: f["valor"] for f in filas}

    def registrar_atencion(self, paciente_id: str, tipo: str, resumen: str, cita_id: Optional[int] = None) -> int:
        conn = get_db_connection()
        cursor = conn.execute(
            "INSERT INTO atenciones (paciente_id, fecha, tipo, resumen, cita_id) VALUES (?, ?, ?, ?, ?)",
            (paciente_id, _ahora(), tipo, resumen, cita_id),
        )
        conn.commit()
        conn.close()
        return cursor.lastrowid

    def atenciones(self, paciente_id: str, limite: int = 5) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        filas = conn.execute(
            "SELECT * FROM atenciones WHERE paciente_id = ? ORDER BY id DESC LIMIT ?", (paciente_id, limite)
        ).fetchall()
        conn.close()
        return [dict(f) for f in filas]

    def registrar_indicacion(
        self, paciente_id: str, cita_id: Optional[int], texto: str, archivo: Optional[str] = None
    ) -> None:
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO indicaciones (paciente_id, cita_id, texto, archivo, fecha) VALUES (?, ?, ?, ?, ?)",
            (paciente_id, cita_id, texto, archivo, _ahora()),
        )
        conn.commit()
        conn.close()

    def indicaciones(self, paciente_id: str, cita_id: Optional[int] = None, limite: int = 5) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        consulta = "SELECT * FROM indicaciones WHERE paciente_id = ?"
        params: List[Any] = [paciente_id]
        if cita_id is not None:
            consulta += " AND cita_id = ?"
            params.append(cita_id)
        filas = conn.execute(consulta + " ORDER BY id DESC LIMIT ?", params + [limite]).fetchall()
        conn.close()
        return [dict(f) for f in filas]

    def citas_pendientes(self, rut: Optional[str]) -> List[Dict[str, Any]]:
        """
        Citas RESERVADAS del paciente. No se compara con la fecha actual porque
        el Mock HIS es un calendario simulado: pendiente equivale a estado RESERVADA.
        """
        objetivo = normalizar_rut(rut)
        if not objetivo:
            return []
        conn = get_db_connection()
        filas = conn.execute(
            """SELECT id, especialidad, medico, sucursal, comuna, fecha, hora, prevision, paciente_rut
               FROM citas WHERE estado = 'RESERVADA' ORDER BY fecha, hora"""
        ).fetchall()
        conn.close()
        return [dict(f) for f in filas if normalizar_rut(f["paciente_rut"]) == objetivo]
