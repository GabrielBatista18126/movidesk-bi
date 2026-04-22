"""Página: Visão Geral — Layout baseado no dashboard de referência."""
import re
import unicodedata

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from dashboard import db


# ── Paleta fixa de cores para analistas ────────────────────────
_CORES_ANALISTAS = [
    "#3498db", "#2ecc71", "#e67e22", "#1abc9c", "#9b59b6",
    "#e74c3c", "#f39c12", "#e91e63", "#00bcd4", "#8bc34a",
]


def _safe_float(value, default: float = 0.0) -> float:
    num = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(num) if pd.notna(num) else default


def _safe_int(value, default: int = 0) -> int:
    num = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return int(num) if pd.notna(num) else default


def _risco_cliente(horas: float, total: float) -> str:
    pct = horas / total * 100 if total > 0 else 0
    if pct >= 20:
        return "alto"
    elif pct >= 10:
        return "médio"
    return "baixo"


def _cor_risco(risco: str) -> str:
    return {"alto": "#e74c3c", "médio": "#f39c12", "baixo": "#2ecc71"}.get(risco, "#999")


def _slug_tipo(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").lower()
    return slug or "sem_tipo"


def render():
    # ── Carrega dados (sem filtro) ──────────────────────────────
    horas_dia_raw = db.horas_por_dia_agente()

    # ── Filtros ──────────────────────────────────────────────────
    datas_disp = sorted(horas_dia_raw["data"].unique().tolist()) if not horas_dia_raw.empty else []
    analistas_disp = sorted(horas_dia_raw["analista"].unique().tolist()) if not horas_dia_raw.empty else []

    # Carrega lancamentos detalhados
    lancamentos_raw = db.lancamentos_detalhados_mes()

    with st.container():
        fc1, fc2, fc3 = st.columns([1, 1, 1])
        with fc1:
            opcoes_data = ["Todos os dias"] + [str(d) for d in datas_disp]
            opcao_data = st.selectbox("Data:", opcoes_data, key="filtro_data")
        with fc2:
            opcoes_analista = ["Todos os analistas"] + analistas_disp
            opcao_analista = st.selectbox("Analista:", opcoes_analista, key="filtro_analista")
        with fc3:
            # Contador de registros filtrados
            _lc = lancamentos_raw.copy() if not lancamentos_raw.empty else pd.DataFrame()
            if not _lc.empty and opcao_analista != "Todos os analistas":
                _lc = _lc[_lc["analista"] == opcao_analista]
            if not _lc.empty and opcao_data != "Todos os dias":
                _lc = _lc[_lc["data"].astype(str) == opcao_data]
            st.markdown(f"<br><span style='color:#888'>{len(_lc)} registro(s)</span>",
                        unsafe_allow_html=True)

    # ── Aplica filtros ──────────────────────────────────────────
    filtro_data_ativo = opcao_data != "Todos os dias"
    filtro_analista_ativo = opcao_analista != "Todos os analistas"

    analista_filtro = opcao_analista if filtro_analista_ativo else None
    data_filtro = opcao_data if filtro_data_ativo else None

    horas_dia = db.horas_por_dia_agente(analista=analista_filtro, data_ref=data_filtro)
    horas_cliente = db.horas_por_cliente_mes(analista=analista_filtro, data_ref=data_filtro)
    horas_analista = db.horas_por_analista_mes(analista=analista_filtro, data_ref=data_filtro)
    tipo_prob = db.tipo_problema_mes(analista=analista_filtro, data_ref=data_filtro)
    prioridade = db.prioridade_mes(analista=analista_filtro, data_ref=data_filtro)

    kpis = db.visao_geral_kpis(analista=analista_filtro, data_ref=data_filtro)
    total_horas = _safe_float(kpis["total_horas"].iloc[0]) if not kpis.empty else 0
    total_apontamentos = _safe_int(kpis["total_apontamentos"].iloc[0]) if not kpis.empty else 0
    total_clientes = _safe_int(kpis["total_clientes"].iloc[0]) if not kpis.empty else 0
    total_analistas = _safe_int(kpis["total_analistas"].iloc[0]) if not kpis.empty else 0

    # ── Banner de alerta ─────────────────────────────────────────
    if not horas_cliente.empty and not horas_analista.empty:
        top_cli = horas_cliente.iloc[0]
        top_ana = horas_analista.iloc[0]
        pct_cli = top_cli["horas"] / total_horas * 100 if total_horas > 0 else 0
        pct_ana = top_ana["horas"] / total_horas * 100 if total_horas > 0 else 0
        st.warning(
            f"⚠ Maior cliente: **{top_cli['cliente']}** — {top_cli['horas']}h ({pct_cli:.0f}%). "
            f"Maior carga: **{top_ana['analista']}** — {top_ana['horas']}h ({pct_ana:.0f}%)."
        )

    # ── KPIs ─────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total de horas", f"{total_horas:.1f}h", help="período completo")
    k2.metric("Apontamentos", f"{total_apontamentos}", help="registros")
    k3.metric("Clientes", f"{total_clientes}", help="com horas")
    k4.metric("Analistas", f"{total_analistas}", help="ativos")

    # ── Horas lançadas por colaborador por dia ───────────────────
    st.markdown("---")
    if not horas_dia.empty:
        st.subheader("Horas lançadas por colaborador por dia")
        analistas = horas_dia["analista"].unique().tolist()
        cor_map = {a: _CORES_ANALISTAS[i % len(_CORES_ANALISTAS)] for i, a in enumerate(analistas)}

        pivot = horas_dia.pivot_table(index="data", columns="analista", values="horas", fill_value=0)
        fig_dia = go.Figure()
        for analista in analistas:
            if analista in pivot.columns:
                fig_dia.add_trace(go.Bar(
                    name=analista,
                    x=pivot.index,
                    y=pivot[analista],
                    marker_color=cor_map[analista],
                ))
        fig_dia.update_layout(
            barmode="group",
            height=380,
            margin=dict(l=0, r=0, t=10, b=40),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            xaxis=dict(
                tickformat="%d/%m/%Y",
                showgrid=False,
                title="Data",
            ),
            yaxis=dict(
                gridcolor="rgba(0,0,0,0.08)",
                title="Horas",
            ),
        )
        st.plotly_chart(fig_dia, width="stretch")

    # ── Horas por cliente + Tipo de problema ─────────────────────
    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Horas por cliente")
        if not horas_cliente.empty:
            fig_cli = px.bar(
                horas_cliente,
                x="cliente",
                y="horas",
                color="cliente",
                labels={"cliente": "", "horas": "Horas"},
                text="horas",
            )
            fig_cli.update_traces(texttemplate="%{text:.1f}", textposition="outside")
            fig_cli.update_layout(
                showlegend=False,
                height=350,
                margin=dict(l=0, r=0, t=10, b=80),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(tickangle=-35, showgrid=False),
                yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
            )
            st.plotly_chart(fig_cli, width="stretch")

    with col2:
        st.subheader("Tipo de problema")
        if not tipo_prob.empty:
            fig_tipo = px.pie(
                tipo_prob,
                names="tipo",
                values="horas",
                hole=0.45,
                custom_data=["tipo"],
            )
            fig_tipo.update_layout(
                height=350,
                margin=dict(l=0, r=0, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(font=dict(size=10)),
            )
            evento_tipo = st.plotly_chart(
                fig_tipo,
                width="stretch",
                key="visao_tipo_demanda_chart",
                on_select="rerun",
                selection_mode="points",
            )

            pontos = []
            if evento_tipo and evento_tipo.selection:
                pontos = evento_tipo.selection.get("points", [])

            if pontos:
                ponto = pontos[0]
                tipo_evento = None
                custom_data = ponto.get("customdata")
                if isinstance(custom_data, (list, tuple)) and custom_data:
                    tipo_evento = str(custom_data[0])
                elif ponto.get("label") is not None:
                    tipo_evento = str(ponto["label"])

                if tipo_evento:
                    st.session_state["visao_tipo_demanda_sel"] = tipo_evento

            tipo_selecionado = st.session_state.get("visao_tipo_demanda_sel")
            tipos_disponiveis = set(tipo_prob["tipo"].astype(str).tolist())

            if tipo_selecionado not in tipos_disponiveis:
                tipo_selecionado = None
                st.session_state["visao_tipo_demanda_sel"] = None

            if tipo_selecionado:
                st.caption(f"Tipo selecionado: **{tipo_selecionado}**")
                tickets_tipo = db.tickets_por_tipo_demanda_mes(
                    tipo=tipo_selecionado,
                    analista=analista_filtro,
                    data_ref=data_filtro,
                )

                if tickets_tipo.empty:
                    st.info("Nenhum ticket encontrado para o tipo selecionado nos filtros atuais.")
                else:
                    df_export = tickets_tipo.copy()
                    df_export["Ticket"] = "#" + df_export["ticket_id"].astype(str)
                    df_export = df_export.rename(columns={
                        "subject": "Título",
                        "cliente": "Cliente",
                    })[["Ticket", "Título", "Cliente"]]

                    st.dataframe(
                        df_export,
                        width="stretch",
                        hide_index=True,
                        height=min(420, 40 + len(df_export) * 35),
                    )

                    mes_ref_arquivo = pd.Timestamp.now().strftime("%Y_%m")
                    tipo_arquivo = _slug_tipo(tipo_selecionado)
                    st.download_button(
                        "Baixar CSV do tipo selecionado",
                        data=df_export.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"movidesk_tickets_tipo_{tipo_arquivo}_{mes_ref_arquivo}.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

                if st.button("Limpar seleção", key="limpar_tipo_demanda", use_container_width=True):
                    st.session_state["visao_tipo_demanda_sel"] = None
            else:
                st.caption("Clique em um tipo no gráfico para listar tickets e exportar CSV.")
        else:
            st.caption("Sem dados de tipo de problema para os filtros selecionados.")
    # ── Carga por analista + Prioridade ──────────────────────────
    st.markdown("---")
    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Carga por analista")
        if not horas_analista.empty:
            df_ana = horas_analista.copy()
            df_ana["pct"] = (df_ana["horas"] / total_horas * 100).round(0).astype(int)
            df_ana["label"] = df_ana["horas"].astype(str) + "h"
            fig_ana = px.bar(
                df_ana.sort_values("horas"),
                x="horas",
                y="analista",
                orientation="h",
                text="label",
                color_discrete_sequence=["#2ecc71"],
                labels={"analista": "", "horas": ""},
            )
            fig_ana.update_traces(textposition="inside", textfont_color="white")
            # Add pct annotation on the right
            for i, row in df_ana.sort_values("horas").reset_index(drop=True).iterrows():
                fig_ana.add_annotation(
                    x=row["horas"] + total_horas * 0.02,
                    y=row["analista"],
                    text=f"{row['pct']}%",
                    showarrow=False,
                    font=dict(size=11),
                )
            fig_ana.update_layout(
                showlegend=False,
                height=320,
                margin=dict(l=0, r=40, t=10, b=10),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=False, showticklabels=False),
                yaxis=dict(showgrid=False),
            )
            st.plotly_chart(fig_ana, width="stretch")

    with col4:
        st.subheader("Prioridade")
        if not prioridade.empty:
            fig_pri = px.pie(
                prioridade,
                names="prioridade",
                values="qtd_tickets",
                hole=0.45,
            )
            fig_pri.update_layout(
                height=320,
                margin=dict(l=0, r=0, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(font=dict(size=10)),
            )
            st.plotly_chart(fig_pri, width="stretch")

    # ── Detalhamento por cliente ─────────────────────────────────
    st.markdown("---")
    st.subheader("Detalhamento por cliente")
    if not horas_cliente.empty:
        df_det_cli = horas_cliente.copy()
        df_det_cli["pct"] = (df_det_cli["horas"] / total_horas * 100).round(0).astype(int).astype(str) + "%"
        df_det_cli["risco"] = df_det_cli["horas"].apply(lambda h: _risco_cliente(h, total_horas))
        df_det_cli["barra"] = df_det_cli["horas"] / df_det_cli["horas"].max()
        df_det_cli["horas_fmt"] = df_det_cli["horas"].apply(lambda h: f"{h:.1f}h")

        for _, row in df_det_cli.iterrows():
            c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 1, 4])
            c1.write(row["cliente"])
            c2.write(f"**{row['horas_fmt']}**")
            c3.write(row["pct"])
            cor = _cor_risco(row["risco"])
            c4.markdown(
                f'<span style="background:{cor};color:#fff;padding:2px 8px;'
                f'border-radius:4px;font-size:12px">{row["risco"]}</span>',
                unsafe_allow_html=True,
            )
            c5.progress(min(row["barra"], 1.0))

    # ── Detalhamento por analista ────────────────────────────────
    st.markdown("---")
    st.subheader("Detalhamento por analista")
    if not horas_analista.empty:
        df_det_ana = horas_analista.copy()
        df_det_ana["pct"] = (df_det_ana["horas"] / total_horas * 100).round(0).astype(int).astype(str) + "%"
        df_det_ana["status"] = "ok"
        df_det_ana["barra"] = df_det_ana["horas"] / df_det_ana["horas"].max()
        df_det_ana["horas_fmt"] = df_det_ana["horas"].apply(lambda h: f"{h:.1f}h")

        for _, row in df_det_ana.iterrows():
            c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 1, 4])
            c1.write(row["analista"])
            c2.write(f"**{row['horas_fmt']}**")
            c3.write(row["pct"])
            c4.markdown(
                '<span style="background:#2ecc71;color:#fff;padding:2px 8px;'
                'border-radius:4px;font-size:12px">ok</span>',
                unsafe_allow_html=True,
            )
            c5.progress(min(row["barra"], 1.0))

    # ── Lançamentos detalhados ──────────────────────────────────
    if filtro_analista_ativo and not lancamentos_raw.empty:
        st.markdown("---")
        lancamentos = lancamentos_raw[lancamentos_raw["analista"] == opcao_analista].copy()
        if filtro_data_ativo:
            lancamentos = lancamentos[lancamentos["data"].astype(str) == opcao_data]

        st.subheader("Lançamentos detalhados")
        st.caption(opcao_analista)

        if not lancamentos.empty:
            df_show = lancamentos.rename(columns={
                "data": "Data",
                "analista": "Analista",
                "cliente": "Cliente",
                "ticket": "Ticket",
                "horas": "Horas",
                "descricao": "Descrição da ação",
            })
            df_show["Data"] = df_show["Data"].astype(str)
            df_show["Horas"] = df_show["Horas"].apply(lambda h: f"{h:.1f}h")

            st.dataframe(
                df_show[["Data", "Analista", "Cliente", "Ticket", "Horas", "Descrição da ação"]],
                width="stretch",
                hide_index=True,
                height=min(700, 40 + len(df_show) * 35),
            )
        else:
            st.info("Nenhum lançamento encontrado para este filtro.")
