"""
Batería de Pruebas Unitarias: Tool Calling y Transaccionalidad Mock HIS (SQLite)
Asignatura: ISY0101 - Ingeniería de Soluciones con Inteligencia Artificial
Proyecto: Sistema Agéntico SaludConecta
"""

import tempfile
from pathlib import Path
import pytest

from src.tools_agenda import (
    init_database,
    get_db_connection,
    consultar_citas_disponibles,
    reservar_cita_medica,
    cancelar_cita_medica
)


@pytest.fixture(autouse=True)
def setup_isolated_db(monkeypatch):
    """
    Crea una base de datos SQLite aislada en un archivo temporal para cada prueba
    e inicializa las 25 citas sintéticas desde el CSV.
    """
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_db_path = Path(temp_file.name)
    temp_file.close()

    # Sobrescribir DB_PATH en tools_agenda mediante monkeypatch
    monkeypatch.setattr("src.tools_agenda.DB_PATH", temp_db_path)

    # Inicializar esquema y registros
    init_database(db_file=temp_db_path, force_reset=True)

    yield temp_db_path

    # Limpiar archivo temporal al finalizar
    if temp_db_path.exists():
        try:
            temp_db_path.unlink()
        except PermissionError:
            pass


# ==============================================================================
# 1. Pruebas de Consulta de Cupos Médicos
# ==============================================================================

def test_consultar_citas_filtro_especialidad():
    """
    Verifica la búsqueda de citas por especialidad médica.
    """
    resultado = consultar_citas_disponibles.invoke({"especialidad": "Cardiología Adulto"})
    assert "Dr. Roberto Silva" in resultado or "Dra. Marcela Lagos" in resultado
    assert "Cardiología Adulto" in resultado
    assert "ID Cita:" in resultado


def test_consultar_citas_filtro_comuna():
    """
    Verifica la búsqueda de citas filtrando por comuna geográfica.
    """
    resultado = consultar_citas_disponibles.invoke({"comuna": "Providencia"})
    assert "Providencia" in resultado
    assert "Centro Médico Providencia" in resultado


def test_consultar_citas_sin_resultados():
    """
    Verifica el manejo elegante cuando no existen cupos para el criterio solicitado.
    """
    resultado = consultar_citas_disponibles.invoke({"especialidad": "Neurocirugía Fetal Inexistente"})
    assert "No se encontraron citas médicas disponibles" in resultado


# ==============================================================================
# 2. Pruebas de Reserva Atómica y Prevención de Doble Agendamiento
# ==============================================================================

def test_reservar_cita_exitosa():
    """
    Verifica el flujo exitoso de reserva atómica en la base de datos.
    """
    cita_id = 1
    paciente_rut = "15.678.901-2"
    paciente_nombre = "Carlos González Muñoz"
    paciente_tel = "+569 8877 6655"

    resultado = reservar_cita_medica.invoke({
        "cita_id": cita_id,
        "paciente_rut": paciente_rut,
        "paciente_nombre": paciente_nombre,
        "paciente_telefono": paciente_tel
    })

    assert "RESERVA CONFIRMADA EXITOSAMENTE" in resultado
    assert f"#{cita_id}" in resultado
    assert paciente_nombre in resultado

    # Verificar estado en la base de datos
    conn = get_db_connection()
    row = conn.execute("SELECT estado, paciente_rut, paciente_nombre FROM citas WHERE id = ?", (cita_id,)).fetchone()
    conn.close()

    assert row["estado"] == "RESERVADA"
    assert row["paciente_rut"] == paciente_rut
    assert row["paciente_nombre"] == paciente_nombre


def test_prevencion_doble_agendamiento_conflicto():
    """
    Verifica que no sea posible reservar una cita que ya fue tomada (control de colisiones).
    """
    cita_id = 2

    # 1. Primera reserva exitosa
    res1 = reservar_cita_medica.invoke({
        "cita_id": cita_id,
        "paciente_rut": "11.111.111-1",
        "paciente_nombre": "Paciente Primero",
        "paciente_telefono": "+56911111111"
    })
    assert "RESERVA CONFIRMADA EXITOSAMENTE" in res1

    # 2. Segundo intento sobre el mismo cupo debe ser rechazado
    res2 = reservar_cita_medica.invoke({
        "cita_id": cita_id,
        "paciente_rut": "22.222.222-2",
        "paciente_nombre": "Paciente Segundo",
        "paciente_telefono": "+56922222222"
    })
    assert "ERROR: La cita con ID 2" in res2
    assert "ya no está disponible" in res2


def test_reservar_cita_inexistente():
    """
    Verifica el manejo de error cuando se intenta reservar un ID de cita inexistente.
    """
    res = reservar_cita_medica.invoke({
        "cita_id": 9999,
        "paciente_rut": "12.345.678-9",
        "paciente_nombre": "Test",
        "paciente_telefono": "+56900000000"
    })
    assert "ERROR: La cita con ID 9999 no existe" in res


# ==============================================================================
# 3. Pruebas de Cancelación y Liberación de Cupo
# ==============================================================================

def test_cancelar_cita_y_liberar_cupo():
    """
    Verifica que al cancelar una cita se libere el cupo a estado 'DISPONIBLE'
    y se autentique el RUT del paciente.
    """
    cita_id = 3
    rut = "17.890.123-4"

    # Reservar
    reservar_cita_medica.invoke({
        "cita_id": cita_id,
        "paciente_rut": rut,
        "paciente_nombre": "María Isabel",
        "paciente_telefono": "+56933333333"
    })

    # Cancelar con RUT erróneo
    res_error = cancelar_cita_medica.invoke({
        "cita_id": cita_id,
        "paciente_rut": "99.999.999-9"
    })
    assert "ERROR DE AUTENTICACIÓN" in res_error

    # Cancelar con RUT correcto
    res_ok = cancelar_cita_medica.invoke({
        "cita_id": cita_id,
        "paciente_rut": rut
    })
    assert "CANCELACIÓN EXITOSA" in res_ok

    # Comprobar que el estado volvió a DISPONIBLE
    conn = get_db_connection()
    row = conn.execute("SELECT estado, paciente_rut FROM citas WHERE id = ?", (cita_id,)).fetchone()
    conn.close()

    assert row["estado"] == "DISPONIBLE"
    assert row["paciente_rut"] is None
