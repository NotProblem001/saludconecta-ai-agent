"""
SaludConecta - Interfaz Gráfica Web (Streamlit)
Asistente Agéntico de Triaje Clínico, Información de Preparación y Agendamiento HIS
Asignatura: ISY0101 | Ingeniería de Soluciones con Inteligencia Artificial - Duoc UC
"""

import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import streamlit as st

# Asegurar codificación UTF-8 en consolas Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src import tools_agenda
from src.agent_orchestrator import SaludConectaAgent

RUTA_HIS_CAIDO = Path("his_no_disponible") / "his.db"

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
            st.session_state.ruta_his = tools_agenda.DB_PATH
            st.session_state.pacientes = {p["paciente_id"]: p["nombre"] for p in agent.memoria.listar_pacientes()}
        except Exception as e:
            st.error(f"❌ Error al inicializar el agente clínico: {str(e)}")
            st.stop()

def mensaje_bienvenida(recordatorio: Optional[str] = None) -> Dict[str, Any]:
    """Primer mensaje del chat; incluye lo que el agente recuerda del paciente."""
    saludo = (
        "👋 **¡Hola! Bienvenido/a a la Red SaludConecta.**\n\n"
        "Soy **SaludBot**, tu asistente clínico y administrativo de orientación asistencial y triaje preliminar. Te puedo orientar en:\n\n"
        "* 📋 **Preparación de Exámenes:** Indicaciones de ayuno, medicamentos y precauciones (LAB, TAC, Resonancia, Endoscopías).\n"
        "* 🩺 **Especialidades Médicas:** Prerrequisitos clínicos e interconsultas para más de 45 especialidades.\n"
        "* 🗓️ **Agendamiento y Citas (Mock HIS):** Consulta de disponibilidad horaria, reserva, reprogramación y anulación de horas médicas.\n"
        "* 💳 **Convenios y Coberturas:** Información institucional para Fonasa (MLE / Bono PAD) e Isapres (I-Med).\n\n"
        "> ⚠️ *Recuerda: Si presentas síntomas de urgencia con riesgo vital, no uses este chat y llama al **SAMU 131**.*\n\n"
        "¿En qué te puedo orientar hoy?"
    )
    return {
        "role": "assistant",
        "content": f"{recordatorio}\n\n{saludo}" if recordatorio else saludo,
        "is_emergency": False,
        "response_time_ms": 0.0,
        "tools_used": [],
        "pii_detected": [],
        "api_notice": None,
        "traza": [],
        "plan": None,
    }


if "messages" not in st.session_state:
    st.session_state.messages = [mensaje_bienvenida()]


def cambiar_paciente() -> None:
    """Inicia una sesión nueva: limpia el corto plazo y carga la memoria del paciente elegido."""
    agente = st.session_state.agent
    st.session_state.messages = [mensaje_bienvenida(agente.iniciar_sesion(st.session_state.paciente))]


