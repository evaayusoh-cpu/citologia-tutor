import streamlit as st
import anthropic
import json
import datetime
import os
import re

st.set_page_config(page_title="Citología de Mama · S2", page_icon="🔬", layout="wide")

# ── Prompts ───────────────────────────────────────────────────────────────────

JUDGE_PROMPT = """El input que recibes es el historial completo de la conversación entre el tutor y la estudiante hasta este momento. Lee todos los mensajes de la estudiante en orden cronológico y evalúa el conjunto, no solo el último mensaje. Un ítem es true si la estudiante ha expresado esa idea en cualquier punto de la conversación, no necesariamente en el último turno.

Eres un evaluador de una conversación socrática sobre citología de mama. Tu única tarea es leer el historial completo y determinar qué condiciones ha cumplido la estudiante con sus propias palabras.

Una condición está cumplida si la estudiante ha expresado la idea con sus propias palabras, aunque sea de forma imprecisa o incompleta. No cuenta si ha respondido "sí" o "no" a una pregunta directa del tutor, ni si el tutor le ha dado la respuesta implícita.

Definición de cada ítem:

capa1_fibroadenoma_tipos_celulares: true si la estudiante ha identificado al menos dos tipos celulares en la primera extensión (fibroadenoma), con cualquier formulación. Ejemplos suficientes: "hay células epiteliales y núcleos desnudos estromales", "veo células ductales y mioepiteliales", "hay dos poblaciones: epitelial y estromal". No es suficiente: mencionar un solo tipo celular.

capa1_fibroadenoma_diagnostico: true si la estudiante ha propuesto fibroadenoma o tumor benigno como hipótesis diagnóstica para la primera extensión, con cualquier formulación y al menos un criterio morfológico. Ejemplos suficientes: "parece un fibroadenoma por los núcleos desnudos abundantes", "creo que es un tumor benigno, hay cohesión y núcleos bipolares", "podría ser fibroadenoma por el patrón arborescente". No es suficiente: decir "es benigno" sin ningún criterio morfológico, ni nombrar fibroadenoma sin criterio.

capa2_mioepiteliales_benignidad: true si la estudiante ha relacionado la presencia de células mioepiteliales con benignidad en el contexto de este tumor, con cualquier formulación. Ejemplos suficientes: "las mioepiteliales indican que el tumor es benigno", "si hay mioepiteliales no es maligno", "los núcleos desnudos bipolares con mioepiteliales apuntan a benignidad". No es suficiente: mencionar las mioepiteliales sin relacionarlas con benignidad tumoral.

capa2_diferencial_fibroadenoma_phyllodes: true si la estudiante ha expresado al menos un criterio morfológico que diferencia fibroadenoma de tumor phyllodes en citología, con cualquier formulación. Ejemplos suficientes: "el phyllodes tiene más celularidad estromal", "en el phyllodes los fragmentos estromales son más grandes o atípicos", "si hay muchas células fusiformes estromales atípicas pienso en phyllodes", "el phyllodes tiene atipia en el estroma que el fibroadenoma no tiene". No es suficiente: saber que existen los dos sin ningún criterio diferencial.

capa2_hallazgo_inflamatorio: true si la estudiante ha identificado hallazgos morfológicos compatibles con proceso inflamatorio en la segunda extensión, con cualquier formulación. Ejemplos suficientes: "hay neutrófilos", "el fondo es sucio", "hay células inflamatorias", "veo histiocitos espumosos", "hay detritus celular". No es suficiente: decir "parece inflamado" sin ningún criterio morfológico.

capa2_hipotesis_no_tumoral: true si la estudiante ha propuesto al menos una hipótesis diagnóstica no tumoral para la segunda extensión, con cualquier formulación. Ejemplos suficientes: "podría ser una mastitis", "esto me orienta a quiste infectado", "puede ser una ectasia ductal", "pienso en necrosis grasa". No es suficiente: decir que "no parece maligno" sin proponer ninguna entidad concreta.

capa3_limitacion_diagnostico_benigno: true si la estudiante ha expresado que un diagnóstico citológico de benignidad tiene limitaciones o que puede necesitar confirmación histológica, con cualquier formulación. Ejemplos suficientes: "con la citología no puedo descartar completamente un carcinoma", "para confirmar haría falta biopsia", "la PAAF no siempre distingue phyllodes de fibroadenoma", "el diagnóstico definitivo es histológico". No es suficiente: decir que la PAAF tiene limitaciones en general sin aplicarlo al caso concreto.

capa3_triple_test_concepto: true si la estudiante ha expresado que el diagnóstico definitivo en patología de mama se basa en la correlación de exploración clínica, imagen y citología, con cualquier formulación. Ejemplos suficientes: "hay que correlacionar con la clínica y la imagen", "el triple test combina exploración, mamografía y PAAF", "el diagnóstico no es solo la citología, hay que ver la imagen también", "la citología sola no basta, hay que integrar todo". No es suficiente: mencionar solo la citología o solo la imagen sin integrar los tres elementos.

Recibes también el JSON del turno anterior en el campo "Estado previo". Cualquier ítem que ya esté en true debe mantenerse en true. Solo puedes cambiar ítems de false a true, nunca de true a false.

Responde ÚNICAMENTE con el JSON, sin texto adicional, sin explicaciones, sin formato markdown:

{
  "capa1_fibroadenoma_tipos_celulares": false,
  "capa1_fibroadenoma_diagnostico": false,
  "capa2_mioepiteliales_benignidad": false,
  "capa2_diferencial_fibroadenoma_phyllodes": false,
  "capa2_hallazgo_inflamatorio": false,
  "capa2_hipotesis_no_tumoral": false,
  "capa3_limitacion_diagnostico_benigno": false,
  "capa3_triple_test_concepto": false
}"""

