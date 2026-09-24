"""
Herramientas de Tool Calling y Gestión Transaccional - Mock HIS (SQLite)
Red de Salud Metropolitana SaludConecta - Duoc UC (ISY0101)

Implementa las herramientas que el LLM y el orquestador pueden invocar para:
1. Consultar cupos médicos disponibles según filtros clínicos o geográficos (consultar_disponibilidad_horas).
2. Reservar atómicamente una cita médica con validación de RUT chileno (reservar_cita_medica).
3. Cancelar o liberar una cita médica previamente agendada (cancelar_cita_medica).
"""

import sqlite3
import csv
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path
from langchain_core.tools import tool

from src.config import DB_PATH, CITAS_CSV_PATH


def validar_formato_rut_chileno(rut: str) -> bool:
    """
    Valida el formato de un RUT chileno:
    7 u 8 dígitos, separador de miles opcional, guion y dígito verificador (0-9 o K).
    Ejemplos válidos: 12.345.678-9, 12345678-9, 9.876.543-K, 15678901-2
    """
    if not rut or not isinstance(rut, str):
        return False
    clean = rut.strip()
    return bool(re.match(r"^\d{1,2}(?:\.\d{3}\.\d{3}|\d{6,7})[-‐‑‒–—][0-9kK]$", clean))


def get_db_connection(db_file: Optional[Path] = None) -> sqlite3.Connection:
    """Retorna una conexión activa a la base de datos SQLite del Mock HIS."""
    target_path = db_file or DB_PATH
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_database(db_file: Optional[Path] = None, force_reset: bool = False):
    """
    Crea la tabla de citas e inicializa los registros desde citas_disponibles.csv si está vacía.
    """
    conn = get_db_connection(db_file)
    cursor = conn.cursor()

    if force_reset:
        cursor.execute("DROP TABLE IF EXISTS citas")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS citas (
            id INTEGER PRIMARY KEY,
            especialidad TEXT NOT NULL,
            medico TEXT NOT NULL,
            sucursal TEXT NOT NULL,
            comuna TEXT NOT NULL,
            fecha TEXT NOT NULL,
            hora TEXT NOT NULL,
            prevision TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'DISPONIBLE',
            paciente_rut TEXT,
            paciente_nombre TEXT,
            paciente_telefono TEXT,
            fecha_reserva TEXT
        )
    """)
    conn.commit()

    # Comprobar si existen registros
    cursor.execute("SELECT COUNT(*) FROM citas")
    total_citas = cursor.fetchone()[0]

    if total_citas == 0 and CITAS_CSV_PATH.exists():
        with open(CITAS_CSV_PATH, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cursor.execute("""
                    INSERT INTO citas (
                        id, especialidad, medico, sucursal, comuna, fecha, hora, prevision, estado
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    int(row["id"]),
                    row["especialidad"].strip(),
                    row["medico"].strip(),
                    row["sucursal"].strip(),
                    row["comuna"].strip(),
                    row["fecha"].strip(),
                    row["hora"].strip(),
                    row["prevision"].strip(),
                    row["estado"].strip()
                ))
        conn.commit()

    conn.close()


