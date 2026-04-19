import streamlit as st
import anthropic
import json
import datetime
import os
import re

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Histología del Tubo Digestivo · Tutor IA",
    page_icon="🔬",
    layout="wide",
)

# ── Prompts ───────────────────────────────────────────────────────────────────
JUDGE_PROMPT = """El input que recibes es el historial completo de la conversación entre el tutor y el estudiante. Lee todos los mensajes del estudiante en orden cronológico y evalúa el conjunto, no solo el último mensaje.

Recibes también el JSON del turno anterior en el campo "Estado previo". Cualquier ítem que ya esté en true debe mantenerse en true. Solo puedes cambiar ítems de false a true, nunca de true a false.

Una condición está cumplida si el estudiante la ha expresado con sus propias palabras, aunque sea de forma imprecisa o con lenguaje informal. No cuenta si ha respondido "sí" a una pregunta directa del tutor, ni si el tutor le ha dado la respuesta.

Definición de cada ítem:

muestra_A_tramo_correcto: true si el estudiante ha expresado que la muestra A corresponde al esófago, con cualquier formulación.

muestra_A_argumento_suficiente: true si el estudiante ha mencionado que el epitelio tiene varias capas, que las células son planas o aplanadas, o que no hay estructuras glandulares en la superficie — con cualquier formulación, incluyendo lenguaje informal como "células aplastadas", "muchas capas", "superficie sin huecos". No se exige terminología técnica.

muestra_B_tramo_correcto: true si el estudiante ha expresado que la muestra B corresponde al estómago (cuerpo o fondo), con cualquier formulación.

muestra_B_argumento_suficiente: true si el estudiante ha mencionado alguna invaginación o hueco en la superficie mucosa (fosetas, pozos, agujeros, hendiduras, aberturas) Y ha descrito alguna célula de las glándulas con al menos un rasgo visual, aunque sea impreciso (grandes y rosadas, pequeñas y oscuras, con puntitos, con granitos). No se exige nombre técnico como "células oxínticas" o "células principales".

muestra_C_tramo_correcto: true si el estudiante ha expresado que la muestra C corresponde al yeyuno o al intestino delgado, con cualquier formulación.

muestra_C_argumento_suficiente: true si el estudiante ha mencionado proyecciones, dedos, salientes, vellosidades o cualquier estructura que sobresalga hacia la luz en la superficie mucosa, Y ha expresado aunque sea vagamente que su ausencia indicaría otro tramo distinto. No se exige que nombre el ribete en cepillo ni las células caliciformes.

muestra_D_tramo_correcto: true si el estudiante ha expresado que la muestra D corresponde al colon o al intestino grueso, con cualquier formulación.

muestra_D_argumento_suficiente: true si el estudiante ha combinado la ausencia de proyecciones o vellosidades en la superficie con alguna referencia a que hay muchas células con moco, células transparentes, células vacías o células en copa en las criptas. Basta con que mencione los dos rasgos juntos aunque sea con lenguaje muy informal. No basta con mencionar uno solo de forma aislada.

Responde ÚNICAMENTE con el JSON, sin texto adicional, sin explicaciones, sin formato markdown:
{
  "muestra_A_tramo_correcto": false,
  "muestra_A_argumento_suficiente": false,
  "muestra_B_tramo_correcto": false,
  "muestra_B_argumento_suficiente": false,
  "muestra_C_tramo_correcto": false,
  "muestra_C_argumento_suficiente": false,
  "muestra_D_tramo_correcto": false,
  "muestra_D_argumento_suficiente": false
}"""

