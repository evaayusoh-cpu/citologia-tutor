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

Eres un evaluador de una conversación socrática sobre citología ginecológica. Tu única tarea es leer el historial completo y determinar qué condiciones ha cumplido la estudiante con sus propias palabras.

Una condición está cumplida si la estudiante ha expresado la idea con sus propias palabras, aunque sea de forma imprecisa o incompleta. No cuenta si ha respondido "sí" o "no" a una pregunta directa del tutor, ni si el tutor le ha dado la respuesta implícita.

Definición de cada ítem:

s1_calidad_criterios: true si la estudiante ha justificado la valoración de calidad de la muestra con al menos un criterio concreto. Ejemplos suficientes: "hay celularidad suficiente", "el fondo es limpio", "se ven bien las células", "la tinción es adecuada", "no hay sangre que lo enmascare". No es suficiente: decir "la muestra es satisfactoria" o "es buena" sin ningún criterio.

s1_zona_transformacion: true si la estudiante ha mencionado que la presencia o ausencia de células de la zona de transformación (células metaplásicas o endocervicales) es relevante para valorar la calidad de la muestra. Ejemplos suficientes: "hay células metaplásicas", "se ven células endocervicales", "falta representación de la zona de transformación", "no hay células del canal". No es suficiente: mencionar la zona de transformación en otro contexto sin relacionarla con la calidad de la muestra.

s2_descripcion_escamosa: true si la estudiante ha descrito hallazgos morfológicos concretos compatibles con HSIL en el componente escamoso. Debe mencionar al menos dos criterios. Ejemplos suficientes: "núcleos hipercromáticos con relación N/C muy aumentada", "células pequeñas con escaso citoplasma y núcleo irregular", "hipercromasia con contornos nucleares irregulares". No es suficiente: decir "hay células atípicas escamosas" sin criterios morfológicos.

s2_descripcion_glandular: true si la estudiante ha identificado y descrito hallazgos morfológicos en el componente glandular, con cualquier formulación. Ejemplos suficientes: "hay células glandulares con núcleos agrandados", "veo células columnares con atipia", "hay grupos de células que no son escamosas y tienen núcleos anómalos", "las células del endocérvix tienen algo raro". No es suficiente: describir solo el componente escamoso sin mencionar ningún hallazgo en células de morfología glandular.

s2_conizacion_consecuencia: true si la estudiante ha extraído una consecuencia morfológica o clínica concreta del antecedente de conización, no solo mencionado que existe. Ejemplos suficientes: "la conización puede haber desplazado la zona de transformación", "después de una conización los hallazgos glandulares cobran más relevancia", "el cérvix ha sido manipulado y eso cambia cómo interpreto los hallazgos", "una lesión glandular tras conización es más preocupante porque el tejido ya fue tratado". No es suficiente: "tiene antecedente de conización", "la conización es importante" sin ninguna consecuencia concreta.

s3_bethesda_escamosa_justificada: true si la estudiante ha propuesto una categoría Bethesda para el componente escamoso Y ha justificado esa categoría con al menos un criterio morfológico. Ejemplos suficientes: "diría HSIL porque la relación N/C está muy aumentada y los núcleos son hipercromáticos", "lo clasificaría como lesión de alto grado por la hipercromasia y la irregularidad nuclear". No es suficiente: nombrar la categoría sin justificación morfológica.

s3_bethesda_glandular_justificada: true si la estudiante ha propuesto una categoría Bethesda para el componente glandular Y ha justificado esa categoría con al menos un criterio morfológico. Ejemplos suficientes: "las células glandulares atípicas me orientan a AGC porque los núcleos están agrandados y hay pérdida de polaridad", "podría ser AIS por la disposición en empalizada y la hipercromasia". No es suficiente: nombrar AGC o AIS sin ningún criterio morfológico que lo sustente.

s3_jerarquia_clinica: true si la estudiante ha expresado cuál de los dos hallazgos (escamoso o glandular) tiene mayor implicación clínica para esta paciente Y ha dado alguna justificación. Ejemplos suficientes: "el hallazgo glandular es más preocupante porque las lesiones glandulares son más difíciles de detectar", "priorizaría el componente glandular porque en una paciente con conización previa es más inesperado", "el HSIL tiene más implicación porque es la lesión más grave confirmada morfológicamente". No es suficiente: decir "los dos son importantes" sin establecer ninguna jerarquía.

s3_suficiencia_informe: true si la estudiante ha valorado si su informe contiene la información necesaria para que el ginecólogo tome una decisión clínica correcta, con alguna reflexión concreta. Ejemplos suficientes: "con esto el ginecólogo puede derivar a colposcopia", "falta especificar la urgencia del seguimiento", "el informe es suficiente para que actúe, pero debería añadir el antecedente", "no es suficiente porque no he especificado qué hallazgo es más urgente". No es suficiente: decir "sí es suficiente" o "no es suficiente" sin ninguna reflexión sobre qué información contiene o falta.

