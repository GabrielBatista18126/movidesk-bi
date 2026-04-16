"""Página: Relatórios para exportação (CSV, XLSX, PDF)."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st

from dashboard import db


REPORTS = {
    "Resumo Executivo Mensal": "resumo_executivo",
    "Consumo por Cliente": "consumo_cliente",
    "Alertas de Receita": "alertas_receita",
    "SLA por Cliente e Categoria": "sla",
    "Produtividade por Analista": "produtividade",
    "Retrabalho e Reabertura": "retrabalho",
    "Backlog de Tickets Abertos": "backlog",
    "Inteligência e Upgrade": "inteligencia",
}


def _filtrar_clientes(df: pd.DataFrame, clientes: list[str], col: str = "client_name") -> pd.DataFrame:
    if df.empty or not clientes or col not in df.columns:
        return df
    return df[df[col].isin(clientes)].copy()


def _query_consumo_contrato_mes(mes_ref: str) -> pd.DataFrame:
    return db.query(
        """
        WITH periodo AS (
            SELECT TO_DATE(:mes_ref || '-01', 'YYYY-MM-DD') AS dt_inicio
        ),
        consumo AS (
            SELECT
                COALESCE(te.organization_id, te.client_id)         AS client_id,
                COALESCE(te.organization_name, te.client_name, '') AS client_name,
                SUM(te.hours_spent)                                AS horas_consumidas,
                COUNT(DISTINCT te.ticket_id)                       AS qtd_tickets,
                COUNT(te.id)                                       AS qtd_lancamentos
            FROM raw.time_entries te
            CROSS JOIN periodo p
            WHERE te.entry_date >= p.dt_inicio
              AND te.entry_date < (p.dt_inicio + INTERVAL '1 month')
              AND te.hours_spent > 0
            GROUP BY 1, 2
        ),
        contrato_mes AS (
            SELECT DISTINCT ON (COALESCE(c.organization_id, c.client_id))
                COALESCE(c.organization_id, c.client_id) AS client_id,
                c.client_name,
                c.plano_nome,
                c.horas_contratadas,
                c.valor_mensal,
                c.hora_extra_valor
            FROM analytics.contratos c
            CROSS JOIN periodo p
            WHERE c.ativo = TRUE
              AND c.vigencia_inicio <= (p.dt_inicio + INTERVAL '1 month - 1 day')::date
              AND (c.vigencia_fim IS NULL OR c.vigencia_fim >= p.dt_inicio)
            ORDER BY COALESCE(c.organization_id, c.client_id),
                     c.vigencia_inicio DESC,
                     c.updated_at DESC NULLS LAST,
                     c.id DESC
        )
        SELECT
            con.client_id,
            con.client_name,
            cm.plano_nome,
            cm.horas_contratadas,
            ROUND(con.horas_consumidas::numeric, 2) AS horas_consumidas,
            con.qtd_tickets,
            con.qtd_lancamentos,
            CASE
                WHEN cm.horas_contratadas > 0
                THEN ROUND((con.horas_consumidas / cm.horas_contratadas * 100)::numeric, 1)
            END AS pct_consumo,
            ROUND(GREATEST(con.horas_consumidas - COALESCE(cm.horas_contratadas, 0), 0)::numeric, 2) AS horas_excedentes,
            ROUND(GREATEST(COALESCE(cm.horas_contratadas, 0) - con.horas_consumidas, 0)::numeric, 2) AS horas_disponiveis,
            ROUND(COALESCE(cm.hora_extra_valor, cm.valor_mensal / NULLIF(cm.horas_contratadas, 0), 0)::numeric, 2) AS valor_hora_ref,
            ROUND(
                (GREATEST(con.horas_consumidas - COALESCE(cm.horas_contratadas, 0), 0)
                 * COALESCE(cm.hora_extra_valor, cm.valor_mensal / NULLIF(cm.horas_contratadas, 0), 0))::numeric,
                2
            ) AS receita_excedente,
            CASE
                WHEN cm.horas_contratadas IS NULL THEN 'SEM_CONTRATO'
                WHEN con.horas_consumidas >= cm.horas_contratadas THEN 'ESTOURADO'
                WHEN con.horas_consumidas >= cm.horas_contratadas * 0.8 THEN 'CRITICO'
                WHEN con.horas_consumidas >= cm.horas_contratadas * 0.6 THEN 'ATENCAO'
                ELSE 'NORMAL'
            END AS status_consumo
        FROM consumo con
        LEFT JOIN contrato_mes cm ON cm.client_id = con.client_id
        ORDER BY con.horas_consumidas DESC
        """,
        {"mes_ref": mes_ref},
    )


def _report_resumo_executivo(mes_ref: str, clientes: list[str]) -> dict[str, pd.DataFrame]:
    consumo = _filtrar_clientes(_query_consumo_contrato_mes(mes_ref), clientes)
    sla = _filtrar_clientes(
        db.query(
            """
            SELECT ano_mes, client_id, client_name, total_tickets, tickets_resolvidos,
                   tmr_horas, tmr_dias, taxa_resolucao_pct
            FROM analytics.v_sla_performance
            WHERE ano_mes = :mes_ref
            ORDER BY total_tickets DESC
            """,
            {"mes_ref": mes_ref},
        ),
        clientes,
    )
    retrabalho = _filtrar_clientes(
        db.query(
            """
            SELECT ano_mes, client_id, client_name, total_tickets, tickets_reabertos, taxa_retrabalho_pct
            FROM analytics.v_retrabalho
            WHERE ano_mes = :mes_ref
            ORDER BY taxa_retrabalho_pct DESC NULLS LAST
            """,
            {"mes_ref": mes_ref},
        ),
        clientes,
    )
    backlog = _filtrar_clientes(db.tickets_abertos(), clientes)

    resumo = pd.DataFrame([
        {
            "mes_referencia": mes_ref,
            "total_horas": round(pd.to_numeric(consumo.get("horas_consumidas"), errors="coerce").fillna(0).sum(), 2),
            "total_lancamentos": int(pd.to_numeric(consumo.get("qtd_lancamentos"), errors="coerce").fillna(0).sum()),
            "total_tickets": int(pd.to_numeric(consumo.get("qtd_tickets"), errors="coerce").fillna(0).sum()),
            "clientes_com_consumo": int(consumo["client_name"].nunique()) if not consumo.empty else 0,
            "clientes_estourados": int((consumo.get("status_consumo") == "ESTOURADO").sum()) if not consumo.empty else 0,
            "receita_excedente": round(pd.to_numeric(consumo.get("receita_excedente"), errors="coerce").fillna(0).sum(), 2),
            "sla_medio_pct": round(pd.to_numeric(sla.get("taxa_resolucao_pct"), errors="coerce").dropna().mean(), 2)
            if not sla.empty else None,
            "retrabalho_medio_pct": round(pd.to_numeric(retrabalho.get("taxa_retrabalho_pct"), errors="coerce").dropna().mean(), 2)
            if not retrabalho.empty else None,
            "tickets_abertos": int(len(backlog)),
        }
    ])

    return {
        "Resumo Executivo": resumo,
        "Consumo por Cliente": consumo,
        "SLA por Cliente": sla,
        "Retrabalho": retrabalho,
    }


def _report_consumo_cliente(mes_ref: str, clientes: list[str]) -> dict[str, pd.DataFrame]:
    consumo = _filtrar_clientes(_query_consumo_contrato_mes(mes_ref), clientes)
    return {"Consumo por Cliente": consumo}


def _report_alertas_receita(mes_ref: str, clientes: list[str]) -> dict[str, pd.DataFrame]:
    consumo = _filtrar_clientes(_query_consumo_contrato_mes(mes_ref), clientes)
    alertas = consumo[consumo["pct_consumo"].fillna(0) >= 80].copy()
    if not alertas.empty:
        alertas["tipo_oportunidade"] = alertas.apply(
            lambda r: "EXCEDENTE_ATUAL" if pd.notna(r["horas_excedentes"]) and r["horas_excedentes"] > 0 else "RISCO",
            axis=1,
        )
    return {"Alertas de Receita": alertas}


def _report_sla(mes_ref: str, clientes: list[str]) -> dict[str, pd.DataFrame]:
    sla_cliente = _filtrar_clientes(
        db.query(
            """
            SELECT ano_mes, client_id, client_name, total_tickets, tickets_resolvidos,
                   tmr_horas, tmr_dias, tickets_urgentes, taxa_resolucao_pct
            FROM analytics.v_sla_performance
            WHERE ano_mes = :mes_ref
            ORDER BY taxa_resolucao_pct ASC NULLS LAST, total_tickets DESC
            """,
            {"mes_ref": mes_ref},
        ),
        clientes,
    )

    sla_categoria = db.query(
        """
        SELECT
            COALESCE(NULLIF(category, ''), 'Sem categoria') AS categoria,
            COUNT(*) AS total_tickets,
            ROUND(AVG(ttr_horas)::numeric, 2) AS ttr_medio_horas,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE dentro_sla_solution = TRUE)
                / NULLIF(COUNT(*) FILTER (WHERE dentro_sla_solution IS NOT NULL), 0),
                1
            ) AS pct_sla_ok
        FROM analytics.v_sla_tickets
        WHERE TO_CHAR(created_date, 'YYYY-MM') = :mes_ref
        GROUP BY 1
        ORDER BY total_tickets DESC
        """,
        {"mes_ref": mes_ref},
    )

    return {
        "SLA por Cliente": sla_cliente,
        "SLA por Categoria": sla_categoria,
    }


def _report_produtividade(mes_ref: str, clientes: list[str]) -> dict[str, pd.DataFrame]:
    prod = db.query(
        """
        SELECT
            ano_mes,
            agent_id,
            agent_name,
            team,
            horas_lancadas,
            qtd_tickets,
            qtd_clientes,
            media_horas_por_ticket,
            tickets_por_hora,
            pct_horas_time
        FROM analytics.v_produtividade_detalhada
        WHERE ano_mes = :mes_ref
        ORDER BY horas_lancadas DESC
        """,
        {"mes_ref": mes_ref},
    )
    return {"Produtividade por Analista": prod}


def _report_retrabalho(mes_ref: str, clientes: list[str]) -> dict[str, pd.DataFrame]:
    retrabalho = _filtrar_clientes(
        db.query(
            """
            SELECT ano_mes, client_id, client_name, total_tickets, tickets_reabertos, taxa_retrabalho_pct
            FROM analytics.v_retrabalho
            WHERE ano_mes = :mes_ref
            ORDER BY taxa_retrabalho_pct DESC NULLS LAST
            """,
            {"mes_ref": mes_ref},
        ),
        clientes,
    )
    reabertos = _filtrar_clientes(db.tickets_reabertos(), clientes, col="cliente")
    return {
        "Retrabalho por Cliente": retrabalho,
        "Tickets Reabertos": reabertos,
    }


def _report_backlog(mes_ref: str, clientes: list[str]) -> dict[str, pd.DataFrame]:
    backlog = _filtrar_clientes(db.tickets_abertos(), clientes)
    resumo_owner = pd.DataFrame()
    if not backlog.empty:
        resumo_owner = (
            backlog.groupby(["owner_name", "owner_team"], dropna=False)
            .agg(
                tickets_abertos=("ticket_id", "count"),
                dias_aberto_medio=("dias_aberto", "mean"),
                horas_total=("time_spent_total_hours", "sum"),
            )
            .reset_index()
            .sort_values("tickets_abertos", ascending=False)
        )
    return {
        "Backlog Detalhado": backlog,
        "Resumo por Responsável": resumo_owner,
    }


def _report_inteligencia(mes_ref: str, clientes: list[str]) -> dict[str, pd.DataFrame]:
    previsoes = _filtrar_clientes(
        db.query(
            """
            SELECT *
            FROM analytics.previsoes_consumo
            WHERE mes_referencia = :mes_ref
            ORDER BY pct_previsto DESC NULLS LAST
            """,
            {"mes_ref": mes_ref},
        ),
        clientes,
    )
    scores = _filtrar_clientes(db.scores(), clientes)
    upgrades = _filtrar_clientes(db.sugestoes_upgrade(), clientes)

    return {
        "Previsões": previsoes,
        "Scores": scores,
        "Sugestões de Upgrade": upgrades,
    }


def _build_report(report_key: str, mes_ref: str, clientes: list[str]) -> dict[str, pd.DataFrame]:
    builders = {
        "resumo_executivo": _report_resumo_executivo,
        "consumo_cliente": _report_consumo_cliente,
        "alertas_receita": _report_alertas_receita,
        "sla": _report_sla,
        "produtividade": _report_produtividade,
        "retrabalho": _report_retrabalho,
        "backlog": _report_backlog,
        "inteligencia": _report_inteligencia,
    }
    return builders[report_key](mes_ref, clientes)


def _first_non_empty_sheet(sheets: dict[str, pd.DataFrame]) -> tuple[str | None, pd.DataFrame | None]:
    for name, df in sheets.items():
        if not df.empty:
            return name, df
    return None, None


def _to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes | None:
    try:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for sheet_name, df in sheets.items():
                safe_name = sheet_name[:31]
                export_df = df if not df.empty else pd.DataFrame({"info": ["Sem dados para os filtros selecionados."]})
                export_df.to_excel(writer, index=False, sheet_name=safe_name)
        return output.getvalue()
    except Exception:
        return None


def _to_pdf_bytes(title: str, mes_ref: str, sheets: dict[str, pd.DataFrame], clientes: list[str]) -> bytes | None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception:
        return None

    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"Movidesk BI — {title}", styles["Heading1"]),
        Paragraph(f"Mês de referência: {mes_ref}", styles["Normal"]),
        Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]),
    ]

    if clientes:
        story.append(Paragraph(f"Clientes filtrados: {', '.join(clientes)}", styles["Normal"]))

    story.append(Spacer(1, 12))

    for idx, (sheet_name, df) in enumerate(sheets.items()):
        story.append(Paragraph(sheet_name, styles["Heading3"]))
        if df.empty:
            story.append(Paragraph("Sem dados para os filtros selecionados.", styles["Normal"]))
        else:
            cols = list(df.columns[:8])
            rows = df[cols].head(30)
            data = [cols]
            for _, row in rows.iterrows():
                data.append([
                    ("-" if pd.isna(row[c]) else str(row[c]))[:42]
                    for c in cols
                ])

            table = Table(data, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(table)
            if len(df) > 30:
                story.append(Paragraph(f"Prévia no PDF: 30 de {len(df)} linhas.", styles["Italic"]))

        if idx < len(sheets) - 1:
            story.append(PageBreak())

    doc.build(story)
    return output.getvalue()


def render():
    st.title("📑 Relatórios para Exportação")
    st.caption("Gere relatórios operacionais e executivos com exportação em CSV, XLSX e PDF.")

    meses = db.meses_disponiveis()
    if not meses:
        st.info("Ainda não há dados para gerar relatórios.")
        return

    col1, col2, col3 = st.columns([2, 1, 3])
    with col1:
        report_label = st.selectbox("Tipo de relatório", options=list(REPORTS.keys()))
    with col2:
        mes_ref = st.selectbox("Mês", options=meses, index=0)
    with col3:
        clientes_base = db.resumo_mes_atual(mes_ref)
        clientes_opts = sorted(clientes_base["client_name"].unique().tolist()) if not clientes_base.empty else []
        clientes_sel = st.multiselect("Filtrar por cliente", options=clientes_opts, default=[])

    with st.spinner("Gerando relatório..."):
        report_key = REPORTS[report_label]
        sheets = _build_report(report_key, mes_ref, clientes_sel)

    if not sheets or all(df.empty for df in sheets.values()):
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
        return

    st.markdown("---")
    st.subheader("Exportação")

    base_file = f"movidesk_{report_key}_{mes_ref}".replace("-", "_")
    first_name, first_df = _first_non_empty_sheet(sheets)
    excel_bytes = _to_excel_bytes(sheets)
    pdf_bytes = _to_pdf_bytes(report_label, mes_ref, sheets, clientes_sel)

    e1, e2, e3 = st.columns(3)
    with e1:
        if first_df is not None:
            st.download_button(
                "⬇️ Baixar CSV",
                data=first_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"{base_file}_{first_name.lower().replace(' ', '_')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
    with e2:
        if excel_bytes:
            st.download_button(
                "⬇️ Baixar XLSX",
                data=excel_bytes,
                file_name=f"{base_file}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    with e3:
        if pdf_bytes:
            st.download_button(
                "⬇️ Baixar PDF",
                data=pdf_bytes,
                file_name=f"{base_file}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.button("PDF indisponível", disabled=True, use_container_width=True)

    st.markdown("---")
    st.subheader("Prévia do relatório")

    tabs = st.tabs(list(sheets.keys()))
    for tab, (sheet_name, df) in zip(tabs, sheets.items()):
        with tab:
            st.caption(f"{len(df)} linha(s)")
            if df.empty:
                st.info("Sem dados para este bloco.")
            else:
                preview = df.head(1000)
                st.dataframe(preview, width="stretch", hide_index=True)
                if len(df) > 1000:
                    st.caption("Prévia limitada a 1000 linhas.")
