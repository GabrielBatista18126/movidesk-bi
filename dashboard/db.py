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

_DATABASE_URL = os.getenv("DATABASE_URL", "")
_DB_HOST = os.getenv("DB_HOST", "localhost")
_DB_PORT = os.getenv("DB_PORT", "5432")
_DB_NAME = os.getenv("DB_NAME", "movidesk_bi")
_DB_USER = os.getenv("DB_USER", "movidesk_user")
_DB_PASS = os.getenv("DB_PASSWORD", "")

_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        if _DATABASE_URL:
            url = _DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        else:
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


def anomalias_recentes(dias: int = 7) -> pd.DataFrame:
    return query(f"""
        SELECT *
        FROM analytics.anomalias_consumo
        WHERE data_detectada >= CURRENT_DATE - INTERVAL '{dias} days'
        ORDER BY z_score DESC, data_detectada DESC
    """)


def previsoes_tickets_proximos() -> pd.DataFrame:
    return query("""
        SELECT *
        FROM analytics.previsoes_tickets_7d
        WHERE data_prevista >= CURRENT_DATE
        ORDER BY data_prevista
    """)


# ─── Personas: queries por analista ───────────────────────────────

def lista_analistas() -> pd.DataFrame:
    return query("""
        SELECT DISTINCT te.agent_id, COALESCE(te.agent_name, te.agent_id) AS nome
        FROM raw.time_entries te
        WHERE te.agent_id IS NOT NULL
          AND te.entry_date >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY nome
    """)


def minha_fila(agent_id: str) -> pd.DataFrame:
    return query(f"""
        SELECT
            t.id              AS ticket_id,
            t.subject,
            COALESCE(t.organization_name, '-') AS cliente,
            t.category,
            t.urgency,
            t.status,
            t.created_date,
            t.sla_solution_date,
            CASE
                WHEN t.sla_solution_date IS NOT NULL
                THEN ROUND(EXTRACT(EPOCH FROM (t.sla_solution_date - NOW()))/3600.0, 1)
            END AS horas_para_sla
        FROM raw.tickets t
        WHERE t.owner_id = '{agent_id}'
          AND t.status NOT IN ('Closed', 'Canceled', 'Resolved')
        ORDER BY t.sla_solution_date NULLS LAST, t.created_date
    """)


def meus_lancamentos(agent_id: str, dias: int = 30) -> pd.DataFrame:
    return query(f"""
        SELECT
            te.entry_date,
            te.ticket_id,
            COALESCE(t.subject, '-') AS subject,
            COALESCE(t.organization_name, '-') AS cliente,
            te.hours_spent,
            te.description
        FROM raw.time_entries te
        LEFT JOIN raw.tickets t ON t.id = te.ticket_id
        WHERE te.agent_id = '{agent_id}'
          AND te.entry_date >= CURRENT_DATE - INTERVAL '{dias} days'
        ORDER BY te.entry_date DESC
    """)


def meus_kpis(agent_id: str) -> dict:
    df = query(f"""
        SELECT
            COALESCE(SUM(te.hours_spent), 0)         AS horas_30d,
            COALESCE(SUM(te.hours_spent) FILTER (
                WHERE te.entry_date >= CURRENT_DATE - INTERVAL '7 days'
            ), 0)                                     AS horas_7d,
            COUNT(DISTINCT te.ticket_id)             AS tickets_atendidos_30d
        FROM raw.time_entries te
        WHERE te.agent_id = '{agent_id}'
          AND te.entry_date >= CURRENT_DATE - INTERVAL '30 days'
    """)
    if df.empty:
        return {"horas_30d": 0, "horas_7d": 0, "tickets_atendidos_30d": 0}
    return df.iloc[0].to_dict()


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
            COALESCE(NULLIF(t.category, ''), 'Sem categoria')
                || ' - '
                || COALESCE(NULLIF(t.ticket_type, ''), 'Sem tipo') AS tipo,
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


# ═══════════════════════════════════════════════════════════════
# SLA (Fase 1)
# ═══════════════════════════════════════════════════════════════

def sla_kpis() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_sla_kpis_mes")


def sla_por_cliente() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_sla_por_cliente LIMIT 30")


def sla_por_categoria() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_sla_por_categoria LIMIT 30")


def tickets_em_risco_sla() -> pd.DataFrame:
    return query("""
        SELECT
            ticket_id,
            subject,
            cliente,
            urgency,
            category,
            ROUND(minutos_ate_estourar_sla::numeric, 0) AS minutos_restantes,
            risco
        FROM analytics.v_tickets_risco_sla
    """)