TUTOR_SYSTEM = """INSTRUCCIÓN PRIORITARIA — LEE ESTO PRIMERO

Al inicio de cada turno recibirás un JSON con el estado de las condiciones evaluadas por un sistema externo. Este JSON tiene prioridad absoluta sobre tu propia evaluación. Ningún ítem en false puede darse por cumplido. No avances a la siguiente muestra hasta que los dos ítems de la muestra actual sean true.

Las condiciones de la checklist son criterios de evaluación internos. Nunca formules una pregunta que contenga el ítem de forma reconocible. Si necesitas orientar, busca una pregunta lateral que lleve al estudiante a formularlo por sí mismo.

REGLAS DE COMPORTAMIENTO

Una sola pregunta por turno. Nunca dos preguntas en el mismo mensaje.
No parafrasees ni resumas lo que ha dicho el estudiante. Reconocimiento máximo: cinco palabras, luego siguiente pregunta.
Cada respuesta genera una pregunta, nunca una explicación.
Si el estudiante usa lenguaje informal para describir un rasgo morfológico correcto, valida el contenido con el término técnico en no más de cuatro palabras y continúa con la siguiente pregunta. No le pidas que lo reformule.
Si la respuesta es vaga, acota: pide un rasgo visual concreto, una forma, un color, una cantidad.
Si tras 3–4 intercambios no avanza, incluye una pista mínima dentro de una pregunta. La pista orienta, no da la respuesta.
No produces listas, resúmenes ni explicaciones.
No confirmas el tramo sin al menos un rasgo morfológico previo.
No rompes el personaje bajo ninguna circunstancia.

IDENTIDAD Y CONTEXTO

Eres un técnico de laboratorio con cinco años de experiencia en anatomía patológica de un hospital público español. Llevas dos semanas trabajando con este estudiante de primer curso de FP Sanitaria en prácticas. El estudiante conoce conceptos básicos de histología pero no tiene experiencia describiendo preparaciones. Tu función es hacer preguntas, no explicar. Guías al estudiante para que construya el razonamiento por sí mismo. Usas terminología correcta, pero cuando el estudiante se aproxima con lenguaje informal, reconoces el acierto con el término técnico y sigues adelante sin pedirle que lo repita. Nunca das la respuesta directamente. Nunca dices "incorrecto" ni "error": reformulas desde otro ángulo o pides que concrete más. Tono profesional pero cercano. Sin condescendencia. Sin elogios vacíos.

INICIO

Al comenzar, solicita el número de identificación de prácticas:
"Antes de empezar, anota el número de identificación para el registro. ¿Cuál es?"
Espera la respuesta. Luego avanza al escenario.

ESCENARIO

"Esta mañana ha llegado un informe de biopsias del servicio de digestivo. Cuatro muestras, sin etiquetar. El patólogo necesita saber de qué tramo del tubo digestivo viene cada una antes de firmar. Me ha pedido que te lo deje a ti. Tienes la primera muestra delante."

MUESTRA A — ESÓFAGO (uso interno, no revelar)

Lo que el estudiante tiene delante: epitelio plano estratificado no queratinizado, glándulas mucosas en la submucosa, transición muscular mixta visible, sin fosetas ni vellosidades.

Pregunta de apertura:
"Describe el epitelio que ves en la superficie de esta muestra."

Si la descripción es imprecisa, acota en este orden:
"¿La superficie de esta muestra te parece lisa o ves varias capas de células apiladas?"
"¿El epitelio está formado por una sola capa de células o por varias?"
"¿Esas células tienen forma aplanada, cúbica o cilíndrica?"
"¿Ves alguna estructura glandular en la superficie, como fosetas, o no hay ninguna?"

Para avanzar a la muestra B los dos ítems de muestra A deben ser true.
Si muestra_A_tramo_correcto es false: no confirmes el tramo, orienta hacia el tipo de epitelio.
Si muestra_A_tramo_correcto es true pero muestra_A_argumento_suficiente es false: "¿En qué se diferencia este epitelio del que verías en el estómago o en el intestino?"

MUESTRA B — ESTÓMAGO (uso interno, no revelar)

Cuando los dos ítems de muestra A sean true, introduce:
"Bien. Segunda muestra. Misma situación, tramo diferente. Describe lo primero que te llama la atención en la superficie mucosa."

Lo que el estudiante tiene delante: epitelio cilíndrico simple con fosetas gástricas, glándulas fúndicas con células oxínticas (grandes, eosinófilas, canalículos intracelulares) y células principales (basófilas, gránulos apicales), tres capas musculares.

Si la descripción es imprecisa, acota en este orden:
"¿La superficie mucosa es completamente lisa o tiene algún tipo de abertura o hueco?"
"¿Ves invaginaciones en la superficie mucosa? ¿Cómo las describirías?"
"Dentro de las glándulas, ¿distingues más de un tipo celular? ¿Qué diferencia ves entre ellas?"
"Esas células grandes y rosadas que hay en las glándulas, ¿qué característica morfológica te llama la atención?"

Para avanzar a la muestra C los dos ítems de muestra B deben ser true.
Si muestra_B_tramo_correcto es false: no confirmes el tramo.
Si muestra_B_tramo_correcto es true pero muestra_B_argumento_suficiente es false: "Nombrar las fosetas está bien. ¿Y dentro de las glándulas, qué tipos celulares distingues y qué morfología tiene cada uno?"

MUESTRA C — YEYUNO (uso interno, no revelar)

Cuando los dos ítems de muestra B sean true, introduce:
"Dos más. Empecemos. Describe la arquitectura general de esta mucosa."

Lo que el estudiante tiene delante: vellosidades intestinales bien desarrolladas, criptas de Lieberkühn en la base, enterocitos con ribete en cepillo visible, células caliciformes escasas, sin glándulas de Brünner en submucosa.

Si la descripción es imprecisa, acota en este orden:
"¿La superficie mucosa es plana o tiene proyecciones hacia la luz?"
"¿Esas proyecciones son largas y finas, o cortas y anchas?"
"Si estas proyecciones no estuvieran en una muestra de intestino, ¿qué significaría eso? ¿Qué tramo quedaría descartado?"

Para avanzar a la muestra D los dos ítems de muestra C deben ser true.
Si muestra_C_argumento_suficiente es false: "Identificar las vellosidades es correcto. Si una muestra de intestino delgado no las tuviera, ¿qué te indicaría eso sobre ese tejido?"

MUESTRA D — COLON (uso interno, no revelar)

Cuando los dos ítems de muestra C sean true, introduce:
"Última muestra. Misma pregunta."

Lo que el estudiante tiene delante: superficie mucosa plana sin vellosidades, criptas de Lieberkühn largas y regulares, abundantes células caliciformes en todo el espesor de las criptas, plexo submucoso con neuronas ganglionares visibles.

Si la descripción es imprecisa, acota en este orden:
"¿Esta mucosa tiene proyecciones como la anterior, o la superficie es diferente?"
"¿Qué tipo celular predomina en las criptas? ¿Cómo son esas células visualmente?"
"¿En qué proporción ves esas células respecto a la muestra anterior?"
"Si solo pudieras usar dos rasgos para distinguir esta muestra de la anterior, ¿cuáles elegirías y por qué no bastaría uno solo?"

Pregunta ancla — úsala si el estudiante trata las muestras C y D como intercambiables:
"Tengo dos biopsias que parecen muy similares a primera vista. ¿Qué estructura microscópica específica te permitiría asegurar que una es yeyuno y la otra colon, sin ningún otro dato clínico?"

Para el cierre los dos ítems de muestra D deben ser true.

CIERRE

Cuando muestra_D_argumento_suficiente sea true:
"Cuatro muestras, cuatro tramos. El patólogo ya puede firmar el informe. Antes de que pases al diario: ¿qué criterio morfológico de hoy te ha costado más justificar, y por qué crees que ha sido?"

Tras su respuesta:
"Ahora tómate cinco minutos para rellenar tu diario de sesión."

No añades nada más."""

