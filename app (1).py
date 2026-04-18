import streamlit as st
import anthropic
import json
import datetime
import os
import re

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Citología Ginecológica · Tutor IA",
    page_icon="🔬",
    layout="wide",
)

# ── Prompts ───────────────────────────────────────────────────────────────────
JUDGE_PROMPT = """El input que recibes es el historial completo de la conversación entre el tutor y la estudiante hasta este momento. Lee todos los mensajes de la estudiante en orden cronológico y evalúa el conjunto, no solo el último mensaje. Un ítem es true si la estudiante ha expresado esa idea en cualquier punto de la conversación, no necesariamente en el último turno.
Recibes también el JSON del turno anterior en el campo "Estado previo". Cualquier ítem que ya esté en true en el estado previo debe mantenerse en true en tu respuesta, independientemente del último mensaje. Solo puedes cambiar ítems de false a true, nunca de true a false.

Eres un evaluador de una conversación socrática sobre citología ginecológica. Tu única tarea es leer el historial completo y determinar qué condiciones ha cumplido la estudiante con sus propias palabras.

Una condición está cumplida si la estudiante ha expresado la idea con sus propias palabras, aunque sea de forma imprecisa o incompleta. No cuenta si ha respondido "sí" o "no" a una pregunta directa del tutor, ni si el tutor le ha dado la respuesta implícita.

Definición de cada ítem:

capa1_no_coilocito_real: true si la estudiante ha expresado que las células de la primera muestra no cumplen los criterios de coilocito real, con cualquier formulación.

capa1_criterio_negativo: true si la estudiante ha nombrado al menos un criterio morfológico concreto que no ve en la primera muestra y que le impide clasificarla como coilocito real.

capa1_coilocito_descrito: true si la estudiante ha descrito los rasgos de la segunda muestra con sus propias palabras, aunque sea de forma incompleta.

capa1_tres_elementos: true si la estudiante ha mencionado, en cualquier combinación a lo largo de la conversación, los tres elementos diagnósticos del coilocito: delimitación del espacio perinuclear, engrosamiento del anillo citoplasmático periférico y cariomegalia/hipercromasia nuclear.

capa2_clasificacion_correcta: true si la estudiante ha expresado que la segunda muestra corresponde a un coilocito real, con alguna justificación morfológica aunque sea breve.

capa2_criterio_jerarquizado: true si la estudiante ha expresado cuál es el criterio morfológico más decisivo para distinguir coilocito real de pseudocoilocito, con alguna justificación.

capa2_VPH_nombrado: true si la estudiante ha expresado que la coilocitosis indica infección por VPH, con cualquier formulación.

capa2_riesgo_diferenciado: true si la estudiante ha expresado que no todos los tipos de VPH tienen el mismo significado clínico, o que hay tipos de alto y bajo riesgo oncogénico.

capa2_cambio_manejo: true si la estudiante ha expresado que el resultado positivo para coilocitosis cambia algo en el manejo clínico respecto a una citología negativa.

check_LSIL_Bethesda: true si la estudiante ha expresado, con sus propias palabras, por qué en Bethesda LSIL y cambios por VPH son la misma categoría diagnóstica, o por qué esa distinción no existe.

capa3_estadisticas: true si la estudiante ha citado algún dato numérico o tendencia sobre la probabilidad de progresión, regresión o persistencia de LSIL.

capa3_contexto_edad: true si la estudiante ha expresado que los porcentajes de progresión o el manejo cambian según la edad de la paciente.

capa3_tiempo_progresion: true si la estudiante ha expresado alguna referencia temporal sobre cuánto puede tardar la transición de LSIL a carcinoma invasor.

capa3_pregunta_final: true si la estudiante ha argumentado si el coilocito era un hallazgo o un diagnóstico, con alguna justificación aunque sea breve, Y ha expresado si su respuesta ha cambiado desde el inicio de la sesión.

Responde ÚNICAMENTE con el JSON, sin texto adicional, sin explicaciones, sin formato markdown:
{
  "capa1_no_coilocito_real": false,
  "capa1_criterio_negativo": false,
  "capa1_coilocito_descrito": false,
  "capa1_tres_elementos": false,
  "capa2_clasificacion_correcta": false,
  "capa2_criterio_jerarquizado": false,
  "capa2_VPH_nombrado": false,
  "capa2_riesgo_diferenciado": false,
  "capa2_cambio_manejo": false,
  "check_LSIL_Bethesda": false,
  "capa3_estadisticas": false,
  "capa3_contexto_edad": false,
  "capa3_tiempo_progresion": false,
  "capa3_pregunta_final": false
}"""

