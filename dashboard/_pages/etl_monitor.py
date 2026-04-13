"""Página: Monitor do ETL."""
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard import db

PROJECT_DIR = Path(__file__).resolve().parents[2]
VENV_PYTHON = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
ETL_PYTHON = str(VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable))


def render():
    st.title("⚙️ Monitor do ETL")
    st.caption("Histórico de execuções e saúde do pipeline")

    df = db.etl_historico()

    if df.empty:
        st.info("Nenhuma execução registrada ainda.")
        return

    # ── Health check ──────────────────────────────────────────────
    ultima = df.iloc[0]
    ultima_inicio = pd.to_datetime(ultima["started_at"], utc=True, errors="coerce")
    agora = datetime.now(timezone.utc)
    minutos_desde = (agora - ultima_inicio).total_seconds() / 60 if pd.notna(ultima_inicio) else None

    if minutos_desde is None:
        st.warning("⚠️ Não foi possível determinar quando o ETL rodou pela última vez.")
    elif minutos_desde > 15:
        st.error(
            f"🔴 ETL parado há {minutos_desde:.0f} minutos. "
            "Verifique o scheduler (`scripts/etl_scheduler.py`)."
        )
    elif ultima["status"] == "FAILURE":
        st.error("🔴 Última execução falhou. Veja o log abaixo.")
    else:
        st.success(f"🟢 ETL saudável · última execução há {minutos_desde:.0f} min.")

    # Taxa de sucesso (últimas 50)
    df_50 = df.head(50)
    sucessos = int((df_50["status"] == "SUCCESS").sum())
    taxa_sucesso = sucessos / len(df_50) * 100 if len(df_50) else 0

    # ── KPIs ──────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("🕐 Última execução",   str(ultima["started_at"])[:16])
    k2.metric("✅ Status",            ultima["status"])
    k3.metric("📦 Registros (última)", int(ultima["records_in"] or 0))
    k4.metric("⏱️ Duração (última)",  f"{int(ultima['duracao_segundos'] or 0)}s")
    k5.metric("🎯 Taxa sucesso (50)", f"{taxa_sucesso:.0f}%")

    st.markdown("---")

    # ── Histórico de status ───────────────────────────────────────
    col1, col2 = st.columns([3, 2])

    with col1:
        st.subheader("📋 Histórico de execuções")
        df_show = df[["started_at", "finished_at", "status", "records_in",
                       "duracao_segundos", "full_load", "error_msg"]].copy()
        df_show.columns = ["Início", "Fim", "Status", "Registros", "Duração (s)", "Full Load", "Erro"]
        df_show["Início"]   = df_show["Início"].astype(str).str[:16]
        df_show["Fim"]      = df_show["Fim"].astype(str).str[:16]
        df_show["Status"]   = df_show["Status"].apply(
            lambda s: f"✅ {s}" if s == "SUCCESS" else (f"❌ {s}" if s == "FAILURE" else f"🔄 {s}")
        )
        st.dataframe(df_show, width="stretch", hide_index=True)

    with col2:
        st.subheader("📊 Distribuição de status")
        status_count = df["status"].value_counts().reset_index()
        status_count.columns = ["Status", "Qtd"]
        cores = {"SUCCESS": "#70AD47", "FAILURE": "#C00000", "RUNNING": "#FFC000"}
        fig = px.pie(
            status_count,
            names="Status",
            values="Qtd",
            color="Status",
            color_discrete_map=cores,
            hole=0.4,
        )
        fig.update_layout(
            height=260,
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, width="stretch")

    st.markdown("---")

    # ── Duração ao longo do tempo ──────────────────────────────────
    st.subheader("⏱️ Duração das execuções")
    df_dur = df[df["duracao_segundos"].notna()].copy()
    if not df_dur.empty:
        df_dur["started_at"] = df_dur["started_at"].astype(str).str[:16]
        fig2 = px.bar(
            df_dur.tail(15),
            x="started_at",
            y="duracao_segundos",
            color="status",
            color_discrete_map={"SUCCESS": "#70AD47", "FAILURE": "#C00000", "RUNNING": "#FFC000"},
            labels={"started_at": "Execução", "duracao_segundos": "Duração (s)", "status": "Status"},
            text="duracao_segundos",
        )
        fig2.update_traces(texttemplate="%{text}s", textposition="outside")
        fig2.update_layout(
            height=280,
            margin=dict(l=0, r=0, t=10, b=20),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(tickangle=-30, showgrid=False),
            yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        )
        st.plotly_chart(fig2, width="stretch")

    # ── Botão para rodar ETL manualmente ──────────────────────────
    st.markdown("---")
    st.subheader("▶️ Executar ETL manualmente")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 Rodar ETL incremental", width="stretch"):
            with st.spinner("Executando ETL..."):
                result = subprocess.run(
                    [ETL_PYTHON, "-m", "etl.main"],
                    capture_output=True, text=True,
                    cwd=str(PROJECT_DIR),
                )
            if result.returncode == 0:
                st.success("ETL concluído com sucesso!")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("ETL falhou. Veja o log abaixo:")
                st.code(result.stderr[-2000:])
    with c2:
        if st.button("🔃 Rodar ETL full load", width="stretch", type="secondary"):
            with st.spinner("Executando ETL full load..."):
                result = subprocess.run(
                    [ETL_PYTHON, "-m", "etl.main", "--full"],
                    capture_output=True, text=True,
                    cwd=str(PROJECT_DIR),
                )
            if result.returncode == 0:
                st.success("ETL full load concluído!")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("ETL falhou:")
                st.code(result.stderr[-2000:])
