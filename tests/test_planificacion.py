"""
Pruebas del planificador: extracción de datos, planes, invariantes, replanificación y traza.
"""

import pytest

from src.decision_trace import formatear_traza, leer_traza, sin_pii
from src.planner import (
    Paso,
    Plan,
    PlanInvalido,
    asegurar_invariantes,
    extraer_datos,
    plan_por_reglas,
    relajar_busqueda,
    replanificar,
)
from src.security_guardrails import PIIAnonymizer
from src.tools.schemas import SalidaClasificacion
from tests.conftest import LLMFalso, eventos, plan_json

ANON = PIIAnonymizer()


def clasificacion(intencion):
    return SalidaClasificacion(intencion=intencion)


def plan_con(*herramientas):
    return Plan(intencion="general", objetivo="x", pasos=[Paso(herramienta=h) for h in herramientas])


def nombres(plan):
    return plan.resumen()


@pytest.mark.parametrize("texto,esperado", [
    ("Reservar la cita 4", {"cita_id": 4}),
    ("El cupo #12 por favor", {"cita_id": 12}),
    ("Hora en Maipú por la tarde", {"comuna": "Maipú", "franja": "tarde"}),
    ("Tomo metformina", {"farmacos": ["metformina"], "farmacos_declarados": True}),
    ("¿La metformina es peligrosa?", {"farmacos": ["metformina"], "farmacos_declarados": False}),
    ("Tengo alergia al yodo", {"alergias": ["yodo"]}),
    ("mañana quiero ir", {}),
])
def test_extraer_datos(texto, esperado):
    assert extraer_datos(texto, ANON) == esperado


def test_extraer_datos_personales():
    datos = extraer_datos("Soy Ana Rojas, RUT 12.345.678-5, fono +56911112222", ANON)
    assert datos == {"rut": "12.345.678-5", "telefono": "+56911112222", "nombre": "Ana Rojas"}


def test_numero_solo_es_cita_unicamente_al_elegir_cupo():
    assert extraer_datos("3", ANON) == {}
    assert extraer_datos("3", ANON, "elegir_cupo") == {"cita_id": 3}


def test_nombre_sin_prefijo_solo_cuando_se_esperan_datos():
    assert "nombre" not in extraer_datos("Juan Pérez", ANON)
    assert extraer_datos("Juan Pérez", ANON, "solicitar_datos")["nombre"] == "Juan Pérez"


def test_plan_agendar_valida_antes_de_escribir():
    pasos = nombres(plan_por_reglas(clasificacion("agendar"), {}, "PAC-001"))
    assert pasos.index("solicitar_datos") < pasos.index("validar_reglas") < pasos.index("reservar_cita_medica")
    assert pasos[-1] == "registrar_atencion"


def test_plan_con_cita_conocida_omite_la_busqueda():
    pasos = nombres(plan_por_reglas(clasificacion("agendar"), {"cita_id": 4}, None))
    assert "consultar_disponibilidad_horas" not in pasos
    assert "registrar_atencion" not in pasos


def test_invariante_rechaza_herramienta_desconocida():
    with pytest.raises(PlanInvalido):
        asegurar_invariantes(plan_con("borrar_base_de_datos"), clasificacion("general"), None)


def test_invariante_agrega_validacion_y_datos_antes_de_reservar():
    plan = asegurar_invariantes(plan_con("reservar_cita_medica"), clasificacion("agendar"), None, {"cita_id": 4})
    assert nombres(plan) == ["solicitar_datos", "validar_reglas", "reservar_cita_medica"]
    assert plan.intencion == "agendar"


def test_invariante_reordena_validacion_posterior_a_la_escritura():
    plan = asegurar_invariantes(
        plan_con("reservar_cita_medica", "validar_reglas"), clasificacion("agendar"), None, {"cita_id": 4}
    )
    assert nombres(plan) == ["solicitar_datos", "validar_reglas", "reservar_cita_medica"]


def test_invariante_exige_datos_antes_de_cancelar():
    plan = asegurar_invariantes(plan_con("cancelar_cita_medica"), clasificacion("cancelar"), None)
    assert nombres(plan) == ["solicitar_datos", "cancelar_cita_medica"]


def test_invariante_elimina_pii_de_los_argumentos():
    plan = plan_con("consultar_disponibilidad_horas")
    plan.pasos[0].args = {"paciente_rut": "1-9", "especialidad": "Cardiología"}
    asegurar_invariantes(plan, clasificacion("agendar"), None)
    assert plan.pasos[0].args == {"especialidad": "Cardiología"}


