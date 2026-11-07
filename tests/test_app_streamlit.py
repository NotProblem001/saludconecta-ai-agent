"""
Pruebas de la interfaz con AppTest: selector de paciente, memoria y traza de decisiones.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

RUTA_APP = Path(__file__).resolve().parent.parent / "app.py"


@pytest.fixture
def app(entorno, monkeypatch, chroma_compartido):
    monkeypatch.setattr("src.rag_engine.CHROMA_PERSIST_DIR", chroma_compartido)
    prueba = AppTest.from_file(str(RUTA_APP), default_timeout=30).run()
    assert not prueba.exception
    return prueba


def boton(prueba, texto):
    return next(b for b in prueba.button if texto in b.label)


def test_trazas_y_chips_no_muestran_pii(app):
    app.chat_input[0].set_value("Quiero hora de cardiología, RUT 15.678.901-2").run()

    assert not app.exception
    assert any("Traza de decisiones" in e.label for e in app.expander)
    assert all("15.678.901-2" not in c.value for c in app.caption)


def test_seleccionar_paciente_muestra_memoria(app):
    app.selectbox[0].select("PAC-001").run()

    assert not app.exception
    assert any("Memoria del paciente" in e.label for e in app.expander)
    assert any("metformina" in m.value for m in app.markdown)


def test_escenario_sin_cupos_muestra_replanificacion(app):
    boton(app, "Sin cupos").click().run()

    assert not app.exception
    assert any("REPLAN" in m.value for m in app.markdown)


def test_respuesta_que_menciona_samu_no_se_pinta_como_emergencia(app):
    app.chat_input[0].set_value("¿Cuáles son los prerrequisitos de cardiología adulto?").run()

    assert not app.exception
    assert len(app.error) == 0


def test_codigo_rojo_se_pinta_como_emergencia(app):
    app.chat_input[0].set_value("Me duele el pecho").run()

    assert len(app.error) == 1


def test_caida_simulada_del_his_degrada_y_se_recupera(app):
    app.toggle[0].set_value(True).run()
    boton(app, "Sin cupos").click().run()

    assert not app.exception
    assert any("temporalmente no disponible" in m.value for m in app.markdown)

    app.toggle[0].set_value(False).run()
    assert not app.exception
