-- ════════════════════════════════════════════════════════════════
-- 05_views_semana34.sql — Views para dashboards de alertas
--                         e produtividade (Semana 3-4)
-- ════════════════════════════════════════════════════════════════

-- ── 1. Alerta de consumo (base do dashboard de alertas) ──────────
-- Cruza consumo do mês atual com contrato vigente.
-- Inclui todos os clientes com contrato — não só os que estouraram.
CREATE OR REPLACE VIEW analytics.v_alerta_consumo AS
SELECT
    cv.client_id,
    cv.client_name,
    cv.plano_nome,
    cv.horas_contratadas,
    COALESCE(cm.horas_mes_atual, 0)                                 AS horas_consumidas,
    COALESCE(cm.tickets_mes_atual, 0)                               AS qtd_tickets,
    cv.horas_contratadas - COALESCE(cm.horas_mes_atual, 0)          AS horas_disponiveis,
    ROUND(
        (COALESCE(cm.horas_mes_atual, 0) / cv.horas_contratadas * 100)::NUMERIC, 1
    )                                                               AS pct_consumo,
    CASE
        WHEN COALESCE(cm.horas_mes_atual, 0) >= cv.horas_contratadas        THEN 'ESTOURADO'
        WHEN COALESCE(cm.horas_mes_atual, 0) >= cv.horas_contratadas * 0.8  THEN 'CRITICO'
        WHEN COALESCE(cm.horas_mes_atual, 0) >= cv.horas_contratadas * 0.6  THEN 'ATENCAO'
        ELSE                                                                       'NORMAL'
    END                                                             AS status_consumo,
    DATE_TRUNC('month', CURRENT_DATE)::DATE                         AS mes_referencia
FROM analytics.v_contrato_vigente cv
LEFT JOIN analytics.v_resumo_mes_atual cm ON cm.client_id = cv.client_id;

COMMENT ON VIEW analytics.v_alerta_consumo IS
    'Consumo do mês atual vs. contrato vigente — alimenta o dashboard de alertas';


-- ── 2. Histórico de consumo (tendência) ──────────────────────────
-- Consumo mês a mês de cada cliente que tem contrato.
-- Permite visualizar evolução e sazonalidade.
CREATE OR REPLACE VIEW analytics.v_historico_consumo AS
SELECT
    cm.ano_mes,
    cm.client_id,
    cm.client_name,
    cm.horas_consumidas,
    cm.qtd_tickets,
    cv.horas_contratadas,
    cv.plano_nome,
    ROUND(
        (cm.horas_consumidas / cv.horas_contratadas * 100)::NUMERIC, 1
    )                                   AS pct_consumo,
    CASE
        WHEN cm.horas_consumidas >= cv.horas_contratadas        THEN 'ESTOURADO'
        WHEN cm.horas_consumidas >= cv.horas_contratadas * 0.8  THEN 'CRITICO'
        WHEN cm.horas_consumidas >= cv.horas_contratadas * 0.6  THEN 'ATENCAO'
        ELSE                                                         'NORMAL'
    END                                 AS status_consumo
FROM analytics.v_consumo_mensal cm
JOIN analytics.contratos cv
    ON  cv.client_id      = cm.client_id
    AND cv.vigencia_inicio <= cm.ano_mes
    AND (cv.vigencia_fim IS NULL OR cv.vigencia_fim >= cm.ano_mes);

COMMENT ON VIEW analytics.v_historico_consumo IS
    'Série histórica do consumo vs. contrato por cliente — gráfico de tendência';


-- ── 3. Produtividade detalhada por agente ────────────────────────
-- Expande v_produtividade_agentes com SLA e tempo médio de resolução.
CREATE OR REPLACE VIEW analytics.v_produtividade_detalhada AS
WITH base AS (
    SELECT
        DATE_TRUNC('month', te.entry_date)::DATE                    AS ano_mes,
        te.agent_id,
        te.agent_name,
        a.team,
        ROUND(SUM(te.hours_spent)::NUMERIC, 2)                      AS horas_lancadas,
        COUNT(DISTINCT te.ticket_id)                                AS qtd_tickets,
        COUNT(DISTINCT te.client_id)                                AS qtd_clientes,
        ROUND(AVG(te.hours_spent)::NUMERIC, 2)                      AS media_horas_por_lancamento
    FROM raw.time_entries te
    LEFT JOIN raw.agentes a ON a.id = te.agent_id
    WHERE te.agent_id IS NOT NULL
    GROUP BY 1, 2, 3, 4
)
SELECT
    *,
    ROUND(
        horas_lancadas /
        NULLIF(SUM(horas_lancadas) OVER (PARTITION BY ano_mes), 0) * 100, 1
    )                                                               AS pct_horas_time
FROM base;

COMMENT ON VIEW analytics.v_produtividade_detalhada IS
    'Produtividade por agente com percentual de contribuição no time';


-- ── 4. Ranking de tickets por cliente (mês atual) ────────────────
-- Top tickets que mais consumiram horas no mês corrente.
CREATE OR REPLACE VIEW analytics.v_top_tickets_mes AS
SELECT
    t.id                                    AS ticket_id,
    t.subject,
    t.status,
    t.category,
    t.urgency,
    t.client_id,
    c.business_name                         AS client_name,
    t.owner_id,
    a.business_name                         AS owner_name,
    t.created_date,
    t.time_spent_total_hours,
    -- Horas lançadas só no mês atual (pode ter horas de meses anteriores)
    COALESCE(SUM(te.hours_spent), 0)        AS horas_mes_atual
FROM raw.tickets t
LEFT JOIN raw.clientes c   ON c.id = t.client_id
LEFT JOIN raw.agentes  a   ON a.id = t.owner_id
LEFT JOIN raw.time_entries te
    ON  te.ticket_id = t.id
    AND DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
WHERE t.time_spent_total_hours > 0
GROUP BY t.id, t.subject, t.status, t.category, t.urgency,
         t.client_id, c.business_name, t.owner_id, a.business_name,
         t.created_date, t.time_spent_total_hours;

COMMENT ON VIEW analytics.v_top_tickets_mes IS
    'Tickets com maior consumo de horas — ranking para análise de gargalos';