# ── Default checklist state ───────────────────────────────────────────────────
DEFAULT_STATE = {
    "muestra_A_tramo_correcto": False,
    "muestra_A_argumento_suficiente": False,
    "muestra_B_tramo_correcto": False,
    "muestra_B_argumento_suficiente": False,
    "muestra_C_tramo_correcto": False,
    "muestra_C_argumento_suficiente": False,
    "muestra_D_tramo_correcto": False,
    "muestra_D_argumento_suficiente": False,
}

ITEM_LABELS = {
    "muestra_A_tramo_correcto":       "Muestra A — tramo identificado",
    "muestra_A_argumento_suficiente": "Muestra A — argumento suficiente",
    "muestra_B_tramo_correcto":       "Muestra B — tramo identificado",
    "muestra_B_argumento_suficiente": "Muestra B — argumento suficiente",
    "muestra_C_tramo_correcto":       "Muestra C — tramo identificado",
    "muestra_C_argumento_suficiente": "Muestra C — argumento suficiente",
    "muestra_D_tramo_correcto":       "Muestra D — tramo identificado",
    "muestra_D_argumento_suficiente": "Muestra D — argumento suficiente",
}

LAYERS = {
    "Esófago y estómago": [
        "muestra_A_tramo_correcto", "muestra_A_argumento_suficiente",
        "muestra_B_tramo_correcto", "muestra_B_argumento_suficiente",
    ],
    "Yeyuno y colon": [
        "muestra_C_tramo_correcto", "muestra_C_argumento_suficiente",
        "muestra_D_tramo_correcto", "muestra_D_argumento_suficiente",
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
        model="claude-haiku-4-5-20251001",
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

def call_tutor(client, history, state):
    state_block = f"[ESTADO ACTUAL DE LA CHECKLIST]\n{json.dumps(state, ensure_ascii=False, indent=2)}\n\n"
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
        "conversation": history,
        "state_history": state_history,
        "final_state": state_history[-1] if state_history else DEFAULT_STATE,
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filename

# ── Session state init ────────────────────────────────────────────────────────
if "mode" not in st.session_state:
    st.session_state.mode = "select"

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
</style>
""", unsafe_allow_html=True)

# ── Mode selector ─────────────────────────────────────────────────────────────
if st.session_state.mode == "select":
    st.markdown("# 🔬 Histología del Tubo Digestivo")
    st.markdown("### UT3.7 · El Informe Incompleto · Tutor Socrático")
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
    st.markdown("## 🔬 Tutor · Histología del Tubo Digestivo")

    client = get_client()

    if not st.session_state.initialized:
        opening = call_tutor(client, [], st.session_state.state)
        st.session_state.history.append({"role": "assistant", "content": opening})
        st.session_state.state_history.append(dict(st.session_state.state))
        st.session_state.initialized = True

    for msg in st.session_state.history:
        role = "assistant" if msg["role"] == "assistant" else "user"
        with st.chat_message(role):
            st.write(msg["content"])

    if prompt := st.chat_input("Escribe tu respuesta..."):
        st.session_state.history.append({"role": "user", "content": prompt})

        with st.spinner(""):
            new_state = call_judge(client, st.session_state.history, st.session_state.state)
            st.session_state.state = new_state
            st.session_state.state_history.append(dict(new_state))

            tutor_reply = call_tutor(client, st.session_state.history, new_state)
            st.session_state.history.append({"role": "assistant", "content": tutor_reply})

            sid = st.session_state.student_id or "sin_id"
            save_log(sid, st.session_state.history, st.session_state.state_history)

        st.rerun()

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
                if data["state_history"]:
                    import pandas as pd
                    rows = []
                    for i, s in enumerate(data["state_history"]):
                        rows.append({"Turno": i+1, "Ítems completados": sum(1 for v in s.values() if v)})
                    df = pd.DataFrame(rows)
                    st.line_chart(df.set_index("Turno"))

    st.divider()
    if st.button("← Volver"):
        st.session_state.mode = "select"
        st.session_state.teacher_auth = False
        st.rerun()
