import streamlit as st
import anthropic
import json
import datetime
import os
import re

st.set_page_config(page_title="Citología de Mama · S4", page_icon="🔬", layout="wide")

JUDGE_PROMPT = """El input que recibes es el historial completo de la conversación entre el tutor y la estudiante hasta este momento. Lee todos los mensajes de la estudiante en orden cronológico y evalúa el conjunto, no solo el último mensaje. Un ítem es true si la estudiante ha expresado esa idea en cualquier punto de la conversación, no necesariamente en el último turno.

Eres un evaluador de una conversación socrática sobre citología de mama. Tu única tarea es leer el historial completo y determinar qué condiciones ha cumplido la estudiante con sus propias palabras.

Una condición está cumplida si la estudiante ha expresado la idea con sus propias palabras, aunque sea de forma imprecisa o incompleta. No cuenta si ha respondido "sí" o "no" a una pregunta directa del tutor, ni si el tutor le ha dado la respuesta implícita.

Definición de cada ítem:

capa1_criterio_malignidad_nuclear: true si la estudiante ha descrito al menos dos criterios nucleares de malignidad presentes en la extensión, con cualquier formulación. Ejemplos suficientes: "hay pleomorfismo nuclear e hipercromasia", "los núcleos son grandes e irregulares con nucleolo prominente", "hay pérdida de la relación N/C y cromatina irregular". No es suficiente: decir "hay atipia" o "los núcleos son raros" sin dos criterios concretos.

capa1_perdida_cohesion: true si la estudiante ha identificado la pérdida de cohesión celular o las células aisladas como hallazgo relevante para malignidad, con cualquier formulación. Ejemplos suficientes: "hay células aisladas que no forman grupos", "hay pérdida de cohesión", "las células están disgregadas", "hay células sueltas con atipia". No es suficiente: describir los grupos celulares sin mencionar las células aisladas o la pérdida de cohesión.

capa1_ausencia_mioepiteliales: true si la estudiante ha mencionado la ausencia de células mioepiteliales como criterio de malignidad, con cualquier formulación. Ejemplos suficientes: "no hay mioepiteliales y eso me preocupa", "la ausencia de mioepiteliales apunta a malignidad", "no veo núcleos desnudos estromales", "falta la capa mioepitelial". No es suficiente: no mencionar las mioepiteliales.

capa2_graduacion_nuclear_aplicada: true si la estudiante ha aplicado al menos dos parámetros de la tabla de graduación nuclear al caso concreto, con cualquier formulación. Ejemplos suficientes: "el tamaño nuclear es mayor de cinco veces el eritrocito, lo que da grado 3", "el nucleolo es muy evidente y la membrana nuclear es irregular, eso sería grado 3", "la morfología es muy pleomorfa y la cromatina irregular, grado alto". No es suficiente: mencionar que existe la graduación sin aplicar parámetros concretos al caso.

capa2_grado_nuclear_justificado: true si la estudiante ha propuesto un grado nuclear (1, 2 o 3) Y lo ha justificado con al menos dos parámetros morfológicos del caso, con cualquier formulación. Ejemplos suficientes: "diría grado 3 porque el pleomorfismo es marcado y los nucleolos son muy evidentes", "es grado nuclear alto por la irregularidad de la membrana y el tamaño nuclear extremo". No es suficiente: proponer un grado sin justificación o con un solo parámetro.

capa2_cdis_vs_cdi_concepto: true si la estudiante ha expresado la diferencia entre carcinoma in situ e infiltrante en términos de membrana basal o invasión del estroma, con cualquier formulación. Ejemplos suficientes: "en el in situ no hay invasión del estroma", "la diferencia es si la membrana basal está rota o no", "el infiltrante traspasa la membrana basal y el in situ no", "en el CDIS las células están dentro del conducto sin invadir". No es suficiente: nombrar los dos tipos sin explicar la diferencia.

capa3_limitacion_citologia_invasion: true si la estudiante ha expresado que la citología no puede determinar si hay invasión del estroma, con cualquier formulación. Ejemplos suficientes: "con la citología no puedo saber si es in situ o infiltrante", "para ver la membrana basal necesito histología", "la PAAF no distingue in situ de infiltrante", "el diagnóstico de invasión es histológico". No es suficiente: decir que la PAAF tiene limitaciones sin aplicarlo específicamente a la invasión.

capa3_implicacion_pronostica: true si la estudiante ha relacionado el grado nuclear o el tipo de carcinoma con alguna implicación pronóstica o de manejo, con cualquier formulación. Ejemplos suficientes: "un grado 3 tiene peor pronóstico", "el CDI grado alto requiere tratamiento más agresivo", "el grado nuclear influye en el tipo de tratamiento", "un carcinoma de grado 3 es más agresivo que uno de grado 1". No es suficiente: nombrar el grado sin relacionarlo con pronóstico o manejo.

capa3_informe_completo_maligno: true si la estudiante ha valorado qué debe contener un informe citológico de sospecha de malignidad para que sea clínicamente útil, con cualquier formulación. Ejemplos suficientes: "hay que incluir el grado nuclear", "el informe debe especificar los criterios morfológicos que sustentan la sospecha", "hay que indicar qué prueba complementaria se necesita", "debe quedar claro que es sospecha, no diagnóstico definitivo, y por qué". No es suficiente: decir que el informe debe ser completo sin especificar qué debe incluir en un caso de malignidad.

Recibes también el JSON del turno anterior en el campo "Estado previo". Cualquier ítem que ya esté en true debe mantenerse en true. Solo puedes cambiar ítems de false a true, nunca de true a false.

Responde ÚNICAMENTE con el JSON, sin texto adicional, sin explicaciones, sin formato markdown:

{
  "capa1_criterio_malignidad_nuclear": false,
  "capa1_perdida_cohesion": false,
  "capa1_ausencia_mioepiteliales": false,
  "capa2_graduacion_nuclear_aplicada": false,
  "capa2_grado_nuclear_justificado": false,
  "capa2_cdis_vs_cdi_concepto": false,
  "capa3_limitacion_citologia_invasion": false,
  "capa3_implicacion_pronostica": false,
  "capa3_informe_completo_maligno": false
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

Eres un residente de segundo año de Anatomía Patológica en un hospital público español. Cuarto día de prácticas de esta estudiante de FP Sanitaria. Hasta ahora habéis visto normalidad y patología benigna. Hoy cruzáis el umbral de la malignidad. El caso tiene hallazgos morfológicos que generan sospecha pero no permiten certeza total: esa ambigüedad es la fricción del día.

INICIO

"Código de registro. ¿Cuál es?"

Espera. Luego:

"Cuarto día. Esta mañana ha llegado un caso que no voy a presentarte igual que los anteriores. Solo te digo esto: paciente de 61 años, nódulo de 2,5 cm, consistencia dura, detectado en mamografía de cribado. La extensión está proyectada. Necesito que me hagas un pre-informe antes de que llegue el adjunto. Empieza por los hallazgos morfológicos."

CAPA 1 — IDENTIFICACIÓN DE CRITERIOS DE MALIGNIDAD

La imagen proyectada muestra: PAAF con alta celularidad, células en grupos tridimensionales con pérdida de cohesión y células aisladas, pleomorfismo nuclear marcado, hipercromasia, nucleolos prominentes, relación N/C muy aumentada, ausencia de células mioepiteliales, fondo con escasa necrosis. Compatible con CDI de grado nuclear alto.

Pregunta de apertura:
"Tienes la extensión delante. Descríbeme los hallazgos nucleares primero."

Si describe solo un criterio nuclear:
"¿Hay algún otro criterio nuclear que no hayas mencionado todavía?"

Si describe los núcleos pero no menciona las células aisladas:
"¿La arquitectura celular, cómo es? ¿Las células forman grupos cohesivos o hay alguna otra disposición?"

Si no menciona las mioepiteliales:
"Has descrito el componente epitelial. ¿Hay algún tipo celular que esperarías ver en una lesión benigna y que no está aquí?"

Si tras 3–4 intercambios no llega a mioepiteliales:
"Recuerda lo que hemos visto sobre los marcadores de benignidad en citología de mama. ¿Falta alguno en esta extensión?"

Para avanzar a Capa 2:
capa1_criterio_malignidad_nuclear
capa1_perdida_cohesion
capa1_ausencia_mioepiteliales

CAPA 2 — GRADUACIÓN NUCLEAR Y TIPO DE CARCINOMA

Pregunta de apertura cuando Capa 1 sea true:
"Con los criterios que has descrito, ¿puedes aplicar la tabla de graduación nuclear? ¿Qué parámetros usarías y qué grado te dan?"

Si nombra el grado sin justificarlo con parámetros:
"¿Qué parámetros concretos de la tabla te llevan a ese grado? Necesito al menos dos."

Si aplica parámetros pero no justifica el grado:
"¿Qué grado nuclear asignarías con esos parámetros, y por qué no el grado inmediatamente inferior?"

Cuando capa2_grado_nuclear_justificado sea true, introduce la pregunta sobre in situ vs infiltrante:
"Este extendido tiene alta sospecha de malignidad. Ahora una pregunta distinta: ¿puedes decirme con esta muestra si el carcinoma es in situ o infiltrante?"

Si responde directamente sin razonar la diferencia:
"¿Qué distingue morfológicamente un carcinoma in situ de uno infiltrante, y cómo lo verías en citología?"

Para avanzar a Capa 3:
capa2_graduacion_nuclear_aplicada
capa2_grado_nuclear_justificado
capa2_cdis_vs_cdi_concepto

CAPA 3 — IMPLICACIONES CLÍNICAS Y LÍMITES DEL INFORME

Pregunta de apertura cuando Capa 2 sea true:
"Has dicho que no puedes distinguir in situ de infiltrante con la citología. ¿Eso tiene consecuencias para el informe que vas a emitir?"

Si no relaciona el grado con pronóstico:
"El grado nuclear que has asignado, ¿tiene alguna implicación para el pronóstico o el manejo de esta paciente?"

Si no aborda el contenido del informe de malignidad:
"¿Qué debe incluir un informe de sospecha de malignidad para que el ginecólogo y el cirujano puedan actuar correctamente con él?"

Si el contenido del informe es vago:
"¿Hay algún dato que hayas valorado hoy y que no deberías omitir en el informe aunque genere incertidumbre?"

Para avanzar al cierre:
capa3_limitacion_citologia_invasion
capa3_implicacion_pronostica
capa3_informe_completo_maligno

CIERRE

"Última pregunta antes del diario: esta mañana, cuando has visto esa extensión por primera vez, ¿qué ha sido lo primero que te ha generado sospecha y por qué?"

Tras su respuesta:
"Rellena tu diario de sesión."

No añades nada más."""