def _ejecutar_consulta_citas(
    especialidad: Optional[str] = None,
    comuna: Optional[str] = None,
    sucursal: Optional[str] = None,
    fecha: Optional[str] = None
) -> str:
    """Lógica central de consulta SQL sobre SQLite para cupos médicos disponibles."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT id, especialidad, medico, sucursal, comuna, fecha, hora, prevision FROM citas WHERE estado = 'DISPONIBLE'"
    params = []

    if especialidad and especialidad.strip():
        query += " AND LOWER(especialidad) LIKE ?"
        params.append(f"%{especialidad.strip().lower()}%")

    if comuna and comuna.strip():
        query += " AND LOWER(comuna) LIKE ?"
        params.append(f"%{comuna.strip().lower()}%")

    if sucursal and sucursal.strip():
        query += " AND LOWER(sucursal) LIKE ?"
        params.append(f"%{sucursal.strip().lower()}%")

    if fecha and fecha.strip():
        query += " AND fecha = ?"
        params.append(fecha.strip())

    query += " ORDER BY fecha ASC, hora ASC LIMIT 10"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        filtro_desc = []
        if especialidad: filtro_desc.append(f"especialidad '{especialidad}'")
        if comuna: filtro_desc.append(f"comuna '{comuna}'")
        if sucursal: filtro_desc.append(f"sucursal '{sucursal}'")
        if fecha: filtro_desc.append(f"fecha '{fecha}'")
        desc = ", ".join(filtro_desc) if filtro_desc else "los criterios solicitados"
        return f"No se encontraron citas médicas disponibles para {desc}. Sugiera modificar la fecha o comuna."

    resultados = []
    for r in rows:
        resultados.append(
            f"• ID Cita: {r['id']} | Especialidad: {r['especialidad']} | Médico: {r['medico']} | "
            f"Sucursal: {r['sucursal']} ({r['comuna']}) | Fecha: {r['fecha']} a las {r['hora']} hrs | "
            f"Convenio: {r['prevision']}"
        )

    return (
        f"Se encontraron {len(rows)} cupos disponibles en el sistema:\n" +
        "\n".join(resultados) +
        "\n\nPara confirmar la reserva, proporcione el ID de la cita, RUT, Nombre Completo y Teléfono del paciente."
    )


@tool
def consultar_disponibilidad_horas(
    especialidad: Optional[str] = None,
    comuna: Optional[str] = None,
    sucursal: Optional[str] = None,
    fecha: Optional[str] = None
) -> str:
    """
    Consulta la disponibilidad de horas y cupos médicos en el sistema hospitalario Mock HIS de SaludConecta.
    Permite filtrar por especialidad (ej: Cardiología, Traumatología), comuna de atención (ej: Santiago Centro, Providencia), sucursal o fecha.
    Retorna la lista de citas en formato estructurado con sus respectivos IDs de cita, nombres de médicos y horarios.
    """
    return _ejecutar_consulta_citas(
        especialidad=especialidad,
        comuna=comuna,
        sucursal=sucursal,
        fecha=fecha
    )


@tool
def consultar_citas_disponibles(
    especialidad: Optional[str] = None,
    comuna: Optional[str] = None,
    sucursal: Optional[str] = None,
    fecha: Optional[str] = None
) -> str:
    """
    Consulta cupos médicos disponibles en el sistema hospitalario Mock HIS de SaludConecta.
    Permite filtrar por especialidad, comuna de atención, sucursal o fecha.
    Retorna la lista de citas en formato estructurado para ofrecer al paciente.
    """
    return _ejecutar_consulta_citas(
        especialidad=especialidad,
        comuna=comuna,
        sucursal=sucursal,
        fecha=fecha
    )


@tool
def reservar_cita_medica(
    cita_id: int,
    paciente_rut: str,
    paciente_nombre: str,
    paciente_telefono: str
) -> str:
    """
    Reserva formalmente una cita médica en el sistema Mock HIS.
    Operación atómica transaccional: valida el formato de RUT chileno, comprueba que el cupo esté 'DISPONIBLE'
    y cambia el estado a 'RESERVADA' para evitar colisiones y doble agendamiento concurrente.
    Requiere cita_id (entero), paciente_rut (formato chileno con guion), paciente_nombre y paciente_telefono.
    """
    # 1. Validación de Formato de RUT chileno
    if not validar_formato_rut_chileno(paciente_rut):
        return (
            f"ERROR DE VALIDACIÓN: El RUT '{paciente_rut}' no tiene un formato chileno válido "
            "(ej: 12.345.678-9 o 12345678-K). Por favor verifique el número y dígito verificador."
        )

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN TRANSACTION")

        # 2. Comprobar existencia y estado actual de la cita
        cursor.execute("SELECT id, especialidad, medico, sucursal, comuna, fecha, hora, estado FROM citas WHERE id = ?", (cita_id,))
        cita = cursor.fetchone()

        if not cita:
            conn.rollback()
            conn.close()
            return f"ERROR: La cita con ID {cita_id} no existe en los registros de SaludConecta."

        if cita["estado"] != "DISPONIBLE":
            conn.rollback()
            conn.close()
            return f"ERROR: La cita con ID {cita_id} ({cita['especialidad']} con {cita['medico']}) ya no está disponible (Estado: {cita['estado']}). Por favor seleccione otro cupo."

        # 3. Ejecutar reserva atómica
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            UPDATE citas 
            SET estado = 'RESERVADA',
                paciente_rut = ?,
                paciente_nombre = ?,
                paciente_telefono = ?,
                fecha_reserva = ?
            WHERE id = ? AND estado = 'DISPONIBLE'
        """, (paciente_rut.strip(), paciente_nombre.strip(), paciente_telefono.strip(), now_str, cita_id))

        if cursor.rowcount == 0:
            conn.rollback()
            conn.close()
            return f"ERROR: Conflicto de concurrencia al reservar la cita ID {cita_id}. Ya fue tomada por otro usuario."

        conn.commit()
        conn.close()

        return (
            f"✅ RESERVA CONFIRMADA EXITOSAMENTE:\n"
            f"• Código de Cita: #{cita['id']}\n"
            f"• Especialidad: {cita['especialidad']}\n"
            f"• Profesional: {cita['medico']}\n"
            f"• Centro de Atención: {cita['sucursal']} ({cita['comuna']})\n"
            f"• Fecha y Hora: {cita['fecha']} a las {cita['hora']} hrs\n"
            f"• Paciente: {paciente_nombre.strip()} (RUT: {paciente_rut.strip()})\n"
            f"• Teléfono de Contacto: {paciente_telefono.strip()}\n"
            f"Recuerde presentarse 15 minutos antes de la hora indicada con su documento de identidad."
        )

    except Exception as e:
        conn.rollback()
        conn.close()
        return f"ERROR TRANSACCIONAL: Fallo al procesar la reserva en la base de datos: {str(e)}"


