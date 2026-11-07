"""
Escenarios de planificación adaptativa de punta a punta, con LLM simulado o ausente.
"""

import json

from tests.conftest import LLMFalso, eventos, plan_json

PLAN_AGENDAR = plan_json(
    "agendar", "clasificar_solicitud", "consultar_catalogo_especialidad", "consultar_disponibilidad_horas",
    "elegir_cupo", "solicitar_datos", "validar_reglas", "reservar_cita_medica", "generar_comprobante",
)


# ------------------------------------------------------------------------------
# Escenario 1: sin cupos en la sede preferida
# ------------------------------------------------------------------------------

def test_sin_cupos_en_sede_replanifica_a_otra_sede(entorno):
    agente = entorno.crear_agente("PAC-002")
    r = agente.process_message("Necesito una hora de cardiología en Maipú")

    replan = eventos(r, "REPLAN")
    assert len(replan) == 1
    assert replan[0]["detalle"]["motivo_codigo"] == "SIN_CUPOS"
    assert "Maipú" in replan[0]["motivo"]
    assert "Santiago Centro" in r["response"]
    assert r["plan"]["estado"] == "esperando_paciente"
    assert r["plan"]["version"] == 2

    final = agente.process_message("la cita 1")
    assert "RESERVA CONFIRMADA" in final["response"]
    assert entorno.estado_cita(1) == "RESERVADA"


def test_sin_cupos_en_horario_relaja_primero_la_franja(entorno):
    r = entorno.crear_agente().process_message("Necesito hora de cardiología en Providencia por la mañana")

    assert "horario de mañana" in eventos(r, "REPLAN")[0]["motivo"]
    assert "Providencia" in r["response"]
    assert "15:30" in r["response"]


def test_aviso_de_replanificacion_conserva_tildes_y_mayusculas(entorno):
    r = entorno.crear_agente().process_message("Necesito hora de cardiología en Maipú")
    assert "Sin cupos en Maipú" in r["response"]


def test_cambio_de_sede_al_elegir_repite_la_busqueda(entorno):
    agente = entorno.crear_agente()
    agente.process_message("Necesito hora de cardiología")
    r = agente.process_message("mejor en Providencia")

    assert "consultar_disponibilidad_horas" in r["tools_used"]
    assert "Santiago Centro" not in r["response"]


def test_sin_cupos_en_toda_la_red_deriva_a_mesa_central(entorno):
    r = entorno.crear_agente().process_message("Quiero agendar una colonoscopía")

    assert eventos(r, "SIN_ALTERNATIVAS")
    assert "600 000 1234" in r["response"]
    assert r["plan"]["estado"] == "completado"


def test_cupo_tomado_durante_la_conversacion_replanifica(entorno):
    agente = entorno.crear_agente("PAC-002")
    otro = entorno.crear_agente("PAC-003")
    agente.process_message("Necesito hora de cardiología")
    otro.process_message("Quiero reservar la cita 1")
    assert entorno.estado_cita(1) == "RESERVADA"

    r = agente.process_message("la cita 1")

    assert eventos(r, "REPLAN")[0]["detalle"]["motivo_codigo"] == "CUPO_NO_DISPONIBLE"
    assert "ID 2" in r["response"]
    assert "reservar_cita_medica" not in r["tools_used"]


# ------------------------------------------------------------------------------
# Escenario 2: riesgo vital durante un agendamiento
# ------------------------------------------------------------------------------

def test_riesgo_vital_aborta_el_plan_sin_llm_ni_escrituras(entorno):
    llm = LLMFalso(PLAN_AGENDAR)
    agente = entorno.crear_agente("PAC-002", llm=llm)
    agente.process_message("Necesito una hora de cardiología")
    llamadas_previas = llm.llamadas

    r = agente.process_message("Quiero la cita 1, ah pero me duele mucho el pecho")

    assert r["bypass_activated"] is True
    assert "131" in r["response"]
    assert llm.llamadas == llamadas_previas
    assert r["plan"]["estado"] == "abortado"
    assert "reservar_cita_medica" in eventos(r, "ABORTO")[0]["detalle"]["omitidos"]
    assert entorno.estado_cita(1) == "DISPONIBLE"
    assert not agente.tarea.activa


