"""
main.py — Orquestra o pipeline completo:
          extração → transformação → carga → alertas

Uso:
  python -m etl.main           → incremental (padrão)
  python -m etl.main --full    → full load (primeira vez)
  python -m etl.main --persons → só atualiza clientes/agentes
"""
import logging
import sys
import traceback
from datetime import datetime, timezone

from . import config
from .alerts import alert_contract_overflow, alert_etl_failure
from .extractor import build_session, fetch_persons, fetch_tickets
from .dw import run_dw
from .ml import run_ml
from .loader import (
    get_conn,
    get_watermark,
    log_etl_start,
    log_etl_end,
    reconcile_time_entries,
    upsert_agentes,
    upsert_clientes,
    upsert_organizacoes,
    upsert_tickets,
    upsert_time_entries,
)
from .transformer import (
    collect_all_time_entry_ids,
    transform_persons_to_agentes,
    transform_persons_to_clientes,
    transform_tickets,
    extract_clientes_from_tickets,
    extract_organizacoes_from_tickets,
    extract_agentes_from_tickets,
)

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────

def _check_overflows() -> None:
    """Consulta o banco e dispara alerta se clientes ultrapassaram 80% do contrato."""
    sql = """
        WITH consumo AS (
            SELECT
                COALESCE(te.organization_id, te.client_id) AS org_id,
                COALESCE(te.organization_name, te.client_name) AS org_name,
                SUM(te.hours_spent) AS horas_consumidas
            FROM raw.time_entries te
            WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY 1, 2
        ),
        contrato AS (
            SELECT DISTINCT ON (COALESCE(organization_id, client_id))
                COALESCE(organization_id, client_id) AS org_id,
                horas_contratadas
            FROM analytics.contratos
            WHERE vigencia_inicio <= CURRENT_DATE
              AND (vigencia_fim IS NULL OR vigencia_fim >= CURRENT_DATE)
            ORDER BY COALESCE(organization_id, client_id), vigencia_inicio DESC
        )
        SELECT
            co.org_name,
            ROUND(co.horas_consumidas::numeric, 2),
            ct.horas_contratadas,
            ROUND((co.horas_consumidas / ct.horas_contratadas * 100)::numeric, 1)
        FROM consumo co
        JOIN contrato ct ON ct.org_id = co.org_id
        WHERE co.horas_consumidas >= ct.horas_contratadas * 0.8
        ORDER BY 4 DESC
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        if rows:
            alert_contract_overflow([
                {"client_name": r[0], "horas_consumidas": float(r[1]),
                 "horas_contratadas": float(r[2]), "pct_consumo": float(r[3])}
                for r in rows
            ])
    except Exception as exc:
        logger.warning("Não foi possível verificar estouros: %s", exc)


# ─── Steps ────────────────────────────────────────────────────────

def run_persons(session) -> int:
    logger.info("── Etapa: Persons (clientes + agentes) ──")

    raw_clientes = fetch_persons(session, person_type="2")
    clientes = transform_persons_to_clientes(raw_clientes)
    n_clientes = upsert_clientes(clientes)

    raw_agentes = fetch_persons(session, person_type="4")
    agentes = transform_persons_to_agentes(raw_agentes)
    n_agentes = upsert_agentes(agentes)

    return n_clientes + n_agentes


def run_tickets(session, full_load: bool) -> int:
    logger.info("── Etapa: Tickets + Time Entries ──")

    since = None if full_load else get_watermark("time_entries")
    raw_tickets = fetch_tickets(session, since=since)

    if not raw_tickets:
        logger.info("Nenhum ticket novo encontrado.")
        return 0

    # Extrai organizações reais (clients[].organization) dos tickets
    orgs = extract_organizacoes_from_tickets(raw_tickets)
    upsert_organizacoes(orgs)
    # Mantém raw.clientes sincronizado por compatibilidade
    clientes_from_tickets = extract_clientes_from_tickets(raw_tickets)
    upsert_clientes(clientes_from_tickets)

    agentes_from_tickets = extract_agentes_from_tickets(raw_tickets)
    upsert_agentes(agentes_from_tickets)

    ticket_records, time_entry_records = transform_tickets(raw_tickets)
    n_tickets = upsert_tickets(ticket_records)
    n_te      = upsert_time_entries(time_entry_records)

    # Reconciliação: remove entries deletadas no Movidesk
    if full_load:
        valid_ids = collect_all_time_entry_ids(raw_tickets)
        reconcile_time_entries(valid_ids)
    else:
        # Incremental: reconcilia apenas os tickets que foram atualizados
        updated_ticket_ids = {str(t.get("id")) for t in raw_tickets if t.get("id") is not None}
        if updated_ticket_ids:
            valid_ids = collect_all_time_entry_ids(raw_tickets)
            _reconcile_updated_tickets(updated_ticket_ids, valid_ids)

    return n_tickets + n_te


def _reconcile_updated_tickets(ticket_ids: set[str], valid_entry_ids: set[str]) -> int:
    """Reconcilia entries dos tickets que foram atualizados no incremental.

    Compara entries no banco para esses tickets específicos com as que
    vieram da API — remove as que sumiram.
    """
    if not ticket_ids:
        return 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM raw.time_entries
                WHERE ticket_id = ANY(%s::text[])
                  AND NOT (id = ANY(%s::text[]))
                """,
                (list(ticket_ids), list(valid_entry_ids)),
            )
            deleted = cur.rowcount
        conn.commit()

    logger.info("Reconciliação incremental: %d entries órfãs removidas de %d tickets",
                deleted, len(ticket_ids))
    return deleted


# ─── Entrypoint ───────────────────────────────────────────────────

def run(full_load: bool = False, only_persons: bool = False) -> None:
    start = datetime.now(timezone.utc)
    logger.info("════ ETL Movidesk iniciado | full=%s | persons_only=%s ════",
                full_load, only_persons)

    session    = build_session()
    log_id     = log_etl_start(full_load=full_load)
    total_records = 0

    try:
        total_records += run_persons(session)

        if not only_persons:
            total_records += run_tickets(session, full_load=full_load)
            total_records += run_dw(full_load=full_load)
            total_records += run_ml()
            _check_overflows()

    except Exception as exc:
        logger.error("ETL falhou: %s", exc)
        logger.debug(traceback.format_exc())
        log_etl_end(log_id, status="FAILURE", records_in=total_records, error_msg=str(exc))
        alert_etl_failure(exc, step="Pipeline principal")
        sys.exit(1)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    log_etl_end(log_id, status="SUCCESS", records_in=total_records)
    logger.info("════ ETL concluído em %.1fs | %d registros ════", elapsed, total_records)


if __name__ == "__main__":
    full_load    = "--full"    in sys.argv
    only_persons = "--persons" in sys.argv
    run(full_load=full_load, only_persons=only_persons)
