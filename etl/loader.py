"""
loader.py — Persiste os dados transformados no PostgreSQL via upsert.
            Controla watermark para ingestão incremental.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values

from . import config
from .transformer import (
    AgenteRecord,
    ClienteRecord,
    OrganizacaoRecord,
    TicketRecord,
    TimeEntryRecord,
)

logger = logging.getLogger(__name__)


# ─── Conexão ──────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(**config.DB_CONFIG)


# ─── Watermark ────────────────────────────────────────────────────

def get_watermark(table_name: str) -> Optional[datetime]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT last_run FROM raw.etl_watermark WHERE table_name = %s",
                (table_name,),
            )
            row = cur.fetchone()
            return row[0] if row else None


def set_watermark(cur, table_name: str) -> None:
    cur.execute(
        """
        INSERT INTO raw.etl_watermark (table_name, last_run)
        VALUES (%s, NOW())
        ON CONFLICT (table_name) DO UPDATE SET last_run = NOW()
        """,
        (table_name,),
    )


# ─── ETL Log ──────────────────────────────────────────────────────

def log_etl_start(full_load: bool = False) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO raw.etl_log (started_at, status, full_load)
                VALUES (NOW(), 'RUNNING', %s)
                RETURNING id
                """,
                (full_load,),
            )
            log_id = cur.fetchone()[0]
        conn.commit()
    return log_id


