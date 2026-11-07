"""
Pruebas de las herramientas del agente: contrato Pydantic, reglas, errores y reintentos.
"""

from pathlib import Path

import pytest

from src.memory import MemoriaLargoPlazo
from src.rag_engine import RAGEngine
from src.tools import CATEGORIAS, REGISTRO, consulta
from src.tools.schemas import SalidaBase
from src.tools_agenda import get_db_connection, init_database


@pytest.fixture(autouse=True)
def bd_aislada(monkeypatch, tmp_path):
    ruta = tmp_path / "his.db"
    monkeypatch.setattr("src.tools_agenda.DB_PATH", ruta)
    monkeypatch.setattr("src.config.COMPROBANTES_DIR", tmp_path / "comprobantes")
    monkeypatch.setattr("src.tools.base.ESPERA_BASE_S", 0)
    init_database(db_file=ruta, force_reset=True)
    return ruta


@pytest.fixture(scope="module")
def rag(tmp_path_factory):
    return RAGEngine(
        persist_directory=str(tmp_path_factory.mktemp("chroma")), force_reindex=True, use_mock_embeddings=True
    )


def usar(nombre, **args):
    return REGISTRO[nombre].invoke(args)


def reservar(cita_id=1, rut="15.678.901-2"):
    return usar("reservar_cita_medica", cita_id=cita_id, paciente_rut=rut,
                paciente_nombre="Juan Pérez", paciente_telefono="+56988776655")


def test_tres_categorias_completas():
    assert sorted(n for n, c in CATEGORIAS.items() if c == "consulta") == [
        "buscar_protocolo_rag", "consultar_catalogo_especialidad",
        "consultar_disponibilidad_horas", "consultar_historial_paciente",
    ]
    assert sorted(n for n, c in CATEGORIAS.items() if c == "escritura") == [
        "cancelar_cita_medica", "generar_comprobante", "registrar_atencion",
        "reprogramar_cita", "reservar_cita_medica",
    ]
    assert sorted(n for n, c in CATEGORIAS.items() if c == "razonamiento") == [
        "clasificar_solicitud", "seleccionar_siguiente_accion", "validar_reglas",
    ]


@pytest.mark.parametrize("nombre", sorted(REGISTRO))
def test_contrato_pydantic_y_docstring(nombre):
    tool = REGISTRO[nombre]
    assert tool.args_schema is not None
    assert len(tool.description) > 20


def test_entrada_invalida_no_lanza():
    salida = usar("registrar_atencion", paciente_id="", tipo="reserva", resumen="x")
    assert isinstance(salida, SalidaBase)
    assert salida.error == "ENTRADA_INVALIDA"


def test_disponibilidad_filtra_por_franja():
    manana = usar("consultar_disponibilidad_horas", especialidad="TAC con Contraste", franja="mañana")
    tarde = usar("consultar_disponibilidad_horas", especialidad="TAC con Contraste", franja="tarde")
    assert {c.id for c in manana.cupos} == {26, 28}
    assert {c.id for c in tarde.cupos} == {27}


def test_rag_con_y_sin_grounding(rag):
    consulta.configurar_rag(rag)
    assert usar("buscar_protocolo_rag", consulta="ayuno perfil lipidico").grounding_found is True
    abstencion = usar("buscar_protocolo_rag", consulta="biopsia hepatica espacial gravedad cero")
    assert abstencion.grounding_found is False
    assert "600 000 1234" in abstencion.sintesis


def test_catalogo_retorna_prerrequisito(rag):
    consulta.configurar_rag(rag)
    salida = usar("consultar_catalogo_especialidad", especialidad="Cardiología Adulto")
    assert salida.encontrada and "Electrocardiograma" in salida.prerrequisito


def test_historial_paciente_desconocido():
    assert usar("consultar_historial_paciente", paciente_id="PAC-999").error == "PACIENTE_DESCONOCIDO"


def test_reserva_y_doble_reserva():
    assert reservar().ok is True
    segunda = reservar(rut="11.111.111-1")
    assert (segunda.ok, segunda.error) == (False, "CUPO_NO_DISPONIBLE")


def test_cancelar_exige_titular():
    reservar()
    assert usar("cancelar_cita_medica", cita_id=1, paciente_rut="99.999.999-9").error == "RUT_NO_COINCIDE"
    assert usar("cancelar_cita_medica", cita_id=1, paciente_rut="15.678.901-2").ok is True


def test_reprogramar_mueve_ambos_cupos():
    reservar(1)
    salida = usar("reprogramar_cita", cita_actual=1, cita_id=2, paciente_rut="15678901-2")
    assert salida.ok is True
    conn = get_db_connection()
    estados = {f["id"]: f["estado"] for f in conn.execute("SELECT id, estado FROM citas WHERE id IN (1, 2)")}
    conn.close()
    assert estados == {1: "DISPONIBLE", 2: "RESERVADA"}


