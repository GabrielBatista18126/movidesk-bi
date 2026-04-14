"""Página: Alertas de consumo."""
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard import db

_CORES = {
    "ESTOURADO": "#C00000",
    "CRITICO":   "#FF6B00",
    "ATENCAO":   "#FFC000",
    "NORMAL":    "#70AD47",
}


def _semaforo(status: str) -> str:
    emoji = {"ESTOURADO": "🔴", "CRITICO": "🟠", "ATENCAO": "🟡", "NORMAL": "🟢"}
    return emoji.get(status, "⚪")


def render():
    st.title("🚨 Alertas de Consumo")

    alerta_df = db.alerta_consumo()
    historico_df = db.historico_consumo()

    if alerta_df.empty:
        st.warning("Nenhum contrato cadastrado ainda. Cadastre os contratos para ver os alertas.")
        st.info("Acesse o banco e insira os dados em `analytics.contratos` conforme o README.")
        return

    # ── KPIs ──────────────────────────────────────────────────────
    estourados = len(alerta_df[alerta_df["status_consumo"] == "ESTOURADO"])
    criticos   = len(alerta_df[alerta_df["status_consumo"] == "CRITICO"])
    atencao    = len(alerta_df[alerta_df["status_consumo"] == "ATENCAO"])
    normais    = len(alerta_df[alerta_df["status_consumo"] == "NORMAL"])

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🔴 Estourados",  estourados)
    k2.metric("🟠 Críticos",    criticos)
    k3.metric("🟡 Em atenção",  atencao)
    k4.metric("🟢 Normais",     normais)

    st.markdown("---")

    # ── Filtro de status ──────────────────────────────────────────
    status_opts = ["Todos"] + sorted(alerta_df["status_consumo"].unique().tolist())
    status_sel = st.selectbox("Filtrar por status", options=status_opts)

    df = alerta_df.copy()
    if status_sel != "Todos":
        df = df[df["status_consumo"] == status_sel]

    # ── Tabela com semáforo ───────────────────────────────────────
    st.subheader("📋 Situação dos contratos")
    if not df.empty:
        df_show = df[["client_name", "plano_nome", "horas_contratadas",
                      "horas_consumidas", "horas_disponiveis", "pct_consumo", "status_consumo"]].copy()
        df_show.columns = ["Cliente", "Plano", "Contratadas", "Consumidas", "Disponíveis", "% Consumo", "Status"]
        df_show["Status"] = df_show["Status"].apply(lambda s: f"{_semaforo(s)} {s}")
        df_show["% Consumo"] = df_show["% Consumo"].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "—"
        )
        df_show["Contratadas"] = df_show["Contratadas"].apply(
            lambda x: f"{x:.1f}h" if pd.notna(x) else "—"
        )
        df_show["Consumidas"] = df_show["Consumidas"].apply(
            lambda x: f"{x:.1f}h" if pd.notna(x) else "0.0h"
        )
        df_show["Disponíveis"] = df_show["Disponíveis"].apply(
            lambda x: f"{x:.1f}h" if pd.notna(x) else "—"
        )
        st.dataframe(df_show, width="stretch", hide_index=True)
    else:
        st.info("Nenhum cliente encontrado para o filtro selecionado.")

    st.markdown("---")

    # ── Gráfico gauge / barras de consumo ─────────────────────────
    st.subheader("📊 % de consumo por cliente")
    df_chart = alerta_df[alerta_df["horas_contratadas"] > 0].copy()
    if not df_chart.empty:
        df_chart = df_chart.sort_values("pct_consumo", ascending=True).tail(20)
        df_chart["cor"] = df_chart["status_consumo"].map(_CORES).fillna("#888")

        fig = px.bar(
            df_chart,
            x="pct_consumo",
            y="client_name",
            orientation="h",
            color="status_consumo",
            color_discrete_map=_CORES,
            labels={"pct_consumo": "% Consumo", "client_name": "Cliente", "status_consumo": "Status"},
            text="pct_consumo",
        )
        fig.add_vline(x=80,  line_dash="dash", line_color="#FF6B00", annotation_text="Crítico 80%")
        fig.add_vline(x=100, line_dash="dash", line_color="#C00000", annotation_text="Limite 100%")
        fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        fig.update_layout(
            height=max(350, len(df_chart) * 30),
            margin=dict(l=0, r=60, t=20, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=-0.2),
        )
        st.plotly_chart(fig, width="stretch")

    st.markdown("---")

    # ── Histórico de consumo % ────────────────────────────────────
    st.subheader("📈 Evolução do % de consumo (últimos meses)")
    if not historico_df.empty:
        # Foco nos clientes mais críticos
        alerta_df["pct_consumo"] = pd.to_numeric(alerta_df["pct_consumo"], errors="coerce")
        top = alerta_df.nlargest(8, "pct_consumo")["client_name"].tolist()
        df_hist = historico_df[historico_df["client_name"].isin(top)]

        fig2 = px.line(
            df_hist,
            x="ano_mes",
            y="pct_consumo",
            color="client_name",
            markers=True,
            labels={"ano_mes": "Mês", "pct_consumo": "% Consumo", "client_name": "Cliente"},
        )
        fig2.add_hline(y=80,  line_dash="dash", line_color="#FF6B00", annotation_text="80%")
        fig2.add_hline(y=100, line_dash="dash", line_color="#C00000", annotation_text="100%")
        fig2.update_layout(
            height=350,
            margin=dict(l=0, r=0, t=10, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=-0.4),
            xaxis=dict(showgrid=False),
            yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        )
        st.plotly_chart(fig2, width="stretch")
    else:
        st.info("Sem histórico disponível.")

    st.markdown("---")

    # ── SLA e Tempo Médio de Resolução ────────────────────────────
    st.subheader("📐 SLA — Tempo médio de resolução (mês atual)")
    sla_df = db.sla_performance()
    mes_atual = sla_df["ano_mes"].max() if not sla_df.empty else None
    if mes_atual:
        sla_mes = sla_df[sla_df["ano_mes"] == mes_atual].copy()
        if not sla_mes.empty:
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                tmr_medio = sla_mes["tmr_dias"].mean()
                taxa_media = sla_mes["taxa_resolucao_pct"].mean()
                st.metric("📅 TMR médio (dias)", f"{tmr_medio:.1f}d" if tmr_medio else "—")
                st.metric("✅ Taxa de resolução", f"{taxa_media:.1f}%" if taxa_media else "—")
            with col_s2:
                top_lento = sla_mes.nlargest(5, "tmr_dias")[["client_name", "tmr_dias", "total_tickets"]]
                top_lento.columns = ["Cliente", "TMR (dias)", "Tickets"]
                st.caption("Top 5 clientes com maior TMR:")
                st.dataframe(top_lento, width="stretch", hide_index=True)

    st.markdown("---")

    # ── Taxa de Retrabalho ────────────────────────────────────────
    st.subheader("🔁 Taxa de Retrabalho (reabertura de tickets)")
    ret_df = db.retrabalho()
    if not ret_df.empty:
        mes_atual_ret = ret_df["ano_mes"].max()
        ret_mes = ret_df[ret_df["ano_mes"] == mes_atual_ret]
        ret_com_dados = ret_mes[ret_mes["tickets_reabertos"] > 0].sort_values(
            "taxa_retrabalho_pct", ascending=False
        )
        if not ret_com_dados.empty:
            fig_ret = px.bar(
                ret_com_dados.head(10),
                x="taxa_retrabalho_pct", y="client_name", orientation="h",
                color="taxa_retrabalho_pct", color_continuous_scale="Reds",
                text="taxa_retrabalho_pct",
                labels={"taxa_retrabalho_pct": "% Retrabalho", "client_name": "Cliente"},
            )
            fig_ret.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig_ret.update_layout(
                showlegend=False, coloraxis_showscale=False,
                height=max(250, len(ret_com_dados.head(10)) * 30),
                margin=dict(l=0, r=50, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_ret, width="stretch")
        else:
            st.success("Nenhum ticket reaberto no mês atual.")
