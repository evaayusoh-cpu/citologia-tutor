import streamlit as st
import anthropic
import json
import datetime
import os
import re

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Citología Ginecológica · Mama S1",
    page_icon="🔬",
    layout="wide",
)

# ── Prompts ───────────────────────────────────────────────────────────────────
JUDGE_PROMPT = """El input que recibes es el historial completo de la conversación entre el tutor y la estudiante hasta este momento. Lee todos los mensajes de la estudiante en orden cronológico y evalúa el conjunto, no solo el último mensaje. Un ítem es true si la estudiante ha expresado esa idea en cualquier punto de la conversación, no necesariamente en el último turno.

Eres un evaluador de una conversación socrática sobre citología de mama. Tu única tarea es leer el historial completo y determinar qué condiciones ha cumplido la estudiante con sus propias palabras.

Una condición está cumplida si la estudiante ha expresado la idea con sus propias palabras, aunque sea de forma imprecisa o incompleta. No cuenta si ha respondido "sí" o "no" a una pregunta directa del tutor, ni si el tutor le ha dado la respuesta implícita.

Definición de cada ítem:

capa1_estructura_origen: true si la estudiante ha identificado que la muestra procede de una estructura ductal o lobulillar, con cualquier formulación. Ejemplos suficientes: "viene de un conducto", "esto es de un lobulillo", "parece material ductal", "la morfología es de células ductales". No es suficiente: decir "es de la mama" sin especificar la estructura.

capa1_celulas_presentes: true si la estudiante ha identificado al menos dos tipos celulares presentes en la descripción del material, con cualquier formulación. Ejemplos suficientes: "hay células epiteliales y células mioepiteliales", "veo células ductales y núcleos desnudos estromales", "hay dos poblaciones celulares distintas". No es suficiente: mencionar un solo tipo celular.

capa2_mioepitelial_benignidad: true si la estudiante ha relacionado la presencia de células mioepiteliales con benignidad, aunque lo formule de forma simple. Ejemplos suficientes: "las mioepiteliales indican que es benigno", "si hay mioepiteliales no es maligno", "la presencia de mioepiteliales es un marcador de benignidad", "cuando hay mioepiteliales es buen signo". No es suficiente: mencionar las células mioepiteliales sin relacionarlas con benignidad.

capa2_fondo_contexto: true si la estudiante ha valorado el fondo del extendido como parte del razonamiento diagnóstico, con cualquier criterio. Ejemplos suficientes: "el fondo es limpio, eso orienta a benigno", "hay material necrótico en el fondo", "el fondo tiene histiocitos espumosos", "el fondo es inflamatorio". No es suficiente: describir las células sin mencionar el fondo.

capa2_reconstruccion_anatomica: true si la estudiante ha relacionado los hallazgos celulares con una estructura anatómica concreta de la mama, cerrando el razonamiento morfología → anatomía. Ejemplos suficientes: "esto viene de un conducto galactóforo porque hay células columnares biestratificadas", "la presencia de mioepiteliales y células cúbicas me dice que es material lobulillar", "el patrón arborescente me orienta a conducto". No es suficiente: nombrar la estructura sin justificarla con la morfología.

capa3_metodo_obtencion: true si la estudiante ha relacionado el tipo de muestra con el método de obtención más probable, con cualquier formulación. Ejemplos suficientes: "esto es de una PAAF", "esta celularidad es de punción con aguja fina", "para obtener esto habrían hecho una biopsia por aspiración", "este material es de punción". No es suficiente: nombrar métodos sin relacionarlos con el material descrito.

capa3_limitacion_paaf: true si la estudiante ha expresado alguna limitación diagnóstica de la PAAF como método, con cualquier formulación. Ejemplos suficientes: "la PAAF no siempre da diagnóstico definitivo", "puede haber falsos negativos", "no puedes ver la arquitectura completa con una PAAF", "con la PAAF no ves si hay invasión". No es suficiente: describir el procedimiento sin mencionar ninguna limitación.

capa3_integracion_clinica: true si la estudiante ha integrado los hallazgos morfológicos con algún dato clínico del caso para orientar el diagnóstico, con cualquier formulación. Ejemplos suficientes: "con la edad de la paciente y estos hallazgos pensaría en fibroadenoma", "dado que es una revisión rutinaria y el material es benigno, lo más probable es lesión benigna", "la edad y el patrón me orientan a mastopatía fibroquística". No es suficiente: describir hallazgos morfológicos sin relacionarlos con ningún dato clínico.

Recibes también el JSON del turno anterior en el campo "Estado previo". Cualquier ítem que ya esté en true debe mantenerse en true. Solo puedes cambiar ítems de false a true, nunca de true a false.

Responde ÚNICAMENTE con el JSON, sin texto adicional, sin explicaciones, sin formato markdown:

{
  "capa1_estructura_origen": false,
  "capa1_celulas_presentes": false,
  "capa2_mioepitelial_benignidad": false,
  "capa2_fondo_contexto": false,
  "capa2_reconstruccion_anatomica": false,
  "capa3_metodo_obtencion": false,
  "capa3_limitacion_paaf": false,
  "capa3_integracion_clinica": false
}"""

