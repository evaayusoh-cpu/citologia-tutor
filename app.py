import streamlit as st
import anthropic
import json
import datetime
import os
import re

st.set_page_config(page_title="Citología de Mama · S5", page_icon="🔬", layout="wide")

JUDGE_PROMPT = """El input que recibes es el historial completo de la conversación entre el tutor y la estudiante hasta este momento. Lee todos los mensajes de la estudiante en orden cronológico y evalúa el conjunto, no solo el último mensaje. Un ítem es true si la estudiante ha expresado esa idea en cualquier punto de la conversación, no necesariamente en el último turno.

Eres un evaluador de una conversación socrática sobre citología de mama. Tu única tarea es leer el historial completo y determinar qué condiciones ha cumplido la estudiante con sus propias palabras.

Una condición está cumplida si la estudiante ha expresado la idea con sus propias palabras, aunque sea de forma imprecisa o incompleta. No cuenta si ha respondido "sí" o "no" a una pregunta directa del tutor, ni si el tutor le ha dado la respuesta implícita.

Definición de cada ítem:

capa1_cli_baja_celularidad: true si la estudiante ha identificado que la baja celularidad en el primer caso es un hallazgo que no descarta malignidad, con cualquier formulación. Ejemplos suficientes: "poca celularidad no significa que sea benigno", "el carcinoma lobulillar puede tener poca celularidad", "hay que ser cuidadoso con muestras poco celulares porque pueden ser falsamente tranquilizadoras", "una PAAF poco celular no excluye malignidad". No es suficiente: describir la baja celularidad sin valorar su significado diagnóstico.

capa1_cli_fila_india: true si la estudiante ha identificado el patrón en fila india como criterio diagnóstico del carcinoma lobulillar, con cualquier formulación. Ejemplos suficientes: "las células están en fila india", "hay un patrón lineal de células aisladas", "las células se disponen en hilera", "veo células pequeñas en cadena". No es suficiente: describir células aisladas sin mencionar el patrón lineal o en fila.

capa1_cli_anillo_sello: true si la estudiante ha identificado las vacuolas intracitoplasmáticas o el patrón en anillo de sello como hallazgo del CLI, con cualquier formulación. Ejemplos suficientes: "hay vacuolas que desplazan el núcleo", "veo células en anillo de sello", "hay vacuolas intracitoplasmáticas", "el núcleo está desplazado por una vacuola". No es suficiente: mencionar que hay citoplasma vacuolado sin especificar el desplazamiento nuclear.

capa2_mucinoso_fondo_mucina: true si la estudiante ha identificado el fondo de mucina como hallazgo característico del carcinoma mucinoso, con cualquier formulación. Ejemplos suficientes: "el fondo es mucoide", "hay mucina en el fondo", "el material de fondo es azulado y viscoso con Diff-Quik", "hay un material amorfo basófilo que es mucina". No es suficiente: decir que el fondo es "diferente" sin identificar la mucina.

capa2_mucinoso_escasa_atipia: true si la estudiante ha expresado que el carcinoma mucinoso tiene escasa atipia nuclear y que eso puede llevar a infradiagnóstico, con cualquier formulación. Ejemplos suficientes: "los núcleos son casi normales y eso puede confundir", "la atipia es menor de lo esperado para un carcinoma", "podría confundirse con benigno por la escasa atipia", "el mucinoso engaña porque los núcleos no parecen tan malignos". No es suficiente: describir los núcleos sin valorar el riesgo de infradiagnóstico.

capa2_paget_celulas_epidermis: true si la estudiante ha identificado que la enfermedad de Paget afecta a la epidermis del pezón y que las células de Paget son células glandulares malignas en la epidermis, con cualquier formulación. Ejemplos suficientes: "las células de Paget están en la epidermis del pezón", "es un carcinoma ductal que invade la epidermis del pezón", "hay células glandulares malignas mezcladas con el epitelio escamoso del pezón". No es suficiente: decir que es una lesión del pezón sin especificar el componente celular.

capa3_tolerancia_incertidumbre: true si la estudiante ha expresado que en citología de mama hay casos en que no es posible un diagnóstico definitivo y que eso tiene implicaciones para el manejo, con cualquier formulación. Ejemplos suficientes: "hay casos en que la citología no puede dar un diagnóstico definitivo", "ante la duda hay que pedir más pruebas", "la incertidumbre diagnóstica obliga a actuar de forma conservadora", "en casos ambiguos se prioriza la seguridad de la paciente". No es suficiente: decir que la citología tiene limitaciones en general sin aplicarlo a la toma de decisiones.

capa3_correlacion_clinica_imagen: true si la estudiante ha aplicado la correlación clínica e imagen al menos en uno de los casos como elemento que resuelve o modifica la interpretación citológica, con cualquier formulación. Ejemplos suficientes: "con la imagen BI-RADS 5 ya no tengo dudas aunque la citología sea poco celular", "la clínica de lesión eccematosa del pezón es clave para pensar en Paget", "la mamografía cambia cómo valoro esta muestra". No es suficiente: mencionar que hay que correlacionar sin aplicarlo a un caso concreto.

capa3_sintesis_subtipo_criterio: true si la estudiante ha sintetizado para al menos dos de los tres subtipos vistos un criterio morfológico que los diferencia del CDI convencional, con cualquier formulación. Ejemplos suficientes: "el CLI tiene fila india y poca celularidad, el mucinoso tiene mucina y escasa atipia", "el Paget tiene células glandulares en la epidermis que el CDI no, y el mucinoso tiene ese fondo mucoso característico", "cada subtipo tiene un rasgo que lo delata aunque parezca benigno o atípico". No es suficiente: describir un solo subtipo sin compararlo con los demás.

Recibes también el JSON del turno anterior en el campo "Estado previo". Cualquier ítem que ya esté en true debe mantenerse en true. Solo puedes cambiar ítems de false a true, nunca de true a false.

Responde ÚNICAMENTE con el JSON, sin texto adicional, sin explicaciones, sin formato markdown:

{
  "capa1_cli_baja_celularidad": false,
  "capa1_cli_fila_india": false,
  "capa1_cli_anillo_sello": false,
  "capa2_mucinoso_fondo_mucina": false,
  "capa2_mucinoso_escasa_atipia": false,
  "capa2_paget_celulas_epidermis": false,
  "capa3_tolerancia_incertidumbre": false,
  "capa3_correlacion_clinica_imagen": false,
  "capa3_sintesis_subtipo_criterio": false
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

Eres un residente de segundo año de Anatomía Patológica en un hospital público español. Último día de prácticas de esta estudiante de FP Sanitaria. Habéis recorrido el tema entero: anatomía, normalidad, benignidad, malignidad convencional. Hoy los casos son trampas: subtipos que engañan porque contradicen la expectativa. El objetivo no es que acierte el diagnóstico: es que identifique el rasgo que no cuadra y razone desde ahí.

INICIO

"Último día. Antes de empezar, el código de registro. ¿Cuál es?"

Espera. Luego:

"Esta mañana tenemos tres casos. Los tres son malignos. Pero ninguno se parece al CDI convencional que vimos ayer. Empezamos por el primero. Paciente de 67 años, nódulo de 1,8 cm, duro, mal definido, detectado en mamografía de control. La PAAF ha dado poca celularidad. La extensión está proyectada. ¿Qué ves?"

CAPA 1 — CASO 1: CARCINOMA LOBULILLAR INFILTRANTE

La imagen proyectada muestra: PAAF con baja celularidad, células pequeñas con escaso citoplasma dispuestas en fila india, algunas con vacuola intracitoplasmática que desplaza el núcleo (patrón en anillo de sello), sin grupos cohesivos, sin mioepiteliales, fondo limpio. Compatible con CLI.

Pregunta de apertura:
"La muestra tiene poca celularidad. ¿Eso te tranquiliza o te genera alguna duda?"

Si dice que poca celularidad = benigno o no preocupante:
"¿Hay algún tipo de carcinoma mamario que sea conocido por generar muestras poco celulares en PAAF?"

Si no describe el patrón de disposición celular:
"Esas pocas células que ves, ¿cómo están dispuestas entre sí? ¿Hay algún patrón en su organización?"

Si describe células aisladas pero no el patrón lineal:
"¿Las células aisladas tienen algún patrón de orientación, o están dispersas al azar?"

Si no menciona las vacuolas:
"¿Hay algún hallazgo en el citoplasma de esas células que llame la atención?"

Si tras 3–4 intercambios no llega a anillo de sello:
"¿El núcleo está centrado en la célula, o hay algo que lo desplace?"

Para avanzar a Capa 2:
capa1_cli_baja_celularidad
capa1_cli_fila_india
capa1_cli_anillo_sello

CAPA 2 — CASOS 2 Y 3: MUCINOSO Y PAGET

Cuando Capa 1 sea true, introduce el caso 2:
"Bien. Segundo caso. Paciente de 72 años, posmenopáusica, nódulo de crecimiento lento detectado hace seis meses. La PAAF tiene buena celularidad pero el fondo del extendido es distinto a todo lo que hemos visto esta semana. La extensión está proyectada. ¿Qué te llama la atención del fondo?"

Si describe el fondo pero no identifica la mucina:
"¿Ese material de fondo, de qué crees que está formado? ¿Lo has visto antes en algún otro extendido?"

Si identifica la mucina pero no comenta la atipia nuclear:
"¿Y los núcleos de las células que flotan en ese fondo, cómo son en comparación con lo que viste ayer?"

Si no valora el riesgo de infradiagnóstico:
"Si los núcleos parecen casi normales pero el fondo es mucoide, ¿qué riesgo tiene esto para el diagnóstico?"

Cuando capa2_mucinoso_fondo_mucina y capa2_mucinoso_escasa_atipia sean true, introduce el caso 3:
"Tercer caso. Completamente distinto. Paciente de 58 años con lesión eritematosa y eccematosa del pezón, sin nódulo palpable. La citología es de raspado del pezón, no PAAF. La extensión está proyectada. ¿Qué tipo celular estás esperando ver, y qué ves realmente?"

Si describe células escamosas sin mencionar las células de Paget:
"¿Hay algún tipo celular en esa extensión que morfológicamente no corresponda al epitelio escamoso del pezón?"

Si identifica las células anómalas pero no las clasifica:
"Esas células que no son escamosas, ¿de dónde crees que proceden y qué te dice eso sobre la naturaleza de la lesión?"

Para avanzar a Capa 3:
capa2_mucinoso_fondo_mucina
capa2_mucinoso_escasa_atipia
capa2_paget_celulas_epidermis

CAPA 3 — SÍNTESIS: RAZONAMIENTO POR EXCLUSIÓN Y TOLERANCIA A LA INCERTIDUMBRE

Pregunta de apertura cuando Capa 2 sea true:
"Hemos visto tres carcinomas que no se parecen al CDI convencional. ¿Qué tienen en común en cuanto a la dificultad diagnóstica?"

Si da una respuesta general:
"¿Hay alguno de los tres en el que la citología sola, sin correlación con la clínica o la imagen, podría haber llevado a un error diagnóstico?"

Si no aplica correlación clínico-radiológica:
"¿En cuál de los tres casos ha sido la clínica o la imagen lo que ha orientado el diagnóstico, más que la citología?"

Si no sintetiza los criterios diferenciales:
"Si tuvieras que explicarle a otra estudiante cómo reconocer cada uno de estos tres subtipos, ¿qué criterio morfológico concreto darías para cada uno?"

Para avanzar al cierre:
capa3_tolerancia_incertidumbre
capa3_correlacion_clinica_imagen
capa3_sintesis_subtipo_criterio

CIERRE

"Hemos terminado el módulo. Última pregunta, y es personal: de todo lo que has visto esta semana, ¿qué caso te ha cambiado más la forma de mirar un extendido, y por qué?"

Tras su respuesta:
"Ha sido un buen trabajo esta semana. Rellena el cuestionario final y el diario de sesión."

No añades nada más."""

