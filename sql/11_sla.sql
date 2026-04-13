-- ════════════════════════════════════════════════════════════════
-- 11_sla.sql — Métricas de SLA (Fase 1 da evolução)
-- Adiciona campos de SLA em raw.tickets e cria views analíticas
-- ════════════════════════════════════════════════════════════════

-- ── 1. Novas colunas em raw.tickets ─────────────────────────────
ALTER TABLE raw.tickets
    ADD COLUMN IF NOT EXISTS first_action_date TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS sla_response_date TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS sla_solution_date TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reopened_date     TIMESTAMPTZ;

COMMENT ON COLUMN raw.tickets.first_action_date IS
    'Data da primeira ação do agente (primeira resposta)';
COMMENT ON COLUMN raw.tickets.sla_response_date IS
    'Prazo contratual para primeira resposta (Movidesk slaResponseDate)';
COMMENT ON COLUMN raw.tickets.sla_solution_date IS
    'Prazo contratual para resolução (Movidesk slaSolutionDate)';
COMMENT ON COLUMN raw.tickets.reopened_date IS
    'Data da reabertura do ticket (último reopen se múltiplos)';

CREATE INDEX IF NOT EXISTS idx_tickets_sla_solution ON raw.tickets(sla_solution_date);
CREATE INDEX IF NOT EXISTS idx_tickets_first_action ON raw.tickets(first_action_date);


-- ── 2. View: SLA por ticket (base para agregações) ──────────────
CREATE OR REPLACE VIEW analytics.v_sla_tickets AS
SELECT
    t.id                                                 AS ticket_id,
    t.subject,
    t.status,
    t.urgency,
    t.category,
    t.ticket_type,
    t.organization_id,
    t.organization_name,
    t.owner_id,
    t.owner_team,
    t.created_date,
    t.first_action_date,
    t.resolved_date,
    t.closed_date,
    t.sla_response_date,
    t.sla_solution_date,

    -- TTFR: tempo até primeira resposta (horas)
    CASE
        WHEN t.first_action_date IS NOT NULL AND t.created_date IS NOT NULL
        THEN EXTRACT(EPOCH FROM (t.first_action_date - t.created_date)) / 3600.0
    END AS ttfr_horas,

    -- TTR: tempo total até resolução (horas)
    CASE
        WHEN t.resolved_date IS NOT NULL AND t.created_date IS NOT NULL
        THEN EXTRACT(EPOCH FROM (t.resolved_date - t.created_date)) / 3600.0
    END AS ttr_horas,

    -- Flags de cumprimento de SLA
    CASE
        WHEN t.sla_response_date IS NULL THEN NULL
        WHEN t.first_action_date IS NULL AND NOW() > t.sla_response_date THEN FALSE
        WHEN t.first_action_date IS NOT NULL
             AND t.first_action_date <= t.sla_response_date THEN TRUE
        WHEN t.first_action_date IS NOT NULL
             AND t.first_action_date > t.sla_response_date THEN FALSE
        ELSE NULL
    END AS dentro_sla_response,

    CASE
        WHEN t.sla_solution_date IS NULL THEN NULL
        WHEN t.resolved_date IS NULL AND NOW() > t.sla_solution_date THEN FALSE
        WHEN t.resolved_date IS NOT NULL
             AND t.resolved_date <= t.sla_solution_date THEN TRUE
        WHEN t.resolved_date IS NOT NULL
             AND t.resolved_date > t.sla_solution_date THEN FALSE
        ELSE NULL
    END AS dentro_sla_solution,

    -- Minutos restantes até estourar SLA de solução (só faz sentido p/ tickets abertos)
    CASE
        WHEN t.resolved_date IS NULL AND t.sla_solution_date IS NOT NULL
        THEN EXTRACT(EPOCH FROM (t.sla_solution_date - NOW())) / 60.0
    END AS minutos_ate_estourar_sla
FROM raw.tickets t;

COMMENT ON VIEW analytics.v_sla_tickets IS
    'SLA por ticket: TTFR, TTR e flags de cumprimento';