def sla_serie_temporal() -> pd.DataFrame:
    """% SLA cumprido por dia nos últimos 30 dias."""
    return query("""
        SELECT
            DATE(created_date)                                            AS data,
            COUNT(*)                                                       AS total,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE dentro_sla_solution = TRUE)
                / NULLIF(COUNT(*) FILTER (WHERE dentro_sla_solution IS NOT NULL), 0),
                1
            )                                                              AS pct_sla
        FROM analytics.v_sla_tickets
        WHERE created_date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY DATE(created_date)
        ORDER BY 1
    """)


# ═══════════════════════════════════════════════════════════════
# Produtividade avançada (Fase 2)
# ═══════════════════════════════════════════════════════════════

def matriz_produtividade_semana() -> pd.DataFrame:
    """Horas por analista × dia da semana no mês atual (heatmap)."""
    return query("""
        SELECT
            COALESCE(a.business_name, te.agent_name, 'Sem agente') AS analista,
            EXTRACT(ISODOW FROM te.entry_date)::int                AS dia_semana,
            ROUND(SUM(te.hours_spent)::numeric, 1)                 AS horas
        FROM raw.time_entries te
        LEFT JOIN raw.agentes a ON a.id = te.agent_id
        WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
          AND te.hours_spent > 0
        GROUP BY analista, dia_semana
        ORDER BY analista, dia_semana
    """)


def especialista_por_categoria() -> pd.DataFrame:
    """Quem é o especialista (mais horas) por categoria nos últimos 90 dias."""
    return query("""
        WITH por_cat_agente AS (
            SELECT
                COALESCE(NULLIF(t.category, ''), 'Sem categoria')      AS categoria,
                COALESCE(a.business_name, te.agent_name, 'Sem agente') AS analista,
                SUM(te.hours_spent)                                     AS horas,
                COUNT(DISTINCT te.ticket_id)                            AS tickets,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(NULLIF(t.category, ''), 'Sem categoria')
                    ORDER BY SUM(te.hours_spent) DESC
                )                                                        AS rank
            FROM raw.time_entries te
            JOIN raw.tickets t ON t.id = te.ticket_id
            LEFT JOIN raw.agentes a ON a.id = te.agent_id
            WHERE te.entry_date >= CURRENT_DATE - INTERVAL '90 days'
              AND te.hours_spent > 0
            GROUP BY categoria, analista
        )
        SELECT categoria, analista,
               ROUND(horas::numeric, 1) AS horas,
               tickets
        FROM por_cat_agente
        WHERE rank = 1
        ORDER BY horas DESC
    """)


def carga_vs_capacidade() -> pd.DataFrame:
    """Carga lançada vs capacidade teórica (8h por dia útil) no mês atual."""
    return query("""
        WITH dias_uteis AS (
            SELECT COUNT(*)::numeric AS qtd
            FROM generate_series(
                DATE_TRUNC('month', CURRENT_DATE)::date,
                CURRENT_DATE,
                '1 day'::interval
            ) AS d(dia)
            WHERE EXTRACT(ISODOW FROM d.dia) < 6   -- segunda a sexta
        ),
        carga AS (
            SELECT
                COALESCE(a.business_name, te.agent_name, 'Sem agente') AS analista,
                SUM(te.hours_spent)                                     AS horas_lancadas,
                COUNT(DISTINCT te.ticket_id)                            AS tickets
            FROM raw.time_entries te
            LEFT JOIN raw.agentes a ON a.id = te.agent_id
            WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
              AND te.hours_spent > 0
            GROUP BY analista
        )
        SELECT
            c.analista,
            ROUND(c.horas_lancadas::numeric, 1)          AS horas_lancadas,
            c.tickets,
            ROUND((du.qtd * 8.0)::numeric, 1)            AS capacidade_horas,
            ROUND(
                (100.0 * c.horas_lancadas / NULLIF(du.qtd * 8.0, 0))::numeric, 1
            )                                             AS pct_utilizacao
        FROM carga c CROSS JOIN dias_uteis du
        ORDER BY pct_utilizacao DESC NULLS LAST
    """)


# ═══════════════════════════════════════════════════════════════
# Contratos (Fase 3) — CRUD + saldo
# ═══════════════════════════════════════════════════════════════

def saldo_contratos() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_saldo_contrato")


def listar_contratos() -> pd.DataFrame:
    return query("""
        SELECT
            id, client_id, organization_id, client_name, plano_nome,
            tipo_contrato, horas_contratadas, rollover_horas,
            hora_extra_valor, dia_corte,
            vigencia_inicio, vigencia_fim, valor_mensal,
            ativo, observacoes
        FROM analytics.contratos
        ORDER BY ativo DESC, vigencia_inicio DESC, client_name
    """)