def test_reprogramar_a_cupo_ocupado_no_pierde_la_reserva():
    reservar(1)
    reservar(2, rut="11.111.111-1")
    salida = usar("reprogramar_cita", cita_actual=1, cita_id=2, paciente_rut="15.678.901-2")
    assert salida.error == "CUPO_NO_DISPONIBLE"
    conn = get_db_connection()
    fila = conn.execute("SELECT estado, paciente_rut FROM citas WHERE id = 1").fetchone()
    conn.close()
    assert (fila["estado"], fila["paciente_rut"]) == ("RESERVADA", "15.678.901-2")


def test_comprobante_sin_pii_y_guardado_en_memoria():
    reservar(26)
    salida = usar("generar_comprobante", cita_id=26, paciente_id="PAC-001", indicaciones=["Ayuno de 6 horas"])
    contenido = Path(salida.archivo).read_text(encoding="utf-8")
    assert "Ayuno de 6 horas" in contenido
    assert "15.678.901-2" not in contenido
    assert MemoriaLargoPlazo().indicaciones("PAC-001", cita_id=26)[0]["texto"] == "Ayuno de 6 horas"


@pytest.mark.parametrize("texto,intencion,especialidad,protocolo", [
    ("Necesito hora de cardiología en Maipú", "agendar", "Cardiología Adulto", None),
    ("Quiero reservar la cita 4", "agendar", None, None),
    ("Necesito un TAC de abdomen con contraste", "agendar", "Imagenología - TAC con Contraste", "IMG-102"),
    ("Necesito un TAC con contraste, tomo metformina", "agendar", "Imagenología - TAC con Contraste", "IMG-102"),
    ("¿Qué ayuno necesito para un perfil lipídico?", "preparacion", "Laboratorio Clínico", "LAB-001"),
    ("Quiero cancelar mi cita 4", "cancelar", None, None),
    ("Quiero reprogramar mi hora", "reprogramar", None, None),
    ("¿Qué citas tengo?", "historial", None, None),
    ("¿Dónde tienen cobertura?", "general", None, None),
    ("Me duele la espalda hace meses, necesito una hora", "agendar", "Traumatología - Columna", None),
])
def test_clasificacion(texto, intencion, especialidad, protocolo):
    salida = usar("clasificar_solicitud", texto=texto)
    assert (salida.intencion, salida.especialidad, salida.protocolo) == (intencion, especialidad, protocolo)


def test_validacion_metformina_con_contraste():
    salida = usar("validar_reglas", cita_id=26, farmacos=["Metformina"])
    assert [c.regla for c in salida.conflictos] == ["FARMACO_CONTRASTE"]
    assert "médico tratante" in salida.conflictos[0].mensaje
    assert any("Ayuno" in i for i in salida.indicaciones)


def test_validacion_alergia_yodo_y_sin_conflicto():
    assert [c.regla for c in usar("validar_reglas", cita_id=26, alergias=["yodo"]).conflictos] == ["ALERGIA_CONTRASTE"]
    assert usar("validar_reglas", cita_id=1, farmacos=["metformina"]).conflictos == []


def test_validacion_cupo_tomado_y_colision_de_horario():
    reservar(1)
    assert usar("validar_reglas", cita_id=1).error == "CUPO_NO_DISPONIBLE"
    # Se fuerza que el cupo 6 coincida con la fecha y hora de la cita 1 ya reservada
    conn = get_db_connection()
    conn.execute("UPDATE citas SET fecha = '2026-12-07', hora = '09:00' WHERE id = 6")
    conn.commit()
    conn.close()
    assert usar("validar_reglas", cita_id=6, paciente_rut="15678901-2").error == "COLISION_HORARIO"


@pytest.mark.parametrize("observacion,accion", [
    ({"ok": False, "error": "BD_NO_DISPONIBLE"}, "degradar"),
    ({"ok": False, "error": "CUPO_NO_DISPONIBLE"}, "replanificar"),
    ({"ok": False, "error": "RUT_INVALIDO"}, "finalizar"),
    ({"total_cupos": 0, "pasos_restantes": 2}, "replanificar"),
    ({"grounding_found": False}, "abstener"),
    ({"conflictos_sin_confirmar": 1, "pasos_restantes": 2}, "replanificar"),
    ({"esperando_paciente": True, "pasos_restantes": 2}, "esperar"),
    ({"pasos_restantes": 0}, "finalizar"),
    ({"pasos_restantes": 3}, "continuar"),
])
def test_politica_siguiente_accion(observacion, accion):
    assert usar("seleccionar_siguiente_accion", ultimo_paso="x", **observacion).accion == accion


def test_bd_caida_reintenta_y_degrada(monkeypatch, tmp_path):
    monkeypatch.setattr("src.tools_agenda.DB_PATH", tmp_path / "no_existe" / "his.db")
    intentos = []
    original = consulta.buscar_citas
    monkeypatch.setattr(consulta, "buscar_citas", lambda **k: (intentos.append(1), original(**k))[1])
    salida = usar("consultar_disponibilidad_horas", especialidad="Cardiología")
    assert (salida.ok, salida.error) == (False, "BD_NO_DISPONIBLE")
    assert len(intentos) == 3


def test_bd_caida_en_escritura_no_lanza(monkeypatch, tmp_path):
    monkeypatch.setattr("src.tools_agenda.DB_PATH", tmp_path / "no_existe" / "his.db")
    assert reservar().error == "BD_NO_DISPONIBLE"
