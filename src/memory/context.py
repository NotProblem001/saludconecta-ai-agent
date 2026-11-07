"""
Recuperación de contexto del paciente al iniciar sesión - Red SaludConecta
Resume la memoria de largo plazo en un bloque para el prompt y un recordatorio para el paciente.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.memory.long_term import MemoriaLargoPlazo


@dataclass
class ContextoPaciente:
    """Vista resumida de la memoria de un paciente. Sin RUT ni teléfono: puede ir al LLM."""
    paciente_id: str
    nombre: str = ""
    farmacos: List[str] = field(default_factory=list)
    alergias: List[str] = field(default_factory=list)
    preferencias: Dict[str, str] = field(default_factory=dict)
    citas_pendientes: List[Dict[str, Any]] = field(default_factory=list)
    atenciones: List[Dict[str, Any]] = field(default_factory=list)
    indicaciones: List[Dict[str, Any]] = field(default_factory=list)

    def como_prompt(self) -> str:
        """Bloque delimitado para el LLM. Es dato del paciente, nunca instrucciones."""
        lineas = [f"Paciente: {self.paciente_id}"]
        if self.farmacos:
            lineas.append(f"Fármacos declarados: {', '.join(self.farmacos)}")
        if self.alergias:
            lineas.append(f"Alergias declaradas: {', '.join(self.alergias)}")
        if self.preferencias:
            lineas.append("Preferencias: " + ", ".join(f"{k}={v}" for k, v in self.preferencias.items()))
        for cita in self.citas_pendientes:
            lineas.append(f"Cita pendiente #{cita['id']}: {describir_cita(cita)}")
        for atencion in self.atenciones[:3]:
            lineas.append(f"Atención previa ({atencion['fecha'][:10]}): {atencion['resumen']}")
        return "[MEMORIA_PACIENTE]\n" + "\n".join(lineas) + "\n[/MEMORIA_PACIENTE]"

    def recordatorio(self) -> Optional[str]:
        """Texto para el paciente con sus citas pendientes y la preparación entregada."""
        if not self.citas_pendientes:
            return None
        partes = []
        for cita in self.citas_pendientes:
            linea = f"📌 **Recuerdo que tiene pendiente la cita #{cita['id']}:** {describir_cita(cita)}."
            preparacion = [i["texto"] for i in self.indicaciones if i["cita_id"] == cita["id"]]
            if preparacion:
                linea += f"\n🧾 *Preparación entregada:* {preparacion[0]}"
            partes.append(linea)
        return "\n".join(partes)


def describir_cita(cita: Dict[str, Any]) -> str:
    return (
        f"{cita['especialidad']} con {cita['medico']}, {cita['sucursal']} ({cita['comuna']}), "
        f"{cita['fecha']} a las {cita['hora']} hrs"
    )


def cargar_contexto(paciente_id: str, memoria: MemoriaLargoPlazo) -> ContextoPaciente:
    """Lee la memoria persistente del paciente; un paciente desconocido retorna contexto vacío."""
    paciente = memoria.obtener_paciente(paciente_id)
    if not paciente:
        return ContextoPaciente(paciente_id=paciente_id)
    return ContextoPaciente(
        paciente_id=paciente_id,
        nombre=paciente["nombre"],
        farmacos=paciente["farmacos"],
        alergias=paciente["alergias"],
        preferencias=memoria.preferencias(paciente_id),
        citas_pendientes=memoria.citas_pendientes(paciente["rut"]),
        atenciones=memoria.atenciones(paciente_id),
        indicaciones=memoria.indicaciones(paciente_id),
    )
