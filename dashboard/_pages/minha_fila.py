"""Página: Visão Analista — Minha fila e meus lançamentos."""
import pandas as pd
import streamlit as st

from dashboard import db


def _badge_sla(horas):
    if horas is None or pd.isna(horas):
        return "—"
    if horas < 0:
        return f'<span class="badge-estourado">Estourado</span>'
    if horas < 4:
        return f'<span class="badge-critico">{horas:.1f}h</span>'
    if horas < 24:
        return f'<span class="badge-atencao">{horas:.1f}h</span>'
    return f'<span class="badge-normal">{horas:.1f}h</span>'


def render():
    st.title("🧑‍💻 Minha fila")
    st.caption("Tickets que você é responsável + seus lançamentos recentes")

    analistas = db.lista_analistas()
    if analistas.empty:
        st.warning("Nenhum analista encontrado.")
        return

    nome_para_id = dict(zip(analistas["nome"], analistas["agent_id"]))

    pessoa = st.selectbox(
        "Selecione o analista",
        options=list(nome_para_id.keys()),
        index=0,
        key="analista_atual",
    )
    agent_id = nome_para_id[pessoa]

    # ── KPIs ──────────────────────────────────────────────────────
    k = db.meus_kpis(agent_id)
    fila = db.minha_fila(agent_id)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("⏱️ Horas (7d)",  f"{float(k.get('horas_7d') or 0):.1f}h")
    c2.metric("⏱️ Horas (30d)", f"{float(k.get('horas_30d') or 0):.1f}h")
    c3.metric("🎫 Tickets atendidos (30d)", int(k.get("tickets_atendidos_30d") or 0))
    c4.metric("📥 Em aberto", len(fila))

    st.markdown("---")

    # ── Fila ──────────────────────────────────────────────────────
    st.subheader("📋 Tickets atribuídos a mim")
    if fila.empty:
        st.success("Sem tickets em aberto. Bom trabalho!")
    else:
        df = fila.copy()
        df["Ticket"] = "#" + df["ticket_id"].astype(str)
        df["SLA restante"] = df["horas_para_sla"].apply(_badge_sla)
        df["Aberto em"] = pd.to_datetime(df["created_date"]).dt.strftime("%Y-%m-%d %H:%M")
        st.markdown(
            df.rename(columns={
                "subject": "Assunto", "cliente": "Cliente",
                "category": "Categoria", "urgency": "Urgência",
                "status": "Status",
            })[["Ticket", "Assunto", "Cliente", "Categoria",
                "Urgência", "Status", "SLA restante", "Aberto em"]]
            .to_html(escape=False, index=False),
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Lançamentos ────────────────────────────────────────────────
    st.subheader("📝 Meus lançamentos (30 dias)")
    lanc = db.meus_lancamentos(agent_id, dias=30)
    if lanc.empty:
        st.info("Sem lançamentos no período.")
    else:
        df = lanc.copy()
        df["Data"] = pd.to_datetime(df["entry_date"]).dt.strftime("%Y-%m-%d")
        df["Ticket"] = "#" + df["ticket_id"].astype(str)
        df["Horas"] = df["hours_spent"].apply(lambda v: f"{float(v):.2f}h")
        st.dataframe(
            df.rename(columns={
                "subject": "Assunto", "cliente": "Cliente",
                "description": "Descrição",
            })[["Data", "Ticket", "Assunto", "Cliente", "Horas", "Descrição"]],
            width="stretch", hide_index=True,
            height=min(550, 40 + len(df) * 35),
        )
