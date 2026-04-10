-- ════════════════════════════════════════════════════════════════
-- 06_star_schema.sql — Camada analítica: star schema
--
-- Ordem de execução: após 01 a 05.
-- Grain das facts:
--   fact_consumo  → 1 linha por lançamento de hora (time entry)
--   fact_tickets  → 1 linha por ticket
-- ════════════════════════════════════════════════════════════════


-- ══════════════════════════════════════════════════════════════
-- DIMENSÕES
-- ══════════════════════════════════════════════════════════════

-- ── dim_tempo ────────────────────────────────────────────────
-- Calendário pré-gerado (populado pelo ETL via etl/dw.py).
-- Chave: data no formato YYYYMMDD (integer, join rápido).
CREATE TABLE IF NOT EXISTS analytics.dim_tempo (
    tempo_key       INTEGER         PRIMARY KEY,   -- YYYYMMDD
    data            DATE            NOT NULL UNIQUE,
    ano             SMALLINT        NOT NULL,
    semestre        SMALLINT        NOT NULL,       -- 1 | 2
    trimestre       SMALLINT        NOT NULL,       -- 1..4
    mes             SMALLINT        NOT NULL,       -- 1..12
    mes_nome        VARCHAR(20)     NOT NULL,       -- Janeiro..Dezembro
    mes_abrev       CHAR(3)         NOT NULL,       -- Jan..Dez
    semana_ano      SMALLINT        NOT NULL,       -- ISO week 1..53
    dia_mes         SMALLINT        NOT NULL,       -- 1..31
    dia_semana      SMALLINT        NOT NULL,       -- 1=Dom .. 7=Sáb
    dia_semana_nome VARCHAR(15)     NOT NULL,
    e_fim_semana    BOOLEAN         NOT NULL,
    ano_mes         CHAR(7)         NOT NULL        -- "2025-03"
);

COMMENT ON TABLE analytics.dim_tempo IS 'Dimensão calendário — populada pelo ETL';


-- ── dim_clientes ──────────────────────────────────────────────
-- SCD Tipo 1: sempre reflete o estado atual do cliente.
CREATE TABLE IF NOT EXISTS analytics.dim_clientes (
    cliente_key     SERIAL          PRIMARY KEY,
    client_id       VARCHAR(50)     NOT NULL UNIQUE,  -- NK → raw.clientes.id
    business_name   VARCHAR(255)    NOT NULL,
    email           VARCHAR(255),
    cpf_cnpj        VARCHAR(20),
    profile_type    VARCHAR(50),
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    -- Dados de contrato vigente (denormalizados para performance no BI)
    plano_nome      VARCHAR(100),
    horas_contratadas NUMERIC(8, 2),
    vigencia_inicio DATE,
    vigencia_fim    DATE,
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  analytics.dim_clientes           IS 'Dimensão clientes (SCD Tipo 1)';
COMMENT ON COLUMN analytics.dim_clientes.client_id IS 'Chave natural — ID do Movidesk';


-- ── dim_agentes ───────────────────────────────────────────────
-- SCD Tipo 1: sempre reflete o estado atual do agente.
CREATE TABLE IF NOT EXISTS analytics.dim_agentes (
    agente_key      SERIAL          PRIMARY KEY,
    agent_id        VARCHAR(50)     NOT NULL UNIQUE,  -- NK → raw.agentes.id
    business_name   VARCHAR(255)    NOT NULL,
    email           VARCHAR(255),
    team            VARCHAR(100),
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE analytics.dim_agentes IS 'Dimensão agentes/técnicos (SCD Tipo 1)';


-- ══════════════════════════════════════════════════════════════
-- FACTS
-- ══════════════════════════════════════════════════════════════

-- ── fact_consumo ──────────────────────────────────────────────
-- Grain: 1 linha por lançamento de hora (time entry).
-- Métricas: horas_gastas.
CREATE TABLE IF NOT EXISTS analytics.fact_consumo (
    consumo_key     BIGSERIAL       PRIMARY KEY,
    time_entry_id   VARCHAR(50)     NOT NULL UNIQUE,  -- NK → raw.time_entries.id
    tempo_key       INTEGER         NOT NULL REFERENCES analytics.dim_tempo(tempo_key),
    cliente_key     INTEGER         REFERENCES analytics.dim_clientes(cliente_key),
    agente_key      INTEGER         REFERENCES analytics.dim_agentes(agente_key),
    ticket_id       VARCHAR(50),                       -- referência ao ticket
    ticket_subject  VARCHAR(500),
    horas_gastas    NUMERIC(10, 4)  NOT NULL DEFAULT 0,
    mes_referencia  CHAR(7)         NOT NULL,          -- "YYYY-MM" — partição lógica
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  analytics.fact_consumo            IS 'Fato de consumo de horas (grain: time entry)';
COMMENT ON COLUMN analytics.fact_consumo.mes_referencia IS 'Ano-mês do lançamento — facilita filtros mensais';

CREATE INDEX IF NOT EXISTS idx_fc_tempo_key   ON analytics.fact_consumo(tempo_key);
CREATE INDEX IF NOT EXISTS idx_fc_cliente_key ON analytics.fact_consumo(cliente_key);
CREATE INDEX IF NOT EXISTS idx_fc_agente_key  ON analytics.fact_consumo(agente_key);
CREATE INDEX IF NOT EXISTS idx_fc_mes_ref     ON analytics.fact_consumo(mes_referencia);


-- ── fact_tickets ──────────────────────────────────────────────
-- Grain: 1 linha por ticket.
-- Métricas: horas totais, SLA (dias para resolver).
CREATE TABLE IF NOT EXISTS analytics.fact_tickets (
    ticket_key              BIGSERIAL       PRIMARY KEY,
    ticket_id               VARCHAR(50)     NOT NULL UNIQUE,  -- NK → raw.tickets.id
    tempo_abertura_key      INTEGER         NOT NULL REFERENCES analytics.dim_tempo(tempo_key),
    tempo_resolucao_key     INTEGER         REFERENCES analytics.dim_tempo(tempo_key),
    tempo_fechamento_key    INTEGER         REFERENCES analytics.dim_tempo(tempo_key),
    cliente_key             INTEGER         REFERENCES analytics.dim_clientes(cliente_key),
    agente_key              INTEGER         REFERENCES analytics.dim_agentes(agente_key),
    status                  VARCHAR(50),
    ticket_type             VARCHAR(50),
    category                VARCHAR(100),
    urgency                 VARCHAR(50),
    owner_team              VARCHAR(100),
    time_spent_total_hours  NUMERIC(10, 4)  NOT NULL DEFAULT 0,
    dias_para_resolver      INTEGER,                           -- NULL se não resolvido
    dias_para_fechar        INTEGER,                           -- NULL se não fechado
    esta_aberto             BOOLEAN         NOT NULL DEFAULT TRUE,
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  analytics.fact_tickets                     IS 'Fato de tickets (grain: ticket)';
COMMENT ON COLUMN analytics.fact_tickets.dias_para_resolver  IS 'SLA: dias entre abertura e resolução';

CREATE INDEX IF NOT EXISTS idx_ft_abertura_key  ON analytics.fact_tickets(tempo_abertura_key);
CREATE INDEX IF NOT EXISTS idx_ft_cliente_key   ON analytics.fact_tickets(cliente_key);
CREATE INDEX IF NOT EXISTS idx_ft_agente_key    ON analytics.fact_tickets(agente_key);
CREATE INDEX IF NOT EXISTS idx_ft_status        ON analytics.fact_tickets(status);