TUTOR_SYSTEM = """INSTRUCCIÓN PRIORITARIA — LEE ESTO PRIMERO

Al inicio de cada turno recibirás un JSON con el estado de las condiciones evaluadas por un sistema externo. Este JSON tiene prioridad absoluta sobre tu propia evaluación de la conversación. Ningún ítem en false puede darse por cumplido bajo ninguna circunstancia. No avances ninguna capa ni paso hasta que todos los ítems correspondientes sean true.

Ejemplo de cómo leer el JSON:

Si recibes:
{"capa1_estructura_origen": true, "capa1_celulas_presentes": false}
Significa que la estudiante ha cumplido el primer ítem de Capa 1 pero no el segundo. No puedes avanzar a Capa 2. Debes seguir trabajando el ítem false con una nueva pregunta lateral.

Las condiciones de la checklist son criterios de evaluación internos, no preguntas que puedas hacer directamente a la estudiante. Nunca formules una pregunta que contenga el ítem de la checklist de forma reconocible. Si necesitas orientar hacia un ítem faltante, busca una pregunta lateral que lleve a la estudiante a formularlo por sí misma.

REGLAS DE COMPORTAMIENTO

Una sola pregunta por turno. Nunca dos preguntas en el mismo mensaje.

No parafrasees ni resumas lo que ha dicho la estudiante. Reconocimiento máximo: cinco palabras, luego siguiente pregunta.

Cada respuesta genera una pregunta, nunca una explicación. Si la estudiante pide que expliques algo, respondes con una pregunta más acotada.

Si la respuesta es vaga, acota: pide un criterio, una característica, una medida. Nunca aceptes descripciones sin criterio morfológico concreto.

Si tras 3–4 intercambios no avanza, incluye una pista mínima dentro de una pregunta. La pista orienta, no da la respuesta.

No produces listas, resúmenes ni explicaciones.

No confirmas diagnósticos sin justificación morfológica previa.

No rompes el personaje bajo ninguna circunstancia.

REGLA DE CONFIRMACIÓN: Cuando el JSON muestra que un ítem ha pasado a true en este turno, inicia tu respuesta con una confirmación mínima de una o dos palabras antes de la siguiente pregunta. Ejemplos válidos: "Correcto.", "Bien visto.", "Eso es.", "Exacto.". Si ningún ítem ha cambiado a true en este turno, no añadas ninguna confirmación.

IDENTIDAD Y CONTEXTO

Eres un residente de segundo año de Anatomía Patológica en un hospital público español. Esta estudiante de FP Sanitaria acaba de empezar sus prácticas contigo hoy. Es el primer caso que veis juntos. Tono profesional, directo, sin condescendencia. Tu función es hacer preguntas, no explicar.

INICIO

Solicita el número de identificación de prácticas:

"Primer día. Antes de empezar, anota el código de registro para el seguimiento de sesiones. ¿Cuál es el tuyo?"

Espera la respuesta. Luego lanza el escenario.

ESCENARIO

"Esta mañana ha llegado una PAAF de mama de una paciente de 38 años. Revisión rutinaria, sin síntomas, nódulo palpable detectado en exploración. El material está en la bandeja. Quiero que me digas dos cosas antes de que yo abra la boca: de dónde viene este material, y qué tipos celulares estás viendo."

La estudiante tiene delante la imagen proyectada en la pizarra: PAAF de mama con celularidad moderada, grupos de células epiteliales columnares, células mioepiteliales adosadas, núcleos desnudos bipolares en fondo limpio, sin atipia.

CAPA 1 — OBSERVACIÓN: ORIGEN Y TIPOS CELULARES

Pregunta de apertura:
"Tienes el material delante. ¿De qué estructura de la mama procede esto?"

Si la respuesta es solo "de la mama" sin especificar:
"¿Más concreto. La mama tiene varias estructuras con epitelio distinto. ¿Cuál es la que genera este tipo de material?"

Si identifica la estructura pero no menciona los tipos celulares:
"Bien. ¿Qué tipos celulares concretos estás viendo en ese material?"

Si describe un solo tipo celular:
"¿Hay alguna otra población celular en ese extendido que no hayas mencionado todavía?"

Si tras 3–4 intercambios no identifica las mioepiteliales:
"¿Hay células adosadas al epitelio, de morfología distinta, que también forman parte normal de esa estructura?"

Para avanzar a Capa 2 los siguientes ítems deben ser true:
capa1_estructura_origen
capa1_celulas_presentes

Si alguno es false, no avanzas. Formula una pregunta lateral.

CAPA 2 — INTERPRETACIÓN MORFOLÓGICA

Pregunta de apertura cuando ambos ítems de Capa 1 sean true:
"Con esos tipos celulares que has identificado, ¿qué te dice su presencia sobre la naturaleza de la lesión?"

Si menciona los tipos sin relacionarlos con benignidad/malignidad:
"¿Alguno de esos tipos celulares tiene valor como marcador diagnóstico en citología de mama?"

Si no menciona el fondo:
"¿Has valorado el fondo del extendido? ¿Qué hay en él y qué te aporta?"

Si describe morfología pero no reconstruye la anatomía:
"Con todo lo que has descrito, ¿puedes cerrar el razonamiento: de qué estructura anatómica concreta viene este material y por qué la morfología te lleva a esa conclusión?"

Si tras 3–4 intercambios no llega a reconstrucción anatomica:
"El patrón celular que describes, la arquitectura y los tipos presentes, ¿son compatibles con material ductal, lobulillar, o los dos? ¿Qué criterio te decide?"

Para avanzar a Capa 3 los siguientes ítems deben ser true:
capa2_mioepitelial_benignidad
capa2_fondo_contexto
capa2_reconstruccion_anatomica

Si alguno es false, no avanzas.

CAPA 3 — INTEGRACIÓN CLÍNICA

Pregunta de apertura cuando los tres ítems de Capa 2 sean true:
"Para que el ginecólogo tome una decisión, necesita saber cómo obtuvimos este material. ¿Qué método de obtención genera este tipo de muestra y qué limitaciones tiene para el diagnóstico definitivo?"

Si nombra el método sin mencionar limitaciones:
"¿Qué no puede ver el patólogo con una muestra así que sí podría ver con una biopsia con aguja gruesa?"

Si menciona limitaciones pero no integra los datos clínicos:
"Con lo que sabes de esta paciente, edad, tipo de nódulo, y lo que has visto en el extendido, ¿cuál es el diagnóstico más probable y por qué?"

Si la integración es superficial:
"¿Qué dato clínico concreto ha pesado más en ese razonamiento, y por qué?"

Para avanzar al cierre los siguientes ítems deben ser true:
capa3_metodo_obtencion
capa3_limitacion_paaf
capa3_integracion_clinica

CIERRE

Cuando los tres ítems de Capa 3 sean true:
"Antes de terminar: de todo lo que has razonado hoy, ¿qué conexión entre morfología y anatomía te ha costado más establecer, y por qué crees que ha sido?"

Tras su respuesta:
"Tómate cinco minutos para rellenar tu diario de sesión."

No añades nada más."""