def log_etl_end(
    log_id: int,
    status: str,
    records_in: int = 0,
    error_msg: str | None = None,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE raw.etl_log
                SET finished_at = NOW(),
                    status      = %s,
                    records_in  = %s,
                    error_msg   = %s
                WHERE id = %s
                """,
                (status, records_in, error_msg, log_id),
            )
        conn.commit()


# ─── Organizações ─────────────────────────────────────────────────

def upsert_organizacoes(records: list[OrganizacaoRecord]) -> int:
    """Upserta raw.organizacoes — empresas/clientes reais da API."""
    if not records:
        return 0

    sql = """
        INSERT INTO raw.organizacoes
            (id, business_name, email, cpf_cnpj, is_active, created_date, profile_type, updated_at)
        VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            business_name = EXCLUDED.business_name,
            email         = EXCLUDED.email,
            is_active     = EXCLUDED.is_active,
            updated_at    = NOW()
    """
    values = [
        (r.id, r.business_name, r.email, r.cpf_cnpj,
         r.is_active, r.created_date, r.profile_type, r.ingested_at)
        for r in records
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, values)
        conn.commit()

    logger.info("Organizações upsertadas: %d", len(records))
    return len(records)


# ─── Clientes (raw.clientes — compatibilidade) ────────────────────

def upsert_clientes(records: list[ClienteRecord]) -> int:
    if not records:
        return 0

    sql = """
        INSERT INTO raw.clientes
            (id, business_name, email, cpf_cnpj, is_active, created_date, profile_type, updated_at)
        VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            business_name = EXCLUDED.business_name,
            email         = EXCLUDED.email,
            is_active     = EXCLUDED.is_active,
            updated_at    = NOW()
    """
    values = [
        (r.id, r.business_name, r.email, r.cpf_cnpj,
         r.is_active, r.created_date, r.profile_type, r.ingested_at)
        for r in records
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, values)
            set_watermark(cur, "clientes")
        conn.commit()

    logger.info("Clientes upsertados: %d", len(records))
    return len(records)


# ─── Agentes ──────────────────────────────────────────────────────

def upsert_agentes(records: list[AgenteRecord]) -> int:
    if not records:
        return 0

    sql = """
        INSERT INTO raw.agentes
            (id, business_name, email, team, is_active, updated_at)
        VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            business_name = EXCLUDED.business_name,
            email         = EXCLUDED.email,
            team          = EXCLUDED.team,
            is_active     = EXCLUDED.is_active,
            updated_at    = NOW()
    """
    values = [
        (r.id, r.business_name, r.email, r.team, r.is_active, r.ingested_at)
        for r in records
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, values)
            set_watermark(cur, "agentes")
        conn.commit()

    logger.info("Agentes upsertados: %d", len(records))
    return len(records)


# ─── Tickets ──────────────────────────────────────────────────────

def upsert_tickets(records: list[TicketRecord]) -> int:
    if not records:
        return 0

    sql = """
        INSERT INTO raw.tickets (
            id, subject, status, ticket_type, category, urgency,
            organization_id, organization_name, requester_id, requester_name,
            client_id, owner_id, owner_team,
            created_date, resolved_date, closed_date, last_update,
            first_action_date, sla_response_date, sla_solution_date, reopened_date,
            time_spent_total_hours, updated_at
        ) VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            status                 = EXCLUDED.status,
            organization_id        = EXCLUDED.organization_id,
            organization_name      = EXCLUDED.organization_name,
            requester_id           = EXCLUDED.requester_id,
            requester_name         = EXCLUDED.requester_name,
            client_id              = EXCLUDED.client_id,
            resolved_date          = EXCLUDED.resolved_date,
            closed_date            = EXCLUDED.closed_date,
            last_update            = EXCLUDED.last_update,
            first_action_date      = EXCLUDED.first_action_date,
            sla_response_date      = EXCLUDED.sla_response_date,
            sla_solution_date      = EXCLUDED.sla_solution_date,
            reopened_date          = EXCLUDED.reopened_date,
            time_spent_total_hours = EXCLUDED.time_spent_total_hours,
            updated_at             = NOW()
    """
    values = [
        (
            r.id, r.subject, r.status, r.ticket_type, r.category, r.urgency,
            r.organization_id or None, r.organization_name,
            r.requester_id or None, r.requester_name,
            r.client_id or None, r.owner_id or None, r.owner_team,
            r.created_date, r.resolved_date, r.closed_date, r.last_update,
            r.first_action_date, r.sla_response_date, r.sla_solution_date, r.reopened_date,
            r.time_spent_total_hours, r.ingested_at,
        )
        for r in records
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, values, page_size=500)
            set_watermark(cur, "tickets")
        conn.commit()

    logger.info("Tickets upsertados: %d", len(records))
    return len(records)


# ─── Time Entries ─────────────────────────────────────────────────

def upsert_time_entries(records: list[TimeEntryRecord]) -> int:
    if not records:
        return 0

    sql = """
        INSERT INTO raw.time_entries (
            id, ticket_id, ticket_subject,
            agent_id, agent_name,
            organization_id, organization_name,
            client_id, client_name,
            hours_spent, entry_date, description, updated_at
        ) VALUES %s
        ON CONFLICT (id) DO UPDATE SET
            hours_spent       = EXCLUDED.hours_spent,
            entry_date        = EXCLUDED.entry_date,
            description       = EXCLUDED.description,
            agent_id          = EXCLUDED.agent_id,
            agent_name        = EXCLUDED.agent_name,
            organization_id   = EXCLUDED.organization_id,
            organization_name = EXCLUDED.organization_name,
            client_id         = EXCLUDED.client_id,
            client_name       = EXCLUDED.client_name,
            updated_at        = NOW()
    """
    values = [
        (
            r.id, r.ticket_id, r.ticket_subject,
            r.agent_id or None, r.agent_name,
            r.organization_id or None, r.organization_name,
            r.client_id or None, r.client_name,
            r.hours_spent, r.entry_date, r.description, r.ingested_at,
        )
        for r in records
    ]
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, values, page_size=500)
            set_watermark(cur, "time_entries")
        conn.commit()

    logger.info("Time entries upsertadas: %d", len(records))
    return len(records)


def reconcile_time_entries(valid_ids: set[str]) -> int:
    """Remove do banco time_entries que não existem mais na API.

    Deve ser chamado após um full load para garantir que entries
    deletadas no Movidesk sejam removidas do nosso banco.
    """
    if not valid_ids:
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM raw.time_entries te
                WHERE NOT (te.id = ANY(%s::text[]))
                """,
                (list(valid_ids),),
            )
            deleted = cur.rowcount
        conn.commit()

    logger.info("Reconciliação: %d entries órfãs removidas", deleted)
    return deleted