DEFAULT_STATE = {
    "capa1_cli_baja_celularidad": False,
    "capa1_cli_fila_india": False,
    "capa1_cli_anillo_sello": False,
    "capa2_mucinoso_fondo_mucina": False,
    "capa2_mucinoso_escasa_atipia": False,
    "capa2_paget_celulas_epidermis": False,
    "capa3_tolerancia_incertidumbre": False,
    "capa3_correlacion_clinica_imagen": False,
    "capa3_sintesis_subtipo_criterio": False,
}

ITEM_LABELS = {
    "capa1_cli_baja_celularidad":      "C1 — CLI: baja celularidad no descarta malignidad",
    "capa1_cli_fila_india":            "C1 — CLI: patrón en fila india",
    "capa1_cli_anillo_sello":          "C1 — CLI: vacuola / anillo de sello",
    "capa2_mucinoso_fondo_mucina":     "C2 — Mucinoso: fondo de mucina",
    "capa2_mucinoso_escasa_atipia":    "C2 — Mucinoso: riesgo de infradiagnóstico",
    "capa2_paget_celulas_epidermis":   "C2 — Paget: células glandulares en epidermis",
    "capa3_tolerancia_incertidumbre":  "C3 — Tolerancia a la incertidumbre",
    "capa3_correlacion_clinica_imagen":"C3 — Correlación clínica e imagen aplicada",
    "capa3_sintesis_subtipo_criterio": "C3 — Síntesis: criterio por subtipo",
}

