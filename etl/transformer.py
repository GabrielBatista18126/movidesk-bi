"""
transformer.py — Normaliza e limpa os dados brutos da API antes
                 de persistir no banco.

Mapeamento real da API Movidesk (confirmado via $metadata):
  /persons  → id, businessName, isActive, personType, createdDate
  /tickets  → id, subject, status, type, category, urgency,
               createdDate, lastUpdate, resolvedIn, closedIn, ownerTeam
               + expand: clients($expand=organization), owner,
                         actions($expand=timeAppointments)

  clients[].organization → organização (EMPRESA) do contato
  timeAppointment → id, date, accountedTime, activity, workTypeName,
                    createdBy (agente), createdByTeam
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────

def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        clean = value.split(".")[0].replace("Z", "")
        return datetime.fromisoformat(clean).replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def _parse_date_noon(value: Optional[str]) -> Optional[datetime]:
    """Parse a calendar date (e.g. timeAppointment.date) as noon UTC.

    The Movidesk API returns dates like '2026-04-01T00:00:00' in local
    (Brazil) time.  Storing that as midnight UTC causes it to shift to
    the previous day in UTC-3.  Using noon UTC keeps the date stable
    across any timezone from UTC-12 to UTC+12.
    """
    if not value:
        return None
    try:
        clean = value.split("T")[0]          # keep only YYYY-MM-DD
        d = datetime.fromisoformat(clean)    # date part only
        return d.replace(hour=12, minute=0, second=0, tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def _safe_str(value, max_len: int = 500) -> str:
    return str(value or "")[:max_len].strip()


def _to_float(value) -> float:
    try:
        return round(float(value or 0), 4)
    except (TypeError, ValueError):
        return 0.0


# ─── Data classes ─────────────────────────────────────────────────

@dataclass
class OrganizacaoRecord:
    """Representa uma organização (empresa cliente)."""
    id:            str
    business_name: str
    email:         str
    cpf_cnpj:      str
    is_active:     bool
    created_date:  Optional[datetime]
    profile_type:  str
    ingested_at:   datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ClienteRecord:
    """Mantido por compatibilidade — preferir OrganizacaoRecord para agrupamentos."""
    id:            str
    business_name: str
    email:         str
    cpf_cnpj:      str
    is_active:     bool
    created_date:  Optional[datetime]
    profile_type:  str
    ingested_at:   datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AgenteRecord:
    id:            str
    business_name: str
    email:         str
    team:          str
    is_active:     bool
    ingested_at:   datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TicketRecord:
    id:                     str
    subject:                str
    status:                 str
    ticket_type:            str
    category:               str
    urgency:                str
    # Organização (empresa) — campo principal para agrupamento BI
    organization_id:        Optional[str]
    organization_name:      str
    # Solicitante (contato individual que abriu o ticket)
    requester_id:           Optional[str]
    requester_name:         str
    # client_id: compat — aponta para organização se existir, senão contato
    client_id:              Optional[str]
    owner_id:               Optional[str]
    owner_team:             str
    created_date:           Optional[datetime]
    resolved_date:          Optional[datetime]
    closed_date:            Optional[datetime]
    last_update:            Optional[datetime]
    time_spent_total_hours: float
    ingested_at:            datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TimeEntryRecord:
    id:                str
    ticket_id:         str
    ticket_subject:    str
    agent_id:          Optional[str]
    agent_name:        str
    # Organização (empresa) — campo principal para agrupamento BI
    organization_id:   Optional[str]
    organization_name: str
    # client_id/name: compat
    client_id:         Optional[str]
    client_name:       str
    hours_spent:       float
    entry_date:        datetime
    description:       str
    ingested_at:       datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ─── Transformadores ──────────────────────────────────────────────

def transform_persons_to_clientes(persons: list[dict]) -> list[ClienteRecord]:
    records = []
    for p in persons:
        pid = _safe_str(p.get("id"))
        if not pid:
            continue
        records.append(ClienteRecord(
            id           = pid,
            business_name= _safe_str(p.get("businessName"), 255),
            email        = "",
            cpf_cnpj     = "",
            is_active    = bool(p.get("isActive", True)),
            created_date = _parse_dt(p.get("createdDate")),
            profile_type = str(p.get("personType") or ""),
        ))
    logger.info("Clientes transformados: %d", len(records))
    return records


def transform_persons_to_agentes(persons: list[dict]) -> list[AgenteRecord]:
    records = []
    seen = set()
    for p in persons:
        pid = _safe_str(p.get("id"))
        if not pid or pid in seen:
            continue
        seen.add(pid)
        records.append(AgenteRecord(
            id           = pid,
            business_name= _safe_str(p.get("businessName"), 255),
            email        = "",
            team         = "",
            is_active    = bool(p.get("isActive", True)),
        ))
    logger.info("Agentes transformados: %d", len(records))
    return records


def _extract_org_from_client(client: dict) -> tuple[Optional[str], str]:
    """
    Extrai (organization_id, organization_name) de um objeto client.

    Prioridade:
      1. client.organization.id  → organização vinculada ao contato (ideal)
      2. client.id + personType=2 → o próprio client já é uma organização
      3. fallback → usa o contato como referência
    """
    org = client.get("organization") or {}
    org_id = _safe_str(org.get("id")) if org.get("id") else None
    if org_id:
        return org_id, _safe_str(org.get("businessName"), 255)

    if str(client.get("personType") or "") == "2":
        cid = _safe_str(client.get("id")) if client.get("id") else None
        return cid, _safe_str(client.get("businessName"), 255)

    cid = _safe_str(client.get("id")) if client.get("id") else None
    return cid, _safe_str(client.get("businessName"), 255)


def transform_tickets(tickets: list[dict]) -> tuple[list[TicketRecord], list[TimeEntryRecord]]:
    """
    Transforma tickets da API em TicketRecord + TimeEntryRecord.

    Organização (empresa): clients[0].organization.id/businessName
    Solicitante (contato): clients[0].id/businessName
    """
    ticket_records:     list[TicketRecord]    = []
    time_entry_records: list[TimeEntryRecord] = []
    skipped = 0

    for t in tickets:
        raw_tid = t.get("id")
        if raw_tid is None:
            skipped += 1
            continue
        tid = str(raw_tid)
        subject = _safe_str(t.get("subject"), 500)

        owner      = t.get("owner") or {}
        owner_id   = _safe_str(owner.get("id")) or None
        owner_team = _safe_str(t.get("ownerTeam"), 100)

        clients        = t.get("clients") or []
        client         = clients[0] if clients else {}
        requester_id   = _safe_str(client.get("id")) or None
        requester_name = _safe_str(client.get("businessName"), 255)

        org_id, org_name     = _extract_org_from_client(client)
        compat_client_id     = org_id or requester_id

        total_hours = 0.0
        for action in (t.get("actions") or []):
            for appt in (action.get("timeAppointments") or []):
                total_hours += _to_float(appt.get("accountedTime"))

        ticket_records.append(TicketRecord(
            id                    = tid,
            subject               = subject,
            status                = _safe_str(t.get("status"), 50),
            ticket_type           = _safe_str(t.get("type"), 50),
            category              = _safe_str(t.get("category"), 100),
            urgency               = _safe_str(t.get("urgency"), 50),
            organization_id       = org_id,
            organization_name     = org_name,
            requester_id          = requester_id,
            requester_name        = requester_name,
            client_id             = compat_client_id,
            owner_id              = owner_id,
            owner_team            = owner_team,
            created_date          = _parse_dt(t.get("createdDate")),
            resolved_date         = _parse_dt(t.get("resolvedIn")),
            closed_date           = _parse_dt(t.get("closedIn")),
            last_update           = _parse_dt(t.get("lastUpdate")),
            time_spent_total_hours= round(total_hours, 4),
        ))

        for action in (t.get("actions") or []):
            action_created_by = action.get("createdBy") or {}
            for appt in (action.get("timeAppointments") or []):
                appt_id = appt.get("id")
                if appt_id is None:
                    continue
                hours = _to_float(appt.get("accountedTime"))
                if hours <= 0:
                    continue

                appt_agent = appt.get("createdBy") or action_created_by or {}
                agent_id   = _safe_str(appt_agent.get("id")) or owner_id
                agent_name = _safe_str(appt_agent.get("businessName"), 255)

                entry_date = _parse_date_noon(appt.get("date"))
                if not entry_date:
                    entry_date = datetime.now(timezone.utc)

                time_entry_records.append(TimeEntryRecord(
                    id                = str(appt_id),
                    ticket_id         = tid,
                    ticket_subject    = subject,
                    agent_id          = agent_id,
                    agent_name        = agent_name,
                    organization_id   = org_id,
                    organization_name = org_name,
                    client_id         = compat_client_id,
                    client_name       = org_name or requester_name,
                    hours_spent       = hours,
                    entry_date        = entry_date,
                    description       = _safe_str(
                        appt.get("activity") or appt.get("workTypeName"), 500
                    ),
                ))

    if skipped:
        logger.warning("Tickets ignorados (sem ID): %d", skipped)
    logger.info("Tickets: %d | Time entries: %d", len(ticket_records), len(time_entry_records))
    return ticket_records, time_entry_records


def collect_all_time_entry_ids(tickets: list[dict]) -> set[str]:
    """Coleta todos os IDs de timeAppointments dos tickets da API (incluindo hours=0).

    Usado na reconciliação para identificar entries deletadas no Movidesk.
    """
    ids = set()
    for t in tickets:
        for action in (t.get("actions") or []):
            for appt in (action.get("timeAppointments") or []):
                appt_id = appt.get("id")
                if appt_id is not None:
                    ids.add(str(appt_id))
    return ids


def extract_organizacoes_from_tickets(tickets: list[dict]) -> list[OrganizacaoRecord]:
    """
    Extrai organizações únicas (empresas) dos tickets.
    Fonte: ticket.clients[].organization  (expand clients($expand=organization))
    """
    seen: dict[str, OrganizacaoRecord] = {}
    for t in tickets:
        for c in (t.get("clients") or []):
            org_id, org_name = _extract_org_from_client(c)
            if not org_id or org_id in seen:
                continue
            org = c.get("organization") or {}
            seen[org_id] = OrganizacaoRecord(
                id           = org_id,
                business_name= org_name,
                email        = _safe_str(org.get("email") or c.get("email"), 255),
                cpf_cnpj     = "",
                is_active    = not (org.get("isDeleted") or c.get("isDeleted") or False),
                created_date = _parse_dt(org.get("createdDate") or c.get("createdDate")),
                profile_type = str(org.get("personType") or "2"),
            )
    records = list(seen.values())
    logger.info("Organizações extraídas dos tickets: %d", len(records))
    return records


def extract_clientes_from_tickets(tickets: list[dict]) -> list[ClienteRecord]:
    """Compatibilidade: extrai organizações e converte para ClienteRecord."""
    orgs = extract_organizacoes_from_tickets(tickets)
    return [
        ClienteRecord(
            id=o.id, business_name=o.business_name, email=o.email,
            cpf_cnpj=o.cpf_cnpj, is_active=o.is_active,
            created_date=o.created_date, profile_type=o.profile_type,
            ingested_at=o.ingested_at,
        )
        for o in orgs
    ]


def extract_agentes_from_tickets(tickets: list[dict]) -> list[AgenteRecord]:
    seen: dict[str, AgenteRecord] = {}
    for t in tickets:
        owner = t.get("owner") or {}
        oid   = _safe_str(owner.get("id"))
        if oid and oid not in seen:
            seen[oid] = AgenteRecord(
                id           = oid,
                business_name= _safe_str(owner.get("businessName"), 255),
                email        = _safe_str(owner.get("email"), 255),
                team         = _safe_str(t.get("ownerTeam"), 100),
                is_active    = True,
            )
        for action in (t.get("actions") or []):
            # action.createdBy é a fonte correta do agente que fez a ação
            action_cb = action.get("createdBy") or {}
            act_aid = _safe_str(action_cb.get("id"))
            if act_aid and act_aid not in seen:
                seen[act_aid] = AgenteRecord(
                    id           = act_aid,
                    business_name= _safe_str(action_cb.get("businessName"), 255),
                    email        = _safe_str(action_cb.get("email"), 255),
                    team         = "",
                    is_active    = True,
                )
    records = list(seen.values())
    logger.info("Agentes extraídos dos tickets: %d", len(records))
    return records