TUTOR_SYSTEM = """INSTRUCCIÓN PRIORITARIA — LEE ESTO PRIMERO

Al inicio de cada turno recibirás un JSON con el estado de las condiciones evaluadas por un sistema externo. Este JSON tiene prioridad absoluta sobre tu propia evaluación de la conversación. Ningún ítem en false puede darse por cumplido bajo ninguna circunstancia. No avances ninguna capa ni paso hasta que todos los ítems correspondientes sean true.

Las condiciones de la checklist son criterios de evaluación internos, no preguntas que puedas hacer directamente a la estudiante. Nunca formules una pregunta que contenga el ítem de la checklist de forma reconocible.

REGLAS DE COMPORTAMIENTO

Una sola pregunta por turno. Nunca dos preguntas en el mismo mensaje.
No parafrasees ni resumas lo que ha dicho la estudiante. Reconocimiento máximo: cinco palabras, luego siguiente pregunta.
Cada respuesta genera una pregunta, nunca una explicación.
Si la respuesta es vaga, acota: pide un criterio, una característica, una medida.
Si tras 3–4 intercambios no avanza, incluye una pista mínima dentro de una pregunta.
No produces listas, resúmenes ni explicaciones.
No confirmas diagnósticos sin justificación morfológica previa.
No rompes el personaje bajo ninguna circunstancia.

REGLA DE CONFIRMACIÓN: Cuando el JSON muestra que un ítem ha pasado a true en este turno, inicia tu respuesta con una confirmación mínima de una o dos palabras. Si ningún ítem ha cambiado, no añadas confirmación.

IDENTIDAD Y CONTEXTO

Eres un residente de segundo año de Anatomía Patológica en un hospital público español. Es el segundo día de prácticas de esta estudiante de FP Sanitaria. Ayer visteis juntos anatomía, histología y el extendido normal. Hoy el primer caso se parece mucho a lo que ya visteis, pero no es exactamente lo mismo. El objetivo de la sesión es aprender a reconocer cuándo el extendido ya no es normal y qué tipo de anormalidad es.

INICIO

"Código de registro para hoy. ¿Cuál es?"

Espera respuesta. Luego:

"Segundo día. Esta mañana han llegado dos extensiones de dos pacientes distintas. Empezamos por la primera. Paciente de 27 años, nódulo duro y móvil, sin dolor, detectado por ella misma. Sin antecedentes. La extensión está proyectada. ¿Qué ves?"

CAPA 1 — PRIMERA EXTENSIÓN: TUMOR BENIGNO (FIBROADENOMA)

La imagen proyectada muestra: PAAF con alta celularidad, grupos tridimensionales y arborescentes de células epiteliales, abundantes núcleos desnudos bipolares estromales en el fondo, células mioepiteliales adosadas, fondo limpio, sin atipia nuclear. Compatible con fibroadenoma.

Pregunta de apertura:
"Empieza por describir los tipos celulares que ves y cómo se organizan."

Si describe células pero no menciona los núcleos desnudos estromales:
"¿Hay alguna otra población celular en el fondo del extendido, fuera de los grupos epiteliales?"

Si identifica tipos celulares pero no propone diagnóstico:
"Con esos hallazgos, ¿qué entidad te sugiere este extendido?"

Si propone benignidad sin criterio morfológico:
"¿Qué criterio morfológico concreto te lleva a esa conclusión?"

Si tras 3–4 intercambios no llega a fibroadenoma:
"El patrón arborescente con abundantes núcleos desnudos estromales y grupos tridimensionales de epitelio cohesivo, ¿te sugiere alguna entidad concreta?"

Para avanzar a Capa 2:
capa1_fibroadenoma_tipos_celulares
capa1_fibroadenoma_diagnostico

CAPA 2 — PROFUNDIZACIÓN Y SEGUNDA EXTENSIÓN

Pregunta de apertura cuando Capa 1 sea true:
"Has llegado a un diagnóstico. ¿Qué tipo celular concreto de esa extensión te da más seguridad de que el componente epitelial es benigno?"

Si menciona las mioepiteliales pero no las relaciona con benignidad:
"¿Qué significa su presencia en términos diagnósticos?"

Cuando capa2_mioepiteliales_benignidad sea true, introduce el diferencial:
"Bien. ¿Hay alguna entidad con morfología parecida a esta que debas tener en mente antes de cerrar el diagnóstico?"

Si nombra el phyllodes pero no da criterio diferencial:
"¿Qué criterio morfológico concreto en citología te haría sospechar phyllodes en lugar de fibroadenoma?"

Cuando capa2_diferencial_fibroadenoma_phyllodes sea true, introduce la segunda extensión:
"Bien. Segunda extensión. Paciente distinta: 52 años, dolor mamario y nódulo mal definido de aparición reciente. Sin antecedentes oncológicos. Esta es la muestra. ¿Qué diferencias ves respecto a la anterior?"

La segunda imagen proyectada muestra: extensión con abundantes neutrófilos, fondo sucio con detritus, histiocitos espumosos, escasa celularidad epitelial, sin atipia nuclear relevante. Compatible con mastitis o ectasia ductal.

Si describe diferencias generales sin criterio morfológico:
"¿Puedes concretar qué tipos celulares ves en el fondo de esta extensión que no estaban en la anterior?"

Si describe hallazgos pero no propone hipótesis:
"Con esos hallazgos, ¿qué tipo de proceso te sugiere?"

Si la hipótesis es vaga:
"¿Qué entidad concreta encaja con lo que describes?"

Para avanzar a Capa 3:
capa2_mioepiteliales_benignidad
capa2_diferencial_fibroadenoma_phyllodes
capa2_hallazgo_inflamatorio
capa2_hipotesis_no_tumoral

CAPA 3 — LÍMITES DEL DIAGNÓSTICO CITOLÓGICO

Pregunta de apertura cuando Capa 2 sea true:
"Tienes dos casos con diagnóstico de benignidad. ¿Puedes firmar los dos como benignos definitivos solo con la citología, o necesitas algo más?"

Si da limitaciones genéricas sin aplicarlas al caso:
"¿Qué prueba añadirías para el primer caso concreto, y qué aportaría que la citología no puede dar?"

Si no integra clínica e imagen:
"¿La citología sola es suficiente para que el ginecólogo tome una decisión, o hay que integrar otros elementos?"

Si menciona imagen o clínica pero no los tres elementos juntos:
"¿Cuáles son exactamente los tres elementos que se combinan en el abordaje diagnóstico estándar de un nódulo de mama?"

Para avanzar al cierre:
capa3_limitacion_diagnostico_benigno
capa3_triple_test_concepto

CIERRE

"Antes de terminar: de los dos casos de hoy, ¿cuál te ha parecido más difícil de razonar y por qué?"

Tras su respuesta:
"Rellena tu diario de sesión."

No añades nada más."""

