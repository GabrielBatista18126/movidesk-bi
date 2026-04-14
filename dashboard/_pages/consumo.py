"""Página: Consumo de Contrato."""
import plotly.express as px
import streamlit as st

from dashboard import db


def _badge(status: str) -> str:
    cls = status.lower() if status else "normal"
    return f'<span class="badge-{cls}">{status}</span>'


def render():
    st.title("📋 Consumo de Contrato")

    meses = db.meses_disponiveis()
    consumo_df = db.consumo_mensal()

    # ── Filtros ───────────────────────────────────────────────────
    col_f1, col_f2 = st.columns([2, 3])
    with col_f1:
        mes_sel = st.selectbox(
            "Mês de referência",
            options=meses if meses else ["(sem dados)"],
            index=0,
        )

    resumo = db.resumo_mes_atual(None if mes_sel == "(sem dados)" else mes_sel)

    with col_f2:
        clientes_lista = sorted(resumo["client_name"].unique().tolist()) if not resumo.empty else []
        cliente_sel = st.multiselect("Filtrar por cliente", options=clientes_lista, default=[])

    periodo_label = mes_sel if mes_sel and mes_sel != "(sem dados)" else "mês atual"

    st.markdown("---")

    # ── KPIs do período selecionado ───────────────────────────────
    if not resumo.empty:
        total_horas = resumo["horas_mes_atual"].sum()
        total_clientes = len(resumo)
        total_tickets = resumo["tickets_mes_atual"].sum()

        k1, k2, k3 = st.columns(3)
        k1.metric("⏱️ Total de horas no mês", f"{total_horas:.1f}h")
        k2.metric("🏢 Clientes com lançamentos", total_clientes)
        k3.metric("🎫 Tickets atendidos", int(total_tickets))
    else:
        st.info("Nenhum lançamento encontrado para o período selecionado.")

    st.markdown("---")

    # ── Tabela de consumo ─────────────────────────────────────────
    st.subheader(f"📊 Consumo por cliente — {periodo_label}")
    if not resumo.empty:
        df = resumo.copy()
        if cliente_sel:
            df = df[df["client_name"].isin(cliente_sel)]

        df = df.rename(columns={
            "client_name": "Cliente",
            "horas_mes_atual": "Horas consumidas",
            "tickets_mes_atual": "Tickets",
            "lancamentos_mes_atual": "Lançamentos",
            "ultimo_lancamento": "Último lançamento",
        })
        df["Último lançamento"] = df["Último lançamento"].astype(str).str[:16]
        st.dataframe(
            df[["Cliente", "Horas consumidas", "Tickets", "Lançamentos", "Último lançamento"]],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("Sem dados para o período selecionado.")

    st.markdown("---")

    # ── Gráfico de barras: horas por cliente ──────────────────────
    st.subheader(f"📈 Horas consumidas por cliente — {periodo_label}")
    if not resumo.empty:
        df_bar = resumo.copy()
        if cliente_sel:
            df_bar = df_bar[df_bar["client_name"].isin(cliente_sel)]
        df_bar = df_bar.sort_values("horas_mes_atual", ascending=True).tail(20)

        fig = px.bar(
            df_bar,
            x="horas_mes_atual",
            y="client_name",
            orientation="h",
            color="horas_mes_atual",
            color_continuous_scale="Viridis",
            labels={"horas_mes_atual": "Horas", "client_name": "Cliente"},
            text="horas_mes_atual",
        )
        fig.update_traces(texttemplate="%{text:.1f}h", textposition="outside")
        fig.update_layout(
            showlegend=False,
            coloraxis_showscale=False,
            height=max(350, len(df_bar) * 28),
            margin=dict(l=0, r=40, t=10, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, width="stretch")

    st.markdown("---")

    # ── Histórico mensal por cliente ──────────────────────────────
    st.subheader("🗓️ Histórico mensal de consumo")
    if not consumo_df.empty:
        df_hist = consumo_df.copy()
        if cliente_sel:
            df_hist = df_hist[df_hist["client_name"].isin(cliente_sel)]

        # Top 10 clientes por total de horas
        top_clientes = (
            df_hist.groupby("client_name")["horas_consumidas"]
            .sum()
            .nlargest(10)
            .index.tolist()
        )
        df_hist = df_hist[df_hist["client_name"].isin(top_clientes)]

        fig2 = px.line(
            df_hist,
            x="ano_mes",
            y="horas_consumidas",
            color="client_name",
            markers=True,
            labels={"ano_mes": "Mês", "horas_consumidas": "Horas", "client_name": "Cliente"},
        )
        fig2.update_layout(
            height=380,
            margin=dict(l=0, r=0, t=10, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=-0.4),
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        )
        st.plotly_chart(fig2, width="stretch")
        st.caption("Exibindo os 10 clientes com maior consumo total.")
    else:
        st.info("Sem histórico de consumo disponível.")