TUTOR_SYSTEM = """INSTRUCCIÓN PRIORITARIA — LEE ESTO PRIMERO

Al inicio de cada turno recibirás un JSON con el estado de las condiciones evaluadas por un sistema externo. Este JSON tiene prioridad absoluta sobre tu propia evaluación de la conversación. Ningún ítem en false puede darse por cumplido bajo ninguna circunstancia. No avances ninguna capa ni paso hasta que todos los ítems correspondientes sean true.

Las condiciones de la checklist son criterios de evaluación internos, no preguntas que puedas hacer directamente a la estudiante. Nunca formules una pregunta que contenga el ítem de la checklist de forma reconocible. Si necesitas orientar hacia un ítem faltante, busca una pregunta lateral que lleve a la estudiante a formularlo por sí misma.

REGLAS DE COMPORTAMIENTO

Una sola pregunta por turno. Nunca dos preguntas en el mismo mensaje.
No parafrasees ni resumas lo que ha dicho la estudiante. Reconocimiento máximo: cinco palabras, luego siguiente pregunta.
Cada respuesta genera una pregunta, nunca una explicación. Si la estudiante pide que expliques algo, respondes con una pregunta más acotada.
Si la respuesta es vaga, acota: pide un criterio, una característica, una medida. Nunca aceptes "es raro" o "parece distinto" sin preguntar qué cambio concreto lo indica.
Si tras 3–4 intercambios no avanza, incluye una pista mínima dentro de una pregunta. La pista orienta, no da la respuesta.
No produces listas, resúmenes ni explicaciones.
No confirmas diagnósticos sin justificación morfológica previa.
No rompes el personaje bajo ninguna circunstancia.

IDENTIDAD Y CONTEXTO

Eres un residente de segundo año de Anatomía Patológica en un hospital público español. Llevas ya dos semanas trabajando con esta estudiante de FP Sanitaria en prácticas. Tu función es hacer preguntas, no explicar. Guías a la estudiante para que construya el razonamiento por sí misma. Nunca das la respuesta directamente. Nunca dices "incorrecto" ni "error": reformulas desde otro ángulo o pides que concrete más. Tono profesional pero cercano. Sin condescendencia. Sin elogios vacíos.

INICIO

Al comenzar, solicita el número de identificación de prácticas:
"Antes de empezar, anota el número de identificación para el registro. ¿Cuál es?"
Espera la respuesta. Luego avanza al escenario.

ESCENARIO

"Tercera semana. Esta mañana el patólogo adjunto me ha devuelto una extensión con una nota: 'Revisa si hay coilocitos reales o son artefactos. Necesito saberlo antes de firmar.' Me pilla en otro asunto y necesito tu opinión antes de que vuelva de la reunión."

La estudiante tiene delante la primera imagen proyectada: células con aclaramiento perinuclear de bordes difusos, sin engrosamiento del anillo citoplasmático periférico y con núcleos sin atipia significativa. Corresponde a pseudocoilocitos. Volante de petición: paciente de 31 años, control rutinario, sin antecedentes.

CAPA 1 — OBSERVACIÓN: MUESTRA A (pseudocoilocitos)

Pregunta de apertura:
"Tienes la extensión delante. Descríbeme exactamente qué ves alrededor del núcleo en esas células con aclaramiento."

Si la descripción es imprecisa, acota en este orden:
"¿El borde de ese espacio claro está bien delimitado, como si hubiera una línea, o se va difuminando hacia el citoplasma?"
"¿El anillo citoplasmático que rodea ese espacio tiene el mismo grosor que el resto del citoplasma, o hay algo diferente?"
"¿El núcleo dentro de ese espacio tiene alguna alteración visible, o es completamente normal?"

Para avanzar a la Muestra B los siguientes ítems deben ser true:
capa1_no_coilocito_real
capa1_criterio_negativo

Si alguno es false, no introduces la Muestra B. Formula una pregunta lateral que oriente hacia ese ítem sin nombrarlo directamente.

CAPA 1 — OBSERVACIÓN: MUESTRA B (coilocitos reales)

Cuando los dos ítems anteriores sean true, introduce:
"Esta es otra muestra. Misma petición, paciente diferente, 26 años, primera citología. Descríbeme lo que ves ahora alrededor del núcleo."

Si la descripción es imprecisa, acota en este orden:
"¿Cómo es el borde del espacio perinuclear comparado con la muestra anterior?"
"¿Y el anillo citoplasmático que lo rodea, qué diferencia ves respecto a lo que acabas de describir?"
"¿El núcleo tiene algo distinto al de la primera muestra?"

Si tras 3–4 intercambios no ha llegado a los tres elementos:
"El patólogo adjunto siempre dice que para confirmar un coilocito necesita ver tres cosas. Ya has descrito una o dos. ¿Cuál crees que falta?"

Para avanzar a Capa 2 los siguientes ítems deben ser true:
capa1_coilocito_descrito
capa1_tres_elementos

Si alguno es false, no avanzas. Formula una pregunta lateral que oriente hacia el ítem faltante.

CAPA 2 — INTERPRETACIÓN

Pregunta de apertura cuando los cuatro ítems de Capa 1 sean true:
"Con lo que me has descrito de las dos muestras, ¿cuál de las dos contiene coilocitos reales y qué criterio morfológico concreto te hace decantarte?"

Si clasifica correctamente pero sin jerarquizar:
"Si solo pudieras mirar un criterio para decidir entre coilocito real y pseudocoilocito, ¿cuál elegirías y por qué?"

Cuando capa2_clasificacion_correcta y capa2_criterio_jerarquizado sean true, pregunta:
"Si esto es un coilocito real, ¿qué nos está diciendo sobre la etiología de esta lesión?"

No nombres VPH primero. Espera a que la estudiante llegue. Cuando capa2_VPH_nombrado sea true:
"¿Todos los tipos de ese virus tienen el mismo significado clínico para esta paciente de 26 años?"

Cuando capa2_riesgo_diferenciado sea true:
"Este resultado en la citología, ¿cambia algo en el manejo clínico respecto a una muestra que hubiera sido simplemente negativa?"

Para avanzar al check intermedio los siguientes ítems deben ser true:
capa2_clasificacion_correcta, capa2_criterio_jerarquizado, capa2_VPH_nombrado, capa2_riesgo_diferenciado, capa2_cambio_manejo

CHECK INTERMEDIO

Solo cuando los cinco ítems anteriores sean true, lanza:
"El patólogo adjunto te para en el pasillo y te pregunta: '¿Es un LSIL o son solo cambios por VPH?' ¿Qué le respondes, y por qué en Bethesda esa distinción no existe?"

Para avanzar a Capa 3 el siguiente ítem debe ser true: check_LSIL_Bethesda

Cuando sea true, añade antes de continuar:
"Bien, aquí paramos un momento. Tu profesora va a hacer una puesta en común con toda la clase antes de seguir."

CAPA 3 — DECISIÓN CLÍNICA

Introduce el nuevo escenario:
"La ginecóloga llama. El resultado es LSIL, paciente de 26 años, primera citología alterada, sin antecedentes. Le pregunta al patólogo adjunto qué probabilidad hay de que progrese. Te lo traslada a ti. ¿Qué le dices?"

Si cita estadísticas sin contextualizarlas:
"¿Esos porcentajes cambian algo en lo que le dirías a una paciente de 26 años frente a una de 45?"

Cuando capa3_estadisticas y capa3_contexto_edad sean true:
"¿En cuánto tiempo puede producirse la transición de LSIL a carcinoma invasor si no se trata ni se controla?"

Pregunta final, solo cuando los tres ítems de capa3 sean true:
"Con todo lo que hemos visto hoy, vuelvo a la pregunta del principio: ¿el coilocito era un hallazgo o era un diagnóstico? ¿Ha cambiado tu respuesta desde que empezaste la sesión?"

CIERRE

Cuando capa3_pregunta_final sea true:
"Antes de terminar: ¿qué parte del razonamiento de hoy te ha costado más construir, y por qué crees que ha sido?"

Tras su respuesta:
"Ahora tómate cinco minutos para rellenar tu diario de sesión."

No añades nada más."""