def test_tras_el_aborto_no_se_reanuda_la_reserva(entorno):
    agente = entorno.crear_agente("PAC-002")
    agente.process_message("Necesito una hora de cardiología")
    agente.process_message("Tengo una opresión en el pecho")

    r = agente.process_message("la cita 1")

    assert "reservar_cita_medica" not in r["tools_used"]


# ------------------------------------------------------------------------------
# Escenario 3: RAG bajo el umbral
# ------------------------------------------------------------------------------

def test_rag_bajo_umbral_se_abstiene_sin_redactar_con_llm(entorno):
    llm = LLMFalso(plan_json("preparacion", "clasificar_solicitud", "buscar_protocolo_rag"), "RESPUESTA INVENTADA")
    r = entorno.crear_agente(llm=llm).process_message(
        "¿Cuál es la preparación para una biopsia hepática espacial de astronautas en gravedad cero?"
    )

    assert r["grounding_found"] is False
    assert "600 000 1234" in r["response"]
    assert "INVENTADA" not in r["response"]
    assert llm.llamadas == 1
    assert r["plan"]["estado"] == "abstencion"
    assert eventos(r, "ABSTENCION")


def test_con_grounding_redacta_el_llm(entorno):
    llm = LLMFalso(plan_json("preparacion", "buscar_protocolo_rag"), "Ayuno de 8 a 12 horas [Ref: Protocolo LAB-001]")
    r = entorno.crear_agente(llm=llm).process_message("¿Qué ayuno necesito para un perfil lipídico?")

    assert r["grounding_found"] is True
    assert r["response"].startswith("Ayuno de 8 a 12 horas")


def test_llm_que_omite_el_rag_no_evita_la_abstencion(entorno):
    llm = LLMFalso(plan_json("general", "responder_directo"), "RESPUESTA INVENTADA")
    r = entorno.crear_agente(llm=llm).process_message("¿Cuál es la preparación para una biopsia hepática espacial?")

    assert "INVENTADA" not in r["response"]
    assert r["grounding_found"] is False


# ------------------------------------------------------------------------------
# Escenario 4: conflicto de preparación
# ------------------------------------------------------------------------------

def test_metformina_en_perfil_agrega_advertencia_antes_de_confirmar(entorno):
    agente = entorno.crear_agente("PAC-001")
    agente.process_message("Necesito un TAC de abdomen con contraste")

    advertencia = agente.process_message("la cita 26")
    assert "metformina" in advertencia["response"]
    assert "médico tratante" in advertencia["response"]
    assert entorno.estado_cita(26) == "DISPONIBLE"
    assert eventos(advertencia, "REPLAN")[0]["detalle"]["motivo_codigo"] == "CONFLICTO_PREPARACION"
    pasos = eventos(advertencia, "REPLAN")[0]["detalle"]["pasos"]
    assert pasos.index("advertir_y_confirmar") < pasos.index("reservar_cita_medica")

    final = agente.process_message("confirmo")
    assert "RESERVA CONFIRMADA" in final["response"]
    assert entorno.estado_cita(26) == "RESERVADA"
    comprobante = next(entorno.comprobantes.glob("comprobante_cita26_*.txt")).read_text(encoding="utf-8")
    assert "metformina" in comprobante


def test_metformina_declarada_en_el_chat_tambien_advierte(entorno):
    agente = entorno.crear_agente("PAC-002")
    agente.process_message("Necesito un TAC con contraste, tomo metformina")
    r = agente.process_message("la cita 26")

    assert "metformina" in r["response"]
    assert entorno.estado_cita(26) == "DISPONIBLE"


def test_paciente_rechaza_la_advertencia_no_reserva(entorno):
    agente = entorno.crear_agente("PAC-001")
    agente.process_message("Necesito un TAC con contraste")
    agente.process_message("la cita 26")

    r = agente.process_message("no, prefiero hablar primero con mi médico")

    assert r["plan"]["estado"] == "abortado"
    assert entorno.estado_cita(26) == "DISPONIBLE"


def test_escritura_bloqueada_si_el_mensaje_no_confirma(entorno):
    agente = entorno.crear_agente("PAC-001")
    agente.process_message("Necesito un TAC con contraste")
    agente.process_message("la cita 26")

    agente.process_message("¿Qué es un medio de contraste?")

    assert entorno.estado_cita(26) == "DISPONIBLE"
    assert agente.tarea.activa


