"""
Herramientas de consulta (solo lectura) - Red SaludConecta
"""

import re
from typing import List, Optional

from src.memory.long_term import MemoriaLargoPlazo
from src.rag_engine import RAGEngine, synthesize_rag_response
from src.tools.base import herramienta
from src.tools.schemas import (
    Cupo,
    EntradaCatalogo,
    EntradaDisponibilidad,
    EntradaHistorial,
    EntradaRAG,
    SalidaCatalogo,
    SalidaDisponibilidad,
    SalidaHistorial,
    SalidaRAG,
)
from src.tools_agenda import buscar_citas

# shortcut: motor único por proceso, si conviven agentes con corpus distintos pasarlo por contexto del ejecutor
_rag: Optional[RAGEngine] = None
_umbral: Optional[float] = None


def configurar_rag(motor: RAGEngine, umbral: Optional[float] = None) -> None:
    """Inyecta el motor RAG del agente en las herramientas de consulta."""
    global _rag, _umbral
    _rag, _umbral = motor, umbral


def _motor() -> RAGEngine:
    if _rag is None:
        raise RuntimeError("Motor RAG no configurado")
    return _rag


@herramienta("consulta", EntradaRAG, SalidaRAG)
def buscar_protocolo_rag(e: EntradaRAG) -> SalidaRAG:
    """Busca preparación de exámenes y convenios en los manuales. Si nada supera el umbral, grounding_found=False."""
    datos = _motor().retrieve_with_threshold(e.consulta, top_k=e.top_k, threshold=_umbral)
    return SalidaRAG(
        grounding_found=datos["grounding_found"],
        scores=datos["scores"],
        contexto=datos["context_text"],
        sintesis=synthesize_rag_response(datos, query=e.consulta),
    )


@herramienta("consulta", EntradaCatalogo, SalidaCatalogo)
def consultar_catalogo_especialidad(e: EntradaCatalogo) -> SalidaCatalogo:
    """Busca una especialidad en el catálogo institucional y retorna su prerrequisito clínico."""
    datos = _motor().retrieve_with_threshold(
        f"{e.especialidad} prerrequisito", top_k=1, threshold=_umbral,
        filtro={"source": "catalogo_especialidades.md"},
    )
    if not datos["grounding_found"]:
        return SalidaCatalogo(encontrada=False)
    coincidencia = re.search(r"\*\*Prerrequisito Clínico:\*\*\s*(.+)", datos["documents"][0].page_content)
    return SalidaCatalogo(encontrada=True, prerrequisito=coincidencia.group(1).strip() if coincidencia else "")


def _en_franja(hora: str, franja: Optional[str]) -> bool:
    if franja is None:
        return True
    return (int(hora[:2]) < 13) == (franja == "mañana")


@herramienta("consulta", EntradaDisponibilidad, SalidaDisponibilidad)
def consultar_disponibilidad_horas(e: EntradaDisponibilidad) -> SalidaDisponibilidad:
    """Lista cupos DISPONIBLES del HIS por especialidad, comuna, sucursal, fecha y franja horaria."""
    filas = buscar_citas(especialidad=e.especialidad, comuna=e.comuna, sucursal=e.sucursal, fecha=e.fecha)
    cupos: List[Cupo] = [Cupo(**f) for f in filas if _en_franja(f["hora"], e.franja)]
    return SalidaDisponibilidad(total=len(cupos), cupos=cupos)


@herramienta("consulta", EntradaHistorial, SalidaHistorial)
def consultar_historial_paciente(e: EntradaHistorial) -> SalidaHistorial:
    """Retorna citas pendientes, atenciones previas, indicaciones y preferencias del paciente."""
    memoria = MemoriaLargoPlazo()
    paciente = memoria.obtener_paciente(e.paciente_id)
    if not paciente:
        return SalidaHistorial(ok=False, error="PACIENTE_DESCONOCIDO", mensaje="Paciente no registrado.")
    return SalidaHistorial(
        citas_pendientes=[Cupo(**c) for c in memoria.citas_pendientes(paciente["rut"])],
        atenciones=memoria.atenciones(e.paciente_id),
        indicaciones=memoria.indicaciones(e.paciente_id),
        preferencias=memoria.preferencias(e.paciente_id),
    )