DEFAULT_STATE = {
    "capa1_criterio_malignidad_nuclear": False,
    "capa1_perdida_cohesion": False,
    "capa1_ausencia_mioepiteliales": False,
    "capa2_graduacion_nuclear_aplicada": False,
    "capa2_grado_nuclear_justificado": False,
    "capa2_cdis_vs_cdi_concepto": False,
    "capa3_limitacion_citologia_invasion": False,
    "capa3_implicacion_pronostica": False,
    "capa3_informe_completo_maligno": False,
}

ITEM_LABELS = {
    "capa1_criterio_malignidad_nuclear":  "C1 — Criterios nucleares de malignidad",
    "capa1_perdida_cohesion":             "C1 — Pérdida de cohesión",
    "capa1_ausencia_mioepiteliales":      "C1 — Ausencia de mioepiteliales",
    "capa2_graduacion_nuclear_aplicada":  "C2 — Graduación nuclear aplicada",
    "capa2_grado_nuclear_justificado":    "C2 — Grado nuclear justificado",
    "capa2_cdis_vs_cdi_concepto":         "C2 — CDIS vs CDI: concepto",
    "capa3_limitacion_citologia_invasion":"C3 — Limitación: invasión no visible",
    "capa3_implicacion_pronostica":       "C3 — Implicación pronóstica",
    "capa3_informe_completo_maligno":     "C3 — Contenido del informe maligno",
}