-- ── 3. View: KPIs gerais de SLA no mês atual ────────────────────
CREATE OR REPLACE VIEW analytics.v_sla_kpis_mes AS
SELECT
    COUNT(*) FILTER (
        WHERE DATE_TRUNC('month', created_date) = DATE_TRUNC('month', CURRENT_DATE)
    )                                                                        AS tickets_mes,
    ROUND(AVG(ttfr_horas) FILTER (
        WHERE DATE_TRUNC('month', created_date) = DATE_TRUNC('month', CURRENT_DATE)
    )::numeric, 2)                                                            AS ttfr_medio_horas,
    ROUND(AVG(ttr_horas) FILTER (
        WHERE DATE_TRUNC('month', resolved_date) = DATE_TRUNC('month', CURRENT_DATE)
    )::numeric, 2)                                                            AS ttr_medio_horas,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE dentro_sla_response = TRUE)
        / NULLIF(COUNT(*) FILTER (WHERE dentro_sla_response IS NOT NULL), 0),
        1
    )                                                                         AS pct_sla_response_ok,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE dentro_sla_solution = TRUE)
        / NULLIF(COUNT(*) FILTER (WHERE dentro_sla_solution IS NOT NULL), 0),
        1
    )                                                                         AS pct_sla_solution_ok
FROM analytics.v_sla_tickets;

COMMENT ON VIEW analytics.v_sla_kpis_mes IS
    'KPIs agregados de SLA considerando o mês corrente';


-- ── 4. View: SLA por cliente (ranking) ──────────────────────────
CREATE OR REPLACE VIEW analytics.v_sla_por_cliente AS
SELECT
    COALESCE(organization_name, 'Sem cliente')                                AS cliente,
    COUNT(*)                                                                  AS total_tickets,
    ROUND(AVG(ttfr_horas)::numeric, 2)                                        AS ttfr_medio,
    ROUND(AVG(ttr_horas)::numeric, 2)                                         AS ttr_medio,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE dentro_sla_solution = TRUE)
        / NULLIF(COUNT(*) FILTER (WHERE dentro_sla_solution IS NOT NULL), 0),
        1
    )                                                                         AS pct_sla_ok
FROM analytics.v_sla_tickets
WHERE created_date >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY organization_name
HAVING COUNT(*) >= 3
ORDER BY pct_sla_ok ASC NULLS LAST;

COMMENT ON VIEW analytics.v_sla_por_cliente IS
    'Performance de SLA por cliente nos últimos 90 dias (mín. 3 tickets)';


-- ── 5. View: SLA por categoria ──────────────────────────────────
CREATE OR REPLACE VIEW analytics.v_sla_por_categoria AS
SELECT
    COALESCE(NULLIF(category, ''), 'Sem categoria')                           AS categoria,
    COUNT(*)                                                                  AS total_tickets,
    ROUND(AVG(ttr_horas)::numeric, 2)                                         AS ttr_medio,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE dentro_sla_solution = TRUE)
        / NULLIF(COUNT(*) FILTER (WHERE dentro_sla_solution IS NOT NULL), 0),
        1
    )                                                                         AS pct_sla_ok
FROM analytics.v_sla_tickets
WHERE created_date >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY category
ORDER BY ttr_medio DESC NULLS LAST;


-- ── 6. View: tickets em risco de estourar SLA ───────────────────
CREATE OR REPLACE VIEW analytics.v_tickets_risco_sla AS
SELECT
    ticket_id,
    subject,
    COALESCE(organization_name, '-')                                          AS cliente,
    urgency,
    category,
    created_date,
    sla_solution_date,
    minutos_ate_estourar_sla,
    CASE
        WHEN minutos_ate_estourar_sla < 0         THEN 'ESTOURADO'
        WHEN minutos_ate_estourar_sla < 60        THEN 'CRITICO'
        WHEN minutos_ate_estourar_sla < 240       THEN 'ALTO'
        ELSE 'MEDIO'
    END                                                                       AS risco
FROM analytics.v_sla_tickets
WHERE status NOT IN ('Resolved', 'Closed')
  AND sla_solution_date IS NOT NULL
  AND minutos_ate_estourar_sla < 24 * 60   -- menos de 24h pra vencer
ORDER BY minutos_ate_estourar_sla ASC NULLS FIRST;

COMMENT ON VIEW analytics.v_tickets_risco_sla IS
    'Tickets abertos a menos de 24h de estourar SLA de solução';
