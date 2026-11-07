"""
Ejecuta de punta a punta los escenarios adaptativos e imprime la traza de decisiones.
Trabaja sobre una BD temporal: no modifica el HIS local.

Uso:
    python scripts/run_demo_scenarios.py              # sin LLM: planificador por reglas, no gasta tokens
    python scripts/run_demo_scenarios.py --llm real   # usa el proveedor configurado en .env
"""

import argparse
import logging
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.disable(logging.WARNING)

import src.agent_orchestrator as orquestador
from src import config, tools_agenda
from src.agent_orchestrator import SaludConectaAgent
from src.decision_trace import formatear_traza
from src.tools_agenda import get_db_connection, init_database


@dataclass
class Escenario:
    nombre: str
    paciente: Optional[str]
    turnos: List[str]
    esperado: str
    verificar: Callable[[List[Dict]], bool]
    reiniciar_bd: bool = True
    tumbar_bd: bool = False


def estado_cita(cita_id: int) -> str:
    conn = get_db_connection()
    estado = conn.execute("SELECT estado FROM citas WHERE id = ?", (cita_id,)).fetchone()["estado"]
    conn.close()
    return estado


def hubo(resultados: List[Dict], tipo: str) -> bool:
    return any(e["tipo"] == tipo for r in resultados for e in r["traza"])


ORIGENES: List[str] = []

ESCENARIOS = [
    Escenario(
        "1. Sin cupos en la sede preferida", "PAC-002",
        ["Necesito una hora de cardiología en Maipú", "la cita 1"],
        "Replanifica a otra sede y reserva el cupo elegido",
        lambda r: hubo(r, "REPLAN") and estado_cita(1) == "RESERVADA",
    ),
    Escenario(
        "2. Riesgo vital durante un agendamiento", "PAC-002",
        ["Necesito una hora de cardiología", "Quiero la cita 1, ah pero me duele mucho el pecho"],
        "Aborta el plan, activa Código Rojo y no reserva",
        lambda r: r[-1]["bypass_activated"] and hubo(r, "ABORTO") and estado_cita(1) == "DISPONIBLE",
    ),
    Escenario(
        "3. RAG bajo el umbral", None,
        ["¿Cuál es la preparación para una biopsia hepática espacial de astronautas en gravedad cero?"],
        "Se abstiene y deriva a Mesa Central",
        lambda r: r[0]["grounding_found"] is False and "600 000 1234" in r[0]["response"],
    ),
    Escenario(
        "4. Conflicto de preparación (metformina + contraste)", "PAC-001",
        ["Necesito un TAC de abdomen con contraste", "la cita 26", "confirmo"],
        "Advierte antes de confirmar y reserva solo tras la confirmación",
        lambda r: "metformina" in r[1]["response"] and "RESERVA CONFIRMADA" not in r[1]["response"]
        and hubo(r, "REPLAN") and estado_cita(26) == "RESERVADA",
    ),
    Escenario(
        "5. El paciente vuelve otro día (memoria de largo plazo)", "PAC-001",
        ["¿Dónde tienen cobertura?"],
        "Recuerda la cita pendiente y su preparación",
        lambda r: "cita #26" in r[0]["response"] and "Ayuno" in r[0]["response"],
        reiniciar_bd=False,
    ),
    Escenario(
        "6. Falla de herramienta (BD no disponible)", None,
        ["Necesito una hora de cardiología"],
        "Reintenta y degrada con mensaje controlado",
        lambda r: "temporalmente no disponible" in r[0]["response"],
        tumbar_bd=True,
    ),
]


def ejecutar(escenario: Escenario, ruta_bd: Path, directorio: Path) -> bool:
    tools_agenda.DB_PATH = ruta_bd
    if escenario.reiniciar_bd:
        init_database(force_reset=True)
    agente = SaludConectaAgent(
        use_mock_embeddings=True, paciente_id=escenario.paciente, persist_directory=str(directorio / "chroma")
    )
    if escenario.tumbar_bd:
        tools_agenda.DB_PATH = directorio / "no_existe" / "his.db"

    print("\n" + "=" * 90 + f"\n{escenario.nombre}\nEsperado: {escenario.esperado}\n" + "=" * 90)
    resultados = []
    for turno in escenario.turnos:
        resultado = agente.process_message(turno)
        resultados.append(resultado)
        print(f"\n👤 {turno}\n\n🤖 {resultado['response']}\n\n🧭 Traza:\n{formatear_traza(resultado['traza'])}")

    tools_agenda.DB_PATH = ruta_bd
    ORIGENES.extend(r["plan"]["origen"] for r in resultados if r["plan"])
    return escenario.verificar(resultados)


def main() -> int:
    parser = argparse.ArgumentParser(description="Escenarios adaptativos de SaludConecta")
    parser.add_argument("--llm", choices=["mock", "real"], default="mock")
    args = parser.parse_args()

    if args.llm == "mock":
        orquestador.get_llm_credentials = lambda: ("mock-token", "")

    directorio = Path(tempfile.mkdtemp(prefix="saludconecta_demo_"))
    config.COMPROBANTES_DIR = directorio / "comprobantes"
    resumen = []
    try:
        for escenario in ESCENARIOS:
            resumen.append((escenario, ejecutar(escenario, directorio / "his.db", directorio)))
    finally:
        shutil.rmtree(directorio, ignore_errors=True)

    print("\n" + "=" * 90 + "\nRESUMEN\n" + "=" * 90)
    for escenario, aprobado in resumen:
        print(f"{'OK   ' if aprobado else 'FALLA'} {escenario.nombre}")
    print(f"\nPlanes generados por LLM: {ORIGENES.count('llm')} | por reglas: {ORIGENES.count('reglas')}")
    if args.llm == "real" and "llm" not in ORIGENES:
        print("AVISO: ningún plan provino del LLM. Revise la credencial en .env; esta pasada no valida el LLM real.")
    return 0 if all(aprobado for _, aprobado in resumen) else 1


if __name__ == "__main__":
    sys.exit(main())