LAYERS = {
    "Capa 1 — Criterios de malignidad": [
        "capa1_criterio_malignidad_nuclear",
        "capa1_perdida_cohesion",
        "capa1_ausencia_mioepiteliales",
    ],
    "Capa 2 — Graduación y tipo": [
        "capa2_graduacion_nuclear_aplicada",
        "capa2_grado_nuclear_justificado",
        "capa2_cdis_vs_cdi_concepto",
    ],
    "Capa 3 — Implicaciones clínicas": [
        "capa3_limitacion_citologia_invasion",
        "capa3_implicacion_pronostica",
        "capa3_informe_completo_maligno",
    ],
}

def get_client():
    api_key = st.secrets.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
    if not api_key:
        st.error("⚠️ API key no configurada.")
        st.stop()
    return anthropic.Anthropic(api_key=api_key)

def call_judge(client, history, prev_state):
    history_text = "\n".join([f"{'TUTOR' if m['role']=='assistant' else 'ESTUDIANTE'}: {m['content']}" for m in history])
    user_msg = f"Estado previo:\n{json.dumps(prev_state, ensure_ascii=False)}\n\nHistorial completo:\n{history_text}"
    response = client.messages.create(model="claude-sonnet-4-5", max_tokens=500, system=JUDGE_PROMPT, messages=[{"role": "user", "content": user_msg}])
    raw = re.sub(r"```json|```", "", response.content[0].text.strip()).strip()
    new_state = json.loads(raw)
    for k in prev_state:
        if prev_state[k] is True:
            new_state[k] = True
    return new_state

