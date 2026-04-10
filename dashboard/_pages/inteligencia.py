"""Página: Inteligência — Previsões, Scores e Sugestões de Upgrade."""
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard import db

_COR_CLASS = {"BAIXO": "#70AD47", "MEDIO": "#FFC000", "ALTO": "#FF6B00", "CRITICO": "#C00000"}


def render():
    st.title("🤖 Inteligência")
    st.caption("Previsões de estouro, score de risco e sugestões de upgrade")

    prev_df   = db.previsoes()
    score_df  = db.scores()
    upgrade_df = db.sugestoes_upgrade()

    sem_contratos = prev_df.empty and score_df.empty

    if sem_contratos:
        st.warning("Previsões e scores dependem de contratos cadastrados em `analytics.contratos`.")
        st.info("Cadastre os contratos e execute o ETL novamente para ativar a inteligência.")
        return

    # ════════════════════════════════════════════════════════════
    # PREVISÕES DE ESTOURO
    # ════════════════════════════════════════════════════════════
    st.subheader("📈 Previsões de consumo — mês atual")

    if not prev_df.empty:
        vao_estourar = prev_df[prev_df["vai_estourar"] == True]
        ok = prev_df[prev_df["vai_estourar"] == False]

        k1, k2, k3 = st.columns(3)
        k1.metric("🔴 Vão estourar",   len(vao_estourar))
        k2.metric("🟢 Dentro do limite", len(ok))
        k3.metric("📅 Dias até fim do mês", int(prev_df["dias_ate_fim_mes"].iloc[0]) if not prev_df.empty else "—")

        # Gráfico de barras comparando atual vs previsto vs contratado
        fig = go.Figure()
        df_chart = prev_df.sort_values("pct_previsto", ascending=True).tail(15)

        fig.add_bar(
            x=df_chart["horas_ate_agora"],
            y=df_chart["client_name"],
            name="Atual",
            orientation="h",
            marker_color="#4e79a7",
        )
        fig.add_bar(
            x=df_chart["horas_previstas_fim"] - df_chart["horas_ate_agora"],
            y=df_chart["client_name"],
            name="Previsão adicional",
            orientation="h",
            marker_color="#f28e2b",
            opacity=0.7,
        )
        # Linha do contrato
        for _, row in df_chart.iterrows():
            if row["horas_contratadas"]:
                fig.add_vline(
                    x=row["horas_contratadas"], line_dash="dot",
                    line_color="#C00000", opacity=0.3,
                )

        fig.update_layout(
            barmode="stack",
            height=max(300, len(df_chart) * 30),
            margin=dict(l=0, r=20, t=10, b=0),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=-0.2),
        )
        st.plotly_chart(fig, width="stretch")

        # Tabela de previsões
        df_show = prev_df[[
            "client_name", "horas_ate_agora", "horas_previstas_fim",
            "horas_contratadas", "pct_previsto", "vai_estourar", "dias_ate_fim_mes"
        ]].copy()
        df_show.columns = ["Cliente", "Horas atuais", "Previsão fim mês",
                           "Contratadas", "% Previsto", "Vai estourar", "Dias restantes"]
        df_show["Horas atuais"]     = df_show["Horas atuais"].apply(lambda x: f"{x:.1f}h")
        df_show["Previsão fim mês"] = df_show["Previsão fim mês"].apply(lambda x: f"{x:.1f}h")
        df_show["Contratadas"]      = df_show["Contratadas"].apply(lambda x: f"{x:.1f}h" if x else "—")
        df_show["% Previsto"]       = df_show["% Previsto"].apply(lambda x: f"{x:.1f}%" if x else "—")
        df_show["Vai estourar"]     = df_show["Vai estourar"].apply(lambda x: "🔴 SIM" if x else "🟢 Não")
        st.dataframe(df_show, width="stretch", hide_index=True)
    else:
        st.info("Nenhuma previsão disponível para o mês atual.")

    st.markdown("---")

    # ════════════════════════════════════════════════════════════
    # SCORE DE RISCO
    # ════════════════════════════════════════════════════════════
    st.subheader("🎯 Score de risco por cliente")

    if not score_df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🔴 CRÍTICO", int((score_df["classificacao"] == "CRITICO").sum()))
        c2.metric("🟠 ALTO",    int((score_df["classificacao"] == "ALTO").sum()))
        c3.metric("🟡 MÉDIO",   int((score_df["classificacao"] == "MEDIO").sum()))
        c4.metric("🟢 BAIXO",   int((score_df["classificacao"] == "BAIXO").sum()))

        col_l, col_r = st.columns([3, 2])

        with col_l:
            df_chart = score_df.sort_values("score_total", ascending=True).tail(15)
            fig2 = px.bar(
                df_chart,
                x="score_total",
                y="client_name",
                orientation="h",
                color="classificacao",
                color_discrete_map=_COR_CLASS,
                text="score_total",
                labels={"score_total": "Score", "client_name": "Cliente", "classificacao": "Risco"},
            )
            fig2.update_traces(texttemplate="%{text:.0f}", textposition="outside")
            fig2.update_layout(
                height=max(300, len(df_chart) * 30),
                margin=dict(l=0, r=40, t=10, b=0),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=-0.25),
            )
            st.plotly_chart(fig2, width="stretch")

        with col_r:
            st.subheader("Distribuição de risco")
            class_count = score_df["classificacao"].value_counts().reset_index()
            class_count.columns = ["Classificação", "Qtd"]
            fig3 = px.pie(
                class_count,
                names="Classificação",
                values="Qtd",
                color="Classificação",
                color_discrete_map=_COR_CLASS,
                hole=0.4,
            )
            fig3.update_layout(
                height=280,
                margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=-0.3),
            )
            st.plotly_chart(fig3, width="stretch")

        # Tabela detalhada
        df_show = score_df[[
            "client_name", "classificacao", "score_total",
            "score_historico_estouro", "score_tendencia",
            "score_volatilidade", "meses_analisados",
            "meses_estourados", "media_consumo_pct", "tendencia_pct_mes"
        ]].copy()
        df_show.columns = [
            "Cliente", "Risco", "Score",
            "Componente Histórico", "Componente Tendência",
            "Componente Volatilidade", "Meses analisados",
            "Meses estourados", "Média consumo %", "Tendência %/mês"
        ]
        df_show = df_show.sort_values("Score", ascending=False)
        st.dataframe(df_show, width="stretch", hide_index=True)
    else:
        st.info("Score ainda não calculado. Execute o ETL com contratos cadastrados.")

    st.markdown("---")

    # ════════════════════════════════════════════════════════════
    # SUGESTÕES DE UPGRADE
    # ════════════════════════════════════════════════════════════
    st.subheader("💡 Sugestões de upgrade de plano")

    if not upgrade_df.empty:
        for _, row in upgrade_df.iterrows():
            cor = _COR_CLASS.get(row.get("risco", "BAIXO"), "#888")
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.markdown(f"**{row['client_name']}**")
                c1.caption(f"Plano atual: {row['horas_contratadas_atual']:.0f}h/mês")
                c2.metric("Média 6 meses", f"{row['media_horas_6m']:.1f}h")
                c2.metric("Meses estourados", int(row["meses_estourados"]))
                c3.metric("Sugestão", f"{row['horas_sugeridas']:.0f}h/mês",
                          delta=f"+{row['horas_sugeridas'] - row['horas_contratadas_atual']:.0f}h")
                st.markdown(
                    f'<small style="color:{cor}">⚠️ {row["justificativa"]}</small>',
                    unsafe_allow_html=True,
                )
    else:
        st.info("Nenhuma sugestão de upgrade no momento. Todos os clientes estão dentro do esperado.")