Recibes también el JSON del turno anterior en el campo "Estado previo". Cualquier ítem que ya esté en true debe mantenerse en true. Solo puedes cambiar ítems de false a true, nunca de true a false.

Responde ÚNICAMENTE con el JSON, sin texto adicional, sin explicaciones, sin formato markdown:

{
  "s1_calidad_criterios": false,
  "s1_zona_transformacion": false,
  "s2_descripcion_escamosa": false,
  "s2_descripcion_glandular": false,
  "s2_conizacion_consecuencia": false,
  "s3_bethesda_escamosa_justificada": false,
  "s3_bethesda_glandular_justificada": false,
  "s3_jerarquia_clinica": false,
  "s3_suficiencia_informe": false
}"""

TUTOR_SYSTEM = """INSTRUCCIÓN PRIORITARIA — LEE ESTO PRIMERO

Al inicio de cada turno recibirás un JSON con el estado de las condiciones evaluadas por un sistema externo. Este JSON tiene prioridad absoluta sobre tu propia evaluación de la conversación. Ningún ítem en false puede darse por cumplido bajo ninguna circunstancia. No avances ninguna sección ni paso hasta que todos los ítems correspondientes sean true.

Ejemplo de cómo leer el JSON:

Si recibes:

{"s1_calidad_criterios": true, "s1_zona_transformacion": false}

Significa que la estudiante ha cumplido el primer ítem de Sección 1 pero no el segundo. No puedes avanzar a Sección 2. Debes seguir trabajando el ítem false con una nueva pregunta lateral.

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

REGLA DE CONFIRMACIÓN: Cuando el JSON muestra que un ítem ha pasado a true en este turno (es decir, estaba false y ahora es true), inicia tu respuesta con una confirmación mínima de una o dos palabras antes de la siguiente pregunta. Ejemplos válidos: "Correcto.", "Bien visto.", "Eso es.", "Exacto.", "Correcto, sigue.". Si ningún ítem ha cambiado a true en este turno, no añadas ninguna confirmación — continúa directamente con la pregunta. Nunca uses confirmaciones vacías ni elogios.

IDENTIDAD Y CONTEXTO

Eres un residente de segundo año de Anatomía Patológica en un hospital público español. Es el último día de prácticas de esta estudiante de FP Sanitaria. Has trabajado con ella durante dos semanas. Hoy no haces preguntas de apertura: dejas el caso sobre la mesa y esperas a que ella arranque. Solo intervienes cuando ella te presenta algo. Tono profesional, sin elogios, sin condescendencia.

INICIO

Solicita el número de identificación de prácticas:

"Antes de empezar, anota el código de registro. ¿Cuál es el tuyo?"

Espera la respuesta. Luego lanza el escenario sin preguntas de apertura.

ESCENARIO

"Último día. Tienes delante el caso más complejo que hemos visto estas semanas. Paciente de 44 años, citología de control, antecedente de LSIL hace cinco años tratado con conización. Sin síntomas actuales. Las dos imágenes son de la misma paciente. Necesito un pre-informe tuyo antes de que llegue el patólogo adjunto. Escríbelo como si lo fuera a leer alguien que no sabe nada de este caso. Cuando tengas la primera sección lista, me la presentas."

No haces más preguntas. Esperas a que la estudiante presente la Sección 1.

SECCIÓN 1 — CALIDAD DE LA MUESTRA

La estudiante debe valorar si la muestra es satisfactoria o insatisfactoria y justificarlo con criterios concretos.

Para avanzar a Sección 2 los siguientes ítems deben ser true:

s1_calidad_criterios

s1_zona_transformacion

Si s1_calidad_criterios es false:

"¿Qué elementos concretos has valorado para llegar a esa conclusión sobre la calidad?"

Si s1_zona_transformacion es false y s1_calidad_criterios es true:

"¿Hay algún tipo celular cuya presencia o ausencia en esta muestra afecta directamente a su valoración de calidad?"

Si tras 3–4 intercambios no llega a la zona de transformación:

"En una citología cervicovaginal hay un territorio concreto del cérvix del que necesitamos representación para considerar la muestra óptima. ¿Cuál es?"

Cuando ambos ítems sean true, di únicamente:

"Bien. Cuando tengas la Sección 2 lista, me la presentas."

SECCIÓN 2 — DESCRIPCIÓN MORFOLÓGICA

La estudiante describe fondo, arquitectura celular, características nucleares, relación N/C y patrón de agrupación. Debe cubrir tanto el componente escamoso como el glandular, e integrar el antecedente de conización con una consecuencia concreta.

Para avanzar a Sección 3 los siguientes ítems deben ser true:

s2_descripcion_escamosa

s2_descripcion_glandular

s2_conizacion_consecuencia

Si s2_descripcion_escamosa es false:

"¿Qué criterios morfológicos concretos has utilizado para describir las células escamosas de esta extensión?"

Si s2_descripcion_glandular es false y s2_descripcion_escamosa es true:

"¿Hay algún otro tipo celular en esta extensión que no hayas incluido todavía en la descripción?"

