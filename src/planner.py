"""
Planificación adaptativa (Plan-and-Execute) - Red SaludConecta
Define el plan, extrae datos del mensaje, genera planes por LLM o por reglas, impone
invariantes de seguridad y replanifica. El LLM propone; estas reglas deciden qué se ejecuta.
"""

import logging
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from src.decision_trace import CAMPOS_SENSIBLES
from src.prompts import PROMPT_PLANIFICADOR, format_user_prompt
from src.security_guardrails import PIIAnonymizer
from src.tools import CATEGORIAS, REGISTRO
from src.tools.razonamiento import clasificar_texto, normalizar
from src.tools.schemas import Intencion, SalidaClasificacion

logger = logging.getLogger("saludconecta.planner")

# Pasos que no llaman a una herramienta: esperan al paciente o entregan la respuesta
PASOS_INTERNOS = {
    "elegir_cupo": "Esperar que el paciente elija un cupo.",
    "solicitar_datos": "Reunir los datos personales faltantes.",
    "advertir_y_confirmar": "Advertir el conflicto y esperar confirmación del paciente.",
    "responder_directo": "Responder con RAG y LLM, sin herramientas de agenda.",
}
ESCRITURAS_CON_VALIDACION = ("reservar_cita_medica", "reprogramar_cita")
# Sin este paso, un plan no puede cumplir su intención ni redactar una respuesta
PASO_REQUERIDO = {
    "agendar": "reservar_cita_medica",
    "cancelar": "cancelar_cita_medica",
    "reprogramar": "reprogramar_cita",
    "preparacion": "buscar_protocolo_rag",
    "historial": "consultar_historial_paciente",
}

COMUNAS = {
    "santiago centro": "Santiago Centro",
    "santiago": "Santiago Centro",
    "providencia": "Providencia",
    "la florida": "La Florida",
    "las condes": "Las Condes",
    "maipu": "Maipú",
}
FARMACOS = ("metformina", "insulina", "warfarina", "acenocumarol", "apixaban", "rivaroxaban", "dabigatran")
ESPECIALIDAD_POR_DEFECTO = "Medicina General"  # Vía de acceso según catálogo ESP-MED-GEN


class Paso(BaseModel):
    herramienta: str
    args: Dict[str, Any] = Field(default_factory=dict)
    descripcion: str = ""
    estado: Literal["pendiente", "esperando", "hecho", "omitido"] = "pendiente"


class Plan(BaseModel):
    intencion: Intencion
    objetivo: str
    pasos: List[Paso]
    version: int = 1
    estado: Literal["en_curso", "esperando_paciente", "completado", "abortado", "abstencion", "degradado"] = "en_curso"
    origen: Literal["llm", "reglas"] = "reglas"

    @property
    def siguiente(self) -> Optional[Paso]:
        return next((p for p in self.pasos if p.estado in ("pendiente", "esperando")), None)

    @property
    def pendientes(self) -> int:
        return sum(p.estado in ("pendiente", "esperando") for p in self.pasos)

    def resumen(self) -> List[str]:
        return [p.herramienta for p in self.pasos]

    def indice(self, herramienta: str) -> Optional[int]:
        return next((i for i, p in enumerate(self.pasos) if p.herramienta == herramienta), None)


class PasoPropuesto(BaseModel):
    herramienta: str
    args: Dict[str, Any] = Field(default_factory=dict)
    descripcion: str = ""


class PlanPropuesto(BaseModel):
    """Formato JSON que debe devolver el LLM."""
    intencion: Intencion
    objetivo: str
    pasos: List[PasoPropuesto]


class PlanInvalido(ValueError):
    """El plan propuesto no se puede ejecutar de forma segura."""


# ------------------------------------------------------------------------------
# Extracción determinista de datos del mensaje
# ------------------------------------------------------------------------------

def _extraer_nombre(texto: str, esperando_datos: bool) -> Optional[str]:
    coincidencia = re.search(
        r"(?:me llamo|mi nombre es|nombre|soy|paciente|para)\s+([A-Za-zÁÉÍÓÚáéíóúñÑ ]+?)(?:,|-|\brut\b|\bfono\b|\btel[eé]fono\b|\.|$)",
        texto, re.IGNORECASE,
    )
    if coincidencia:
        return coincidencia.group(1).strip()
    if esperando_datos:
        primero = texto.split(",")[0].strip()
        if re.fullmatch(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]+(?: [A-Za-zÁÉÍÓÚáéíóúñÑ]+)+", primero):
            return primero
    return None


