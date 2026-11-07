"""
Herramientas de razonamiento (reglas deterministas) - Red SaludConecta
Clasifican la solicitud, validan reglas clínicas y deciden la siguiente acción del plan.
Las reglas transcriben data/manual_preparacion.md: el agente advierte y remite al médico,
nunca ajusta tratamientos (Ley N° 20.584).
"""

import re
from typing import Dict, List, NamedTuple, Optional, Tuple

from src.memory.long_term import normalizar_rut
from src.rag_engine import _strip_accents
from src.tools.base import herramienta
from src.tools.schemas import (
    Conflicto,
    EntradaClasificacion,
    EntradaDecision,
    EntradaValidacion,
    SalidaClasificacion,
    SalidaDecision,
    SalidaValidacion,
)
from src.tools_agenda import get_db_connection


class Examen(NamedTuple):
    patron: str
    protocolo: str
    especialidad_agenda: Optional[str]


EXAMENES: List[Examen] = [
    Examen(r"\b(tac|tomografia|escaner)\b", "IMG-102", "Imagenología - TAC con Contraste"),
    Examen(r"\bresonancia\b", "IMG-205", "Imagenología - Resonancia Magnética"),
    Examen(r"\b(curva de glicemia|tolerancia a la glucosa)\b", "LAB-004", "Laboratorio Clínico"),
    Examen(r"\b(perfil lipidico|glicemia|colesterol)\b", "LAB-001", "Laboratorio Clínico"),
    Examen(r"\b(hemograma|vhs)\b", "LAB-002", "Laboratorio Clínico"),
    Examen(r"\b(urocultivo|orina completa)\b", "LAB-003", "Laboratorio Clínico"),
    Examen(r"\becografia\b", "IMG-301", None),
    Examen(r"\b(endoscopia|eda)\b", "EDA-401", None),
    Examen(r"\bcolonoscopia\b", "COL-402", None),
    Examen(r"\bmamografia\b", "IMG-501", None),
]

# Nombre exacto en el HIS -> términos que el paciente suele usar
ESPECIALIDADES: List[Tuple[str, str]] = [
    ("Cardiología Adulto", r"cardiolog\w*|palpitaciones|hipertension|presion alta"),
    ("Traumatología - Columna", r"traumatolog\w*|espalda|lumbar|columna|ciatica"),
    ("Neurología Adulto", r"neurolog\w*|cefalea|migrana|dolor de cabeza"),
    ("Medicina General", r"medicina general|medico general|control general"),
    ("Pediatría", r"pediatr\w*|mi hijo|mi hija"),
    ("Dermatología", r"dermatolog\w*|acne|lunar|piel"),
    ("Gastroenterología", r"gastroenterolog\w*|reflujo|gastritis|acidez"),
    ("Ginecología y Obstetricia", r"ginecolog\w*|obstetricia|matrona"),
    ("Oftalmología", r"oftalmolog\w*|la vista|los ojos"),
    ("Otorrinolaringología", r"otorrino\w*|sinusitis|los oidos"),
    ("Broncopulmonar Adulto", r"broncopulmonar|asma|tos cronica"),
    ("Urología", r"urolog\w*|prostata"),
    ("Endocrinología", r"endocrino\w*|tiroides|diabetes"),
    ("Reumatología", r"reumatolog\w*|artritis"),
]

_PALABRAS_PREPARACION = (
    r"\b(ayuno|preparacion|preparar|preparo|examen|examenes|indicacion|indicaciones|creatinina|"
    r"metformina|biopsia|muestra|sangre|protocolo)\b"
)
_OBJETO_AGENDA = r"\b(hora|horas|cita|cupo|consulta|control)\b"


def normalizar(texto: str) -> str:
    return _strip_accents(texto.lower()).strip()


