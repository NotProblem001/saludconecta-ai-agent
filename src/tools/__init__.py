"""
Catálogo de herramientas del agente, organizadas en consulta, escritura y razonamiento.
Importar los módulos registra cada herramienta en REGISTRO.
"""

from src.tools import consulta, escritura, razonamiento
from src.tools.base import CATEGORIAS, REGISTRO

__all__ = ["CATEGORIAS", "REGISTRO", "consulta", "escritura", "razonamiento"]
