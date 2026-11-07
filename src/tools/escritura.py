"""
Herramientas de escritura sobre el Mock HIS - Red SaludConecta
Reutilizan las transacciones de tools_agenda y las exponen con salida estructurada.
"""

import re
import sqlite3
from datetime import datetime

from src import config
from src.memory.long_term import MemoriaLargoPlazo, normalizar_rut
from src.tools.base import herramienta
from src.tools.schemas import (
    EntradaAtencion,
    EntradaCancelacion,
    EntradaComprobante,
    EntradaReprogramacion,
    EntradaReserva,
    SalidaAtencion,
    SalidaComprobante,
    SalidaEscritura,
)
from src.tools_agenda import (
    cancelar_cita_medica as _cancelar_his,
    get_db_connection,
    reservar_cita_medica as _reservar_his,
    validar_formato_rut_chileno,
)


def _si_falla_bd(texto: str) -> str:
    """Las tools del HIS devuelven el fallo como texto; aquí vuelve a ser error para poder reintentar."""
    if texto.startswith("ERROR TRANSACCIONAL"):
        raise sqlite3.OperationalError(texto)
    return texto


@herramienta("escritura", EntradaReserva, SalidaEscritura)
def reservar_cita_medica(e: EntradaReserva) -> SalidaEscritura:
    """Reserva un cupo de forma atómica. Falla con RUT_INVALIDO o CUPO_NO_DISPONIBLE sin modificar el HIS."""
    texto = _si_falla_bd(_reservar_his.invoke(e.model_dump()))
    if "RESERVA CONFIRMADA" in texto:
        return SalidaEscritura(cita_id=e.cita_id, mensaje=texto)
    codigo = "RUT_INVALIDO" if texto.startswith("ERROR DE VALIDACIÓN") else "CUPO_NO_DISPONIBLE"
    return SalidaEscritura(ok=False, error=codigo, mensaje=texto, cita_id=e.cita_id)


@herramienta("escritura", EntradaCancelacion, SalidaEscritura)
def cancelar_cita_medica(e: EntradaCancelacion) -> SalidaEscritura:
    """Cancela una cita reservada tras verificar el RUT del titular y libera el cupo."""
    texto = _si_falla_bd(_cancelar_his.invoke(e.model_dump()))
    if "CANCELACIÓN EXITOSA" in texto:
        return SalidaEscritura(cita_id=e.cita_id, mensaje=texto)
    codigo = "RUT_NO_COINCIDE" if texto.startswith("ERROR DE AUTENTICACIÓN") else "CITA_NO_RESERVADA"
    return SalidaEscritura(ok=False, error=codigo, mensaje=texto, cita_id=e.cita_id)


@herramienta("escritura", EntradaReprogramacion, SalidaEscritura)
def reprogramar_cita(e: EntradaReprogramacion) -> SalidaEscritura:
    """Mueve una reserva a un cupo nuevo en una sola transacción: o cambian ambos cupos o ninguno."""
    if not validar_formato_rut_chileno(e.paciente_rut):
        return SalidaEscritura(ok=False, error="RUT_INVALIDO", mensaje="El RUT no tiene formato chileno válido.")

    conn = get_db_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        actual = conn.execute("SELECT * FROM citas WHERE id = ?", (e.cita_actual,)).fetchone()
        es_titular = actual and normalizar_rut(actual["paciente_rut"]) == normalizar_rut(e.paciente_rut)
        if not es_titular or actual["estado"] != "RESERVADA":
            conn.rollback()
            return SalidaEscritura(
                ok=False, error="RUT_NO_COINCIDE", cita_id=e.cita_actual,
                mensaje=f"La cita #{e.cita_actual} no está reservada a nombre de este paciente.",
            )
        ocupada = conn.execute(
            """UPDATE citas SET estado = 'RESERVADA', paciente_rut = ?, paciente_nombre = ?,
               paciente_telefono = ?, fecha_reserva = ? WHERE id = ? AND estado = 'DISPONIBLE'""",
            (actual["paciente_rut"], actual["paciente_nombre"], actual["paciente_telefono"],
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), e.cita_id),
        )
        if ocupada.rowcount == 0:
            conn.rollback()
            return SalidaEscritura(
                ok=False, error="CUPO_NO_DISPONIBLE", cita_id=e.cita_id,
                mensaje=f"El cupo #{e.cita_id} ya no está disponible.",
            )
        conn.execute(
            """UPDATE citas SET estado = 'DISPONIBLE', paciente_rut = NULL, paciente_nombre = NULL,
               paciente_telefono = NULL, fecha_reserva = NULL WHERE id = ?""",
            (e.cita_actual,),
        )
        nueva = conn.execute("SELECT * FROM citas WHERE id = ?", (e.cita_id,)).fetchone()
        conn.commit()
        return SalidaEscritura(
            cita_id=e.cita_id,
            mensaje=(
                f"✅ REPROGRAMACIÓN EXITOSA: la cita #{e.cita_actual} se movió al cupo #{e.cita_id}: "
                f"{nueva['especialidad']} con {nueva['medico']}, {nueva['sucursal']} ({nueva['comuna']}), "
                f"{nueva['fecha']} a las {nueva['hora']} hrs."
            ),
        )
    finally:
        conn.close()


@herramienta("escritura", EntradaAtencion, SalidaAtencion)
def registrar_atencion(e: EntradaAtencion) -> SalidaAtencion:
    """Registra en el HIS el resumen de la atención para futuras sesiones del paciente."""
    atencion_id = MemoriaLargoPlazo().registrar_atencion(e.paciente_id, e.tipo, e.resumen, e.cita_id)
    return SalidaAtencion(atencion_id=atencion_id, mensaje=f"Atención #{atencion_id} registrada.")


@herramienta("escritura", EntradaComprobante, SalidaComprobante)
def generar_comprobante(e: EntradaComprobante) -> SalidaComprobante:
    """Genera un comprobante .txt de la cita con sus indicaciones. No incluye RUT ni teléfono."""
    conn = get_db_connection()
    cita = conn.execute("SELECT * FROM citas WHERE id = ?", (e.cita_id,)).fetchone()
    conn.close()
    if not cita:
        return SalidaComprobante(ok=False, error="CITA_INEXISTENTE", mensaje=f"La cita #{e.cita_id} no existe.")

    lineas = [
        "RED SALUDCONECTA - COMPROBANTE DE CITA",
        f"Código de cita: #{cita['id']}",
        f"Especialidad: {cita['especialidad']}",
        f"Profesional: {cita['medico']}",
        f"Centro: {cita['sucursal']} ({cita['comuna']})",
        f"Fecha y hora: {cita['fecha']} a las {cita['hora']} hrs",
    ]
    if e.indicaciones:
        lineas += ["", "INDICACIONES:"] + [f"- {i}" for i in e.indicaciones]
    lineas += ["", "Documento orientativo. No sustituye la indicación de su médico tratante (Ley N° 20.584)."]

    config.COMPROBANTES_DIR.mkdir(parents=True, exist_ok=True)
    marca = re.sub(r"\D", "", datetime.now().isoformat())
    archivo = config.COMPROBANTES_DIR / f"comprobante_cita{cita['id']}_{marca}.txt"
    archivo.write_text("\n".join(lineas), encoding="utf-8")

    if e.paciente_id and e.indicaciones:
        MemoriaLargoPlazo().registrar_indicacion(e.paciente_id, e.cita_id, " ".join(e.indicaciones), str(archivo))
    return SalidaComprobante(archivo=str(archivo), mensaje=f"Comprobante generado: {archivo.name}")