def clasificar_texto(texto: str) -> SalidaClasificacion:
    """Clasificación por reglas de intención, especialidad, protocolo y urgencia preliminar."""
    t = normalizar(texto)

    examen = next((x for x in EXAMENES if re.search(x.patron, t)), None)
    especialidad = examen.especialidad_agenda if examen else None
    if especialidad is None:
        especialidad = next((nombre for nombre, patron in ESPECIALIDADES if re.search(rf"\b(?:{patron})\b", t)), None)

    verbo_reserva = bool(re.search(r"\b(agendar|agenda|reservar|reserva|sacar|pedir|tomar|confirmar|confirmo)\b", t))
    pide_algo = bool(re.search(r"\b(necesito|quiero|busco)\b", t))
    objeto = bool(re.search(_OBJETO_AGENDA, t)) or bool(re.search(r"\bid\b|#\d", t))

    if re.search(r"\b(cancelar|cancela|anular|anula)\b", t) and objeto:
        intencion = "cancelar"
    elif re.search(r"\b(reprogramar|reprograma|reagendar|cambiar|mover)\b", t) and objeto:
        intencion = "reprogramar"
    elif re.search(r"\b(mis citas|mi cita|mis horas|mi historial|que citas tengo|citas tengo)\b", t):
        intencion = "historial"
    elif verbo_reserva and (objeto or examen):
        intencion = "agendar"
    elif re.search(_PALABRAS_PREPARACION, t) and not (pide_algo and objeto):
        intencion = "preparacion"
    elif pide_algo and (objeto or examen):
        intencion = "agendar"
    elif examen:
        intencion = "preparacion"
    else:
        intencion = "general"

    if re.search(r"\b(fiebre|mucho dolor|empeorando|desde ayer|desde hoy)\b", t):
        nivel_esi = 3
    elif re.search(r"\b(dolor|duele|molestia|sintoma|sintomas)\b", t):
        nivel_esi = 4
    else:
        nivel_esi = 5

    return SalidaClasificacion(
        intencion=intencion,
        especialidad=especialidad,
        protocolo=examen.protocolo if examen else None,
        nivel_esi=nivel_esi,
    )


@herramienta("razonamiento", EntradaClasificacion, SalidaClasificacion)
def clasificar_solicitud(e: EntradaClasificacion) -> SalidaClasificacion:
    """Clasifica intención, especialidad o examen y urgencia ESI preliminar (no diagnóstica)."""
    return clasificar_texto(e.texto)


class ReglaPreparacion(NamedTuple):
    protocolo: str
    campo: str
    terminos: Tuple[str, ...]
    regla: str
    mensaje: str


REGLAS_PREPARACION: List[ReglaPreparacion] = [
    ReglaPreparacion(
        "IMG-102", "farmacos", ("metformina",), "FARMACO_CONTRASTE",
        "Usted usa metformina y el TAC con contraste requiere evaluar su suspensión el día del examen y "
        "durante las 48 horas posteriores (riesgo de acidosis láctica). Consulte a su médico tratante antes "
        "del examen; SaludBot no modifica tratamientos.",
    ),
    ReglaPreparacion(
        "IMG-102", "alergias", ("yodo", "contraste"), "ALERGIA_CONTRASTE",
        "Usted registra alergia al yodo o a medios de contraste: debe coordinar con su médico tratante un "
        "protocolo de desensibilización iniciado 12 a 24 horas antes del estudio.",
    ),
    ReglaPreparacion(
        "LAB-001", "farmacos", ("insulina", "metformina"), "HIPOGLICEMIANTE_AYUNO",
        "Pacientes diabéticos no deben administrarse insulina matinal ni hipoglicemiantes orales en ayunas "
        "antes de la muestra: lleve su medicación y colación para después de la punción.",
    ),
    ReglaPreparacion(
        "EDA-401", "farmacos", ("warfarina", "acenocumarol", "apixaban", "rivaroxaban", "dabigatran"),
        "ANTICOAGULANTE_ENDOSCOPIA",
        "Usted usa anticoagulantes: consulte con su médico tratante la pauta de suspensión días antes del examen.",
    ),
    ReglaPreparacion(
        "IMG-205", "alergias", ("marcapasos", "implante coclear"), "METAL_RESONANCIA",
        "La resonancia está contraindicada con marcapasos antiguos o implantes cocleares: confirme con su "
        "médico tratante antes de asistir.",
    ),
]