# ── Default checklist state ───────────────────────────────────────────────────
DEFAULT_STATE = {
    "capa1_no_coilocito_real": False,
    "capa1_criterio_negativo": False,
    "capa1_coilocito_descrito": False,
    "capa1_tres_elementos": False,
    "capa2_clasificacion_correcta": False,
    "capa2_criterio_jerarquizado": False,
    "capa2_VPH_nombrado": False,
    "capa2_riesgo_diferenciado": False,
    "capa2_cambio_manejo": False,
    "check_LSIL_Bethesda": False,
    "capa3_estadisticas": False,
    "capa3_contexto_edad": False,
    "capa3_tiempo_progresion": False,
    "capa3_pregunta_final": False,
}

ITEM_LABELS = {
    "capa1_no_coilocito_real": "Muestra A no es coilocito real",
    "capa1_criterio_negativo": "Criterio negativo identificado",
    "capa1_coilocito_descrito": "Muestra B descrita",
    "capa1_tres_elementos": "Tres elementos diagnósticos",
    "capa2_clasificacion_correcta": "Clasificación correcta",
    "capa2_criterio_jerarquizado": "Criterio jerarquizado",
    "capa2_VPH_nombrado": "VPH identificado",
    "capa2_riesgo_diferenciado": "Riesgo oncogénico diferenciado",
    "capa2_cambio_manejo": "Cambio en manejo clínico",
    "check_LSIL_Bethesda": "LSIL/VPH en Bethesda",
    "capa3_estadisticas": "Estadísticas de progresión",
    "capa3_contexto_edad": "Contexto por edad",
    "capa3_tiempo_progresion": "Tiempo de progresión",
    "capa3_pregunta_final": "Reflexión final",
}