def organizacoes_disponiveis() -> pd.DataFrame:
    """Lista de organizações (empresas) para cadastrar contrato."""
    return query("""
        SELECT DISTINCT
            COALESCE(t.organization_id, t.client_id) AS id,
            COALESCE(NULLIF(t.organization_name, ''), c.business_name) AS nome
        FROM raw.tickets t
        LEFT JOIN raw.clientes c ON c.id = t.client_id
        WHERE COALESCE(t.organization_id, t.client_id) IS NOT NULL
          AND COALESCE(NULLIF(t.organization_name, ''), c.business_name) IS NOT NULL
        ORDER BY nome
    """)


def inserir_contrato(client_id, client_name, plano_nome, tipo_contrato,
                     horas_contratadas, rollover_horas, hora_extra_valor,
                     dia_corte, vigencia_inicio, vigencia_fim, valor_mensal,
                     observacoes) -> None:
    with _engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO analytics.contratos
                (client_id, organization_id, client_name, plano_nome, tipo_contrato,
                 horas_contratadas, rollover_horas, hora_extra_valor,
                 dia_corte, vigencia_inicio, vigencia_fim, valor_mensal, observacoes, ativo)
            VALUES
                (:cid, :cid, :cname, :plano, :tipo,
                 :horas, :rollover, :hextra, :dcorte,
                 :vini, :vfim, :vmensal, :obs, TRUE)
        """), {
            "cid": client_id, "cname": client_name, "plano": plano_nome,
            "tipo": tipo_contrato, "horas": horas_contratadas,
            "rollover": rollover_horas, "hextra": hora_extra_valor,
            "dcorte": dia_corte, "vini": vigencia_inicio, "vfim": vigencia_fim,
            "vmensal": valor_mensal, "obs": observacoes,
        })


def atualizar_contrato(contrato_id, **campos) -> None:
    allowed = {"plano_nome", "tipo_contrato", "horas_contratadas",
               "rollover_horas", "hora_extra_valor", "dia_corte",
               "vigencia_inicio", "vigencia_fim", "valor_mensal",
               "observacoes", "ativo", "client_name"}
    updates = {k: v for k, v in campos.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["cid"] = contrato_id
    with _engine().begin() as conn:
        conn.execute(text(f"""
            UPDATE analytics.contratos
               SET {set_clause}, updated_at = NOW()
             WHERE id = :cid
        """), updates)


def encerrar_contrato(contrato_id) -> None:
    with _engine().begin() as conn:
        conn.execute(text("""
            UPDATE analytics.contratos
               SET ativo = FALSE,
                   vigencia_fim = COALESCE(vigencia_fim, CURRENT_DATE),
                   updated_at = NOW()
             WHERE id = :cid
        """), {"cid": contrato_id})


# ═══════════════════════════════════════════════════════════════
# Retrabalho (Fase 4)
# ═══════════════════════════════════════════════════════════════

def tickets_reabertos() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_tickets_reabertos LIMIT 100")


def problemas_recorrentes() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_problemas_recorrentes LIMIT 50")


def subjects_frequentes() -> pd.DataFrame:
    return query("SELECT * FROM analytics.v_subjects_frequentes")


def descricoes_para_cluster() -> pd.DataFrame:
    """Descrições de ações do mês atual para clusterização TF-IDF."""
    return query("""
        SELECT
            te.ticket_id,
            te.description,
            COALESCE(te.organization_name, '-') AS cliente
        FROM raw.time_entries te
        WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
          AND te.description IS NOT NULL
          AND LENGTH(te.description) > 20
    """)


def ticket_medio_por_categoria() -> pd.DataFrame:
    """Tempo médio por ticket por categoria (identifica problemas caros)."""
    return query("""
        SELECT
            COALESCE(NULLIF(t.category, ''), 'Sem categoria') AS categoria,
            COUNT(DISTINCT te.ticket_id)                      AS tickets,
            ROUND(SUM(te.hours_spent)::numeric, 1)            AS horas_totais,
            ROUND(
                (SUM(te.hours_spent)::numeric
                 / NULLIF(COUNT(DISTINCT te.ticket_id), 0)),
                2
            )                                                  AS horas_por_ticket
        FROM raw.time_entries te
        JOIN raw.tickets t ON t.id = te.ticket_id
        WHERE te.entry_date >= CURRENT_DATE - INTERVAL '90 days'
          AND te.hours_spent > 0
        GROUP BY categoria
        HAVING COUNT(DISTINCT te.ticket_id) >= 2
        ORDER BY horas_por_ticket DESC
    """)