AYUNOS: Dict[str, str] = {
    "IMG-102": "Ayuno absoluto de 6 horas (sólidos y líquidos) y creatinina sérica vigente si corresponde.",
    "LAB-001": "Ayuno estricto de 8 a 12 horas; hasta 250 ml de agua pura sin gas.",
    "LAB-002": "Ayuno liviano de 4 a 6 horas.",
    "LAB-004": "Ayuno estricto nocturno de 8 a 10 horas; 2 horas y media de permanencia.",
    "EDA-401": "Ayuno de 8 horas para sólidos y 4 horas para agua; acompañante adulto obligatorio.",
}


@herramienta("razonamiento", EntradaValidacion, SalidaValidacion)
def validar_reglas(e: EntradaValidacion) -> SalidaValidacion:
    """Valida antes de escribir: cupo vigente, colisión de horario, fármacos incompatibles y ayuno."""
    conn = get_db_connection()
    cita = conn.execute("SELECT * FROM citas WHERE id = ?", (e.cita_id,)).fetchone()
    if not cita or cita["estado"] != "DISPONIBLE":
        conn.close()
        return SalidaValidacion(
            ok=False, error="CUPO_NO_DISPONIBLE",
            mensaje=f"El cupo #{e.cita_id} no existe o ya no está disponible.",
        )
    mismas_horas = conn.execute(
        "SELECT id, paciente_rut FROM citas WHERE estado = 'RESERVADA' AND fecha = ? AND hora = ?",
        (cita["fecha"], cita["hora"]),
    ).fetchall()
    conn.close()

    objetivo = normalizar_rut(e.paciente_rut)
    if objetivo and any(normalizar_rut(f["paciente_rut"]) == objetivo for f in mismas_horas):
        return SalidaValidacion(
            ok=False, error="COLISION_HORARIO",
            mensaje=f"Ya tiene otra cita reservada el {cita['fecha']} a las {cita['hora']} hrs.",
        )

    protocolo = clasificar_texto(cita["especialidad"]).protocolo
    declarados = {
        "farmacos": [normalizar(f) for f in e.farmacos],
        "alergias": [normalizar(a) for a in e.alergias],
    }
    conflictos = [
        Conflicto(regla=r.regla, protocolo=r.protocolo, mensaje=r.mensaje)
        for r in REGLAS_PREPARACION
        if r.protocolo == protocolo and any(t in d for t in r.terminos for d in declarados[r.campo])
    ]
    return SalidaValidacion(
        conflictos=conflictos,
        indicaciones=[AYUNOS[protocolo]] if protocolo in AYUNOS else [],
    )


@herramienta("razonamiento", EntradaDecision, SalidaDecision)
def seleccionar_siguiente_accion(e: EntradaDecision) -> SalidaDecision:
    """Política determinista: decide cómo sigue el plan a partir de la última observación."""
    if not e.ok:
        if e.error == "BD_NO_DISPONIBLE":
            return SalidaDecision(accion="degradar", motivo=f"{e.ultimo_paso}: BD no disponible tras reintentos")
        if e.error in ("CUPO_NO_DISPONIBLE", "COLISION_HORARIO"):
            return SalidaDecision(accion="replanificar", motivo=e.error)
        return SalidaDecision(accion="finalizar", motivo=f"{e.ultimo_paso}: {e.error}")
    if e.total_cupos == 0:
        return SalidaDecision(accion="replanificar", motivo="SIN_CUPOS")
    if e.grounding_found is False:
        return SalidaDecision(accion="abstener", motivo="RAG bajo el umbral de similitud")
    if e.conflictos_sin_confirmar:
        return SalidaDecision(accion="replanificar", motivo="CONFLICTO_PREPARACION")
    if e.esperando_paciente:
        return SalidaDecision(accion="esperar", motivo=f"{e.ultimo_paso}: falta información del paciente")
    if e.pasos_restantes == 0:
        return SalidaDecision(accion="finalizar", motivo="Plan completado")
    return SalidaDecision(accion="continuar", motivo="Paso completado")
