"""
extractor.py — Consome a API do Movidesk com paginação, retry e
               estratégia incremental via watermark.

Campos mapeados a partir do $metadata real da API:
  /tickets  → TicketApiDto
  /persons  → PersonApiDto
  actions   → TicketActionApiDto (com timeAppointments aninhado)
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote

import requests

from . import config

logger = logging.getLogger(__name__)


class ApiExtractionError(RuntimeError):
    """Raised when extraction from Movidesk API fails after retries."""


# ─── Sessão HTTP ──────────────────────────────────────────────────

def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    return session


def _url(endpoint: str, params: dict) -> str:
    """
    Monta a URL com token + parâmetros OData sem codificar o '$'.
    O requests re-codifica parâmetros passados via dict, por isso
    embutimos tudo diretamente na URL string.
    """
    token_part = f"token={config.MOVIDESK_TOKEN}"
    safe_chars = "(),*;@$':="
    odata_parts = [f"{k}={quote(str(v), safe=safe_chars)}".replace("%24", "$")
                   for k, v in params.items()]
    return f"{config.MOVIDESK_BASE_URL}/{endpoint}?{token_part}&{'&'.join(odata_parts)}"


# ─── Genérico: GET com paginação e retry ─────────────────────────

def _get_with_retry(session: requests.Session, url: str) -> list:
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=30)

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", config.RETRY_DELAY * attempt))
                logger.warning("Rate limit (429). Aguardando %ds...", wait)
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else [data]

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response else 0
            if status >= 500:
                logger.warning("Erro servidor %d (tentativa %d/%d)", status, attempt, config.MAX_RETRIES)
                time.sleep(config.RETRY_DELAY * attempt)
            else:
                logger.error("Erro HTTP nao recuperavel %d: %s", status, exc)
                raise

        except requests.exceptions.RequestException as exc:
            logger.warning("Erro de rede (tentativa %d/%d): %s", attempt, config.MAX_RETRIES, exc)
            time.sleep(config.RETRY_DELAY * attempt)

    logger.error("Falha apos %d tentativas: %s", config.MAX_RETRIES, url)
    raise ApiExtractionError(f"Falha apos {config.MAX_RETRIES} tentativas: {url}")


def _paginate(session: requests.Session, endpoint: str, params: dict, entity: str) -> list[dict]:
    results = []
    skip = 0

    while True:
        paged = {**params, "$top": config.PAGE_SIZE, "$skip": skip}
        batch = _get_with_retry(session, _url(endpoint, paged))

        if not batch:
            break

        results.extend(batch)
        logger.info("[%s] skip=%d -> %d registros acumulados", entity, skip, len(results))

        if len(batch) < config.PAGE_SIZE:
            break

        skip += config.PAGE_SIZE
        time.sleep(0.25)

    return results


# ─── Persons (clientes + agentes) ────────────────────────────────

def fetch_persons(session: requests.Session, person_type: str = "2") -> list[dict]:
    """
    person_type:
      "1" → Pessoa física
      "2" → Empresa / Organização
      "4" → Agente interno

    Campos disponíveis confirmados no $metadata da API:
      id, businessName, isActive, personType, createdDate
    """
    params = {
        "$select": "id,businessName,isActive,personType,createdDate",
        "$filter": f"personType eq {person_type}",
        "$orderby": "id asc",
    }
    return _paginate(session, "persons", params, f"persons(type={person_type})")


# ─── Tickets + Actions + TimeAppointments ────────────────────────

def fetch_tickets(session: requests.Session, since: Optional[datetime] = None) -> list[dict]:
    """
    Busca tickets com clients, owner e apontamentos de horas.

    Estrutura retornada:
      ticket.clients[]           → dados do cliente
      ticket.owner               → dados do agente responsável
      ticket.actions[].timeAppointments[]  → lançamentos de horas
        timeAppointment.accountedTime      → horas gastas (Double)
        timeAppointment.createdBy          → agente que lançou
        timeAppointment.date               → data do lançamento
    """
    odata_filter = "isDeleted eq false"

    if since:
        since_safe = since - timedelta(hours=1)
        since_str  = since_safe.strftime("%Y-%m-%dT%H:%M:%SZ")
        odata_filter += f" and lastUpdate gt {since_str}"
        logger.info("Extracao incremental desde: %s", since_str)
    else:
        logger.info("Extracao completa (full load)")

    params = {
        "$select": (
            "id,subject,status,type,category,urgency,"
            "createdDate,lastUpdate,resolvedIn,closedIn,"
            "ownerTeam,actionCount"
        ),
        "$expand": "clients($expand=organization),owner,actions($expand=timeAppointments,createdBy)",
        "$filter": odata_filter,
        "$orderby": "lastUpdate asc",
    }

    return _paginate(session, "tickets", params, "tickets")
