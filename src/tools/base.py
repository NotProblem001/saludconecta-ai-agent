"""
Infraestructura común de herramientas - Red SaludConecta
El decorador `herramienta` da a cada función esquema Pydantic, logging, reintentos ante
fallas de BD y errores tipados, de modo que ninguna excepción llegue al grafo.
"""

import logging
import sqlite3
import time
from functools import wraps
from typing import Callable, Dict, Literal, Type

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ValidationError

from src.tools.schemas import SalidaBase

logger = logging.getLogger("saludconecta.tools")

Categoria = Literal["consulta", "escritura", "razonamiento"]

REINTENTOS_BD = 2
ESPERA_BASE_S = 0.1

REGISTRO: Dict[str, StructuredTool] = {}
CATEGORIAS: Dict[str, Categoria] = {}


def herramienta(categoria: Categoria, entrada: Type[BaseModel], salida: Type[SalidaBase]) -> Callable:
    """Registra `fn(entrada) -> salida` como StructuredTool con manejo uniforme de errores."""

    def decorador(fn: Callable) -> StructuredTool:
        nombre = fn.__name__

        @wraps(fn)
        def ejecutar(**kwargs) -> SalidaBase:
            inicio = time.perf_counter()
            datos = entrada(**kwargs)

            for intento in range(REINTENTOS_BD + 1):
                try:
                    resultado = fn(datos)
                    logger.info(
                        "%s [%s] ok=%s error=%s intento=%d %.1f ms", nombre, categoria, resultado.ok,
                        resultado.error, intento + 1, (time.perf_counter() - inicio) * 1000,
                    )
                    return resultado
                except sqlite3.Error as e:
                    logger.warning("%s: fallo de BD intento %d/%d: %s", nombre, intento + 1, REINTENTOS_BD + 1, e)
                    if intento < REINTENTOS_BD:
                        time.sleep(ESPERA_BASE_S * 2 ** intento)
                except Exception:
                    logger.exception("%s: error interno", nombre)
                    return salida(ok=False, error="ERROR_INTERNO", mensaje=f"Fallo interno en {nombre}.")

            return salida(ok=False, error="BD_NO_DISPONIBLE", mensaje="El sistema de agenda no está disponible.")

        def rechazar_entrada(e: ValidationError) -> SalidaBase:
            logger.warning("%s: entrada inválida (%d errores)", nombre, e.error_count())
            return salida(ok=False, error="ENTRADA_INVALIDA", mensaje=f"Parámetros inválidos para {nombre}.")

        tool = StructuredTool.from_function(
            func=ejecutar, name=nombre, description=fn.__doc__, args_schema=entrada,
            handle_validation_error=rechazar_entrada,
        )
        REGISTRO[nombre] = tool
        CATEGORIAS[nombre] = categoria
        return tool

    return decorador