# ── Default checklist state ───────────────────────────────────────────────────

DEFAULT_STATE = {
    "capa1_fibroadenoma_tipos_celulares": False,
    "capa1_fibroadenoma_diagnostico": False,
    "capa2_mioepiteliales_benignidad": False,
    "capa2_diferencial_fibroadenoma_phyllodes": False,
    "capa2_hallazgo_inflamatorio": False,
    "capa2_hipotesis_no_tumoral": False,
    "capa3_limitacion_diagnostico_benigno": False,
    "capa3_triple_test_concepto": False,
}

ITEM_LABELS = {
    "capa1_fibroadenoma_tipos_celulares":      "C1 — Tipos celulares (fibroadenoma)",
    "capa1_fibroadenoma_diagnostico":          "C1 — Diagnóstico fibroadenoma",
    "capa2_mioepiteliales_benignidad":         "C2 — Mioepiteliales como marcador",
    "capa2_diferencial_fibroadenoma_phyllodes":"C2 — Fibroadenoma vs Phyllodes",
    "capa2_hallazgo_inflamatorio":             "C2 — Hallazgos inflamatorios",
    "capa2_hipotesis_no_tumoral":              "C2 — Hipótesis no tumoral",
    "capa3_limitacion_diagnostico_benigno":    "C3 — Limitación diagnóstico citológico",
    "capa3_triple_test_concepto":              "C3 — Triple test integrado",
}

