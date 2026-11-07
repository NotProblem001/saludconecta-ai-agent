"""
Módulo de Configuración y Conectividad LLM - Red SaludConecta
Gestiona las credenciales, rutas del sistema, clientes de OpenAI/GitHub Models y parámetros de entorno.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Tuple
from dotenv import load_dotenv

# Inyectar almacén de certificados de Windows para evitar errores SSL con antivirus/proxies
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

# Configuración del logger para diagnósticos técnicos explícitos
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("saludconecta.config")

# Cargar variables de entorno desde el archivo .env en la raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# ------------------------------------------------------------------------------
# Rutas del Sistema de Archivos
# ------------------------------------------------------------------------------
DATA_DIR = BASE_DIR / "data"
CITAS_CSV_PATH = DATA_DIR / "citas_disponibles.csv"
MANUAL_PATH = DATA_DIR / "manual_preparacion.md"
CATALOGO_PATH = DATA_DIR / "catalogo_especialidades.md"
PACIENTES_CSV_PATH = DATA_DIR / "pacientes_simulados.csv"
COMPROBANTES_DIR = Path(os.getenv("COMPROBANTES_DIR", str(BASE_DIR / "comprobantes")))

DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "saludconecta_his.db")))
CHROMA_PERSIST_DIR = Path(os.getenv("CHROMA_PERSIST_DIRECTORY", str(BASE_DIR / "chroma_db")))

# ------------------------------------------------------------------------------
# Parámetros del Modelo y RAG
# ------------------------------------------------------------------------------
DEFAULT_MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL_NAME", "text-embedding-3-small")
RAG_SIMILARITY_THRESHOLD = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.75"))

# Tokens y URLs (Prioridad: OpenRouter -> OpenAI directo -> GitHub Models -> Groq)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_BASE_URL = os.getenv("GITHUB_BASE_URL", "https://models.inference.ai.azure.com")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")


def get_llm_credentials() -> Tuple[str, str]:
    """
    Resuelve la tupla (api_key, base_url) evaluando en orden de prioridad:
    1. OpenRouter API (si OPENROUTER_API_KEY está configurado o OPENAI_API_KEY inicia con sk-or-)
    2. OpenAI API directo (si OPENAI_API_KEY está configurado y no es el placeholder)
    3. GitHub Models (si GITHUB_TOKEN está configurado y no es el placeholder)
    4. Groq API (si GROQ_API_KEY está configurado)
    5. Credenciales mock por defecto para ejecución local / offline
    """
    if OPENROUTER_API_KEY and OPENROUTER_API_KEY.strip() and not OPENROUTER_API_KEY.startswith("sk-or-tu-token"):
        return OPENROUTER_API_KEY.strip(), OPENROUTER_BASE_URL.strip()

    if OPENAI_API_KEY and OPENAI_API_KEY.strip().startswith("sk-or-"):
        return OPENAI_API_KEY.strip(), OPENROUTER_BASE_URL.strip()

    if OPENAI_API_KEY and OPENAI_API_KEY.strip() and not OPENAI_API_KEY.startswith("sk-tu-api-key"):
        return OPENAI_API_KEY.strip(), OPENAI_BASE_URL.strip()

    if GITHUB_TOKEN and GITHUB_TOKEN.strip() and not GITHUB_TOKEN.startswith("ghp_tu_token"):
        return GITHUB_TOKEN.strip(), GITHUB_BASE_URL.strip()

    if GROQ_API_KEY and GROQ_API_KEY.strip():
        return GROQ_API_KEY.strip(), GROQ_BASE_URL.strip()

    return "mock-token", GITHUB_BASE_URL


def get_llm(
    temperature: float = 0.1,
    model_name: Optional[str] = None,
    streaming: bool = False,
    max_tokens: int = 600,
    timeout: float = 8.0
):
    """
    Instancia y retorna un cliente ChatOpenAI con parámetros calibrados para estabilidad diagnóstica:
    - Soporte nativo para OpenRouter, OpenAI, GitHub Models y Groq.
    - temperature=0.1 (estabilidad diagnóstica y reducción de alucinaciones)
    - max_tokens=600 (control estricto de extensión y costo de tokens)
    - timeout calibrado y fail-fast con degradación elegante
    """
    from langchain_openai import ChatOpenAI

    api_key, base_url = get_llm_credentials()
    default_headers = {}

    if "openrouter.ai" in base_url:
        if model_name:
            chosen_model = model_name
        elif DEFAULT_MODEL_NAME.startswith("openai/") or "/" in DEFAULT_MODEL_NAME:
            chosen_model = DEFAULT_MODEL_NAME
        else:
            chosen_model = f"openai/{DEFAULT_MODEL_NAME}"
        default_headers = {
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "SaludConecta AI Agent"
        }
        effective_timeout = timeout or 8.0
        effective_retries = 1
    elif "groq.com" in base_url:
        chosen_model = model_name or "llama-3.3-70b-versatile"
        effective_timeout = timeout or 6.0
        effective_retries = 0
    else:
        chosen_model = model_name or DEFAULT_MODEL_NAME
        effective_timeout = timeout or 4.0
        effective_retries = 0

    logger.info(
        "Inicializando ChatOpenAI | Modelo: %s | Base URL: %s | Temp: %.1f | MaxTokens: %d",
        chosen_model, base_url, temperature, max_tokens
    )

    kwargs = {
        "model": chosen_model,
        "temperature": temperature,
        "api_key": api_key,
        "base_url": base_url,
        "streaming": streaming,
        "timeout": effective_timeout,
        "max_retries": effective_retries,
        "max_tokens": max_tokens,
    }
    if default_headers:
        kwargs["default_headers"] = default_headers

    return ChatOpenAI(**kwargs)


def get_chat_model(
    temperature: float = 0.1,
    model_name: Optional[str] = None,
    streaming: bool = False,
    max_tokens: int = 600,
    timeout: float = 8.0
):
    """
    Función canónica de interfaz para instanciar el modelo de chat (LLM).
    Compatible 100% con GitHub Models API (https://models.inference.ai.azure.com)
    y OpenAI estándar vía variables de entorno (GITHUB_TOKEN / OPENAI_API_KEY).
    """
    return get_llm(
        temperature=temperature,
        model_name=model_name,
        streaming=streaming,
        max_tokens=max_tokens,
        timeout=timeout
    )


def format_api_error(error: Exception) -> str:
    """
    Manejo explícito y diagnóstico de errores de API (cuota, red, auth, timeout).
    Registra en logs y genera mensaje técnico detallado sin ocultar la causa tras plantillas estáticas.
    """
    err_str = str(error)
    err_type = type(error).__name__
    logger.warning("Fallo detectado en inferencia LLM/API [%s]: %s", err_type, err_str, exc_info=False)

    if "ConnectError" in err_str or "Connection error" in err_str or "getaddrinfo" in err_str:
        return (
            f"[DIAGNÓSTICO TÉCNICO: Error de Conectividad ({err_type})]\n"
            f"No fue posible establecer conexión con el endpoint remoto ({err_str}).\n"
            "El sistema activa el motor clínico y tool calling local sin interrupción del servicio."
        )
    elif "429" in err_str or "rate_limit" in err_str.lower() or "quota" in err_str.lower():
        return (
            f"[DIAGNÓSTICO TÉCNICO: Límite de Cuota o Rate Limit ({err_type})]\n"
            "El endpoint remoto reportó agotamiento de cuota o rate limit de tokens.\n"
            "El sistema activa el motor clínico y tool calling local sin interrupción del servicio."
        )
    elif "401" in err_str or "invalid_api_key" in err_str.lower() or "authentication" in err_str.lower():
        return (
            f"[DIAGNÓSTICO TÉCNICO: Error de Autenticación ({err_type})]\n"
            "Token o API Key no válido o expirado.\n"
            "El sistema activa el motor clínico y tool calling local sin interrupción del servicio."
        )
    else:
        return (
            f"[DIAGNÓSTICO TÉCNICO: Excepción de Inferencia ({err_type})]\n"
            f"Detalle: {err_str}"
        )


def get_embeddings(model_name: Optional[str] = None):
    """
    Instancia y retorna un cliente de embeddings.
    Prioriza OpenAIEmbeddings(model="text-embedding-3-small") persistido en ChromaDB
    únicamente si existe OPENAI_API_KEY activa (GitHub Models solo provee inferencia de chat).
    Para GitHub Models o entornos sin conexión / testing, utiliza DeterministicFallbackEmbeddings.
    """
    if (
        OPENAI_API_KEY
        and OPENAI_API_KEY.strip()
        and not OPENAI_API_KEY.startswith("sk-tu-api-key")
    ):
        try:
            from langchain_openai import OpenAIEmbeddings
            from src.rag_engine import ResilientEmbeddings
            base_emb = OpenAIEmbeddings(
                model=model_name or DEFAULT_EMBEDDING_MODEL,
                api_key=OPENAI_API_KEY.strip(),
                base_url=OPENAI_BASE_URL.strip(),
                max_retries=0,
                request_timeout=4.0
            )
            return ResilientEmbeddings(base_emb)
        except Exception as e:
            logger.warning("Fallo al instanciar OpenAIEmbeddings (%s). Utilizando DeterministicFallbackEmbeddings.", e)

    from src.rag_engine import DeterministicFallbackEmbeddings
    return DeterministicFallbackEmbeddings()


def get_embeddings_model(model_name: Optional[str] = None):
    """
    Función canónica de interfaz para instanciar el modelo de embeddings.
    Compatible con OpenAI Embeddings si OPENAI_API_KEY está configurada,
    o DeterministicFallbackEmbeddings para entornos GitHub Models / pruebas offline.
    """
    return get_embeddings(model_name=model_name)