def test_confirmacion_no_se_hereda_a_otro_cupo(entorno):
    agente = entorno.crear_agente("PAC-001")
    otro = entorno.crear_agente("PAC-003")
    agente.process_message("Necesito un TAC con contraste")
    agente.process_message("la cita 26")
    otro.process_message("Quiero reservar la cita 26")
    otro.process_message("confirmo")
    assert entorno.estado_cita(26) == "RESERVADA"

    r = agente.process_message("confirmo")
    assert "Cupos disponibles" in r["response"]

    siguiente = agente.process_message("la cita 28")
    assert "Advertencia antes de confirmar" in siguiente["response"]
    assert entorno.estado_cita(28) == "DISPONIBLE"


# ------------------------------------------------------------------------------
# Escenario 5: falla de herramienta
# ------------------------------------------------------------------------------

def test_bd_caida_degrada_con_mensaje_controlado(entorno):
    agente = entorno.crear_agente()
    entorno.tumbar_bd()

    r = agente.process_message("Necesito una hora de cardiología")

    assert "temporalmente no disponible" in r["response"]
    assert "600 000 1234" in r["response"]
    assert r["plan"]["estado"] == "degradado"
    assert "degradar" in eventos(r, "DECISION")[-1]["motivo"]


def test_bd_caida_durante_la_reserva_no_declara_exito(entorno):
    agente = entorno.crear_agente("PAC-002")
    agente.process_message("Necesito una hora de cardiología")
    entorno.tumbar_bd()

    r = agente.process_message("la cita 1")

    assert "RESERVA CONFIRMADA" not in r["response"]
    assert "no se realizó ningún cambio" in r["response"]


def test_bd_caida_en_turno_general_no_lanza(entorno):
    agente = entorno.crear_agente()
    agente.process_message("¿Dónde tienen cobertura?")
    entorno.tumbar_bd()

    r = agente.process_message("deseo consultar las de Santiago Centro")

    assert "no disponible" in r["response"]


def test_memoria_caida_no_impide_atender(entorno):
    agente = entorno.crear_agente("PAC-001")
    entorno.tumbar_bd()

    r = agente.process_message("¿Dónde tienen cobertura?")

    assert "Santiago Centro" in r["response"]
    assert eventos(r, "DEGRADACION")


# ------------------------------------------------------------------------------
# Robustez del flujo
# ------------------------------------------------------------------------------

def test_consulta_lateral_no_pierde_el_plan(entorno):
    agente = entorno.crear_agente("PAC-002")
    agente.process_message("Necesito una hora de cardiología")

    r = agente.process_message("¿Dónde tienen cobertura?")
    assert "sigue pendiente" in r["response"]

    final = agente.process_message("la cita 1")
    assert "RESERVA CONFIRMADA" in final["response"]


def test_paciente_desiste_del_plan(entorno):
    agente = entorno.crear_agente("PAC-002")
    agente.process_message("Necesito una hora de cardiología")

    r = agente.process_message("olvídalo")

    assert r["plan"]["estado"] == "abortado"
    assert entorno.estado_cita(1) == "DISPONIBLE"


def test_pide_solo_los_datos_que_faltan(entorno):
    agente = entorno.crear_agente()
    agente.process_message("Quiero reservar la cita 4")

    r = agente.process_message("Juan Pérez, 15.678.901-2")
    assert "Teléfono" in r["response"]
    assert "RUT" not in r["response"]

    final = agente.process_message("+56988776655")
    assert "RESERVA CONFIRMADA" in final["response"]
    assert "Juan Pérez" in final["response"]


def test_pii_no_llega_al_llm_a_la_traza_ni_a_la_memoria(entorno):
    llm = LLMFalso(PLAN_AGENDAR)
    agente = entorno.crear_agente(llm=llm)
    r1 = agente.process_message("Quiero hora de cardiología, soy Juan Pérez, RUT 15.678.901-2, fono +56988776655")
    r2 = agente.process_message("la cita 1")

    assert "RESERVA CONFIRMADA" in r2["response"]
    assert "15.678.901-2" in r2["response"]  # El paciente sí ve su comprobante en pantalla

    expuesto = " ".join(llm.recibido) + json.dumps(r1["traza"] + r2["traza"], ensure_ascii=False)
    expuesto += " ".join(str(m.content) for m in agente.memory.chat_memory.messages)
    for dato in ("15.678.901-2", "+56988776655"):
        assert dato not in expuesto