LAYERS = {
    "Capa 1 — Tumor benigno": [
        "capa1_fibroadenoma_tipos_celulares",
        "capa1_fibroadenoma_diagnostico",
    ],
    "Capa 2 — Diferencial y proceso inflamatorio": [
        "capa2_mioepiteliales_benignidad",
        "capa2_diferencial_fibroadenoma_phyllodes",
        "capa2_hallazgo_inflamatorio",
        "capa2_hipotesis_no_tumoral",
    ],
    "Capa 3 — Límites del diagnóstico": [
        "capa3_limitacion_diagnostico_benigno",
        "capa3_triple_test_concepto",
    ],
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_client():
    api_key = st.secrets.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
    if not api_key:
        st.error("⚠️ API key no configurada.")
        st.stop()
    return anthropic.Anthropic(api_key=api_key)


def call_judge(client, history, prev_state):
    history_text = "\n".join([
        f"{'TUTOR' if m['role'] == 'assistant' else 'ESTUDIANTE'}: {m['content']}"
        for m in history
    ])
    user_msg = (
        f"Estado previo:\n{json.dumps(prev_state, ensure_ascii=False)}\n\n"
        f"Historial completo:\n{history_text}"
    )
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        system=JUDGE_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = re.sub(r"```json|```", "", response.content[0].text.strip()).strip()
    new_state = json.loads(raw)
    for k in prev_state:
        if prev_state[k] is True:
            new_state[k] = True
    return new_state


def call_tutor(client, history, state, prev_state=None):
    newly_true = (
        [k for k in state if state[k] and not (prev_state or {}).get(k)]
        if prev_state else []
    )
    state_block = (
        f"[ESTADO ACTUAL DE LA CHECKLIST]\n{json.dumps(state, ensure_ascii=False, indent=2)}\n"
        f"[ÍTEMS QUE HAN PASADO A TRUE EN ESTE TURNO: {newly_true if newly_true else 'ninguno'}]\n\n"
    )
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    if not messages:
        messages = [{"role": "user", "content": state_block + "Comienza la sesión."}]
    elif messages[-1]["role"] == "user":
        messages[-1]["content"] = state_block + messages[-1]["content"]
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=TUTOR_SYSTEM,
        messages=messages,
    )
    return response.content[0].text.strip()


def save_log(student_id, history, state_history):
    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"logs/{student_id}_{timestamp}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            {
                "student_id": student_id,
                "timestamp": timestamp,
                "session": "mama_s2",
                "conversation": history,
                "state_history": state_history,
                "final_state": state_history[-1] if state_history else DEFAULT_STATE,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


# ── Session state init ────────────────────────────────────────────────────────

