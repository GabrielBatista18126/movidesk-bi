"""Página: Produtividade do Time."""
import plotly.express as px
import streamlit as st

from dashboard import db


def render():
    st.title("👥 Produtividade do Time")
    st.caption("Análise individual por agente — mês atual e histórico")

    resumo_df = db.produtividade_agente_resumo()
    hist_df   = db.produtividade()

    # ── KPIs do time ──────────────────────────────────────────────
    if not resumo_df.empty:
        total_horas    = resumo_df["horas_mes_atual"].sum()
        total_tickets  = resumo_df["tickets_mes_atual"].sum()
        agentes_ativos = int((resumo_df["horas_mes_atual"] > 0).sum())
        ef_vals = resumo_df[resumo_df["tickets_por_hora_mes"].notna()]["tickets_por_hora_mes"]
        eficiencia_media = ef_vals.mean() if not ef_vals.empty else None

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("⏱️ Horas lançadas", f"{total_horas:.1f}h")
        k2.metric("🎫 Tickets atendidos", int(total_tickets))
        k3.metric("👤 Agentes ativos", agentes_ativos)
        k4.metric("⚡ Eficiência média",
                  f"{eficiencia_media:.2f} tkts/h" if eficiencia_media else "—")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🏆 Ranking — Horas lançadas (mês)")
        if not resumo_df.empty:
            df_r = resumo_df[resumo_df["horas_mes_atual"] > 0].sort_values(
                "horas_mes_atual", ascending=True)
            fig = px.bar(
                df_r, x="horas_mes_atual", y="agent_name", orientation="h",
                color="horas_mes_atual", color_continuous_scale="Blues",
                text="horas_mes_atual",
                labels={"horas_mes_atual": "Horas", "agent_name": "Agente"},
            )
            fig.update_traces(texttemplate="%{text:.1f}h", textposition="outside")
            fig.update_layout(
                showlegend=False, coloraxis_showscale=False,
                height=max(280, len(df_r) * 32),
                margin=dict(l=0, r=40, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, width="stretch")

    with col2:
        st.subheader("⚡ Eficiência — Tickets por hora")
        if not resumo_df.empty:
            df_ef = resumo_df[
                resumo_df["tickets_por_hora_mes"].notna() &
                (resumo_df["horas_mes_atual"] > 0)
            ].sort_values("tickets_por_hora_mes", ascending=True)
            if not df_ef.empty:
                fig2 = px.bar(
                    df_ef, x="tickets_por_hora_mes", y="agent_name", orientation="h",
                    color="tickets_por_hora_mes", color_continuous_scale="Greens",
                    text="tickets_por_hora_mes",
                    labels={"tickets_por_hora_mes": "Tkts/h", "agent_name": "Agente"},
                )
                fig2.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                fig2.update_layout(
                    showlegend=False, coloraxis_showscale=False,
                    height=max(280, len(df_ef) * 32),
                    margin=dict(l=0, r=40, t=10, b=0),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig2, width="stretch")

    st.markdown("---")

    # ── Tabela detalhada ──────────────────────────────────────────
    st.subheader("📋 Detalhamento por agente — mês atual")
    if not resumo_df.empty:
        df_show = resumo_df.rename(columns={
            "agent_name": "Agente", "team": "Time",
            "horas_mes_atual": "Horas", "tickets_mes_atual": "Tickets",
            "clientes_mes_atual": "Clientes",
            "tickets_por_hora_mes": "Tkts/hora",
            "media_horas_por_ticket_mes": "h/ticket",
            "total_horas_historico": "Horas (total)",
            "total_tickets_historico": "Tickets (total)",
        })
        cols = ["Agente", "Time", "Horas", "Tickets", "Clientes",
                "Tkts/hora", "h/ticket", "Horas (total)", "Tickets (total)"]
        st.dataframe(
            df_show[[c for c in cols if c in df_show.columns]],
            width="stretch", hide_index=True,
        )

    st.markdown("---")

    # ── Evolução histórica ────────────────────────────────────────
    st.subheader("📈 Evolução de horas por agente (histórico)")
    if not hist_df.empty:
        agentes_lista = sorted(hist_df["agent_name"].unique().tolist())
        sel = st.multiselect(
            "Selecionar agentes", options=agentes_lista,
            default=agentes_lista[:6] if len(agentes_lista) >= 6 else agentes_lista,
        )
        df_h = hist_df[hist_df["agent_name"].isin(sel)] if sel else hist_df
        fig3 = px.line(
            df_h, x="ano_mes", y="horas_lancadas", color="agent_name",
            markers=True,
            labels={"ano_mes": "Mês", "horas_lancadas": "Horas", "agent_name": "Agente"},
        )
        fig3.update_layout(
            height=350, margin=dict(l=0, r=0, t=10, b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=-0.45),
        )
        st.plotly_chart(fig3, width="stretch")

    # ── Tempo médio por ticket ────────────────────────────────────
    if not hist_df.empty and "media_horas_por_ticket" in hist_df.columns:
        st.subheader("⏱️ Tempo médio por ticket (histórico)")
        df_tmt = hist_df[hist_df["media_horas_por_ticket"].notna()]
        df_tmt = df_tmt[df_tmt["agent_name"].isin(sel)] if sel else df_tmt
        if not df_tmt.empty:
            fig4 = px.line(
                df_tmt, x="ano_mes", y="media_horas_por_ticket", color="agent_name",
                markers=True,
                labels={"ano_mes": "Mês", "media_horas_por_ticket": "h/ticket",
                        "agent_name": "Agente"},
            )
            fig4.update_layout(
                height=280, margin=dict(l=0, r=0, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=-0.45),
            )
            st.plotly_chart(fig4, width="stretch")