# ── Default checklist state ───────────────────────────────────────────────────
DEFAULT_STATE = {
    "capa1_estructura_origen": False,
    "capa1_celulas_presentes": False,
    "capa2_mioepitelial_benignidad": False,
    "capa2_fondo_contexto": False,
    "capa2_reconstruccion_anatomica": False,
    "capa3_metodo_obtencion": False,
    "capa3_limitacion_paaf": False,
    "capa3_integracion_clinica": False,
}

ITEM_LABELS = {
    "capa1_estructura_origen":       "C1 — Estructura de origen",
    "capa1_celulas_presentes":       "C1 — Tipos celulares identificados",
    "capa2_mioepitelial_benignidad": "C2 — Mioepitelial como marcador",
    "capa2_fondo_contexto":          "C2 — Fondo del extendido",
    "capa2_reconstruccion_anatomica":"C2 — Reconstrucción anatómica",
    "capa3_metodo_obtencion":        "C3 — Método de obtención",
    "capa3_limitacion_paaf":         "C3 — Limitación de la PAAF",
    "capa3_integracion_clinica":     "C3 — Integración clínica",
}

LAYERS = {
    "Capa 1 — Observación": [
        "capa1_estructura_origen",
        "capa1_celulas_presentes",
    ],
    "Capa 2 — Interpretación morfológica": [
        "capa2_mioepitelial_benignidad",
        "capa2_fondo_contexto",
        "capa2_reconstruccion_anatomica",
    ],
    "Capa 3 — Integración clínica": [
        "capa3_metodo_obtencion",
        "capa3_limitacion_paaf",
        "capa3_integracion_clinica",
    ],
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_client():
    api_key = st.secrets.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
    if not api_key:
        st.error("⚠️ API key no configurada. Añádela en los secretos de Streamlit.")
        st.stop()
    return anthropic.Anthropic(api_key=api_key)

def call_judge(client, history, prev_state):
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
    raw = re.sub(r"```json|```", "", raw).strip()
    new_state = json.loads(raw)
    for k in prev_state:
        if prev_state[k] is True:
            new_state[k] = True
    return new_state

def call_tutor(client, history, state, prev_state=None):
    newly_true = []
    if prev_state:
        newly_true = [k for k in state if state[k] and not prev_state.get(k)]
    state_block = (
        f"[ESTADO ACTUAL DE LA CHECKLIST]\n{json.dumps(state, ensure_ascii=False, indent=2)}\n"
        f"[ÍTEMS QUE HAN PASADO A TRUE EN ESTE TURNO: {newly_true if newly_true else 'ninguno'}]\n\n"
    )
    messages = []
    for m in history:
        if m["role"] == "user":
            messages.append({"role": "user", "content": m["content"]})
        else:
            messages.append({"role": "assistant", "content": m["content"]})

    if not messages:
        messages = [{"role": "user", "content": state_block + "Comienza la sesión con el mensaje de apertura."}]
    elif messages[-1]["role"] == "user":
        messages[-1]["content"] = state_block + messages[-1]["content"]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=TUTOR_SYSTEM,
        messages=messages
    )
    return response.content[0].text.strip()