def test_invariante_quita_memoria_si_no_hay_paciente():
    plan = asegurar_invariantes(plan_con("consultar_historial_paciente", "responder_directo"), clasificacion("general"), None)
    assert nombres(plan) == ["responder_directo"]


def test_invariante_rechaza_plan_vacio():
    with pytest.raises(PlanInvalido):
        asegurar_invariantes(plan_con(), clasificacion("general"), None)


def test_invariante_rechaza_reserva_sin_cupo_conocido():
    with pytest.raises(PlanInvalido):
        asegurar_invariantes(plan_con("reservar_cita_medica"), clasificacion("agendar"), None, {})


def test_invariante_rechaza_elegir_cupo_sin_busqueda():
    with pytest.raises(PlanInvalido):
        asegurar_invariantes(plan_con("elegir_cupo"), clasificacion("general"), None)


@pytest.mark.parametrize("intencion", ["agendar", "cancelar", "reprogramar", "preparacion", "historial"])
def test_invariante_rechaza_intencion_sin_su_paso_clave(intencion):
    plan = Plan(intencion=intencion, objetivo="x", pasos=[Paso(herramienta="clasificar_solicitud")])
    with pytest.raises(PlanInvalido):
        asegurar_invariantes(plan, clasificacion("general"), "PAC-001")


def test_relajar_quita_franja_antes_que_sede():
    busqueda = {"especialidad": "X", "comuna": "Maipú", "franja": "tarde"}
    assert "horario" in relajar_busqueda(busqueda)
    assert "Maipú" in relajar_busqueda(busqueda)
    assert relajar_busqueda(busqueda) is None


def test_replanificar_sin_alternativas_retorna_none_y_no_sube_version():
    plan = plan_con("consultar_disponibilidad_horas")
    assert replanificar(plan, "SIN_CUPOS", {"busqueda": {"especialidad": "X"}}) is None
    assert plan.version == 1


def test_replanificar_inserta_advertencia_tras_validar():
    plan = plan_con("validar_reglas", "reservar_cita_medica")
    replanificar(plan, "CONFLICTO_PREPARACION", {})
    assert nombres(plan) == ["validar_reglas", "advertir_y_confirmar", "reservar_cita_medica"]
    assert plan.version == 2


def test_cupo_perdido_en_plan_sin_busqueda_agrega_busqueda():
    plan = plan_con("solicitar_datos", "validar_reglas", "reservar_cita_medica")
    datos = {"cita_id": 4, "busqueda": {}}
    replanificar(plan, "CUPO_NO_DISPONIBLE", datos)
    assert nombres(plan)[:3] == ["solicitar_datos", "consultar_disponibilidad_horas", "elegir_cupo"]
    assert "cita_id" not in datos


def test_plan_del_llm_se_ejecuta(entorno):
    llm = LLMFalso(plan_json("general", "responder_directo"), "Hola desde el LLM")
    r = entorno.crear_agente(llm=llm).process_message("Hola")
    assert r["plan"]["origen"] == "llm"
    assert r["response"] == "Hola desde el LLM"


def test_json_invalido_del_llm_cae_al_plan_por_reglas(entorno):
    r = entorno.crear_agente(llm=LLMFalso("esto no es json")).process_message("¿Qué citas tengo?")
    assert r["plan"]["origen"] == "reglas"
    assert eventos(r, "PLAN_LLM_DESCARTADO")


def test_llm_que_propone_herramienta_prohibida_cae_al_plan_por_reglas(entorno):
    llm = LLMFalso(plan_json("agendar", "ejecutar_sql"))
    r = entorno.crear_agente(llm=llm).process_message("Necesito hora de cardiología")
    assert r["plan"]["origen"] == "reglas"
    assert "Cupos disponibles" in r["response"]


def test_llm_que_salta_la_validacion_no_evita_la_advertencia(entorno):
    llm = LLMFalso(plan_json("agendar", "reservar_cita_medica"))
    agente = entorno.crear_agente("PAC-001", llm=llm)

    r = agente.process_message("Quiero reservar la cita 26")

    assert "metformina" in r["response"]
    assert entorno.estado_cita(26) == "DISPONIBLE"


def test_argumentos_del_llm_no_pisan_la_replanificacion(entorno):
    """Caso real: el LLM fijaba comuna=Maipú y la sede relajada volvía a filtrarse."""
    llm = LLMFalso(plan_json(
        "agendar", "clasificar_solicitud", "consultar_disponibilidad_horas", "elegir_cupo", "solicitar_datos",
        "validar_reglas", "reservar_cita_medica",
        consultar_disponibilidad_horas={"especialidad": "Cardiología", "comuna": "Maipú"},
    ))
    r = entorno.crear_agente(llm=llm).process_message("Necesito una hora de cardiología en Maipú")

    assert "Santiago Centro" in r["response"]
    assert r["plan"]["estado"] == "esperando_paciente"