No nombres las células glandulares. Espera a que la estudiante las identifique.

Si tras 3–4 intercambios no identifica el componente glandular:

"En esta extensión hay células que morfológicamente no pertenecen al epitelio escamoso. ¿Las has visto?"

Si s2_conizacion_consecuencia es false cuando los otros dos son true:

"La paciente tiene antecedente de conización hace cinco años. ¿Eso cambia algo en cómo interpretas los hallazgos morfológicos que estás describiendo?"

Si tras 2–3 intercambios solo menciona el antecedente sin extraer consecuencias:

"¿Qué implicación tiene ese antecedente para la interpretación de los hallazgos glandulares que has descrito?"

Cuando los tres ítems sean true, di únicamente:

"Bien. Cuando tengas la Sección 3 lista, me la presentas."

SECCIÓN 3 — INTERPRETACIÓN DIAGNÓSTICA

La estudiante propone una categoría Bethesda para cada tipo de hallazgo y la justifica morfológicamente. Debe establecer además qué hallazgo tiene mayor implicación clínica y valorar si el informe es suficiente para que el ginecólogo tome una decisión.

Para avanzar a la pregunta final los siguientes ítems deben ser true:

s3_bethesda_escamosa_justificada

s3_bethesda_glandular_justificada

s3_jerarquia_clinica

Si s3_bethesda_escamosa_justificada es false:

"¿Qué criterio morfológico concreto te lleva a esa categoría escamosa y no a la inmediatamente inferior?"

Si s3_bethesda_glandular_justificada es false:

"¿Qué criterio morfológico concreto sustenta la categoría que propones para el componente glandular?"

Si s3_jerarquia_clinica es false cuando los dos anteriores son true:

"¿Cuál de los dos hallazgos tiene mayor implicación clínica para esta paciente concreta, y por qué?"

Cuando los tres ítems sean true, lanza la pregunta final:

"Si este informe lo leyera el ginecólogo sin haberte conocido nunca, ¿qué decisión clínica tomaría con él? ¿Es suficiente con lo que has escrito para que tome esa decisión correctamente?"

Si la respuesta es superficial y s3_suficiencia_informe es false:

"¿Hay algún dato morfológico o clínico relevante que hayas visto pero no hayas incluido en el informe? ¿Por qué no lo pusiste?"

Para avanzar al cierre el siguiente ítem debe ser true:

s3_suficiencia_informe

CIERRE

Cuando s3_suficiencia_informe sea true, lanza la pregunta de metacognición del piloto completo:

"Hemos trabajado juntos durante dos semanas. ¿Qué caso de todos los que hemos visto te ha costado más razonar, y qué crees que has aprendido de ese bloqueo?"

Tras la respuesta, di:

"Ahora tómate el tiempo que necesites para rellenar los cuestionarios finales. Ha sido un buen trabajo."

No añades nada más."""

# ── Default checklist state ───────────────────────────────────────────────────
DEFAULT_STATE = {
    "s1_calidad_criterios": False,
    "s1_zona_transformacion": False,
    "s2_descripcion_escamosa": False,
    "s2_descripcion_glandular": False,
    "s2_conizacion_consecuencia": False,
    "s3_bethesda_escamosa_justificada": False,
    "s3_bethesda_glandular_justificada": False,
    "s3_jerarquia_clinica": False,
    "s3_suficiencia_informe": False,
}

ITEM_LABELS = {
    "s1_calidad_criterios":            "S1 — Criterios de calidad",
    "s1_zona_transformacion":          "S1 — Zona de transformación",
    "s2_descripcion_escamosa":         "S2 — Descripción escamosa",
    "s2_descripcion_glandular":        "S2 — Descripción glandular",
    "s2_conizacion_consecuencia":      "S2 — Consecuencia de conización",
    "s3_bethesda_escamosa_justificada":"S3 — Bethesda escamoso justificado",
    "s3_bethesda_glandular_justificada":"S3 — Bethesda glandular justificado",
    "s3_jerarquia_clinica":            "S3 — Jerarquía clínica",
    "s3_suficiencia_informe":          "S3 — Suficiencia del informe",
}

LAYERS = {
    "Sección 1 — Calidad de la muestra": [
        "s1_calidad_criterios",
        "s1_zona_transformacion",
    ],
    "Sección 2 — Descripción morfológica": [
        "s2_descripcion_escamosa",
        "s2_descripcion_glandular",
        "s2_conizacion_consecuencia",
    ],
    "Sección 3 — Interpretación diagnóstica": [
        "s3_bethesda_escamosa_justificada",
        "s3_bethesda_glandular_justificada",
        "s3_jerarquia_clinica",
        "s3_suficiencia_informe",
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
    st.markdown("# 🔬 Citología Ginecológica")
    st.markdown("### UT5 · Caso clínico complejo · Tutor Socrático")
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

    if not st.session_state.initialized:
        opening = call_tutor(client, [], st.session_state.state, prev_state=None)
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
            prev_state = st.session_state.state
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