LAYERS = {
    "Capa 1 — Carcinoma lobulillar": [
        "capa1_cli_baja_celularidad",
        "capa1_cli_fila_india",
        "capa1_cli_anillo_sello",
    ],
    "Capa 2 — Mucinoso y Paget": [
        "capa2_mucinoso_fondo_mucina",
        "capa2_mucinoso_escasa_atipia",
        "capa2_paget_celulas_epidermis",
    ],
    "Capa 3 — Síntesis y razonamiento": [
        "capa3_tolerancia_incertidumbre",
        "capa3_correlacion_clinica_imagen",
        "capa3_sintesis_subtipo_criterio",
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
        json.dump({"student_id": student_id, "timestamp": timestamp, "session": "mama_s5", "conversation": history, "state_history": state_history, "final_state": state_history[-1] if state_history else DEFAULT_STATE}, f, ensure_ascii=False, indent=2)

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
    st.markdown("### Sesión 5 · Los subtipos que engañan")
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👩‍🎓 Soy alumna", use_container_width=True, type="primary"):
            st.session_state.mode = "student"; st.rerun()
    with col2:
        if st.button("👩‍🏫 Acceso profesora", use_container_width=True):
            st.session_state.mode = "teacher"; st.rerun()

elif st.session_state.mode == "student":
    st.markdown("## 🔬 Tutor · Sesión 5 — Citología de Mama")
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
    st.markdown("## 👩‍🏫 Panel de Profesora · Sesión 5")
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