def test_llm_no_puede_cancelar_si_el_paciente_no_lo_pidio(entorno):
    """Caso real: sin plan activo, el LLM interpretó 'la cita 1' como cancelar."""
    entorno.crear_agente("PAC-002").process_message("Quiero reservar la cita 1")

    llm = LLMFalso(plan_json("cancelar", "solicitar_datos", "cancelar_cita_medica"), "Respuesta general")
    r = entorno.crear_agente("PAC-002", llm=llm).process_message("la cita 1")

    assert entorno.estado_cita(1) == "RESERVADA"
    assert "cancelar_cita_medica" not in r["tools_used"]
    assert eventos(r, "PLAN_LLM_DESCARTADO")


def test_llm_no_puede_reservar_si_el_paciente_no_lo_pidio(entorno):
    llm = LLMFalso(plan_json("agendar", "solicitar_datos", "validar_reglas", "reservar_cita_medica"), "Respuesta general")
    entorno.crear_agente("PAC-002", llm=llm).process_message("la cita 1")

    assert entorno.estado_cita(1) == "DISPONIBLE"


def test_llm_no_convierte_un_agendamiento_en_consulta(entorno):
    """Caso real: 'Necesito un TAC' terminaba en una respuesta informativa sin cupos."""
    llm = LLMFalso(plan_json("preparacion", "clasificar_solicitud", "buscar_protocolo_rag"))
    r = entorno.crear_agente("PAC-001", llm=llm).process_message("Necesito un TAC de abdomen con contraste")

    assert r["plan"]["intencion"] == "agendar"
    assert "Cupos disponibles" in r["response"]


def test_llm_puede_iniciar_busqueda_si_las_reglas_no_reconocen_la_solicitud(entorno):
    llm = LLMFalso(plan_json(
        "agendar", "consultar_disponibilidad_horas", "elegir_cupo", "solicitar_datos", "validar_reglas",
        "reservar_cita_medica",
    ))
    r = entorno.crear_agente(llm=llm).process_message("Me gustaría que me viera un doctor pronto")

    assert r["plan"]["origen"] == "llm"
    assert "Cupos disponibles" in r["response"]


def test_planificador_recibe_la_conversacion_reciente(entorno):
    llm = LLMFalso(plan_json("general", "responder_directo"), "Primera respuesta")
    agente = entorno.crear_agente(llm=llm)
    agente.process_message("¿Dónde tienen cobertura?")

    agente.process_message("¿Y los fines de semana?")

    assert "[CONVERSACION_RECIENTE]" in llm.recibido[-2]
    assert "Dónde tienen cobertura" in llm.recibido[-2]


def test_respuesta_del_llm_sin_comillas_envolventes(entorno):
    llm = LLMFalso(plan_json("general", "responder_directo"), '"Hola, ¿en qué le ayudo?"')
    r = entorno.crear_agente(llm=llm).process_message("Hola")
    assert r["response"] == "Hola, ¿en qué le ayudo?"


def test_llm_caido_no_interrumpe_al_paciente(entorno):
    class LLMCaido:
        def invoke(self, _):
            raise ConnectionError("Connection error")

    r = entorno.crear_agente(llm=LLMCaido()).process_message("¿Dónde tienen cobertura?")

    assert "Santiago Centro" in r["response"]
    assert "Conectividad" in r["api_notice"]


def test_traza_se_persiste_y_se_puede_consultar(entorno):
    agente = entorno.crear_agente()
    agente.process_message("Necesito hora de cardiología en Maipú")

    tipos = [e["tipo"] for e in leer_traza(agente.traza.session_id)]

    assert tipos[0] == "PLAN_INICIAL"
    assert "REPLAN" in tipos


def test_traza_con_bd_caida_se_conserva_en_memoria(entorno):
    agente = entorno.crear_agente()
    entorno.tumbar_bd()
    r = agente.process_message("¿Dónde tienen cobertura?")
    assert r["traza"]


def test_sin_pii_enmascara_campos_personales():
    assert sin_pii({"paciente_rut": "1-9", "cita_id": 3}) == {"paciente_rut": "***", "cita_id": 3}


def test_formatear_traza():
    texto = formatear_traza([{"turno": 1, "tipo": "REPLAN", "paso": "x", "motivo": "sin cupos"}])
    assert "REPLAN" in texto and "sin cupos" in texto