def extraer_datos(texto: str, anonimizador: PIIAnonymizer, paso_en_espera: Optional[str] = None) -> Dict[str, Any]:
    """Obtiene del mensaje crudo los datos útiles para la tarea. No usa el LLM: aquí viaja el PII."""
    datos: Dict[str, Any] = {}
    t = normalizar(texto)

    rut = anonimizador.RUT_PATTERN.search(texto)
    if rut:
        datos["rut"] = rut.group(0).strip()
    sin_rut = anonimizador.RUT_PATTERN.sub(" ", texto)
    telefono = anonimizador.PHONE_PATTERN.search(sin_rut)
    if telefono:
        datos["telefono"] = telefono.group(0).strip()
    if rut or paso_en_espera == "solicitar_datos":
        nombre = _extraer_nombre(sin_rut, paso_en_espera == "solicitar_datos")
        if nombre:
            datos["nombre"] = nombre

    cita = re.search(r"(?:cita|cupo|id|numero|opcion|#)\s*(?:id\s*)?#?\s*(\d{1,3})\b", t)
    if not cita and paso_en_espera == "elegir_cupo":
        cita = re.fullmatch(r"\s*(?:la\s+|el\s+)?(\d{1,3})\s*", t)
    if cita:
        datos["cita_id"] = int(cita.group(1))

    comuna = next((v for k, v in COMUNAS.items() if re.search(rf"\b{k}\b", t)), None)
    if comuna:
        datos["comuna"] = comuna
    if re.search(r"\b(en|por|de) la manana\b", t):
        datos["franja"] = "mañana"
    elif re.search(r"\b(en|por|de) la tarde\b", t):
        datos["franja"] = "tarde"

    farmacos = [f for f in FARMACOS if re.search(rf"\b{f}\b", t)]
    if farmacos:
        datos["farmacos"] = farmacos
        datos["farmacos_declarados"] = bool(re.search(r"\b(tomo|uso|me inyecto|estoy con|en tratamiento con)\b", t))
    alergia = re.search(r"alergi\w+\s+(?:al?\s+|a la\s+)?(yodo|contraste)", t)
    if alergia:
        datos["alergias"] = [alergia.group(1)]
    return datos


def es_negativa(texto: str) -> bool:
    return bool(re.search(r"\b(no|mejor no|cancela|cancelar|olvidalo|dejalo)\b", normalizar(texto)))


def es_confirmacion(texto: str) -> bool:
    return bool(re.search(r"\b(confirmo|acepto|entendido|de acuerdo|continuar|si|ok|dale)\b", normalizar(texto)))


def desiste(texto: str) -> bool:
    return bool(re.search(r"\b(olvidalo|dejalo|ya no quiero|no quiero seguir|mejor no)\b", normalizar(texto)))


# ------------------------------------------------------------------------------
# Generación de planes
# ------------------------------------------------------------------------------

def _paso(herramienta: str) -> Paso:
    descripcion = PASOS_INTERNOS.get(herramienta) or REGISTRO[herramienta].description.split(".")[0]
    return Paso(herramienta=herramienta, descripcion=descripcion)


def _pasos(*herramientas: Optional[str]) -> List[Paso]:
    return [_paso(h) for h in herramientas if h]


def plan_por_reglas(clasificacion: SalidaClasificacion, datos: Dict[str, Any], paciente_id: Optional[str]) -> Plan:
    """Planes canónicos por intención. También es el respaldo cuando no hay LLM disponible."""
    intencion = clasificacion.intencion
    registrar = "registrar_atencion" if paciente_id else None

    if intencion == "agendar":
        cierre = _pasos("solicitar_datos", "validar_reglas", "reservar_cita_medica", "generar_comprobante", registrar)
        if datos.get("cita_id"):
            return Plan(intencion=intencion, objetivo=f"Reservar el cupo #{datos['cita_id']}", pasos=cierre)
        catalogo = None if clasificacion.protocolo else "consultar_catalogo_especialidad"
        busqueda = _pasos("clasificar_solicitud", catalogo, "consultar_disponibilidad_horas", "elegir_cupo")
        return Plan(intencion=intencion, objetivo="Agendar una atención", pasos=busqueda + cierre)

    if intencion == "cancelar":
        return Plan(
            intencion=intencion, objetivo="Cancelar una cita",
            pasos=_pasos("solicitar_datos", "cancelar_cita_medica", registrar),
        )

    if intencion == "reprogramar":
        return Plan(
            intencion=intencion, objetivo="Reprogramar una cita",
            pasos=_pasos("solicitar_datos", "consultar_disponibilidad_horas", "elegir_cupo", "validar_reglas",
                         "reprogramar_cita", "generar_comprobante", registrar),
        )

    if intencion == "preparacion":
        return Plan(
            intencion=intencion, objetivo="Informar la preparación oficial",
            pasos=_pasos("clasificar_solicitud", "buscar_protocolo_rag"),
        )

    if intencion == "historial" and paciente_id:
        return Plan(intencion=intencion, objetivo="Revisar citas e historial", pasos=_pasos("consultar_historial_paciente"))

    return Plan(intencion="general", objetivo="Orientar al paciente", pasos=_pasos("responder_directo"))