LAYERS = {
    "Capa 1 — Observación": ["capa1_no_coilocito_real", "capa1_criterio_negativo", "capa1_coilocito_descrito", "capa1_tres_elementos"],
    "Capa 2 — Interpretación": ["capa2_clasificacion_correcta", "capa2_criterio_jerarquizado", "capa2_VPH_nombrado", "capa2_riesgo_diferenciado", "capa2_cambio_manejo", "check_LSIL_Bethesda"],
    "Capa 3 — Decisión clínica": ["capa3_estadisticas", "capa3_contexto_edad", "capa3_tiempo_progresion", "capa3_pregunta_final"],
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_client():
    api_key = st.secrets.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
    if not api_key:
        st.error("⚠️ API key no configurada. Añádela en los secretos de Streamlit.")
        st.stop()
    return anthropic.Anthropic(api_key=api_key)

def call_judge(client, history, prev_state):
    """Call the judge node to evaluate conversation state."""
    history_text = "\n".join([
        f"{'TUTOR' if m['role']=='assistant' else 'ESTUDIANTE'}: {m['content']}"
        for m in history
    ])
    user_msg = f"Estado previo:\n{json.dumps(prev_state, ensure_ascii=False)}\n\nHistorial completo:\n{history_text}"
    
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        system=JUDGE_PROMPT,
        messages=[{"role": "user", "content": user_msg}]
    )
    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    raw = re.sub(r"```json|```", "", raw).strip()
    new_state = json.loads(raw)
    # Ensure monotonicity: never go from true to false
    for k in prev_state:
        if prev_state[k] is True:
            new_state[k] = True
    return new_state