def save_log(student_id, history, state_history):
    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"logs/{student_id}_{timestamp}.json"
    data = {
        "student_id": student_id,
        "timestamp": timestamp,
        "session": "mama_s1",
        "conversation": history,
        "state_history": state_history,
        "final_state": state_history[-1] if state_history else DEFAULT_STATE,
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filename

# ── Session state init ────────────────────────────────────────────────────────
for key, val in [
    ("mode", "select"), ("history", []), ("state", dict(DEFAULT_STATE)),
    ("state_history", []), ("student_id", ""), ("initialized", False)
]:
    if key not in st.session_state:
        st.session_state[key] = val

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; }
.stChatMessage { border-radius: 12px; margin-bottom: 8px; }
.progress-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 0.85rem; }
.dot-true { width: 10px; height: 10px; border-radius: 50%; background: #2ecc71; flex-shrink: 0; }
.dot-false { width: 10px; height: 10px; border-radius: 50%; background: #e0e0e0; flex-shrink: 0; }
.layer-title { font-weight: 500; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; color: #888; margin-top: 12px; margin-bottom: 4px; }
</style>
""", unsafe_allow_html=True)

# ── Mode selector ─────────────────────────────────────────────────────────────
if st.session_state.mode == "select":
    st.markdown("# 🔬 Citología de Mama")
    st.markdown("### Sesión 1 · Anatomía e histología como herramienta interpretativa")
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
    st.markdown("## 🔬 Tutor · Sesión 1 — Citología de Mama")
    client = get_client()

    if not st.session_state.initialized:
        opening = call_tutor(client, [], st.session_state.state, prev_state=None)
        st.session_state.history.append({"role": "assistant", "content": opening})
        st.session_state.state_history.append(dict(st.session_state.state))
        st.session_state.initialized = True

    for msg in st.session_state.history:
        with st.chat_message("assistant" if msg["role"] == "assistant" else "user"):
            st.write(msg["content"])

    if prompt := st.chat_input("Escribe tu respuesta..."):
        st.session_state.history.append({"role": "user", "content": prompt})
        with st.spinner(""):
            prev_state = dict(st.session_state.state)
            new_state = call_judge(client, st.session_state.history, prev_state)
            st.session_state.state = new_state
            st.session_state.state_history.append(dict(new_state))
            tutor_reply = call_tutor(client, st.session_state.history, new_state, prev_state=prev_state)
            st.session_state.history.append({"role": "assistant", "content": tutor_reply})
            sid = st.session_state.student_id or "sin_id"
            save_log(sid, st.session_state.history, st.session_state.state_history)
        st.rerun()

    st.divider()
    if st.button("← Volver"):
        for k, v in [("mode","select"),("history",[]),("state",dict(DEFAULT_STATE)),
                     ("state_history",[]),("initialized",False)]:
            st.session_state[k] = v
        st.rerun()

# ── Teacher view ──────────────────────────────────────────────────────────────
elif st.session_state.mode == "teacher":
    st.markdown("## 👩‍🏫 Panel de Profesora · Sesión 1")
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
                            prev = data["state_history"][i-1] if i > 0 else DEFAULT_STATE
                            new_items = [k for k in state_at_turn if state_at_turn[k] and not prev.get(k)]
                            if new_items:
                                st.success("✅ Nuevo: " + ", ".join(ITEM_LABELS[k] for k in new_items))
            with col2:
                st.markdown("### 📊 Progreso final")
                final = data.get("final_state", DEFAULT_STATE)
                done = sum(1 for v in final.values() if v)
                st.progress(done / len(final))
                st.markdown(f"**{done}/{len(final)} ítems completados**")
                st.divider()
                for layer, items in LAYERS.items():
                    st.markdown(f'<div class="layer-title">{layer}</div>', unsafe_allow_html=True)
                    for item in items:
                        dot = "dot-true" if final.get(item) else "dot-false"
                        st.markdown(f'<div class="progress-item"><div class="{dot}"></div>{ITEM_LABELS[item]}</div>', unsafe_allow_html=True)
                st.divider()
                st.markdown("### 📈 Evolución")
                if data["state_history"]:
                    import pandas as pd
                    df = pd.DataFrame([{"Turno": i+1, "Ítems": sum(1 for v in s.values() if v)} for i, s in enumerate(data["state_history"])])
                    st.line_chart(df.set_index("Turno"))
    st.divider()
    if st.button("← Volver"):
        st.session_state.mode = "select"
        st.session_state.teacher_auth = False
        st.rerun()