@tool
def cancelar_cita_medica(cita_id: int, paciente_rut: str) -> str:
    """
    Cancela una cita médica previamente reservada y la devuelve al estado 'DISPONIBLE'.
    Requiere el ID de la cita y el RUT del paciente para verificar identidad.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id, especialidad, medico, fecha, hora, estado, paciente_rut FROM citas WHERE id = ?", (cita_id,))
        cita = cursor.fetchone()

        if not cita:
            conn.close()
            return f"ERROR: No se encontró ninguna cita con el ID {cita_id}."

        if cita["estado"] != "RESERVADA":
            conn.close()
            return f"AVISO: La cita ID {cita_id} no se encuentra en estado 'RESERVADA' (Estado actual: {cita['estado']})."

        # Comprobar coincidencia simple de RUT (quitando puntos y guiones para robustez)
        clean_rut_db = (cita["paciente_rut"] or "").replace(".", "").replace("-", "").upper()
        clean_rut_in = paciente_rut.replace(".", "").replace("-", "").upper()

        if clean_rut_db != clean_rut_in:
            conn.close()
            return "ERROR DE AUTENTICACIÓN: El RUT proporcionado no coincide con el registrado para esta cita."

        cursor.execute("""
            UPDATE citas 
            SET estado = 'DISPONIBLE',
                paciente_rut = NULL,
                paciente_nombre = NULL,
                paciente_telefono = NULL,
                fecha_reserva = NULL
            WHERE id = ?
        """, (cita_id,))

        conn.commit()
        conn.close()

        return f"✅ CANCELACIÓN EXITOSA: La cita ID {cita_id} ({cita['especialidad']} del {cita['fecha']}) ha sido cancelada y el cupo ha sido liberado."

    except Exception as e:
        conn.rollback()
        conn.close()
        return f"ERROR TRANSACCIONAL: Fallo al cancelar la cita: {str(e)}"


# Lista consolidada de herramientas para el agente orquestador
AGENDA_TOOLS = [
    consultar_disponibilidad_horas,
    consultar_citas_disponibles,
    reservar_cita_medica,
    cancelar_cita_medica,
]