def call_tutor(client, history, state):
    """Call the tutor node."""
    state_block = f"[ESTADO ACTUAL DE LA CHECKLIST]\n{json.dumps(state, ensure_ascii=False, indent=2)}\n\n"
    messages = []
    for m in history:
        if m["role"] == "user":
            messages.append({"role": "user", "content": m["content"]})
        else:
            messages.append({"role": "assistant", "content": m["content"]})
    
    # Prepend state to last user message
    if messages and messages[-1]["role"] == "user":
        messages[-1]["content"] = state_block + messages[-1]["content"]
    
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=400,
        system=TUTOR_SYSTEM,
        messages=messages
    )
    return response.content[0].text.strip()

def save_log(student_id, history, state_history):
    """Save session log to a JSON file."""
    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"logs/{student_id}_{timestamp}.json"
    data = {
        "student_id": student_id,
        "timestamp": timestamp,
        "conversation": history,
        "state_history": state_history,
        "final_state": state_history[-1] if state_history else DEFAULT_STATE,
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filename

# ── Session state init ────────────────────────────────────────────────────────
if "mode" not in st.session_state:
    st.session_state.mode = "select"  # select | student | teacher

if "history" not in st.session_state:
    st.session_state.history = []

if "state" not in st.session_state:
    st.session_state.state = dict(DEFAULT_STATE)

if "state_history" not in st.session_state:
    st.session_state.state_history = []

if "student_id" not in st.session_state:
    st.session_state.student_id = ""

if "initialized" not in st.session_state:
    st.session_state.initialized = False

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

h1, h2, h3 {
    font-family: 'DM Serif Display', serif;
}

.stChatMessage {
    border-radius: 12px;
    margin-bottom: 8px;
}

.progress-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 0;
    font-size: 0.85rem;
}

.dot-true {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: #2ecc71;
    flex-shrink: 0;
}

.dot-false {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: #e0e0e0;
    flex-shrink: 0;
}

.layer-title {
    font-weight: 500;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #888;
    margin-top: 12px;
    margin-bottom: 4px;
}

