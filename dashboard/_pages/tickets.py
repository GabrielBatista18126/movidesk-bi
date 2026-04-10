"""Página: Tickets em Aberto."""
import plotly.express as px
import streamlit as st

from dashboard import db

_COR_URG = {"Urgent": "#C00000", "High": "#FF6B00", "Normal": "#FFC000", "Low": "#70AD47"}


def render():
    st.title("🎫 Tickets em Aberto")

    df = db.tickets_abertos()

    if df.empty:
        st.success("Nenhum ticket em aberto no momento!")
        return

    # ── Filtros ───────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        urg_opts = ["Todas"] + sorted(df["urgency"].dropna().unique().tolist())
        urg_sel  = st.selectbox("Urgência", urg_opts)
    with c2:
        cli_opts = ["Todos"] + sorted(df["client_name"].dropna().unique().tolist())
        cli_sel  = st.selectbox("Cliente", cli_opts)
    with c3:
        dias_min = st.number_input("Aberto há mais de (dias)", min_value=0, value=0, step=1)

    filtered = df.copy()
    if urg_sel  != "Todas": filtered = filtered[filtered["urgency"]     == urg_sel]
    if cli_sel  != "Todos": filtered = filtered[filtered["client_name"] == cli_sel]
    if dias_min  > 0:       filtered = filtered[filtered["dias_aberto"] >= dias_min]

    st.markdown("---")

    # ── KPIs ──────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🎫 Total em aberto", len(filtered))
    k2.metric("🔴 Urgentes",  int((filtered["urgency"] == "Urgent").sum()))
    k3.metric("🟠 High",      int((filtered["urgency"] == "High").sum()))
    avg_dias = filtered["dias_aberto"].mean() if not filtered.empty else 0
    k4.metric("📅 Tempo médio aberto", f"{avg_dias:.0f} dias")

    st.markdown("---")

    col_l, col_r = st.columns([2, 3])

    with col_l:
        st.subheader("🎯 Por urgência")
        urg_count = filtered["urgency"].value_counts().reset_index()
        urg_count.columns = ["urgency", "count"]
        fig = px.pie(
            urg_count,
            names="urgency",
            values="count",
            color="urgency",
            color_discrete_map=_COR_URG,
            hole=0.4,
        )
        fig.update_layout(
            height=280,
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=-0.3),
        )
        st.plotly_chart(fig, width="stretch")

    with col_r:
        st.subheader("⏳ Tickets mais antigos (dias em aberto)")
        top_antigos = filtered.nlargest(10, "dias_aberto")[
            ["subject", "client_name", "urgency", "dias_aberto", "time_spent_total_hours"]
        ].copy()
        top_antigos.columns = ["Ticket", "Cliente", "Urgência", "Dias aberto", "Horas lançadas"]
        top_antigos["Horas lançadas"] = top_antigos["Horas lançadas"].apply(lambda x: f"{x:.1f}h" if x else "0h")
        st.dataframe(top_antigos, width="stretch", hide_index=True)

    st.markdown("---")

    # ── Tickets por cliente ───────────────────────────────────────
    st.subheader("🏢 Tickets em aberto por cliente")
    cli_count = (
        filtered.groupby("client_name")
        .agg(total=("ticket_id", "count"), horas=("time_spent_total_hours", "sum"))
        .reset_index()
        .sort_values("total", ascending=True)
        .tail(15)
    )
    fig2 = px.bar(
        cli_count,
        x="total",
        y="client_name",
        orientation="h",
        color="total",
        color_continuous_scale="Reds",
        text="total",
        labels={"total": "Tickets", "client_name": "Cliente"},
    )
    fig2.update_traces(texttemplate="%{text}", textposition="outside")
    fig2.update_layout(
        showlegend=False,
        coloraxis_showscale=False,
        height=max(300, len(cli_count) * 28),
        margin=dict(l=0, r=30, t=10, b=0),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig2, width="stretch")

    st.markdown("---")

    # ── Tabela completa ───────────────────────────────────────────
    st.subheader("📋 Lista completa")
    df_show = filtered[[
        "ticket_id", "subject", "status", "urgency", "client_name",
        "owner_name", "owner_team", "dias_aberto", "time_spent_total_hours"
    ]].copy()
    df_show.columns = ["ID", "Ticket", "Status", "Urgência", "Cliente",
                       "Responsável", "Time", "Dias aberto", "Horas lançadas"]
    df_show["Horas lançadas"] = df_show["Horas lançadas"].apply(lambda x: f"{x:.1f}h" if x else "0h")
    df_show = df_show.sort_values("Dias aberto", ascending=False)
    st.dataframe(df_show, width="stretch", hide_index=True)
    st.caption(f"{len(df_show)} tickets exibidos")
