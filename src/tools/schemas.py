"""
Esquemas Pydantic de entrada y salida de las herramientas del agente - Red SaludConecta
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SalidaBase(BaseModel):
    """Contrato común: una herramienta nunca lanza excepciones al grafo."""
    ok: bool = True
    error: Optional[str] = Field(default=None, description="Código de error para el planificador.")
    mensaje: str = Field(default="", description="Texto legible del resultado.")


# ------------------------------------------------------------------------------
# Consulta
# ------------------------------------------------------------------------------

class EntradaRAG(BaseModel):
    consulta: str = Field(..., min_length=1, description="Pregunta ya anonimizada.")
    top_k: int = Field(default=3, ge=1, le=10)


class SalidaRAG(SalidaBase):
    grounding_found: bool = False
    scores: List[float] = Field(default_factory=list)
    contexto: str = Field(default="", description="Fragmentos para el LLM o directriz de abstención.")
    sintesis: str = Field(default="", description="Respuesta sin LLM, con cita del protocolo.")


class EntradaCatalogo(BaseModel):
    especialidad: str = Field(..., min_length=1)


class SalidaCatalogo(SalidaBase):
    encontrada: bool = False
    prerrequisito: str = ""


class EntradaDisponibilidad(BaseModel):
    especialidad: Optional[str] = None
    comuna: Optional[str] = None
    sucursal: Optional[str] = None
    fecha: Optional[str] = Field(default=None, description="Formato AAAA-MM-DD.")
    franja: Optional[Literal["mañana", "tarde"]] = None


class Cupo(BaseModel):
    id: int
    especialidad: str
    medico: str
    sucursal: str
    comuna: str
    fecha: str
    hora: str
    prevision: str


class SalidaDisponibilidad(SalidaBase):
    total: int = 0
    cupos: List[Cupo] = Field(default_factory=list)


class EntradaHistorial(BaseModel):
    paciente_id: str = Field(..., min_length=1)


class SalidaHistorial(SalidaBase):
    citas_pendientes: List[Cupo] = Field(default_factory=list)
    atenciones: List[Dict[str, Any]] = Field(default_factory=list)
    indicaciones: List[Dict[str, Any]] = Field(default_factory=list)
    preferencias: Dict[str, str] = Field(default_factory=dict)


# ------------------------------------------------------------------------------
# Escritura
# ------------------------------------------------------------------------------

class EntradaReserva(BaseModel):
    cita_id: int
    paciente_rut: str
    paciente_nombre: str
    paciente_telefono: str


class EntradaCancelacion(BaseModel):
    cita_id: int
    paciente_rut: str


class EntradaReprogramacion(BaseModel):
    cita_actual: int
    cita_id: int = Field(..., description="Cupo nuevo.")
    paciente_rut: str


class SalidaEscritura(SalidaBase):
    cita_id: Optional[int] = None


class EntradaAtencion(BaseModel):
    paciente_id: str = Field(..., min_length=1)
    tipo: str = Field(..., description="reserva, cancelacion, reprogramacion u orientacion.")
    resumen: str = Field(..., min_length=1, description="Resumen sin datos personales.")
    cita_id: Optional[int] = None


class SalidaAtencion(SalidaBase):
    atencion_id: Optional[int] = None


class EntradaComprobante(BaseModel):
    cita_id: int
    paciente_id: Optional[str] = None
    indicaciones: List[str] = Field(default_factory=list)


class SalidaComprobante(SalidaBase):
    archivo: Optional[str] = None


# ------------------------------------------------------------------------------
# Razonamiento
# ------------------------------------------------------------------------------

Intencion = Literal["agendar", "cancelar", "reprogramar", "preparacion", "historial", "general"]


class EntradaClasificacion(BaseModel):
    texto: str = Field(..., min_length=1)


class SalidaClasificacion(SalidaBase):
    intencion: Intencion = "general"
    especialidad: Optional[str] = None
    protocolo: Optional[str] = None
    nivel_esi: int = Field(default=5, ge=1, le=5, description="Estimación preliminar no diagnóstica.")


class EntradaValidacion(BaseModel):
    cita_id: int
    paciente_rut: Optional[str] = None
    farmacos: List[str] = Field(default_factory=list)
    alergias: List[str] = Field(default_factory=list)


class Conflicto(BaseModel):
    regla: str
    protocolo: Optional[str] = None
    mensaje: str


class SalidaValidacion(SalidaBase):
    conflictos: List[Conflicto] = Field(default_factory=list, description="Requieren confirmación del paciente.")
    indicaciones: List[str] = Field(default_factory=list, description="Ayuno y preparación informativos.")


class EntradaDecision(BaseModel):
    ultimo_paso: str
    ok: bool = True
    error: Optional[str] = None
    total_cupos: Optional[int] = None
    grounding_found: Optional[bool] = None
    conflictos_sin_confirmar: int = 0
    esperando_paciente: bool = False
    pasos_restantes: int = 0


class SalidaDecision(SalidaBase):
    accion: Literal["continuar", "replanificar", "esperar", "abstener", "degradar", "finalizar"] = "continuar"
    motivo: str = ""
