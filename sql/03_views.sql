-- ════════════════════════════════════════════════════════════════
-- 03_views.sql — Views analíticas para o Power BI
--               Dashboard básico de consumo (Semana 1-2)
-- ════════════════════════════════════════════════════════════════

-- ── 1. Consumo mensal por cliente ────────────────────────────────
-- Horas lançadas por cliente, mês a mês.
-- Filtro padrão no Power BI: ano_mes = mês atual.
CREATE OR REPLACE VIEW analytics.v_consumo_mensal AS
SELECT
    DATE_TRUNC('month', te.entry_date)::DATE   AS ano_mes,
    te.client_id,
    te.client_name,
    ROUND(SUM(te.hours_spent)::NUMERIC, 2)     AS horas_consumidas,
    COUNT(DISTINCT te.ticket_id)               AS qtd_tickets,
    COUNT(*)                                   AS qtd_lancamentos
FROM raw.time_entries te
GROUP BY 1, 2, 3;

COMMENT ON VIEW analytics.v_consumo_mensal IS
    'Horas consumidas por cliente por mês — base do dashboard de consumo';


-- ── 2. Consumo mensal por agente ─────────────────────────────────
-- Produtividade dos técnicos mês a mês.
CREATE OR REPLACE VIEW analytics.v_produtividade_agentes AS
SELECT
    DATE_TRUNC('month', te.entry_date)::DATE   AS ano_mes,
    te.agent_id,
    te.agent_name,
    ROUND(SUM(te.hours_spent)::NUMERIC, 2)     AS horas_lancadas,
    COUNT(DISTINCT te.ticket_id)               AS qtd_tickets_atendidos,
    COUNT(DISTINCT te.client_id)               AS qtd_clientes_atendidos
FROM raw.time_entries te
WHERE te.agent_id IS NOT NULL
GROUP BY 1, 2, 3;

COMMENT ON VIEW analytics.v_produtividade_agentes IS
    'Horas lançadas por agente por mês — base do dashboard de produtividade';


-- ── 3. Tickets em aberto ─────────────────────────────────────────
-- Situação atual dos tickets ativos (não fechados).
CREATE OR REPLACE VIEW analytics.v_tickets_abertos AS
SELECT
    t.id                                       AS ticket_id,
    t.subject,
    t.status,
    t.ticket_type,
    t.category,
    t.urgency,
    t.client_id,
    c.business_name                            AS client_name,
    t.owner_id,
    a.business_name                            AS owner_name,
    a.team                                     AS owner_team,
    t.created_date,
    NOW() - t.created_date                     AS tempo_aberto,
    EXTRACT(DAY FROM NOW() - t.created_date)   AS dias_aberto,
    t.time_spent_total_hours
FROM raw.tickets t
LEFT JOIN raw.clientes c ON c.id = t.client_id
LEFT JOIN raw.agentes  a ON a.id = t.owner_id
WHERE t.status NOT IN ('Resolved', 'Closed');

COMMENT ON VIEW analytics.v_tickets_abertos IS
    'Tickets ainda em aberto com cliente, agente e tempo decorrido';


-- ── 4. Resumo do mês atual (card KPI) ───────────────────────────
-- Uma linha por cliente com totais do mês corrente.
-- Usado nos cards de KPI do dashboard.
CREATE OR REPLACE VIEW analytics.v_resumo_mes_atual AS
SELECT
    te.client_id,
    te.client_name,
    ROUND(SUM(te.hours_spent)::NUMERIC, 2)     AS horas_mes_atual,
    COUNT(DISTINCT te.ticket_id)               AS tickets_mes_atual,
    COUNT(*)                                   AS lancamentos_mes_atual,
    MAX(te.entry_date)                         AS ultimo_lancamento
FROM raw.time_entries te
WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
GROUP BY 1, 2;

COMMENT ON VIEW analytics.v_resumo_mes_atual IS
    'Totais do mês corrente por cliente — alimenta os KPIs do dashboard';


-- ── 5. Histórico de execuções do ETL ────────────────────────────
-- Para monitoramento da saúde do pipeline no próprio Power BI.
CREATE OR REPLACE VIEW analytics.v_etl_historico AS
SELECT
    id,
    started_at,
    finished_at,
    status,
    records_in,
    full_load,
    error_msg,
    EXTRACT(EPOCH FROM (finished_at - started_at))::INT AS duracao_segundos
FROM raw.etl_log
ORDER BY started_at DESC;

COMMENT ON VIEW analytics.v_etl_historico IS
    'Histórico de execuções do ETL para monitoramento no Power BI';
