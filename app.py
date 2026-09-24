"""
SaludConecta - Interfaz Gráfica Web (Streamlit)
Asistente Agéntico de Triaje Clínico, Información de Preparación y Agendamiento HIS
Asignatura: ISY0101 | Ingeniería de Soluciones con Inteligencia Artificial - Duoc UC
"""

import sys
import time
from typing import Dict, Any, List
import streamlit as st

# Asegurar codificación UTF-8 en consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.agent_orchestrator import SaludConectaAgent

# ==============================================================================
# 1. CONFIGURACIÓN DE PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="SaludConecta - Asistente de Triaje y Agendamiento",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados para identidad corporativa médica
st.markdown("""
<style>
    .reportview-container {
        background-color: #f8fafc;
    }
    .main-header {
        background: linear-gradient(135deg, #0d9488 0%, #0369a1 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        color: white;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .main-header h1 {
        color: white;
        margin: 0;
        font-size: 2rem;
        font-weight: 700;
    }
    .main-header p {
        color: #e0f2fe;
        margin: 0.5rem 0 0 0;
        font-size: 1.05rem;
    }
    .emergency-box {
        background-color: #fef2f2;
        border-left: 6px solid #dc2626;
        padding: 1rem;
        border-radius: 8px;
        margin-bottom: 1rem;
        color: #991b1b;
        font-weight: 500;
    }
    .disclaimer-card {
        background-color: #f1f5f9;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        font-size: 0.85rem;
        color: #475569;
        margin-top: 1rem;
        border-top: 1px solid #e2e8f0;
    }
    .metric-badge {
        display: inline-block;
        background: #e2e8f0;
        color: #334155;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 6px;
    }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# 2. GESTIÓN DE ESTADO DE SESIÓN (AGENT & HISTORIAL)
# ==============================================================================
if "agent" not in st.session_state:
    with st.spinner("🏥 Inicializando SaludBot y subsistemas de la Red SaludConecta..."):
        try:
            agent = SaludConectaAgent()
            agent.setup()
            st.session_state.agent = agent
        except Exception as e:
            st.error(f"❌ Error al inicializar el agente clínico: {str(e)}")
            st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "👋 **¡Hola! Bienvenido/a a la Red SaludConecta.**\n\n"
                "Soy **SaludBot**, tu asistente clínico y administrativo de orientación asistencial y triaje preliminar. Te puedo orientar en:\n\n"
                "* 📋 **Preparación de Exámenes:** Indicaciones de ayuno, medicamentos y precauciones (LAB, TAC, Resonancia, Endoscopías).\n"
                "* 🩺 **Especialidades Médicas:** Prerrequisitos clínicos e interconsultas para más de 45 especialidades.\n"
                "* 🗓️ **Agendamiento y Citas (Mock HIS):** Consulta de disponibilidad horaria, reserva y anulación de horas médicas.\n"
                "* 💳 **Convenios y Coberturas:** Información institucional para Fonasa (MLE / Bono PAD) e Isapres (I-Med).\n\n"
                "> ⚠️ *Recuerda: Si presentas síntomas de urgencia con riesgo vital, no uses este chat y llama al **SAMU 131**.*\n\n"
                "¿En qué te puedo orientar hoy?"
            ),
            "is_emergency": False,
            "response_time_ms": 0.0,
            "tools_used": [],
            "pii_detected": [],
            "api_notice": None,
        }
    ]


# ==============================================================================
# 3. SIDEBAR INFORMATIVO Y BOTONES DE PRUEBA RÁPIDA
# ==============================================================================
prompt_to_process = None

with st.sidebar:
    st.markdown("## 🏥 Red SaludConecta")
    st.markdown("*Sistema de Triaje Inteligente y Agendamiento Hospitalario (HIS)*")
    
    st.markdown("---")

    # Cuadro de Advertencia Crítica de Código Rojo
    st.markdown("""
    <div class="emergency-box">
        🚨 <strong>URGENCIAS VITALES</strong><br>
        Ante dolor torácico opresivo, dificultad respiratoria severa, asfixia o sospecha de ACV (boca torcida, debilidad en un brazo):<br><br>
        <strong>LLAME INMEDIATAMENTE AL SAMU 131</strong> o acuda al Servicio de Urgencia más cercano.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # Resumen Institucional
    st.markdown("### 🏢 Información de la Red")
    st.markdown("""
    * **Cobertura:** 5 sedes RM (Santiago Centro, Providencia, Las Condes, La Florida, Maipú).
    * **Horario:** Lun-Vie 08:00 a 20:00 hrs | Sáb 08:30 a 14:00 hrs.
    * **Convenios:** Fonasa (Tramos A-D, MLE, Bono PAD) e Isapres (vía I-Med).
    * **Mesa Central:** 📞 **600 000 1234**
    """)

    st.markdown("---")

    # Selector de Modo de Prueba Rápida (Requisitos 1 al 4)
    st.markdown("### ⚡ Casos de Prueba Rápida")
    st.caption("Validación interactiva de los 4 escenarios clave:")

    if st.button("🧪 1. Consulta Ayuno LAB-001 (RAG)", use_container_width=True):
        prompt_to_process = "¿Cuáles son las indicaciones de ayuno para un examen de perfil lipídico y glicemia?"

    if st.button("🚨 2. Alerta Código Rojo (SAMU 131)", use_container_width=True):
        prompt_to_process = "Tengo un dolor muy fuerte en el pecho que se me sube a la mandíbula y brazo izquierdo"

    if st.button("📍 3. Sedes y Horas Santiago Centro", use_container_width=True):
        prompt_to_process = "¿Dónde tienen cobertura? Deseo consultar las horas disponibles en Santiago Centro."

    if st.button("⚠️ 4. Pregunta Fuera de Dominio (Abstención)", use_container_width=True):
        prompt_to_process = "¿Cuál es el protocolo de preparación para una biopsia hepática espacial de astronautas en gravedad cero?"

    st.markdown("---")

    # Botón Reiniciar Conversación
    if st.button("🔄 Reiniciar Conversación", use_container_width=True, type="secondary"):
        try:
            if "agent" in st.session_state:
                st.session_state.agent.reset_conversation()
            st.session_state.messages = [
                {
                    "role": "assistant",
                    "content": (
                        "👋 **¡Hola! Bienvenido/a a la Red SaludConecta.**\n\n"
                        "Soy **SaludBot**, tu asistente clínico y administrativo de orientación asistencial y triaje preliminar. Te puedo orientar en:\n\n"
                        "* 📋 **Preparación de Exámenes:** Indicaciones de ayuno, medicamentos y precauciones (LAB, TAC, Resonancia, Endoscopías).\n"
                        "* 🩺 **Especialidades Médicas:** Prerrequisitos clínicos e interconsultas para más de 45 especialidades.\n"
                        "* 🗓️ **Agendamiento y Citas (Mock HIS):** Consulta de disponibilidad horaria, reserva y anulación de horas médicas.\n"
                        "* 💳 **Convenios y Coberturas:** Información institucional para Fonasa (MLE / Bono PAD) e Isapres (I-Med).\n\n"
                        "> ⚠️ *Recuerda: Si presentas síntomas de urgencia con riesgo vital, no uses este chat y llama al **SAMU 131**.*\n\n"
                        "¿En qué te puedo orientar hoy?"
                    ),
                    "is_emergency": False,
                    "response_time_ms": 0.0,
                    "tools_used": [],
                    "pii_detected": [],
                    "api_notice": None,
                }
            ]
            st.rerun()
        except Exception as e:
            st.error(f"Error al reiniciar: {e}")

    st.markdown("---")

    # Información Académica
    st.caption("""
    📘 **Proyecto:** SaludConecta AI Agent  
    🎓 **Asignatura:** ISY0101 - Ingeniería de Soluciones con Inteligencia Artificial  
    🏛️ **Institución:** Duoc UC  
    🛡️ **Seguridad:** Bypass determinista Código Rojo + PII Anonymizer + RAG Cosine Abstention
    """)


# ==============================================================================
# 4. ENCABEZADO PRINCIPAL DE LA APLICACIÓN
# ==============================================================================
st.markdown("""
<div class="main-header">
    <h1>🏥 SaludConecta - Asistente Clínico Inteligente</h1>
    <p>Orientación clínica fáctica de exámenes, validación de prerrequisitos y agendamiento médico integrado con Mock HIS.</p>
</div>
""", unsafe_allow_html=True)


# ==============================================================================
# 5. RENDERIZACIÓN DEL HISTORIAL DE MENSAJES (PERSISTENTE EN SESSION_STATE)
# ==============================================================================
for msg in st.session_state.messages:
    avatar_icon = "🩺" if msg["role"] == "assistant" else "👤"
    with st.chat_message(msg["role"], avatar=avatar_icon):
        if msg.get("is_emergency", False):
            st.error(msg["content"])
        else:
            st.markdown(msg["content"])

        # Metadatos del mensaje (tiempo de respuesta, herramientas, PII)
        metadata_chips = []
        if msg.get("response_time_ms", 0) > 0:
            metadata_chips.append(f"⏱️ **Latencia:** {msg['response_time_ms']:.2f} ms")
        if msg.get("tools_used"):
            tools_str = ", ".join(f"`{t}`" for t in msg["tools_used"])
            metadata_chips.append(f"🛠️ **HIS Tools:** {tools_str}")
        if msg.get("pii_detected"):
            pii_str = ", ".join(f"{e['type']}: {e['original']}" if isinstance(e, dict) else str(e) for e in msg["pii_detected"])
            metadata_chips.append(f"🔒 **PII Protegido:** {pii_str}")

        if metadata_chips:
            st.caption(" • ".join(metadata_chips))

        if msg.get("api_notice"):
            with st.expander("🛠️ Telemetría y Diagnóstico Técnico", expanded=False):
                st.caption(msg["api_notice"])


# ==============================================================================
# 6. ENTRADA DE TEXTO Y PROCESAMIENTO CON AGENTE
# ==============================================================================
user_text = st.chat_input("Escriba su consulta médica, de preparación o agendamiento...")

if user_text:
    prompt_to_process = user_text

if prompt_to_process:
    # 1. Registrar mensaje del usuario en el historial
    st.session_state.messages.append({
        "role": "user",
        "content": prompt_to_process,
        "is_emergency": False,
        "response_time_ms": 0.0,
        "tools_used": [],
        "pii_detected": [],
        "api_notice": None,
    })

    # 2. Procesar con la instancia del agente en session_state
    start_time = time.perf_counter()
    try:
        result = st.session_state.agent.process_message(prompt_to_process)
        response_text = result.get("response", "No se obtuvo respuesta del sistema.")
        is_emergency = result.get("bypass_activated", False) or "CÓDIGO ROJO" in response_text or "SAMU" in response_text
        response_time = (time.perf_counter() - start_time) * 1000
        tools_used = result.get("tools_used", [])
        pii_detected = result.get("pii_detected", [])
        api_notice = result.get("api_notice")

        # 3. Registrar respuesta del asistente en el historial
        st.session_state.messages.append({
            "role": "assistant",
            "content": response_text,
            "is_emergency": is_emergency,
            "response_time_ms": response_time,
            "tools_used": tools_used,
            "pii_detected": pii_detected,
            "api_notice": api_notice,
        })

    except Exception as e:
        error_msg = (
            "⚠️ **Aviso Técnico de Conexión:**\n\n"
            "Ocurrió un error al procesar la solicitud en el modelo remoto. "
            "Por favor, reformule su consulta o comuníquese con nuestra **Central Telefónica al 600 000 1234**.\n\n"
            f"*Detalle técnico: {str(e)}*"
        )
        st.session_state.messages.append({
            "role": "assistant",
            "content": error_msg,
            "is_emergency": False,
            "response_time_ms": 0.0,
            "tools_used": [],
            "pii_detected": [],
            "api_notice": str(e),
        })

    # 4. Refrescar la página para renderizar el nuevo estado de manera determinista
    st.rerun()
