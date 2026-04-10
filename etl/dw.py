"""
dw.py — Popula a camada analítica (star schema) a partir das tabelas raw.

Após o refactoring v2:
  - dim_clientes  → populada de raw.organizacoes (empresas)
  - fact_consumo  → join por organization_id (não mais client_id)
  - fact_tickets  → join por organization_id
"""
import logging
from datetime import date, timedelta
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values

from . import config

logger = logging.getLogger(__name__)


def _get_conn():
    return psycopg2.connect(**config.DB_CONFIG)


# ─── dim_tempo ────────────────────────────────────────────────────

_MESES_PT = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]
_MESES_ABREV = [
    "", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
    "Jul", "Ago", "Set", "Out", "Nov", "Dez",
]
_DIAS_SEMANA_PT = [
    "Segunda-feira", "Terça-feira", "Quarta-feira",
    "Quinta-feira", "Sexta-feira", "Sábado", "Domingo",
]


def populate_dim_tempo(start_year: int = 2020, end_year: int = 2030) -> int:
    start   = date(start_year, 1, 1)
    end     = date(end_year, 12, 31)
    rows    = []
    current = start

    while current <= end:
        iso_year, iso_week, iso_day = current.isocalendar()
        dia_semana = iso_day % 7 + 1
        nome_dia   = _DIAS_SEMANA_PT[iso_day - 1]
        rows.append((
            int(current.strftime("%Y%m%d")),
            current,
            current.year,
            1 if current.month <= 6 else 2,
            (current.month - 1) // 3 + 1,
            current.month,
            _MESES_PT[current.month],
            _MESES_ABREV[current.month],
            iso_week,
            current.day,
            dia_semana,
            nome_dia,
            iso_day >= 6,
            current.strftime("%Y-%m"),
        ))
        current += timedelta(days=1)

    sql = """
        INSERT INTO analytics.dim_tempo (
            tempo_key, data, ano, semestre, trimestre, mes, mes_nome, mes_abrev,
            semana_ano, dia_mes, dia_semana, dia_semana_nome, e_fim_semana, ano_mes
        ) VALUES %s
        ON CONFLICT (tempo_key) DO NOTHING
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows, page_size=1000)
        conn.commit()

    logger.info("dim_tempo: %d datas garantidas (%d–%d)", len(rows), start_year, end_year)
    return len(rows)


# ─── dim_clientes (populada de raw.organizacoes) ──────────────────

def populate_dim_clientes() -> int:
    """
    Upserta dim_clientes a partir de raw.organizacoes + contrato vigente.
    Após o refactoring, dim_clientes representa ORGANIZAÇÕES (empresas).
    """
    sql_insert = """
        INSERT INTO analytics.dim_clientes (
            client_id, business_name, email, cpf_cnpj, profile_type, is_active,
            plano_nome, horas_contratadas, vigencia_inicio, vigencia_fim,
            updated_at
        )
        SELECT
            o.id,
            o.business_name,
            o.email,
            o.cpf_cnpj,
            o.profile_type,
            o.is_active,
            cv.plano_nome,
            cv.horas_contratadas,
            cv.vigencia_inicio,
            cv.vigencia_fim,
            NOW()
        FROM raw.organizacoes o
        LEFT JOIN analytics.v_contrato_vigente cv ON cv.client_id = o.id
        ON CONFLICT (client_id) DO UPDATE SET
            business_name     = EXCLUDED.business_name,
            email             = EXCLUDED.email,
            is_active         = EXCLUDED.is_active,
            plano_nome        = EXCLUDED.plano_nome,
            horas_contratadas = EXCLUDED.horas_contratadas,
            vigencia_inicio   = EXCLUDED.vigencia_inicio,
            vigencia_fim      = EXCLUDED.vigencia_fim,
            updated_at        = NOW()
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_insert)
            count = cur.rowcount
        conn.commit()

    logger.info("dim_clientes: %d linhas sincronizadas (via organizacoes)", count)
    return count


# ─── dim_agentes ──────────────────────────────────────────────────