def asegurar_invariantes(
    plan: Plan, clasificacion: SalidaClasificacion, paciente_id: Optional[str], datos: Optional[Dict[str, Any]] = None
) -> Plan:
    """
    Reglas que ningún plan puede saltarse, venga de donde venga:
    solo pasos conocidos, sin PII en argumentos, y toda escritura precedida de sus validaciones.
    """
    desconocidos = [p.herramienta for p in plan.pasos if p.herramienta not in REGISTRO and p.herramienta not in PASOS_INTERNOS]
    if desconocidos:
        raise PlanInvalido(f"Herramientas no permitidas: {desconocidos}")

    for paso in plan.pasos:
        paso.args = {k: v for k, v in paso.args.items() if k not in CAMPOS_SENSIBLES}

    if not paciente_id:
        plan.pasos = [p for p in plan.pasos if p.herramienta not in ("registrar_atencion", "consultar_historial_paciente")]
    if not plan.pasos:
        raise PlanInvalido("El plan no tiene pasos ejecutables")

    if clasificacion.intencion == "preparacion" and plan.indice("buscar_protocolo_rag") is None:
        plan.pasos = [p for p in plan.pasos if p.herramienta != "responder_directo"]
        plan.pasos.append(_paso("buscar_protocolo_rag"))
        plan.intencion = "preparacion"

    # La escritura presente define la intención, aunque el LLM haya declarado otra
    plan.intencion = next((i for i, h in PASO_REQUERIDO.items() if h in plan.resumen()), plan.intencion)
    requerido = PASO_REQUERIDO.get(plan.intencion)
    if requerido and plan.indice(requerido) is None:
        raise PlanInvalido(f"La intención {plan.intencion} exige {requerido}")

    necesita_cupo = any(h in plan.resumen() for h in ESCRITURAS_CON_VALIDACION)
    if necesita_cupo and plan.indice("elegir_cupo") is None and not (datos or {}).get("cita_id"):
        raise PlanInvalido("Escritura sin cupo conocido ni paso para elegirlo")
    if plan.indice("elegir_cupo") is not None:
        busqueda = plan.indice("consultar_disponibilidad_horas")
        if busqueda is None or busqueda > plan.indice("elegir_cupo"):
            raise PlanInvalido("elegir_cupo exige una búsqueda previa")

    for escritura in ESCRITURAS_CON_VALIDACION:
        if plan.indice(escritura) is not None:
            _exigir_antes(plan, "validar_reglas", escritura)
            _exigir_antes(plan, "solicitar_datos", "validar_reglas")
    if plan.indice("cancelar_cita_medica") is not None:
        _exigir_antes(plan, "solicitar_datos", "cancelar_cita_medica")
    return plan


def _exigir_antes(plan: Plan, previo: str, posterior: str) -> None:
    """Garantiza que `previo` ocurra antes de `posterior`, moviéndolo o agregándolo."""
    indice = plan.indice(previo)
    if indice is None or indice > plan.indice(posterior):
        plan.pasos = [p for p in plan.pasos if p.herramienta != previo]
        plan.pasos.insert(plan.indice(posterior), _paso(previo))


def plan_por_llm(llm: Any, sanitizado: str, contexto_paciente: str) -> Plan:
    """Pide al LLM un plan JSON. Cualquier error de formato se propaga para caer al plan por reglas."""
    parser = PydanticOutputParser(pydantic_object=PlanPropuesto)
    catalogo = "\n".join(
        f"- {nombre} ({CATEGORIAS[nombre]}): {tool.description}" for nombre, tool in REGISTRO.items()
    ) + "\n" + "\n".join(f"- {nombre} (interno): {desc}" for nombre, desc in PASOS_INTERNOS.items())
    sistema = PROMPT_PLANIFICADOR.format(
        catalogo=catalogo, contexto=contexto_paciente or "Sin memoria del paciente.",
        formato=parser.get_format_instructions(),
    )
    respuesta = llm.invoke([SystemMessage(content=sistema), HumanMessage(content=format_user_prompt(sanitizado))])
    propuesto = parser.parse(str(respuesta.content))
    return Plan(
        intencion=propuesto.intencion, objetivo=propuesto.objetivo, origen="llm",
        pasos=[Paso(**p.model_dump()) for p in propuesto.pasos],
    )


