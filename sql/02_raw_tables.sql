-- ════════════════════════════════════════════════════════════════
-- 02_raw_tables.sql — Tabelas brutas (espelho da API Movidesk)
-- ════════════════════════════════════════════════════════════════

-- ── Clientes (organizations / persons) ──────────────────────────
CREATE TABLE IF NOT EXISTS raw.clientes (
    id              VARCHAR(50)     NOT NULL,
    business_name   VARCHAR(255)    NOT NULL,
    email           VARCHAR(255),
    cpf_cnpj        VARCHAR(20),
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_date    TIMESTAMPTZ,
    profile_type    VARCHAR(50),                           -- "Organization" | "Person"
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_clientes PRIMARY KEY (id)
);

COMMENT ON TABLE  raw.clientes           IS 'Clientes importados da API Movidesk (persons)';
COMMENT ON COLUMN raw.clientes.id        IS 'ID interno do Movidesk';
COMMENT ON COLUMN raw.clientes.cpf_cnpj  IS 'CPF ou CNPJ (sem formatação)';


-- ── Agentes (técnicos / suporte) ────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.agentes (
    id              VARCHAR(50)     NOT NULL,
    business_name   VARCHAR(255)    NOT NULL,
    email           VARCHAR(255),
    team            VARCHAR(100),
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_agentes PRIMARY KEY (id)
);

COMMENT ON TABLE raw.agentes IS 'Agentes internos (técnicos de suporte)';


-- ── Tickets ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.tickets (
    id                      VARCHAR(50)     NOT NULL,
    subject                 VARCHAR(500)    NOT NULL,
    status                  VARCHAR(50),                   -- New | InAttendance | Resolved | Closed
    ticket_type             VARCHAR(50),                   -- Incident | Request | Problem
    category                VARCHAR(100),
    urgency                 VARCHAR(50),                   -- Low | Normal | High | Urgent
    client_id               VARCHAR(50),
    owner_id                VARCHAR(50),
    owner_team              VARCHAR(100),
    created_date            TIMESTAMPTZ,
    resolved_date           TIMESTAMPTZ,
    closed_date             TIMESTAMPTZ,
    last_update             TIMESTAMPTZ,
    time_spent_total_hours  NUMERIC(10, 4)  NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_tickets      PRIMARY KEY (id),
    CONSTRAINT fk_ticket_client FOREIGN KEY (client_id) REFERENCES raw.clientes(id) ON DELETE SET NULL,
    CONSTRAINT fk_ticket_owner  FOREIGN KEY (owner_id)  REFERENCES raw.agentes(id)  ON DELETE SET NULL
);

COMMENT ON TABLE  raw.tickets                     IS 'Tickets importados do Movidesk';
COMMENT ON COLUMN raw.tickets.time_spent_total_hours IS 'Total de horas lançadas (soma das time entries)';
COMMENT ON COLUMN raw.tickets.status              IS 'Status atual: New, InAttendance, Resolved, Closed';

CREATE INDEX IF NOT EXISTS idx_tickets_client_id    ON raw.tickets(client_id);
CREATE INDEX IF NOT EXISTS idx_tickets_owner_id     ON raw.tickets(owner_id);
CREATE INDEX IF NOT EXISTS idx_tickets_created_date ON raw.tickets(created_date);
CREATE INDEX IF NOT EXISTS idx_tickets_status       ON raw.tickets(status);


-- ── Time Entries ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.time_entries (
    id              VARCHAR(50)     NOT NULL,
    ticket_id       VARCHAR(50)     NOT NULL,
    ticket_subject  VARCHAR(500),
    agent_id        VARCHAR(50),
    agent_name      VARCHAR(255),
    client_id       VARCHAR(50),
    client_name     VARCHAR(255),
    hours_spent     NUMERIC(10, 4)  NOT NULL DEFAULT 0,
    entry_date      TIMESTAMPTZ     NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_time_entries          PRIMARY KEY (id),
    CONSTRAINT fk_te_ticket             FOREIGN KEY (ticket_id)  REFERENCES raw.tickets(id)  ON DELETE CASCADE,
    CONSTRAINT fk_te_agent              FOREIGN KEY (agent_id)   REFERENCES raw.agentes(id)  ON DELETE SET NULL,
    CONSTRAINT fk_te_client             FOREIGN KEY (client_id)  REFERENCES raw.clientes(id) ON DELETE SET NULL,
    CONSTRAINT ck_hours_positive        CHECK (hours_spent >= 0)
);

COMMENT ON TABLE  raw.time_entries             IS 'Lançamentos de horas por ticket';
COMMENT ON COLUMN raw.time_entries.hours_spent IS 'Horas gastas (convertido de minutos do Movidesk)';

CREATE INDEX IF NOT EXISTS idx_te_ticket_id   ON raw.time_entries(ticket_id);
CREATE INDEX IF NOT EXISTS idx_te_agent_id    ON raw.time_entries(agent_id);
CREATE INDEX IF NOT EXISTS idx_te_client_id   ON raw.time_entries(client_id);
CREATE INDEX IF NOT EXISTS idx_te_entry_date  ON raw.time_entries(entry_date);
-- idx_te_year_month removido: cast TIMESTAMPTZ->DATE não é IMMUTABLE no PostgreSQL
-- Filtros por mês usam idx_te_entry_date normalmente


-- ── Controle de ETL (watermark incremental) ─────────────────────
CREATE TABLE IF NOT EXISTS raw.etl_watermark (
    table_name  VARCHAR(100)    NOT NULL,
    last_run    TIMESTAMPTZ     NOT NULL,

    CONSTRAINT pk_watermark PRIMARY KEY (table_name)
);

COMMENT ON TABLE raw.etl_watermark IS 'Controla a última execução do ETL por tabela (ingestão incremental)';


-- ── Log de execuções do ETL ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.etl_log (
    id          SERIAL          PRIMARY KEY,
    started_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status      VARCHAR(20),                       -- 'SUCCESS' | 'FAILURE'
    records_in  INTEGER         DEFAULT 0,
    error_msg   TEXT,
    full_load   BOOLEAN         DEFAULT FALSE
);