def populate_dim_agentes() -> int:
    sql_insert = """
        INSERT INTO analytics.dim_agentes (
            agent_id, business_name, email, team, is_active, updated_at
        )
        SELECT id, business_name, email, team, is_active, NOW()
        FROM raw.agentes
        ON CONFLICT (agent_id) DO UPDATE SET
            business_name = EXCLUDED.business_name,
            email         = EXCLUDED.email,
            team          = EXCLUDED.team,
            is_active     = EXCLUDED.is_active,
            updated_at    = NOW()
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_insert)
            count = cur.rowcount
        conn.commit()

    logger.info("dim_agentes: %d linhas sincronizadas", count)
    return count


# ─── fact_consumo ─────────────────────────────────────────────────

def populate_fact_consumo(since: Optional[str] = None) -> int:
    """
    Upserta fact_consumo a partir de raw.time_entries.
    JOIN por organization_id → dim_clientes (organização correta).
    """
    where = "WHERE te.entry_date >= %(since)s" if since else ""

    sql_insert = f"""
        INSERT INTO analytics.fact_consumo (
            time_entry_id, tempo_key, cliente_key, agente_key,
            ticket_id, ticket_subject, horas_gastas, mes_referencia, updated_at
        )
        SELECT
            te.id,
            TO_CHAR(te.entry_date, 'YYYYMMDD')::INTEGER,
            dc.cliente_key,
            da.agente_key,
            te.ticket_id,
            te.ticket_subject,
            te.hours_spent,
            TO_CHAR(te.entry_date, 'YYYY-MM'),
            NOW()
        FROM raw.time_entries te
        LEFT JOIN analytics.dim_clientes dc
            ON dc.client_id = COALESCE(te.organization_id, te.client_id)
        LEFT JOIN analytics.dim_agentes da ON da.agent_id = te.agent_id
        {where}
        ON CONFLICT (time_entry_id) DO UPDATE SET
            horas_gastas  = EXCLUDED.horas_gastas,
            cliente_key   = EXCLUDED.cliente_key,
            agente_key    = EXCLUDED.agente_key,
            updated_at    = NOW()
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_insert, {"since": since})
            count = cur.rowcount
        conn.commit()

    logger.info("fact_consumo: %d linhas upsertadas", count)
    return count


# ─── fact_tickets ─────────────────────────────────────────────────

def populate_fact_tickets(since: Optional[str] = None) -> int:
    """
    Upserta fact_tickets a partir de raw.tickets.
    JOIN por organization_id → dim_clientes (organização correta).
    """
    where = "WHERE t.last_update >= %(since)s OR t.created_date >= %(since)s" if since else ""

    sql_insert = f"""
        INSERT INTO analytics.fact_tickets (
            ticket_id,
            tempo_abertura_key, tempo_resolucao_key, tempo_fechamento_key,
            cliente_key, agente_key,
            status, ticket_type, category, urgency, owner_team,
            time_spent_total_hours,
            dias_para_resolver, dias_para_fechar, esta_aberto,
            updated_at
        )
        SELECT
            t.id,
            TO_CHAR(t.created_date,  'YYYYMMDD')::INTEGER,
            CASE WHEN t.resolved_date IS NOT NULL
                 THEN TO_CHAR(t.resolved_date, 'YYYYMMDD')::INTEGER END,
            CASE WHEN t.closed_date IS NOT NULL
                 THEN TO_CHAR(t.closed_date,   'YYYYMMDD')::INTEGER END,
            dc.cliente_key,
            da.agente_key,
            t.status,
            t.ticket_type,
            t.category,
            t.urgency,
            t.owner_team,
            t.time_spent_total_hours,
            CASE WHEN t.resolved_date IS NOT NULL
                 THEN EXTRACT(DAY FROM t.resolved_date - t.created_date)::INTEGER END,
            CASE WHEN t.closed_date IS NOT NULL
                 THEN EXTRACT(DAY FROM t.closed_date - t.created_date)::INTEGER END,
            t.status NOT IN ('Resolved', 'Closed'),
            NOW()
        FROM raw.tickets t
        LEFT JOIN analytics.dim_clientes dc
            ON dc.client_id = COALESCE(t.organization_id, t.client_id)
        LEFT JOIN analytics.dim_agentes da ON da.agent_id = t.owner_id
        {where}
        ON CONFLICT (ticket_id) DO UPDATE SET
            tempo_resolucao_key    = EXCLUDED.tempo_resolucao_key,
            tempo_fechamento_key   = EXCLUDED.tempo_fechamento_key,
            cliente_key            = EXCLUDED.cliente_key,
            status                 = EXCLUDED.status,
            time_spent_total_hours = EXCLUDED.time_spent_total_hours,
            dias_para_resolver     = EXCLUDED.dias_para_resolver,
            dias_para_fechar       = EXCLUDED.dias_para_fechar,
            esta_aberto            = EXCLUDED.esta_aberto,
            updated_at             = NOW()
    """
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_insert, {"since": since})
            count = cur.rowcount
        conn.commit()

    logger.info("fact_tickets: %d linhas upsertadas", count)
    return count


# ─── Orquestrador ─────────────────────────────────────────────────

def run_dw(full_load: bool = False) -> int:
    logger.info("── DW: iniciando carga da camada analítica ──")

    populate_dim_tempo(start_year=2020, end_year=2030)
    n_cli = populate_dim_clientes()
    n_age = populate_dim_agentes()

    if full_load:
        since = None
    else:
        from datetime import datetime, timezone, timedelta
        since = (datetime.now(timezone.utc) - timedelta(days=35)).strftime("%Y-%m-%d")

    n_consumo = populate_fact_consumo(since=since)
    n_tickets = populate_fact_tickets(since=since)

    total = n_cli + n_age + n_consumo + n_tickets
    logger.info("── DW: concluído | dims=%d | facts=%d ──", n_cli + n_age, n_consumo + n_tickets)
    return total