def simular_caida_his() -> None:
    """Apunta el HIS a una ruta inexistente para demostrar la degradación controlada."""
    tools_agenda.DB_PATH = RUTA_HIS_CAIDO if st.session_state.his_caido else st.session_state.ruta_his


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

    # Identificación simulada y memoria de largo plazo
    st.markdown("### 👤 Paciente de la sesión")
    pacientes = st.session_state.pacientes
    st.selectbox(
        "Identificador simulado",
        options=[None] + list(pacientes),
        format_func=lambda pid: "Sin identificar" if pid is None else f"{pid} · {pacientes[pid]}",
        key="paciente",
        on_change=cambiar_paciente,
    )

    contexto = st.session_state.agent.contexto
    if contexto:
        with st.expander("🧠 Memoria del paciente", expanded=True):
            st.markdown(f"**Fármacos:** {', '.join(contexto.farmacos) or 'sin registro'}")
            st.markdown(f"**Alergias:** {', '.join(contexto.alergias) or 'sin registro'}")
            preferencias = ", ".join(f"{k}: {v}" for k, v in contexto.preferencias.items())
            st.markdown(f"**Preferencias:** {preferencias or 'sin registro'}")
            for cita in contexto.citas_pendientes:
                st.markdown(f"📌 Cita #{cita['id']}: {cita['especialidad']}, {cita['fecha']} {cita['hora']}")
            for atencion in contexto.atenciones[:3]:
                st.caption(f"{atencion['fecha'][:10]}: {atencion['resumen']}")

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

    # Escenarios de planificación adaptativa
    st.markdown("### ⚡ Escenarios Adaptativos")
    st.caption("Para el escenario 4 seleccione antes al paciente PAC-001.")

    if st.button("🔄 1. Sin cupos en la sede", width="stretch"):
        prompt_to_process = "Necesito una hora de cardiología en Maipú"

    if st.button("🚨 2. Riesgo vital durante el plan", width="stretch"):
        prompt_to_process = "Quiero la cita 1, ah pero me duele mucho el pecho"

    if st.button("⚠️ 3. Fuera de dominio (abstención)", width="stretch"):
        prompt_to_process = "¿Cuál es el protocolo de preparación para una biopsia hepática espacial de astronautas en gravedad cero?"

    if st.button("💊 4. TAC con contraste y metformina", width="stretch"):
        prompt_to_process = "Necesito un TAC de abdomen con contraste"

    st.toggle("🔌 5. Simular caída del HIS", key="his_caido", on_change=simular_caida_his)

    if st.button("🧪 Consulta de ayuno LAB-001 (RAG)", width="stretch"):
        prompt_to_process = "¿Cuáles son las indicaciones de ayuno para un examen de perfil lipídico y glicemia?"

    if st.button("📍 Sedes y horas Santiago Centro", width="stretch"):
        prompt_to_process = "¿Dónde tienen cobertura? Deseo consultar las horas disponibles en Santiago Centro."

    st.markdown("---")

    # Botón Reiniciar Conversación
    if st.button("🔄 Reiniciar Conversación", width="stretch", type="secondary"):
        cambiar_paciente()
        st.rerun()

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
            # Markdown une las líneas con "•": como lista, cada cupo o indicación queda en su línea
            st.markdown(msg["content"].replace("\n• ", "\n- "))

        # Metadatos del mensaje (tiempo de respuesta, herramientas, PII)
        metadata_chips = []
        if msg.get("response_time_ms", 0) > 0:
            metadata_chips.append(f"⏱️ **Latencia:** {msg['response_time_ms']:.2f} ms")
        if msg.get("tools_used"):
            tools_str = ", ".join(f"`{t}`" for t in msg["tools_used"])
            metadata_chips.append(f"🛠️ **HIS Tools:** {tools_str}")
        if msg.get("pii_detected"):
            pii_str = ", ".join(sorted({e["type"] for e in msg["pii_detected"]}))
            metadata_chips.append(f"🔒 **PII Protegido:** {pii_str}")

        if metadata_chips:
            st.caption(" • ".join(metadata_chips))

        if msg.get("traza"):
            plan = msg.get("plan")
            etiqueta = f"🧭 Traza de decisiones · plan v{plan['version']} ({plan['estado']})" if plan else "🧭 Traza de decisiones"
            with st.expander(etiqueta, expanded=False):
                for evento in msg["traza"]:
                    paso = f" `{evento['paso']}`" if evento.get("paso") else ""
                    st.markdown(f"**{evento['tipo']}**{paso}: {evento['motivo']}")

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
        is_emergency = result.get("bypass_activated", False)
        # En Código Rojo se informa el tiempo del guardrail, que es el que garantiza la respuesta inmediata
        response_time = result["response_time_ms"] if is_emergency else (time.perf_counter() - start_time) * 1000
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
            "traza": result.get("traza", []),
            "plan": result.get("plan"),
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
