"""Página: Módulo de Contratos — CRUD e saldos do ciclo."""
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard import db


_TIPOS_CONTRATO = {
    "mensal_fixo":              "Mensal Fixo",
    "banco_horas_mensal":       "Banco de Horas Mensal",
    "banco_horas_trimestral":   "Banco de Horas Trimestral",
}


def _fmt_moeda(v):
    if v is None or pd.isna(v):
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _render_saldo():
    st.subheader("📊 Saldo do ciclo atual")
    saldo = db.saldo_contratos()
    if saldo.empty:
        st.info("Nenhum contrato ativo com saldo calculado.")
        return

    # KPIs
    total_contratados = saldo["horas_contratadas"].sum()
    total_consumido   = saldo["horas_consumidas"].sum()
    total_excedente   = saldo["horas_excedentes"].sum()
    total_faturamento = saldo["faturamento_excedente"].sum()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Horas contratadas", f"{total_contratados:.0f}h")
    k2.metric("Horas consumidas",  f"{total_consumido:.1f}h")
    k3.metric("Horas excedentes",  f"{total_excedente:.1f}h")
    k4.metric("Faturamento excedente", _fmt_moeda(total_faturamento))

    # Tabela
    df = saldo.copy()
    df["% Utilização"] = df["pct_utilizado"].apply(
        lambda v: f"{v:.1f}%" if pd.notna(v) else "—"
    )
    df["Status"] = df["pct_utilizado"].apply(
        lambda v: "🔴 Estourado" if pd.notna(v) and v >= 100
        else "🟡 Alto"    if pd.notna(v) and v >= 80
        else "🟢 Normal"
    )
    df["Fat. excedente"] = df["faturamento_excedente"].apply(_fmt_moeda)

    st.dataframe(
        df.rename(columns={
            "client_name":        "Cliente",
            "plano_nome":         "Plano",
            "tipo_contrato":      "Tipo",
            "horas_contratadas":  "Contratadas",
            "horas_consumidas":   "Consumidas",
            "horas_saldo":        "Saldo",
            "horas_excedentes":   "Excedentes",
            "ciclo_inicio":       "Início ciclo",
            "ciclo_fim":          "Fim ciclo",
        })[[
            "Cliente", "Plano", "Tipo",
            "Contratadas", "Consumidas", "Saldo", "Excedentes",
            "% Utilização", "Status", "Fat. excedente",
            "Início ciclo", "Fim ciclo",
        ]],
        width="stretch", hide_index=True,
        height=min(500, 40 + len(df) * 35),
    )

    # Gráfico barras
    if len(df) > 0:
        st.markdown("### Consumo × contratado")
        df_plot = df.sort_values("pct_utilizado", ascending=True).tail(20)
        fig = px.bar(
            df_plot,
            x=["horas_consumidas", "horas_saldo"],
            y="client_name", orientation="h",
            color_discrete_map={
                "horas_consumidas": "#3498db",
                "horas_saldo":      "#95a5a6",
            },
            labels={"value": "Horas", "client_name": "Cliente", "variable": ""},
        )
        fig.update_layout(
            barmode="stack",
            height=max(300, len(df_plot) * 28),
            margin=dict(l=0, r=0, t=10, b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, width="stretch")


def _render_lista_contratos():
    st.subheader("📋 Contratos cadastrados")
    contratos = db.listar_contratos()
    if contratos.empty:
        st.info("Nenhum contrato cadastrado ainda. Use a aba 'Novo contrato' para criar.")
        return

    df = contratos.copy()
    df["Status"] = df["ativo"].apply(lambda a: "✅ Ativo" if a else "⛔ Encerrado")
    df["Tipo"]   = df["tipo_contrato"].map(_TIPOS_CONTRATO).fillna(df["tipo_contrato"])

    st.dataframe(
        df.rename(columns={
            "client_name":         "Cliente",
            "plano_nome":          "Plano",
            "horas_contratadas":   "Horas",
            "vigencia_inicio":     "Início",
            "vigencia_fim":        "Fim",
            "dia_corte":           "Dia corte",
            "hora_extra_valor":    "R$/h extra",
            "rollover_horas":      "Rollover",
        })[[
            "id", "Cliente", "Plano", "Tipo", "Horas",
            "Início", "Fim", "Dia corte", "R$/h extra",
            "Rollover", "Status",
        ]],
        width="stretch", hide_index=True,
        height=min(500, 40 + len(df) * 35),
    )

    # Editar/encerrar
    st.markdown("---")
    st.markdown("### ✏️ Editar contrato")
    ids = df["id"].tolist()
    if ids:
        escolhido = st.selectbox(
            "Selecione o contrato:",
            options=ids,
            format_func=lambda i: f"#{i} — {df[df['id']==i]['client_name'].iloc[0]}",
        )
        linha = df[df["id"] == escolhido].iloc[0]

        col1, col2 = st.columns(2)
        with col1:
            with st.form(f"form_edit_{escolhido}"):
                novo_plano = st.text_input("Plano", value=linha["plano_nome"] or "")
                novas_horas = st.number_input(
                    "Horas contratadas", min_value=0.0, step=1.0,
                    value=float(linha["horas_contratadas"] or 0),
                )
                novo_extra = st.number_input(
                    "R$ por hora extra", min_value=0.0, step=10.0,
                    value=float(linha["hora_extra_valor"] or 0),
                )
                novo_ativo = st.checkbox("Ativo", value=bool(linha["ativo"]))
                novo_rollover = st.checkbox("Rollover", value=bool(linha["rollover_horas"]))
                salvar = st.form_submit_button("💾 Salvar")
                if salvar:
                    db.atualizar_contrato(
                        int(escolhido),
                        plano_nome=novo_plano,
                        horas_contratadas=novas_horas,
                        hora_extra_valor=novo_extra if novo_extra > 0 else None,
                        ativo=novo_ativo,
                        rollover_horas=novo_rollover,
                    )
                    st.cache_data.clear()
                    st.success(f"Contrato #{escolhido} atualizado.")
                    st.rerun()

        with col2:
            st.caption("⚠️ Encerramento define fim = hoje e marca como inativo.")
            if st.button("⛔ Encerrar contrato", key=f"enc_{escolhido}"):
                db.encerrar_contrato(int(escolhido))
                st.cache_data.clear()
                st.success(f"Contrato #{escolhido} encerrado.")
                st.rerun()


def _render_novo_contrato():
    st.subheader("➕ Novo contrato")

    orgs = db.organizacoes_disponiveis()
    if orgs.empty:
        st.warning("Nenhuma organização encontrada no banco.")
        return

    with st.form("form_novo_contrato", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            org_opts = orgs["nome"].tolist()
            org_sel = st.selectbox("Cliente:", options=org_opts)
            plano = st.text_input("Nome do plano", placeholder="ex: Plano 40h Premium")
            horas = st.number_input("Horas contratadas/mês", min_value=1.0, step=1.0, value=40.0)
            tipo = st.selectbox(
                "Tipo de contrato:",
                options=list(_TIPOS_CONTRATO.keys()),
                format_func=lambda k: _TIPOS_CONTRATO[k],
            )
            rollover = st.checkbox("Horas acumulam entre ciclos (rollover)", value=False)

        with col2:
            vini = st.date_input("Início da vigência", value=date.today())
            vfim = st.date_input("Fim da vigência (opcional)", value=None)
            hextra = st.number_input("R$ por hora extra (0 = sem cobrança)",
                                     min_value=0.0, step=10.0, value=0.0)
            vmensal = st.number_input("Valor mensal do contrato (R$)",
                                      min_value=0.0, step=100.0, value=0.0)
            dcorte = st.number_input("Dia de corte do ciclo", min_value=1, max_value=28, value=1)

        obs = st.text_area("Observações", height=80)

        if st.form_submit_button("💾 Criar contrato"):
            if not plano:
                st.error("Informe o nome do plano.")
                return
            row_org = orgs[orgs["nome"] == org_sel].iloc[0]
            db.inserir_contrato(
                client_id=row_org["id"], client_name=org_sel,
                plano_nome=plano, tipo_contrato=tipo,
                horas_contratadas=horas, rollover_horas=rollover,
                hora_extra_valor=hextra if hextra > 0 else None,
                dia_corte=int(dcorte),
                vigencia_inicio=vini, vigencia_fim=vfim,
                valor_mensal=vmensal if vmensal > 0 else None,
                observacoes=obs or None,
            )
            st.cache_data.clear()
            st.success(f"Contrato criado para {org_sel}.")
            st.rerun()


def render():
    st.title("📄 Gestão de Contratos")
    st.caption("Ciclo de horas, faturamento de excedentes, CRUD")

    tab1, tab2, tab3 = st.tabs(["📊 Saldo", "📋 Contratos", "➕ Novo"])
    with tab1:
        _render_saldo()
    with tab2:
        _render_lista_contratos()
    with tab3:
        _render_novo_contrato()
