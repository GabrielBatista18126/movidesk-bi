"""Página: SLA — Métricas de tempo de resposta e resolução."""
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from dashboard import db


def _cor_risco(risco: str) -> str:
    return {
        "ESTOURADO": "#c0392b",
        "CRITICO":   "#e74c3c",
        "ALTO":      "#e67e22",
        "MEDIO":     "#f39c12",
    }.get(risco, "#7f8c8d")


def _fmt_horas(h):
    if h is None or pd.isna(h):
        return "—"
    if h < 1:
        return f"{int(h * 60)} min"
    if h < 24:
        return f"{h:.1f} h"
    return f"{h/24:.1f} d"


def _fmt_min_restante(m):
    if m is None or pd.isna(m):
        return "—"
    if m < 0:
        return f"estourou há {_fmt_horas(abs(m)/60)}"
    if m < 60:
        return f"{int(m)} min"
    return _fmt_horas(m / 60)


def render():
    st.title("📏 SLA & Tempo de Resposta")

    # ── KPIs ──────────────────────────────────────────────────────
    kpis = db.sla_kpis()
    if kpis.empty:
        st.info("Sem dados de SLA ainda. Rode o ETL full para carregar os campos novos.")
        return

    row = kpis.iloc[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Tickets no mês", int(row.get("tickets_mes") or 0))
    c2.metric("TTFR médio", _fmt_horas(row.get("ttfr_medio_horas")))
    c3.metric("TTR médio", _fmt_horas(row.get("ttr_medio_horas")))
    pct_resp = row.get("pct_sla_response_ok")
    pct_sol  = row.get("pct_sla_solution_ok")
    c4.metric("% SLA resposta OK", f"{pct_resp:.1f}%" if pct_resp is not None else "—")
    c5.metric("% SLA resolução OK", f"{pct_sol:.1f}%" if pct_sol is not None else "—")

    st.markdown("---")

    # ── Tickets em risco ──────────────────────────────────────────
    st.subheader("🚨 Tickets em risco de estourar SLA (próximas 24h)")
    risco = db.tickets_em_risco_sla()
    if risco.empty:
        st.success("Nenhum ticket em risco no momento.")
    else:
        df = risco.copy()
        df["Ticket"] = "#" + df["ticket_id"].astype(str)
        df["Tempo restante"] = df["minutos_restantes"].apply(_fmt_min_restante)
        df_show = df.rename(columns={
            "subject":  "Assunto",
            "cliente":  "Cliente",
            "urgency":  "Urgência",
            "category": "Categoria",
            "risco":    "Risco",
        })[["Ticket", "Assunto", "Cliente", "Urgência", "Categoria", "Tempo restante", "Risco"]]

        def _colorize(val):
            return f"color: {_cor_risco(val)}; font-weight: 700"

        styled = df_show.style.map(_colorize, subset=["Risco"])
        st.dataframe(styled, width="stretch", hide_index=True,
                     height=min(500, 40 + len(df_show) * 35))

    st.markdown("---")

    # ── Série temporal ────────────────────────────────────────────
    st.subheader("📈 % SLA cumprido por dia (últimos 30 dias)")
    serie = db.sla_serie_temporal()
    if not serie.empty:
        fig = px.line(
            serie, x="data", y="pct_sla",
            markers=True,
            labels={"data": "Data", "pct_sla": "% SLA OK"},
        )
        fig.update_traces(line=dict(color="#3498db", width=2))
        fig.add_hline(y=95, line_dash="dash", line_color="#2ecc71",
                      annotation_text="Meta 95%", annotation_position="top right")
        fig.update_yaxes(range=[0, 105])
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Sem dados no período.")

    st.markdown("---")

    # ── Ranking por cliente ───────────────────────────────────────
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🏢 SLA por cliente (90 dias)")
        por_cliente = db.sla_por_cliente()
        if por_cliente.empty:
            st.caption("Sem dados suficientes.")
        else:
            df = por_cliente.copy()
            df["TTR médio"] = df["ttr_medio"].apply(_fmt_horas)
            df["% SLA OK"]  = df["pct_sla_ok"].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
            st.dataframe(
                df.rename(columns={
                    "cliente": "Cliente",
                    "total_tickets": "Tickets",
                })[["Cliente", "Tickets", "TTR médio", "% SLA OK"]],
                width="stretch", hide_index=True,
                height=min(500, 40 + len(df) * 35),
            )

    with col_b:
        st.subheader("📂 SLA por categoria (90 dias)")
        por_cat = db.sla_por_categoria()
        if por_cat.empty:
            st.caption("Sem dados.")
        else:
            df = por_cat.copy()
            df["TTR médio"] = df["ttr_medio"].apply(_fmt_horas)
            df["% SLA OK"]  = df["pct_sla_ok"].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
            st.dataframe(
                df.rename(columns={
                    "categoria": "Categoria",
                    "total_tickets": "Tickets",
                })[["Categoria", "Tickets", "TTR médio", "% SLA OK"]],
                width="stretch", hide_index=True,
                height=min(500, 40 + len(df) * 35),
            )
