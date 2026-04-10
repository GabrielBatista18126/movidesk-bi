"""Conexão e queries reutilizáveis para o dashboard."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

_DB_HOST = os.getenv("DB_HOST", "localhost")
_DB_PORT = os.getenv("DB_PORT", "5432")
_DB_NAME = os.getenv("DB_NAME", "movidesk_bi")
_DB_USER = os.getenv("DB_USER", "movidesk_user")
_DB_PASS = os.getenv("DB_PASSWORD", "")

_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        url = URL.create(
            drivername="postgresql+psycopg2",
            username=_DB_USER,
            password=_DB_PASS,
            host=_DB_HOST,
            port=int(_DB_PORT),
            database=_DB_NAME,
        )
        _ENGINE = create_engine(url, pool_pre_ping=True)
    return _ENGINE


def _query_raw(sql: str, params=None) -> pd.DataFrame:
    """Executa query sem cache (uso interno)."""
    try:
        with _engine().connect() as conn:
            df = pd.read_sql_query(text(sql), conn, params=params)
        return df
    except Exception as e:
        st.error(f"Erro ao consultar banco: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=120)
def query(sql: str, params=None) -> pd.DataFrame:
    return _query_raw(sql, params)


def resumo_mes_atual() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_resumo_mes_atual ORDER BY horas_mes_atual DESC")


def consumo_mensal() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_consumo_mensal ORDER BY ano_mes, client_name")


def alerta_consumo() -> pd.DataFrame:
    return query("""
        SELECT * FROM analytics.v_alerta_consumo
        ORDER BY pct_consumo DESC NULLS LAST
    """)


def historico_consumo() -> pd.DataFrame:
    return query("""
        SELECT * FROM analytics.v_historico_consumo
        ORDER BY ano_mes, client_name
    """)


def produtividade() -> pd.DataFrame:
    return query("""
        SELECT * FROM analytics.v_produtividade_detalhada
        ORDER BY ano_mes DESC, horas_lancadas DESC
    """)


def produtividade_agente_resumo() -> pd.DataFrame:
    return query("""
        SELECT * FROM analytics.v_produtividade_agente_resumo
        ORDER BY horas_mes_atual DESC
    """)


def sla_performance() -> pd.DataFrame:
    return query("""
        SELECT * FROM analytics.v_sla_performance
        ORDER BY ano_mes DESC, total_tickets DESC
    """)


def retrabalho() -> pd.DataFrame:
    return query("""
        SELECT * FROM analytics.v_retrabalho
        ORDER BY ano_mes DESC, taxa_retrabalho_pct DESC NULLS LAST
    """)


def tickets_abertos() -> pd.DataFrame:
    return query("""
        SELECT * FROM analytics.v_tickets_abertos
        ORDER BY dias_aberto DESC NULLS LAST
    """)


def top_tickets() -> pd.DataFrame:
    return query("""
        SELECT * FROM analytics.v_top_tickets_mes
        ORDER BY horas_mes_atual DESC
        LIMIT 50
    """)


def previsoes() -> pd.DataFrame:
    return query("""
        SELECT * FROM analytics.previsoes_consumo
        WHERE mes_referencia = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
        ORDER BY pct_previsto DESC NULLS LAST
    """)


def scores() -> pd.DataFrame:
    return query("""
        SELECT * FROM analytics.score_clientes
        ORDER BY score_total DESC
    """)


def sugestoes_upgrade() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_sugestoes_upgrade")


def etl_historico() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_etl_historico LIMIT 20")


def meses_disponiveis() -> list:
    df = query("SELECT DISTINCT ano_mes FROM analytics.v_consumo_mensal ORDER BY ano_mes DESC")
    return df["ano_mes"].tolist() if not df.empty else []


# ── Queries para Visão Geral (estilo referência) ────────────────

def visao_geral_kpis() -> pd.DataFrame:
    """KPIs: total horas, apontamentos, clientes, analistas."""
    return query("""
        SELECT
            ROUND(SUM(te.hours_spent)::numeric, 1)           AS total_horas,
            COUNT(*)                                          AS total_apontamentos,
            COUNT(DISTINCT COALESCE(te.organization_id, te.client_id)) AS total_clientes,
            COUNT(DISTINCT te.agent_id)                       AS total_analistas
        FROM raw.time_entries te
        WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
          AND te.hours_spent > 0
    """)


def horas_por_dia_agente() -> pd.DataFrame:
    """Horas lançadas por colaborador por dia (mês atual)."""
    return query("""
        SELECT
            te.entry_date::date                                AS data,
            COALESCE(a.business_name, te.agent_name, 'Sem agente') AS analista,
            ROUND(SUM(te.hours_spent)::numeric, 1)             AS horas
        FROM raw.time_entries te
        LEFT JOIN raw.agentes a ON a.id = te.agent_id
        WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
          AND te.hours_spent > 0
        GROUP BY 1, 2
        ORDER BY 1, 2
    """)


def horas_por_cliente_mes() -> pd.DataFrame:
    """Horas por cliente no mês atual."""
    return query("""
        SELECT
            COALESCE(te.organization_name, te.client_name, '') AS cliente,
            ROUND(SUM(te.hours_spent)::numeric, 1)             AS horas,
            COUNT(*)                                            AS apontamentos
        FROM raw.time_entries te
        WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
          AND te.hours_spent > 0
        GROUP BY 1
        ORDER BY 2 DESC
    """)


def horas_por_analista_mes() -> pd.DataFrame:
    """Carga por analista no mês atual."""
    return query("""
        SELECT
            COALESCE(a.business_name, te.agent_name, 'Sem agente') AS analista,
            ROUND(SUM(te.hours_spent)::numeric, 1)                  AS horas,
            COUNT(*)                                                 AS apontamentos,
            COUNT(DISTINCT COALESCE(te.organization_id, te.client_id)) AS clientes
        FROM raw.time_entries te
        LEFT JOIN raw.agentes a ON a.id = te.agent_id
        WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
          AND te.hours_spent > 0
        GROUP BY 1
        ORDER BY 2 DESC
    """)


def tipo_problema_mes() -> pd.DataFrame:
    """Distribuição por categoria+tipo (tipo de problema) no mês atual."""
    return query("""
        SELECT
            COALESCE(t.category, 'Sem categoria')
                || ' - '
                || COALESCE(NULLIF(te.description, ''), 'Sem descrição') AS tipo,
            ROUND(SUM(te.hours_spent)::numeric, 1) AS horas,
            COUNT(*) AS qtd
        FROM raw.time_entries te
        JOIN raw.tickets t ON t.id = te.ticket_id
        WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
          AND te.hours_spent > 0
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT 10
    """)


def prioridade_mes() -> pd.DataFrame:
    """Distribuição por categoria + urgência no mês atual."""
    return query("""
        SELECT
            COALESCE(t.category, 'Sem categoria')
                || ' - '
                || COALESCE(NULLIF(t.urgency, ''), 'Sem urgência') AS prioridade,
            COUNT(DISTINCT te.ticket_id) AS qtd_tickets,
            ROUND(SUM(te.hours_spent)::numeric, 1) AS horas
        FROM raw.time_entries te
        JOIN raw.tickets t ON t.id = te.ticket_id
        WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
          AND te.hours_spent > 0
        GROUP BY 1
        ORDER BY 2 DESC
    """)


def datas_disponiveis_mes() -> list:
    """Datas com lançamentos no mês atual para filtro."""
    df = query("""
        SELECT DISTINCT te.entry_date::date AS data
        FROM raw.time_entries te
        WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
          AND te.hours_spent > 0
        ORDER BY 1
    """)
    return df["data"].tolist() if not df.empty else []


def analistas_disponiveis_mes() -> list:
    """Analistas com lançamentos no mês atual para filtro."""
    df = query("""
        SELECT DISTINCT COALESCE(a.business_name, te.agent_name, 'Sem agente') AS analista
        FROM raw.time_entries te
        LEFT JOIN raw.agentes a ON a.id = te.agent_id
        WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
          AND te.hours_spent > 0
        ORDER BY 1
    """)
    return df["analista"].tolist() if not df.empty else []


def lancamentos_detalhados_mes() -> pd.DataFrame:
    """Lancamentos individuais do mes atual com descricao da acao."""
    return query("""
        SELECT
            te.entry_date::date                                       AS data,
            COALESCE(a.business_name, te.agent_name, 'Sem agente')    AS analista,
            COALESCE(te.organization_name, te.client_name, '')        AS cliente,
            '#' || te.ticket_id                                       AS ticket,
            ROUND(te.hours_spent::numeric, 1)                         AS horas,
            COALESCE(te.description, '')                              AS descricao
        FROM raw.time_entries te
        LEFT JOIN raw.agentes a ON a.id = te.agent_id
        WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
          AND te.hours_spent > 0
        ORDER BY te.entry_date::date, te.ticket_id
    """)