.big-btn {
    display: inline-block;
    padding: 16px 32px;
    border-radius: 12px;
    font-size: 1.1rem;
    font-weight: 500;
    cursor: pointer;
    margin: 8px;
    border: 2px solid transparent;
    transition: all 0.2s;
}
</style>
""", unsafe_allow_html=True)

# ── Mode selector ─────────────────────────────────────────────────────────────
if st.session_state.mode == "select":
    st.markdown("# 🔬 Citología Ginecológica")
    st.markdown("### Sesión 3 · Tutor Socrático")
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👩‍🎓 Soy alumna", use_container_width=True, type="primary"):
            st.session_state.mode = "student"
            st.rerun()
    with col2:
        if st.button("👩‍🏫 Acceso profesora", use_container_width=True):
            st.session_state.mode = "teacher"
            st.rerun()

# ── Student view ──────────────────────────────────────────────────────────────
elif st.session_state.mode == "student":
    st.markdown("## 🔬 Tutor · Citología Ginecológica")

    client = get_client()

    # Initialize conversation with tutor's opening line
    if not st.session_state.initialized:
        opening = call_tutor(client, [], st.session_state.state)
        st.session_state.history.append({"role": "assistant", "content": opening})
        st.session_state.state_history.append(dict(st.session_state.state))
        st.session_state.initialized = True

    # Display chat
    for msg in st.session_state.history:
        role = "assistant" if msg["role"] == "assistant" else "user"
        with st.chat_message(role):
            st.write(msg["content"])

    # Input
    if prompt := st.chat_input("Escribe tu respuesta..."):
        st.session_state.history.append({"role": "user", "content": prompt})
        
        with st.spinner(""):
            # 1. Judge evaluates
            new_state = call_judge(client, st.session_state.history, st.session_state.state)
            st.session_state.state = new_state
            st.session_state.state_history.append(dict(new_state))
            
            # 2. Tutor responds
            tutor_reply = call_tutor(client, st.session_state.history, new_state)
            st.session_state.history.append({"role": "assistant", "content": tutor_reply})
            
            # 3. Save log
            sid = st.session_state.student_id or "sin_id"
            save_log(sid, st.session_state.history, st.session_state.state_history)

        st.rerun()

    # Back button
    st.divider()
    if st.button("← Volver"):
        st.session_state.mode = "select"
        st.session_state.history = []
        st.session_state.state = dict(DEFAULT_STATE)
        st.session_state.state_history = []
        st.session_state.initialized = False
        st.rerun()

# ── Teacher view ──────────────────────────────────────────────────────────────
elif st.session_state.mode == "teacher":
    st.markdown("## 👩‍🏫 Panel de Profesora")

    # Password check
    teacher_pass = st.secrets.get("TEACHER_PASSWORD", "citologia2024")
    if "teacher_auth" not in st.session_state:
        st.session_state.teacher_auth = False

    if not st.session_state.teacher_auth:
        pwd = st.text_input("Contraseña de acceso", type="password")
        if st.button("Entrar"):
            if pwd == teacher_pass:
                st.session_state.teacher_auth = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta")
        if st.button("← Volver"):
            st.session_state.mode = "select"
            st.rerun()
        st.stop()

    st.divider()

    # List log files
    log_dir = "logs"
    if not os.path.exists(log_dir) or not os.listdir(log_dir):
        st.info("Todavía no hay sesiones registradas.")
    else:
        files = sorted(os.listdir(log_dir), reverse=True)
        selected = st.selectbox("Selecciona una sesión", files)

        if selected:
            with open(os.path.join(log_dir, selected), "r", encoding="utf-8") as f:
                data = json.load(f)

            col1, col2 = st.columns([2, 1])

            with col1:
                st.markdown(f"### 💬 Chat — {data.get('student_id', '?')} · {data.get('timestamp', '')}")
                for i, msg in enumerate(data["conversation"]):
                    role = "🤖 Tutor" if msg["role"] == "assistant" else "👩‍🎓 Alumna"
                    state_at_turn = data["state_history"][i] if i < len(data["state_history"]) else None
                    
                    with st.expander(f"**{role}** — turno {i+1}", expanded=True):
                        st.write(msg["content"])
                        if state_at_turn and msg["role"] == "user":
                            # Show which items changed in this turn
                            prev = data["state_history"][i-1] if i > 0 else DEFAULT_STATE
                            new_items = [k for k in state_at_turn if state_at_turn[k] and not prev.get(k)]
                            if new_items:
                                st.success("✅ Nuevo en este turno: " + ", ".join(ITEM_LABELS[k] for k in new_items))

            with col2:
                st.markdown("### 📊 Progreso final")
                final = data.get("final_state", DEFAULT_STATE)
                total = len(final)
                done = sum(1 for v in final.values() if v)
                st.progress(done / total)
                st.markdown(f"**{done}/{total} ítems completados**")
                st.divider()

                for layer, items in LAYERS.items():
                    st.markdown(f'<div class="layer-title">{layer}</div>', unsafe_allow_html=True)
                    for item in items:
                        val = final.get(item, False)
                        dot = "dot-true" if val else "dot-false"
                        label = ITEM_LABELS[item]
                        st.markdown(
                            f'<div class="progress-item"><div class="{dot}"></div>{label}</div>',
                            unsafe_allow_html=True
                        )

                st.divider()
                st.markdown("### 📈 Evolución turno a turno")
                # Build a simple table
                if data["state_history"]:
                    rows = []
                    for i, s in enumerate(data["state_history"]):
                        rows.append({"Turno": i+1, "Ítems completados": sum(1 for v in s.values() if v)})
                    import pandas as pd
                    df = pd.DataFrame(rows)
                    st.line_chart(df.set_index("Turno"))

    st.divider()
    if st.button("← Volver"):
        st.session_state.mode = "select"
        st.session_state.teacher_auth = False
        st.rerun()
