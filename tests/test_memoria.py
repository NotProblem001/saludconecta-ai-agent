"""
Pruebas de memoria de corto plazo, largo plazo y continuidad entre sesiones.
"""

from src.memory import EstadoTarea, MemoriaLargoPlazo, MemoriaVentana, cargar_contexto, normalizar_rut
from tests.conftest import LLMFalso, eventos


def test_ventana_conserva_solo_k_turnos():
    memoria = MemoriaVentana(k=2)
    for i in range(5):
        memoria.add_user_message(f"u{i}")
        memoria.add_ai_message(f"a{i}")
    assert [m.content for m in memoria.messages] == ["u3", "a3", "u4", "a4"]


def test_estado_tarea_cerrar_conserva_solo_lo_indicado():
    tarea = EstadoTarea(datos={"rut": "1-9", "cita_id": 4})
    tarea.cerrar(conservar=("rut",))
    assert tarea.datos == {"rut": "1-9"}
    assert tarea.activa is False


def test_turnos_de_una_tarea_larga_conservan_los_datos(entorno):
    agente = entorno.crear_agente()
    agente.process_message("Necesito una hora de cardiología en Providencia")
    agente.process_message("la cita 3")
    assert agente.tarea.datos["cita_id"] == 3
    r = agente.process_message("Soy Ana Rojas, RUT 12.345.678-5, fono +56911112222")
    assert "RESERVA CONFIRMADA" in r["response"]
    assert "#3" in r["response"]


def test_preferencias_son_idempotentes(entorno):
    memoria = MemoriaLargoPlazo()
    memoria.guardar_preferencia("PAC-001", "sede", "Maipú")
    memoria.guardar_preferencia("PAC-001", "sede", "Providencia")
    assert memoria.preferencias("PAC-001") == {"sede": "Providencia"}


def test_rut_se_compara_sin_formato():
    assert normalizar_rut("15.678.901-2") == normalizar_rut("156789012")


def test_contexto_del_paciente_no_incluye_pii(entorno):
    agente = entorno.crear_agente("PAC-001")
    agente.process_message("Quiero reservar la cita 1")

    bloque = cargar_contexto("PAC-001", MemoriaLargoPlazo()).como_prompt()

    assert bloque.startswith("[MEMORIA_PACIENTE]")
    assert "metformina" in bloque
    assert "Cita pendiente #1" in bloque
    assert "15.678.901-2" not in bloque
    assert "+56988776655" not in bloque


def test_paciente_desconocido_retorna_contexto_vacio(entorno):
    contexto = cargar_contexto("PAC-999", MemoriaLargoPlazo())
    assert contexto.citas_pendientes == []
    assert contexto.recordatorio() is None


def test_paciente_vuelve_otro_dia_y_el_agente_recuerda_cita_y_preparacion(entorno):
    primera_sesion = entorno.crear_agente("PAC-001")
    primera_sesion.process_message("Necesito un TAC con contraste")
    primera_sesion.process_message("la cita 26")
    primera_sesion.process_message("confirmo")

    # Agente nuevo: nada de la sesión anterior sobrevive salvo la memoria persistente
    segunda_sesion = entorno.crear_agente("PAC-001")
    recordatorio = segunda_sesion.iniciar_sesion("PAC-001")

    assert "cita #26" in recordatorio
    assert "2026-12-09" in recordatorio
    assert "metformina" in recordatorio
    assert "Ayuno absoluto de 6 horas" in recordatorio


def test_primer_turno_incluye_el_recordatorio_y_luego_no(entorno):
    entorno.crear_agente("PAC-002").process_message("Quiero reservar la cita 1")

    agente = entorno.crear_agente("PAC-002")
    r1 = agente.process_message("¿Dónde tienen cobertura?")
    r2 = agente.process_message("¿Dónde tienen cobertura?")

    assert "Recuerdo que tiene pendiente" in r1["response"]
    assert "Recuerdo que tiene pendiente" not in r2["response"]


def test_memoria_se_inyecta_al_prompt_del_llm(entorno):
    entorno.crear_agente("PAC-002").process_message("Quiero reservar la cita 1")

    llm = LLMFalso()
    entorno.crear_agente("PAC-002", llm=llm).process_message("Hola")

    assert "[MEMORIA_PACIENTE]" in llm.recibido[0]
    assert "Cita pendiente #1" in llm.recibido[0]


def test_preferencia_de_sede_se_recuerda_entre_sesiones(entorno):
    entorno.crear_agente("PAC-002").process_message("Quiero reservar la cita 3")
    assert MemoriaLargoPlazo().preferencias("PAC-002") == {"sede": "Providencia", "franja": "tarde"}

    r = entorno.crear_agente("PAC-002").process_message("Necesito una hora de medicina general")

    assert "Providencia" in eventos(r, "PREFERENCIA")[0]["motivo"]


def test_farmaco_declarado_persiste_entre_sesiones(entorno):
    entorno.crear_agente("PAC-002").process_message("Tomo metformina, necesito hora de medicina general")
    assert "metformina" in MemoriaLargoPlazo().obtener_paciente("PAC-002")["farmacos"]


def test_atencion_registrada_queda_en_el_historial(entorno):
    entorno.crear_agente("PAC-002").process_message("Quiero reservar la cita 1")

    r = entorno.crear_agente("PAC-002").process_message("¿Qué citas tengo?")

    assert "consultar_historial_paciente" in r["tools_used"]
    assert "Cita #1" in r["response"]
    assert "Reservar el cupo #1" in r["response"]


def test_cancelar_deduce_la_cita_desde_la_memoria(entorno):
    entorno.crear_agente("PAC-002").process_message("Quiero reservar la cita 1")

    r = entorno.crear_agente("PAC-002").process_message("Quiero cancelar mi cita")

    assert "CANCELACIÓN EXITOSA" in r["response"]
    assert entorno.estado_cita(1) == "DISPONIBLE"


def test_cancelar_con_rut_ajeno_no_libera_el_cupo(entorno):
    entorno.crear_agente("PAC-002").process_message("Quiero reservar la cita 1")

    r = entorno.crear_agente().process_message("Quiero cancelar la cita 1, RUT 99.999.999-9")

    assert "no coincide" in r["response"]
    assert entorno.estado_cita(1) == "RESERVADA"


def test_reprogramar_de_punta_a_punta(entorno):
    entorno.crear_agente("PAC-002").process_message("Quiero reservar la cita 1")

    agente = entorno.crear_agente("PAC-002")
    agente.process_message("Quiero reprogramar mi cita")
    r = agente.process_message("la cita 2")

    assert "REPROGRAMACIÓN EXITOSA" in r["response"]
    assert (entorno.estado_cita(1), entorno.estado_cita(2)) == ("DISPONIBLE", "RESERVADA")


def test_reset_limpia_corto_plazo_pero_no_largo_plazo(entorno):
    agente = entorno.crear_agente("PAC-002")
    agente.process_message("Quiero reservar la cita 1")

    recordatorio = agente.iniciar_sesion("PAC-002")

    assert agente.memory.chat_memory.messages == []
    assert "cita #1" in recordatorio