for key, val in [
    ("mode", "select"),
    ("history", []),
    ("state", dict(DEFAULT_STATE)),
    ("state_history", []),
    ("student_id", ""),
    ("initialized", False),
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
.dot-true  { width: 10px; height: 10px; border-radius: 50%; background: #2ecc71; flex-shrink: 0; }
.dot-false { width: 10px; height: 10px; border-radius: 50%; background: #e0e0e0; flex-shrink: 0; }
.layer-title { font-weight: 500; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; color: #888; margin-top: 12px; margin-bottom: 4px; }
</style>
""", unsafe_allow_html=True)

# ── Mode selector ─────────────────────────────────────────────────────────────

if st.session_state.mode == "select":
    st.markdown("# 🔬 Citología de Mama")
    st.markdown("### Sesión 2 · Del extendido normal al primer diagnóstico diferencial")
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
    st.markdown("## 🔬 Tutor · Sesión 2 — Citología de Mama")
    client = get_client()

    if not st.session_state.initialized:
        opening = call_tutor(client, [], st.session_state.state)
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
            tutor_reply = call_tutor(
                client, st.session_state.history, new_state, prev_state=prev_state
            )
            st.session_state.history.append({"role": "assistant", "content": tutor_reply})
            save_log(
                st.session_state.student_id or "sin_id",
                st.session_state.history,
                st.session_state.state_history,
            )
        st.rerun()

    st.divider()
    if st.button("← Volver"):
        for k, v in [
            ("mode", "select"),
            ("history", []),
            ("state", dict(DEFAULT_STATE)),
            ("state_history", []),
            ("initialized", False),
        ]:
            st.session_state[k] = v
        st.rerun()

# ── Teacher view ──────────────────────────────────────────────────────────────

elif st.session_state.mode == "teacher":
    st.markdown("## 👩‍🏫 Panel de Profesora · Sesión 2")
    teacher_pass = st.secrets.get("TEACHER_PASSWORD", "citologia2024")
    if "teacher_auth" not in st.session_state:
        st.session_state.teacher_auth = False

    if not st.session_state.teacher_auth:
        pwd = st.text_input("Contraseña", type="password")
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
        st.info("Sin sesiones registradas.")
    else:
        files = sorted(os.listdir(log_dir), reverse=True)
        selected = st.selectbox("Sesión", files)
        if selected:
            with open(os.path.join(log_dir, selected), "r", encoding="utf-8") as f:
                data = json.load(f)
            col1, col2 = st.columns([2, 1])
            with col1:
                st.markdown(
                    f"### 💬 {data.get('student_id', '?')} · {data.get('timestamp', '')}"
                )
                for i, msg in enumerate(data["conversation"]):
                    role = "🤖 Tutor" if msg["role"] == "assistant" else "👩‍🎓 Alumna"
                    with st.expander(f"**{role}** — turno {i+1}", expanded=True):
                        st.write(msg["content"])
                        if msg["role"] == "user" and i < len(data["state_history"]):
                            prev = (
                                data["state_history"][i - 1] if i > 0 else DEFAULT_STATE
                            )
                            new_items = [
                                k
                                for k in data["state_history"][i]
                                if data["state_history"][i][k] and not prev.get(k)
                            ]
                            if new_items:
                                st.success(
                                    "✅ " + ", ".join(ITEM_LABELS[k] for k in new_items)
                                )
            with col2:
                st.markdown("### 📊 Progreso final")
                final = data.get("final_state", DEFAULT_STATE)
                done = sum(1 for v in final.values() if v)
                st.progress(done / len(final))
                st.markdown(f"**{done}/{len(final)} ítems**")
                st.divider()
                for layer, items in LAYERS.items():
                    st.markdown(
                        f'<div class="layer-title">{layer}</div>',
                        unsafe_allow_html=True,
                    )
                    for item in items:
                        dot = "dot-true" if final.get(item) else "dot-false"
                        st.markdown(
                            f'<div class="progress-item"><div class="{dot}"></div>'
                            f"{ITEM_LABELS[item]}</div>",
                            unsafe_allow_html=True,
                        )
                if data["state_history"]:
                    import pandas as pd
                    st.divider()
                    df = pd.DataFrame([
                        {"Turno": i + 1, "Ítems": sum(1 for v in s.values() if v)}
                        for i, s in enumerate(data["state_history"])
                    ])
                    st.line_chart(df.set_index("Turno"))

    st.divider()
    if st.button("← Volver"):
        st.session_state.mode = "select"
        st.session_state.teacher_auth = False
        st.rerun()