def call_tutor(client, history, state, prev_state=None):
    newly_true = [k for k in state if state[k] and not (prev_state or {}).get(k)] if prev_state else []
    state_block = f"[ESTADO ACTUAL DE LA CHECKLIST]\n{json.dumps(state, ensure_ascii=False, indent=2)}\n[ÍTEMS QUE HAN PASADO A TRUE EN ESTE TURNO: {newly_true if newly_true else 'ninguno'}]\n\n"
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    if not messages:
        messages = [{"role": "user", "content": state_block + "Comienza la sesión."}]
    elif messages[-1]["role"] == "user":
        messages[-1]["content"] = state_block + messages[-1]["content"]
    response = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=400, system=TUTOR_SYSTEM, messages=messages)
    return response.content[0].text.strip()

def save_log(student_id, history, state_history):
    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"logs/{student_id}_{timestamp}.json", "w", encoding="utf-8") as f:
        json.dump({"student_id": student_id, "timestamp": timestamp, "session": "mama_s4", "conversation": history, "state_history": state_history, "final_state": state_history[-1] if state_history else DEFAULT_STATE}, f, ensure_ascii=False, indent=2)

for key, val in [("mode","select"),("history",[]),("state",dict(DEFAULT_STATE)),("state_history",[]),("student_id",""),("initialized",False)]:
    if key not in st.session_state:
        st.session_state[key] = val

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'DM Serif Display', serif; }
.stChatMessage { border-radius: 12px; margin-bottom: 8px; }
.progress-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 0.85rem; }
.dot-true { width: 10px; height: 10px; border-radius: 50%; background: #2ecc71; flex-shrink: 0; }
.dot-false { width: 10px; height: 10px; border-radius: 50%; background: #e0e0e0; flex-shrink: 0; }
.layer-title { font-weight: 500; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; color: #888; margin-top: 12px; margin-bottom: 4px; }
</style>""", unsafe_allow_html=True)

if st.session_state.mode == "select":
    st.markdown("# 🔬 Citología de Mama")
    st.markdown("### Sesión 4 · El umbral de la malignidad")
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👩‍🎓 Soy alumna", use_container_width=True, type="primary"):
            st.session_state.mode = "student"; st.rerun()
    with col2:
        if st.button("👩‍🏫 Acceso profesora", use_container_width=True):
            st.session_state.mode = "teacher"; st.rerun()

elif st.session_state.mode == "student":
    st.markdown("## 🔬 Tutor · Sesión 4 — Citología de Mama")
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
            tutor_reply = call_tutor(client, st.session_state.history, new_state, prev_state=prev_state)
            st.session_state.history.append({"role": "assistant", "content": tutor_reply})
            save_log(st.session_state.student_id or "sin_id", st.session_state.history, st.session_state.state_history)
        st.rerun()
    st.divider()
    if st.button("← Volver"):
        for k, v in [("mode","select"),("history",[]),("state",dict(DEFAULT_STATE)),("state_history",[]),("initialized",False)]:
            st.session_state[k] = v
        st.rerun()

elif st.session_state.mode == "teacher":
    st.markdown("## 👩‍🏫 Panel de Profesora · Sesión 4")
    teacher_pass = st.secrets.get("TEACHER_PASSWORD", "citologia2024")
    if "teacher_auth" not in st.session_state:
        st.session_state.teacher_auth = False
    if not st.session_state.teacher_auth:
        pwd = st.text_input("Contraseña", type="password")
        if st.button("Entrar"):
            if pwd == teacher_pass:
                st.session_state.teacher_auth = True; st.rerun()
            else:
                st.error("Contraseña incorrecta")
        if st.button("← Volver"):
            st.session_state.mode = "select"; st.rerun()
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
                st.markdown(f"### 💬 {data.get('student_id','?')} · {data.get('timestamp','')}")
                for i, msg in enumerate(data["conversation"]):
                    role = "🤖 Tutor" if msg["role"] == "assistant" else "👩‍🎓 Alumna"
                    with st.expander(f"**{role}** — turno {i+1}", expanded=True):
                        st.write(msg["content"])
                        if msg["role"] == "user" and i < len(data["state_history"]):
                            prev = data["state_history"][i-1] if i > 0 else DEFAULT_STATE
                            new_items = [k for k in data["state_history"][i] if data["state_history"][i][k] and not prev.get(k)]
                            if new_items:
                                st.success("✅ " + ", ".join(ITEM_LABELS[k] for k in new_items))
            with col2:
                st.markdown("### 📊 Progreso final")
                final = data.get("final_state", DEFAULT_STATE)
                done = sum(1 for v in final.values() if v)
                st.progress(done / len(final))
                st.markdown(f"**{done}/{len(final)} ítems**")
                st.divider()
                for layer, items in LAYERS.items():
                    st.markdown(f'<div class="layer-title">{layer}</div>', unsafe_allow_html=True)
                    for item in items:
                        dot = "dot-true" if final.get(item) else "dot-false"
                        st.markdown(f'<div class="progress-item"><div class="{dot}"></div>{ITEM_LABELS[item]}</div>', unsafe_allow_html=True)
                if data["state_history"]:
                    import pandas as pd
                    st.divider()
                    df = pd.DataFrame([{"Turno": i+1, "Ítems": sum(1 for v in s.values() if v)} for i, s in enumerate(data["state_history"])])
                    st.line_chart(df.set_index("Turno"))
    st.divider()
    if st.button("← Volver"):
        st.session_state.mode = "select"; st.session_state.teacher_auth = False; st.rerun()
