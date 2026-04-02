"""Fitness Tracker (multi-utente) — Track your gym progress."""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
from datetime import date

import database as db
import auth
import progression_engine as pe

# ─── Page config (must be the first Streamlit command) ────────────────────────

st.set_page_config(
    page_title="Fitness Tracker",
    page_icon="🏋️",
    layout="centered",
    initial_sidebar_state="auto",
)

# ─── Database init ────────────────────────────────────────────────────────────

# Initialize schema once per browser session to avoid running DDL on every rerun.
if not st.session_state.get("_db_initialized", False):
    db.init_db()
    st.session_state["_db_initialized"] = True

# ─── Authentication gate ─────────────────────────────────────────────────────

if not auth.show_auth_page():
    st.stop()

# From here on, user is authenticated
user_id = auth.get_current_user_id()
user_name = auth.get_current_user_name()

# Seed default exercises for new users
if st.session_state.get("_seeded_exercises_user_id") != user_id:
    db.seed_default_exercises_for_user(user_id)
    st.session_state["_seeded_exercises_user_id"] = user_id

# ─── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    }
    [data-testid="stSidebar"] * {
        color: #e0e0e0 !important;
    }
    [data-testid="stSidebar"] .stRadio label {
        font-size: 1.1rem;
        padding: 0.3rem 0;
    }

    /* Main content */
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }

    /* Cards / metric boxes */
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem 1.2rem;
        border-radius: 12px;
        color: white !important;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }
    [data-testid="stMetric"] label,
    [data-testid="stMetric"] [data-testid="stMetricValue"],
    [data-testid="stMetric"] [data-testid="stMetricDelta"] {
        color: white !important;
    }

    /* Primary buttons */
    button[kind="primary"] {
        min-height: 2.8rem;
        border-radius: 8px;
        font-weight: 600;
    }

    /* Expander headers */
    .streamlit-expanderHeader {
        font-weight: 600;
        font-size: 1rem;
    }

    /* Dataframes */
    [data-testid="stDataFrame"] {
        border-radius: 8px;
        overflow: hidden;
    }

    /* Header styling */
    h1 { color: #1a1a2e; }
    h2 { border-bottom: 3px solid #667eea; padding-bottom: 0.3rem; }

    /* ── Mobile Responsive ──────────────────────────── */
    @media (max-width: 768px) {
        /* Stack all column layouts vertically */
        [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap !important;
            gap: 0.2rem !important;
        }
        [data-testid="stHorizontalBlock"] > div {
            flex: 1 1 100% !important;
            min-width: 100% !important;
            width: 100% !important;
        }

        /* Tighter padding */
        .block-container {
            padding-left: 0.8rem !important;
            padding-right: 0.8rem !important;
            /* Keep first heading clear of Streamlit mobile top bar */
            padding-top: max(3.8rem, env(safe-area-inset-top)) !important;
            max-width: 100% !important;
        }

        /* Bigger touch targets */
        input[type="number"],
        input[type="text"],
        input[type="password"],
        textarea {
            font-size: 1.1rem !important;
            min-height: 2.8rem !important;
        }
        button {
            min-height: 3rem !important;
            font-size: 1rem !important;
        }

        /* Metric boxes spacing */
        [data-testid="stMetric"] {
            margin-bottom: 0.5rem !important;
        }

        /* Radio nav larger taps */
        [data-testid="stSidebar"] .stRadio label {
            font-size: 1.2rem !important;
            padding: 0.6rem 0 !important;
        }

        /* Headers smaller for mobile */
        h1 { font-size: 1.5rem !important; }
        h2 { font-size: 1.25rem !important; }

        /* Full width controls */
        [data-testid="stSelectbox"],
        [data-testid="stNumberInput"] {
            width: 100% !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# ─── Sidebar Navigation ─────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("# 🏋️ Fitness Tracker")
    st.markdown(
        f'<p style="color: #ffffff; font-size: 1.05rem; font-weight: 600;">'
        f'👤 {user_name} <span style="opacity: 0.85;">({st.session_state["username"]})</span></p>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    selected = st.radio(
        "Navigazione",
        ["🏋️  Registra allenamento", "📋  Storico", "📈  Progressi",
         "🚀  Progression Engine", "⚙️  Esercizi"],
        key="nav_page",
    )

    st.markdown("---")
    if st.button("🚪 Logout", use_container_width=True, type="primary"):
        auth.logout()
        st.rerun()
    st.markdown(
        '<p style="color: #ffffff; opacity: 0.7; font-size: 0.8rem; text-align: center;">'
        'Fitness Tracker v1.0</p>',
        unsafe_allow_html=True,
    )

# ─── Helper ──────────────────────────────────────────────────────────────────

def _exercises_select(key: str):
    """Render an exercise selector grouped by category."""
    exercises = db.get_all_exercises(user_id)
    if not exercises:
        st.warning("Nessun esercizio configurato. Vai alla sezione ⚙️ Esercizi.")
        return None, None
    options = {f"{e['name']}  ({e['category']})": e["id"] for e in exercises}
    label = st.selectbox("Esercizio", list(options.keys()), key=key)
    return options[label], label


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: LOG WORKOUT
# ═══════════════════════════════════════════════════════════════════════════════

if selected == "🏋️  Registra allenamento":
    st.header("🏋️ Registra allenamento")

    col_date, col_ex = st.columns([1, 2])
    with col_date:
        workout_date = st.date_input("📅 Data", value=date.today(), key="log_date")
    with col_ex:
        ex_id, ex_label = _exercises_select("log_exercise")

    if ex_id is not None:
        # ── Inline progression suggestion ──
        suggestion = pe.get_exercise_suggestion_for_workout(user_id, ex_id)
        if suggestion and suggestion.type != pe.SuggestionType.NO_DATA:
            label, style = pe.SUGGESTION_DISPLAY[suggestion.type]
            with st.container():
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #1a1a2e, #16213e);
                            padding: 1rem 1.2rem; border-radius: 10px;
                            border-left: 4px solid {'#4CAF50' if style == 'success' else '#FF9800' if style == 'warning' else '#2196F3'};
                            margin-bottom: 1rem; color: #e0e0e0;">
                    <strong>{label}</strong><br>
                    <span style="font-size: 0.95em;">{suggestion.reasoning}</span>
                    {f'<br><br>🎯 <strong>{suggestion.suggested_weight_kg:.1f} kg × {suggestion.suggested_reps_target} reps</strong>' if suggestion.suggested_weight_kg else ''}
                </div>""", unsafe_allow_html=True)

        # ── Rest timer ──
        with st.expander("⏱️ Timer recupero", expanded=False):
            components.html("""
            <div style="text-align:center;font-family:-apple-system,BlinkMacSystemFont,sans-serif;">
                <div id="td" style="font-size:3rem;font-weight:bold;color:#667eea;margin:0.3rem 0;
                                     font-variant-numeric:tabular-nums;">00:00</div>
                <div style="display:flex;gap:0.5rem;justify-content:center;flex-wrap:wrap;">
                    <button onclick="startT(60)" style="min-width:4.3rem;padding:0.65rem 0.9rem;border-radius:8px;border:none;
                        background:#667eea;color:white;font-size:1rem;font-weight:600;cursor:pointer;">1:00</button>
                    <button onclick="startT(90)" style="min-width:4.3rem;padding:0.65rem 0.9rem;border-radius:8px;border:none;
                        background:#667eea;color:white;font-size:1rem;font-weight:600;cursor:pointer;">1:30</button>
                    <button onclick="startT(120)" style="min-width:4.3rem;padding:0.65rem 0.9rem;border-radius:8px;border:none;
                        background:#667eea;color:white;font-size:1rem;font-weight:600;cursor:pointer;">2:00</button>
                    <button onclick="startT(180)" style="min-width:4.3rem;padding:0.65rem 0.9rem;border-radius:8px;border:none;
                        background:#764ba2;color:white;font-size:1rem;font-weight:600;cursor:pointer;">3:00</button>
                    <button onclick="resetT()" style="min-width:4.3rem;padding:0.65rem 0.9rem;border-radius:8px;border:none;
                        background:#e74c3c;color:white;font-size:1rem;font-weight:600;cursor:pointer;">⏹</button>
                </div>
            </div>
            <script>
            let iv,rm=0;
            function startT(s){clearInterval(iv);rm=s;upd();iv=setInterval(()=>{rm--;upd();
                if(rm<=0){clearInterval(iv);try{navigator.vibrate([200,100,200])}catch(e){}
                try{let ac=new(window.AudioContext||window.webkitAudioContext)();let o=ac.createOscillator();
                o.frequency.value=800;o.connect(ac.destination);o.start();setTimeout(()=>o.stop(),300);}catch(e){}
                document.getElementById('td').style.color='#4CAF50';}},1000);}
            function resetT(){clearInterval(iv);rm=0;upd();}
            function upd(){let m=Math.floor(rm/60),s=rm%60;let d=document.getElementById('td');
                d.textContent=String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
                d.style.color=rm<=5&&rm>0?'#e74c3c':'#667eea';}
            </script>
            """, height=190)

        st.markdown("---")
        st.subheader("Aggiungi serie")

        # Pre-fill weight from progression suggestion
        default_kg = round(suggestion.suggested_weight_kg, 1) if (suggestion and suggestion.suggested_weight_kg) else 0.0

        num_sets = st.number_input("Numero di serie", min_value=1,
                                   max_value=10, value=3, key="num_sets")

        with st.form("log_sets_form"):
            set_data = []
            for i in range(int(num_sets)):
                st.markdown(f"**Serie {i+1}**")
                c1, c2 = st.columns(2)
                w = c1.number_input("Kg", min_value=0.0, step=0.5, value=default_kg,
                                    key=f"w_{i}")
                r = c2.number_input("Reps", min_value=0, step=1, value=0,
                                    key=f"r_{i}")
                set_data.append((w, r))

            notes = st.text_area("📝 Note (opzionale)", key="log_notes",
                                 placeholder="Es: sentito fastidio alla spalla...")
            save_sets = st.form_submit_button("💾 Salva serie", type="primary", use_container_width=True)

        if save_sets:
            saved = 0
            for idx, (w, r) in enumerate(set_data, start=1):
                if r > 0 and w > 0:
                    db.log_set(user_id, ex_id, workout_date, idx, r, w, notes)
                    saved += 1
            if saved:
                st.success(f"✅ {saved} serie salvate per {ex_label}!")
                # Record outcome for the progression engine feedback loop
                saved_weights = [w for w, r in set_data if r > 0 and w > 0]
                saved_reps = [r for w, r in set_data if r > 0 and w > 0]
                if saved_weights:
                    pe.record_outcome_for_exercise(
                        user_id, ex_id,
                        actual_weight=max(saved_weights),
                        actual_avg_reps=sum(saved_reps) / len(saved_reps),
                        workout_date=workout_date,
                    )
                st.rerun()
            else:
                st.error("Inserisci almeno una serie con kg > 0 e reps > 0.")

    # -- Show today's logged exercises --
    today_logs = db.get_logs_for_date(user_id, workout_date)
    if today_logs:
        st.markdown("---")
        st.subheader(f"📋 Allenamento del {workout_date.strftime('%d/%m/%Y')}")
        df = pd.DataFrame(today_logs)
        display_df = df[["exercise_name", "set_number", "weight_kg", "reps", "notes"]].copy()
        display_df.columns = ["Esercizio", "Serie", "Kg", "Reps", "Note"]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Volume summary
        df["volume"] = df["weight_kg"] * df["reps"]
        summary = df.groupby("exercise_name").agg(
            Serie=("set_number", "count"),
            Volume_totale=("volume", "sum"),
            Peso_max=("weight_kg", "max"),
        ).reset_index()
        summary.columns = ["Esercizio", "Serie", "Volume totale (kg)", "Peso max (kg)"]

        st.markdown("#### Riepilogo sessione")
        m1, m2, m3 = st.columns(3)
        m1.metric("🏋️ Esercizi", len(summary))
        m2.metric("📊 Volume totale", f"{summary['Volume totale (kg)'].sum():.0f} kg")
        m3.metric("🔢 Serie totali", int(summary["Serie"].sum()))

        st.dataframe(summary, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: HISTORY
# ═══════════════════════════════════════════════════════════════════════════════

elif selected == "📋  Storico":
    st.header("📋 Storico allenamenti")

    dates = db.get_workout_dates(user_id)
    if not dates:
        st.info("📭 Nessun allenamento registrato. Inizia dalla sezione Registra!")
    else:
        hist_date = st.selectbox("📅 Seleziona data", dates, key="hist_date")
        logs = db.get_logs_for_date(
            user_id,
            date.fromisoformat(hist_date) if isinstance(hist_date, str) else hist_date,
        )
        if logs:
            df = pd.DataFrame(logs)
            display_df = df[["exercise_name", "set_number", "weight_kg", "reps", "notes"]].copy()
            display_df.columns = ["Esercizio", "Serie", "Kg", "Reps", "Note"]
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            # Delete single entry
            with st.expander("🗑️ Elimina una registrazione"):
                del_options = {
                    f"{r['exercise_name']} — Serie {r['set_number']} — {r['weight_kg']}kg x {r['reps']}": r["id"]
                    for r in logs
                }
                del_choice = st.selectbox("Seleziona voce da eliminare",
                                          list(del_options.keys()), key="del_log")
                if st.button("Elimina", key="btn_del_log", type="primary"):
                    db.delete_log(user_id, del_options[del_choice])
                    st.success("✅ Registrazione eliminata.")
                    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════

elif selected == "📈  Progressi":
    st.header("📈 Progressi")

    ex_id_a, ex_label_a = _exercises_select("analytics_exercise")

    if ex_id_a is not None:
        progress = db.get_exercise_progress(user_id, ex_id_a)
        if not progress:
            st.info("📭 Nessun dato per questo esercizio. Registra qualche allenamento!")
        else:
            pdf = pd.DataFrame(progress)
            pdf["workout_date"] = pd.to_datetime(pdf["workout_date"])

            # Time filter
            filter_options = {
                "Ultimo mese": pd.Timedelta(days=30),
                "Ultimi 3 mesi": pd.Timedelta(days=90),
                "Ultimi 6 mesi": pd.Timedelta(days=180),
                "Ultimo anno": pd.Timedelta(days=365),
                "Tutto": None,
            }
            col_filter, _ = st.columns([2, 3])
            with col_filter:
                time_filter = st.selectbox("📅 Periodo", list(filter_options.keys()),
                                           index=len(filter_options) - 1, key="time_filter")
            cutoff = filter_options[time_filter]
            if cutoff is not None:
                min_date = pd.Timestamp.now() - cutoff
                pdf = pdf[pdf["workout_date"] >= min_date]

            if pdf.empty:
                st.info("📭 Nessun dato nel periodo selezionato.")
            else:
                # Summary stats on top
                c1, c2, c3 = st.columns(3)
                c1.metric("🏋️ Record peso", f"{pdf['max_weight'].max():.1f} kg")
                c2.metric("📊 Volume max", f"{pdf['total_volume'].max():.0f} kg")
                c3.metric("🔄 Reps max", int(pdf["max_reps"].max()))

                if len(pdf) >= 2:
                    first, last = pdf.iloc[0], pdf.iloc[-1]
                    delta_w = last["max_weight"] - first["max_weight"]
                    delta_v = last["total_volume"] - first["total_volume"]
                    if delta_w >= 0:
                        st.success(
                            f"📈 Dal {first['workout_date'].strftime('%d/%m/%Y')} "
                            f"al {last['workout_date'].strftime('%d/%m/%Y')}: "
                            f"peso max **+{delta_w:.1f} kg**, "
                            f"volume **{'+' if delta_v >= 0 else ''}{delta_v:.0f} kg**"
                        )
                    else:
                        st.warning(
                            f"📉 Dal {first['workout_date'].strftime('%d/%m/%Y')} "
                            f"al {last['workout_date'].strftime('%d/%m/%Y')}: "
                            f"peso max **{delta_w:.1f} kg**, "
                            f"volume **{'+' if delta_v >= 0 else ''}{delta_v:.0f} kg**"
                        )

                st.markdown("---")

                _range_buttons = dict(
                    buttons=list([
                        dict(count=1, label="1m", step="month", stepmode="backward"),
                        dict(count=3, label="3m", step="month", stepmode="backward"),
                        dict(count=6, label="6m", step="month", stepmode="backward"),
                        dict(count=1, label="1a", step="year", stepmode="backward"),
                        dict(step="all", label="Tutto"),
                    ])
                )

                # Chart 1 & 2 side by side
                col_chart1, col_chart2 = st.columns(2)

                with col_chart1:
                    fig1 = px.line(
                        pdf, x="workout_date", y="max_weight",
                        markers=True,
                        title="Peso massimo per sessione (kg)",
                        labels={"workout_date": "Data", "max_weight": "Kg"},
                    )
                    fig1.update_traces(line=dict(width=3, color="#667eea"), marker=dict(size=8))
                    fig1.update_layout(
                        height=350, template="plotly_white",
                        xaxis=dict(rangeselector=_range_buttons),
                    )
                    st.plotly_chart(fig1, use_container_width=True)

                with col_chart2:
                    fig2 = px.bar(
                        pdf, x="workout_date", y="total_volume",
                        title="Volume totale per sessione (kg x reps)",
                        labels={"workout_date": "Data", "total_volume": "Volume (kg)"},
                        color_discrete_sequence=["#764ba2"],
                    )
                    fig2.update_layout(
                        height=350, template="plotly_white",
                        xaxis=dict(rangeselector=_range_buttons),
                    )
                    st.plotly_chart(fig2, use_container_width=True)

                # Chart 3: Dettaglio reps per serie (barre raggruppate)
                raw_logs = db.get_logs_for_exercise(user_id, ex_id_a)
                if raw_logs:
                    rdf = pd.DataFrame(raw_logs)
                    rdf["workout_date"] = pd.to_datetime(rdf["workout_date"])
                    if cutoff is not None:
                        rdf = rdf[rdf["workout_date"] >= min_date]
                    if not rdf.empty:
                        rdf["label"] = "Serie " + rdf["set_number"].astype(str)
                        rdf["data"] = rdf["workout_date"].dt.strftime("%d/%m")
                        fig3 = px.bar(
                            rdf, x="data", y="reps", color="label",
                            barmode="group",
                            text=rdf["weight_kg"].apply(lambda x: f"{x:.0f}kg"),
                            title="Ripetizioni per serie (etichetta = peso)",
                            labels={"data": "Data", "reps": "Reps", "label": "Serie"},
                            hover_data={"weight_kg": ":.1f", "reps": True,
                                        "label": False, "data": False},
                        )
                        fig3.update_traces(textposition="outside", textfont_size=10)
                        fig3.update_layout(
                            height=400, template="plotly_white",
                            xaxis=dict(type="category"),
                            yaxis=dict(title="Reps"),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                        xanchor="right", x=1),
                        )
                        st.plotly_chart(fig3, use_container_width=True)

                st.markdown("---")

                # Chart 4 & 5 side by side: 1RM stimato + Peso medio vs max
                col_chart4, col_chart5 = st.columns(2)

                # 1RM stimato (Epley: 1RM = w * (1 + r/30))
                pdf["estimated_1rm"] = pdf["max_weight"] * (1 + pdf["max_reps"] / 30)

                with col_chart4:
                    fig4 = px.line(
                        pdf, x="workout_date", y="estimated_1rm",
                        markers=True,
                        title="1RM stimato — Formula di Epley",
                        labels={"workout_date": "Data", "estimated_1rm": "1RM (kg)"},
                    )
                    fig4.update_traces(line=dict(width=3, color="#e74c3c"), marker=dict(size=8))
                    fig4.update_layout(
                        height=350, template="plotly_white",
                        xaxis=dict(rangeselector=_range_buttons),
                    )
                    st.plotly_chart(fig4, use_container_width=True)

                with col_chart5:
                    # Peso medio per serie vs peso max
                    if raw_logs:
                        rdf_avg = rdf.groupby("workout_date").agg(
                            peso_medio=("weight_kg", "mean"),
                            peso_max=("weight_kg", "max"),
                        ).reset_index()
                        import plotly.graph_objects as go
                        fig5 = go.Figure()
                        fig5.add_trace(go.Scatter(
                            x=rdf_avg["workout_date"], y=rdf_avg["peso_max"],
                            mode="lines+markers", name="Peso max",
                            line=dict(width=3, color="#667eea"), marker=dict(size=8),
                        ))
                        fig5.add_trace(go.Scatter(
                            x=rdf_avg["workout_date"], y=rdf_avg["peso_medio"],
                            mode="lines+markers", name="Peso medio",
                            line=dict(width=2, color="#2ecc71", dash="dash"), marker=dict(size=6),
                        ))
                        fig5.update_layout(
                            title="Peso medio vs Peso max per sessione",
                            height=350, template="plotly_white",
                            xaxis=dict(title="Data", rangeselector=_range_buttons),
                            yaxis=dict(title="Kg"),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                        xanchor="right", x=1),
                        )
                        st.plotly_chart(fig5, use_container_width=True)

                # Chart 6 & 7 side by side: Tonnellaggio cumulativo + Distribuzione reps
                col_chart6, col_chart7 = st.columns(2)

                with col_chart6:
                    pdf_sorted = pdf.sort_values("workout_date")
                    pdf_sorted["volume_cumulativo"] = pdf_sorted["total_volume"].cumsum()
                    fig6 = px.area(
                        pdf_sorted, x="workout_date", y="volume_cumulativo",
                        title="Tonnellaggio cumulativo",
                        labels={"workout_date": "Data", "volume_cumulativo": "Volume (kg)"},
                    )
                    fig6.update_traces(
                        line=dict(width=2, color="#f39c12"),
                        fillcolor="rgba(243, 156, 18, 0.2)",
                    )
                    fig6.update_layout(
                        height=350, template="plotly_white",
                        xaxis=dict(rangeselector=_range_buttons),
                    )
                    st.plotly_chart(fig6, use_container_width=True)

                with col_chart7:
                    if raw_logs and not rdf.empty:
                        fig7 = px.histogram(
                            rdf, x="reps", nbins=max(int(rdf["reps"].max() - rdf["reps"].min() + 1), 5),
                            title="Distribuzione ripetizioni",
                            labels={"reps": "Reps", "count": "Frequenza"},
                            color_discrete_sequence=["#9b59b6"],
                        )
                        fig7.update_layout(
                            height=350, template="plotly_white",
                            yaxis=dict(title="Frequenza"),
                            bargap=0.1,
                        )
                        st.plotly_chart(fig7, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: PROGRESSION ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

elif selected == "🚀  Progression Engine":
    st.header("🚀 Progression Engine")
    st.caption("Sistema decisionale che analizza i tuoi dati e suggerisce come progredire.")

    tab_dashboard, tab_config, tab_history = st.tabs([
        "📊 Dashboard", "⚙️ Configura target", "📜 Storico decisioni"
    ])

    # ── TAB: Dashboard ──
    with tab_dashboard:
        targets = db.get_all_exercise_targets(user_id)

        if not targets:
            st.info(
                "🎯 Nessun target configurato. Vai alla tab **Configura target** "
                "per impostare range di ripetizioni e step di progressione per i tuoi esercizi."
            )
        else:
            if st.button("🔄 Analizza tutti gli esercizi", type="primary",
                         use_container_width=True):
                results = pe.analyze_all_exercises(user_id, save=True)
                st.session_state["pe_results"] = results

            results = st.session_state.get("pe_results")
            if not results:
                # Auto-analyze on first load (without saving)
                results = pe.analyze_all_exercises(user_id, save=False)

            if results:
                # Group by suggestion type for overview
                type_counts = {}
                for _, s in results:
                    label, _ = pe.SUGGESTION_DISPLAY[s.type]
                    type_counts[label] = type_counts.get(label, 0) + 1

                cols = st.columns(min(len(type_counts), 4))
                for i, (label, count) in enumerate(type_counts.items()):
                    cols[i % len(cols)].metric(label, count)

                st.markdown("---")

                # Per-exercise cards
                for ex_info, suggestion in results:
                    label, style = pe.SUGGESTION_DISPLAY[suggestion.type]
                    color_map = {"success": "#4CAF50", "warning": "#FF9800", "info": "#2196F3"}
                    border_color = color_map.get(style, "#2196F3")

                    with st.expander(
                        f"**{ex_info['name']}** ({ex_info['category']}) → {label}",
                        expanded=(style == "success" or style == "warning"),
                    ):
                        col_info, col_action = st.columns([3, 1])

                        with col_info:
                            st.markdown(suggestion.reasoning)
                            st.caption(
                                f"📊 Sessioni analizzate: {suggestion.sessions_analyzed} | "
                                f"Peso attuale: {suggestion.current_weight:.1f} kg | "
                                f"Media reps: {suggestion.current_avg_reps:.1f}"
                            )

                        with col_action:
                            if suggestion.suggested_weight_kg:
                                st.metric(
                                    "Prossimo workout",
                                    f"{suggestion.suggested_weight_kg:.1f} kg",
                                    delta=f"{suggestion.suggested_weight_kg - suggestion.current_weight:+.1f} kg"
                                    if suggestion.current_weight > 0 else None,
                                )
                            if suggestion.suggested_reps_target:
                                st.markdown(f"🎯 **{suggestion.suggested_reps_target} reps**")

    # ── TAB: Configure targets ──
    with tab_config:
        st.subheader("🎯 Imposta target per esercizio")
        st.caption(
            "Configura il range di ripetizioni e lo step di peso per ogni esercizio. "
            "Il motore userà questi parametri per i suggerimenti di progressione."
        )

        exercises = db.get_all_exercises(user_id)
        if not exercises:
            st.warning("Nessun esercizio. Creane almeno uno nella sezione ⚙️ Esercizi.")
        else:
            # Quick-setup presets
            st.markdown("#### ⚡ Setup rapido con preset")
            preset_col1, preset_col2, preset_col3 = st.columns(3)

            with preset_col1:
                if st.button("💪 Forza (3-6 reps, +2.5kg)", use_container_width=True):
                    for ex in exercises:
                        db.upsert_exercise_target(
                            user_id, ex["id"], target_sets=5,
                            target_reps_min=3, target_reps_max=6,
                            progression_step_kg=2.5)
                    st.success("✅ Preset Forza applicato a tutti gli esercizi!")
                    st.rerun()

            with preset_col2:
                if st.button("🏗️ Ipertrofia (8-12 reps, +2.5kg)", use_container_width=True):
                    for ex in exercises:
                        db.upsert_exercise_target(
                            user_id, ex["id"], target_sets=3,
                            target_reps_min=8, target_reps_max=12,
                            progression_step_kg=2.5)
                    st.success("✅ Preset Ipertrofia applicato!")
                    st.rerun()

            with preset_col3:
                if st.button("🔥 Resistenza (12-20 reps, +1.25kg)", use_container_width=True):
                    for ex in exercises:
                        db.upsert_exercise_target(
                            user_id, ex["id"], target_sets=3,
                            target_reps_min=12, target_reps_max=20,
                            progression_step_kg=1.25)
                    st.success("✅ Preset Resistenza applicato!")
                    st.rerun()

            st.markdown("---")
            st.markdown("#### 🎛️ Configurazione per esercizio")

            # Show current targets with edit capability
            grouped = db.get_exercises_by_category(user_id)
            for cat, cat_exercises in sorted(grouped.items()):
                with st.expander(f"**{cat}** ({len(cat_exercises)} esercizi)"):
                    for ex in cat_exercises:
                        current = db.get_exercise_target(user_id, ex["id"])
                        with st.form(key=f"target_{ex['id']}"):
                            st.markdown(f"**{ex['name']}**")
                            c1, c2, c3, c4 = st.columns(4)
                            t_sets = c1.number_input(
                                "Serie", min_value=1, max_value=10,
                                value=current["target_sets"] if current else 3,
                                key=f"ts_{ex['id']}")
                            t_min = c2.number_input(
                                "Reps min", min_value=1, max_value=30,
                                value=current["target_reps_min"] if current else 8,
                                key=f"trmin_{ex['id']}")
                            t_max = c3.number_input(
                                "Reps max", min_value=1, max_value=50,
                                value=current["target_reps_max"] if current else 12,
                                key=f"trmax_{ex['id']}")
                            t_step = c4.number_input(
                                "Step kg", min_value=0.5, max_value=10.0, step=0.5,
                                value=current["progression_step_kg"] if current else 2.5,
                                key=f"tstep_{ex['id']}")
                            if st.form_submit_button("💾 Salva", use_container_width=True):
                                if t_min > t_max:
                                    st.error("Reps min deve essere ≤ Reps max")
                                else:
                                    db.upsert_exercise_target(
                                        user_id, ex["id"], int(t_sets),
                                        int(t_min), int(t_max), float(t_step))
                                    st.success(f"✅ Target salvato per {ex['name']}")

    # ── TAB: Suggestion history ──
    with tab_history:
        st.subheader("📜 Storico decisioni del motore")
        st.caption(
            "Ogni suggerimento generato viene salvato con il contesto completo. "
        )

        ex_id_h, ex_label_h = _exercises_select("history_exercise")
        if ex_id_h:
            history = db.get_suggestion_history(user_id, ex_id_h, limit=30)
            if not history:
                st.info("Nessuna decisione registrata per questo esercizio.")
            else:
                for entry in history:
                    label, style = pe.SUGGESTION_DISPLAY.get(
                        pe.SuggestionType(entry["suggestion_type"]),
                        ("❓ Sconosciuto", "info"))

                    outcome_icon = ""
                    if entry["outcome_accepted"] is True:
                        outcome_icon = " ✅ Seguito"
                    elif entry["outcome_accepted"] is False:
                        outcome_icon = " ❌ Non seguito"
                    else:
                        outcome_icon = " ⏳ In attesa"

                    ts = entry["generated_at"]
                    date_str = ts.strftime("%d/%m/%Y %H:%M") if hasattr(ts, "strftime") else str(ts)

                    with st.expander(f"{date_str} — {label}{outcome_icon}"):
                        st.markdown(entry["reasoning"])
                        col_ctx, col_sug, col_out = st.columns(3)
                        with col_ctx:
                            st.markdown("**📊 Contesto**")
                            st.caption(
                                f"Sessioni: {entry['context_last_sessions']}\n\n"
                                f"Peso: {entry['context_current_weight']:.1f} kg\n\n"
                                f"Media reps: {entry['context_current_avg_reps']:.1f}\n\n"
                                f"Volume: {entry['context_current_volume']:.0f} kg")
                        with col_sug:
                            st.markdown("**🎯 Suggerito**")
                            if entry["suggested_weight_kg"]:
                                st.caption(f"Peso: {entry['suggested_weight_kg']:.1f} kg")
                            if entry["suggested_reps_target"]:
                                st.caption(f"Reps: {entry['suggested_reps_target']}")
                        with col_out:
                            st.markdown("**📋 Outcome**")
                            if entry["outcome_actual_weight"]:
                                st.caption(
                                    f"Peso reale: {entry['outcome_actual_weight']:.1f} kg\n\n"
                                    f"Reps reali: {entry['outcome_actual_avg_reps']:.1f}\n\n"
                                    f"Data: {entry['outcome_date']}")
                            else:
                                st.caption("Non ancora registrato")


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: MANAGE EXERCISES
# ═══════════════════════════════════════════════════════════════════════════════

elif selected == "⚙️  Esercizi":
    st.header("⚙️ Gestione esercizi")

    CATEGORIES = ["Petto", "Schiena", "Spalle", "Gambe", "Braccia", "Core", "Altro"]

    with st.form("add_exercise_form"):
        st.subheader("➕ Aggiungi nuovo esercizio")
        col_name, col_cat = st.columns([2, 1])
        with col_name:
            new_name = st.text_input("Nome esercizio")
        with col_cat:
            new_cat = st.selectbox("Categoria", CATEGORIES)
        submitted = st.form_submit_button("➕ Aggiungi", use_container_width=True, type="primary")
        if submitted:
            if new_name.strip():
                try:
                    db.add_exercise(new_name, new_cat, user_id)
                    st.success(f"✅ Esercizio '{new_name}' aggiunto!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Esercizio già esistente o errore: {e}")
            else:
                st.error("Inserisci un nome per l'esercizio.")

    st.markdown("---")
    st.subheader("📚 Esercizi esistenti")

    grouped = db.get_exercises_by_category(user_id)
    for cat, exercises in sorted(grouped.items()):
        with st.expander(f"**{cat}** ({len(exercises)} esercizi)", expanded=False):
            for ex in exercises:
                cols = st.columns([4, 1])
                cols[0].write(ex["name"])
                if cols[1].button("🗑️", key=f"del_ex_{ex['id']}",
                                  help="Elimina esercizio e tutti i dati"):
                    db.delete_exercise(ex["id"], user_id)
                    st.rerun()