def _concuerda_con_reglas(plan: Plan, clasificacion: SalidaClasificacion, datos: Dict[str, Any]) -> bool:
    """
    El LLM no puede iniciar por sí solo una escritura que el paciente no pidió.
    Si las reglas reconocen la intención, manda esa. Si no la reconocen, el LLM puede aportar
    una lectura o una búsqueda de cupos, pero nunca cancelar, reprogramar ni reservar un cupo directo.
    """
    if clasificacion.intencion != "general":
        return plan.intencion == clasificacion.intencion
    if plan.intencion == "agendar":
        return not datos.get("cita_id")
    return plan.intencion not in ("cancelar", "reprogramar")


def crear_plan(
    llm: Any, sanitizado: str, contexto_paciente: str, datos: Dict[str, Any], paciente_id: Optional[str]
) -> Tuple[Plan, Optional[str]]:
    """Retorna el plan seguro y, si el LLM falló, el motivo para dejarlo en la traza."""
    clasificacion = clasificar_texto(sanitizado)
    aviso = None
    if llm is not None:
        try:
            plan = asegurar_invariantes(plan_por_llm(llm, sanitizado, contexto_paciente), clasificacion, paciente_id, datos)
            if not _concuerda_con_reglas(plan, clasificacion, datos):
                raise PlanInvalido(f"Intención {plan.intencion} sin respaldo en el mensaje")
            return plan, None
        except Exception as e:
            aviso = f"Plan LLM descartado ({type(e).__name__}); se usa plan por reglas"
            logger.warning(aviso)
    plan = plan_por_reglas(clasificacion, datos, paciente_id)
    return asegurar_invariantes(plan, clasificacion, paciente_id, datos), aviso


# ------------------------------------------------------------------------------
# Replanificación
# ------------------------------------------------------------------------------

def relajar_busqueda(busqueda: Dict[str, Any]) -> Optional[str]:
    """Quita la restricción más débil: primero el horario y luego la sede."""
    if busqueda.get("franja"):
        franja = busqueda.pop("franja")
        return f"sin cupos en horario de {franja}: se amplía a cualquier horario"
    if busqueda.get("comuna"):
        comuna = busqueda.pop("comuna")
        return f"sin cupos en {comuna}: se amplía a otras sedes"
    return None


def replanificar(plan: Plan, motivo: str, datos: Dict[str, Any]) -> Optional[str]:
    """Modifica el plan según el motivo. Retorna la explicación, o None si no quedan alternativas."""
    if motivo == "SIN_CUPOS":
        explicacion = relajar_busqueda(datos["busqueda"])
        if explicacion:
            plan.pasos[plan.indice("consultar_disponibilidad_horas")].estado = "pendiente"
    elif motivo == "CONFLICTO_PREPARACION":
        plan.pasos.insert(plan.indice("validar_reglas") + 1, _paso("advertir_y_confirmar"))
        explicacion = "conflicto de preparación: se agrega advertencia antes de confirmar"
    elif motivo in ("CUPO_NO_DISPONIBLE", "COLISION_HORARIO"):
        # La confirmación era para el cupo perdido: el cupo nuevo se valida y advierte de nuevo
        datos.pop("cita_id", None)
        datos.pop("confirmado", None)
        plan.pasos = [p for p in plan.pasos if p.herramienta != "advertir_y_confirmar"]
        posicion = plan.indice("validar_reglas") if plan.indice("validar_reglas") is not None else 0
        for paso in plan.pasos:
            if paso.herramienta in ("validar_reglas", "reservar_cita_medica", "reprogramar_cita"):
                paso.estado = "pendiente"
        if plan.indice("elegir_cupo") is None:
            plan.pasos[posicion:posicion] = _pasos("consultar_disponibilidad_horas", "elegir_cupo")
        else:
            plan.pasos[plan.indice("consultar_disponibilidad_horas")].estado = "pendiente"
            plan.pasos[plan.indice("elegir_cupo")].estado = "pendiente"
        explicacion = "el cupo elegido no está disponible: se buscan alternativas"
    else:
        explicacion = None

    if explicacion:
        plan.version += 1
    return explicacion
