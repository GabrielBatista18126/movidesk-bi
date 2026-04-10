-- =============================================================================
-- 08_refactoring_v2.sql
-- Drop todas as views analytics para permitir recriação limpa
DROP VIEW IF EXISTS analytics.v_sugestoes_upgrade        CASCADE;
DROP VIEW IF EXISTS analytics.v_produtividade_detalhada  CASCADE;
DROP VIEW IF EXISTS analytics.v_historico_consumo        CASCADE;
DROP VIEW IF EXISTS analytics.v_alerta_consumo           CASCADE;
DROP VIEW IF EXISTS analytics.v_top_tickets_mes          CASCADE;
DROP VIEW IF EXISTS analytics.v_tickets_abertos          CASCADE;
DROP VIEW IF EXISTS analytics.v_resumo_mes_atual         CASCADE;
DROP VIEW IF EXISTS analytics.v_produtividade_agentes    CASCADE;
DROP VIEW IF EXISTS analytics.v_consumo_mensal           CASCADE;
DROP VIEW IF EXISTS analytics.v_etl_historico            CASCADE;
DROP VIEW IF EXISTS analytics.v_contrato_vigente         CASCADE;
-- Refactoring: Separação Organização × Usuário/Contato
-- Corrige o problema central: BI agora agrupa por ORGANIZAÇÃO (empresa),
-- não por usuário/contato individual.
-- =============================================================================

-- 1. Tabela raw.organizacoes (empresas clientes)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw.organizacoes (
    id            VARCHAR(50)  PRIMARY KEY,
    business_name VARCHAR(255) NOT NULL DEFAULT '',
    email         VARCHAR(255) DEFAULT '',
    cpf_cnpj      VARCHAR(20)  DEFAULT '',
    is_active     BOOLEAN      DEFAULT TRUE,
    created_date  TIMESTAMPTZ,
    profile_type  VARCHAR(50)  DEFAULT '',
    created_at    TIMESTAMPTZ  DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  DEFAULT NOW()
);

-- 2. Adicionar colunas de organização em raw.tickets
-- ─────────────────────────────────────────────────
ALTER TABLE raw.tickets
    ADD COLUMN IF NOT EXISTS organization_id   VARCHAR(50),
    ADD COLUMN IF NOT EXISTS organization_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS requester_id      VARCHAR(50),
    ADD COLUMN IF NOT EXISTS requester_name    VARCHAR(255);

-- 3. Adicionar colunas de organização em raw.time_entries
-- ───────────────────────────────────────────────────────
ALTER TABLE raw.time_entries
    ADD COLUMN IF NOT EXISTS organization_id   VARCHAR(50),
    ADD COLUMN IF NOT EXISTS organization_name VARCHAR(255);

-- 4. Índices
-- ──────────
CREATE INDEX IF NOT EXISTS idx_tickets_org_id ON raw.tickets(organization_id);
CREATE INDEX IF NOT EXISTS idx_te_org_id      ON raw.time_entries(organization_id);

-- 5. Backfill: usa client_id existente como organization_id (ponto de partida)
--    Após o próximo ETL full load, os dados serão sobrescritos com org real
-- ──────────────────────────────────────────────────────────────────────────
UPDATE raw.tickets t
SET
    organization_id   = c.id,
    organization_name = c.business_name
FROM raw.clientes c
WHERE t.client_id = c.id
  AND t.organization_id IS NULL;

UPDATE raw.time_entries te
SET
    organization_id   = te.client_id,
    organization_name = te.client_name
WHERE te.organization_id IS NULL;

-- 6. Popula raw.organizacoes a partir de raw.clientes existentes
-- ──────────────────────────────────────────────────────────────
INSERT INTO raw.organizacoes (id, business_name, email, cpf_cnpj, is_active, created_date, profile_type, created_at, updated_at)
SELECT id, business_name, email, cpf_cnpj, is_active, created_date, profile_type, created_at, updated_at
FROM raw.clientes
ON CONFLICT (id) DO UPDATE SET
    business_name = EXCLUDED.business_name,
    email         = EXCLUDED.email,
    is_active     = EXCLUDED.is_active,
    updated_at    = NOW();

-- 7. Atualiza analytics.contratos para suportar organization_id
-- ─────────────────────────────────────────────────────────────
ALTER TABLE analytics.contratos
    ADD COLUMN IF NOT EXISTS organization_id VARCHAR(50);

UPDATE analytics.contratos
SET organization_id = client_id
WHERE organization_id IS NULL;

-- =============================================================================
-- VIEWS REFATORADAS — agrupamento por ORGANIZAÇÃO
-- =============================================================================

-- v_contrato_vigente: suporte a organization_id
-- ──────────────────────────────────────────────
CREATE VIEW analytics.v_contrato_vigente AS
SELECT DISTINCT ON (COALESCE(organization_id, client_id))
    COALESCE(organization_id, client_id) AS client_id,
    client_name,
    plano_nome,
    horas_contratadas,
    vigencia_inicio,
    vigencia_fim,
    valor_mensal
FROM analytics.contratos
WHERE vigencia_inicio <= CURRENT_DATE
  AND (vigencia_fim IS NULL OR vigencia_fim >= CURRENT_DATE)
ORDER BY COALESCE(organization_id, client_id), vigencia_inicio DESC;

-- v_consumo_mensal: agrupado por ORGANIZAÇÃO
-- ───────────────────────────────────────────
CREATE VIEW analytics.v_consumo_mensal AS
SELECT
    TO_CHAR(te.entry_date, 'YYYY-MM')                          AS ano_mes,
    COALESCE(te.organization_id, te.client_id)                 AS client_id,
    COALESCE(te.organization_name, te.client_name, '')         AS client_name,
    ROUND(SUM(te.hours_spent)::numeric, 2)                     AS horas_consumidas,
    COUNT(DISTINCT te.ticket_id)                               AS qtd_tickets,
    COUNT(te.id)                                               AS qtd_lancamentos
FROM raw.time_entries te
WHERE te.hours_spent > 0
GROUP BY 1, 2, 3;

-- v_resumo_mes_atual: agrupado por ORGANIZAÇÃO
-- ─────────────────────────────────────────────
CREATE VIEW analytics.v_resumo_mes_atual AS
SELECT
    COALESCE(te.organization_id, te.client_id)                 AS client_id,
    COALESCE(te.organization_name, te.client_name, '')         AS client_name,
    ROUND(SUM(te.hours_spent)::numeric, 2)                     AS horas_mes_atual,
    COUNT(DISTINCT te.ticket_id)                               AS tickets_mes_atual,
    COUNT(te.id)                                               AS lancamentos_mes_atual,
    MAX(te.entry_date)                                         AS ultimo_lancamento
FROM raw.time_entries te
WHERE DATE_TRUNC('month', te.entry_date) = DATE_TRUNC('month', CURRENT_DATE)
  AND te.hours_spent > 0
GROUP BY 1, 2;

-- v_produtividade_agentes: por agente (lógica correta)
-- ─────────────────────────────────────────────────────
CREATE VIEW analytics.v_produtividade_agentes AS
SELECT
    TO_CHAR(te.entry_date, 'YYYY-MM')                          AS ano_mes,
    te.agent_id,
    COALESCE(a.business_name, te.agent_name, '')               AS agent_name,
    ROUND(SUM(te.hours_spent)::numeric, 2)                     AS horas_lancadas,
    COUNT(DISTINCT te.ticket_id)                               AS qtd_tickets_atendidos,
    COUNT(DISTINCT COALESCE(te.organization_id, te.client_id)) AS qtd_clientes_atendidos
FROM raw.time_entries te
LEFT JOIN raw.agentes a ON a.id = te.agent_id
WHERE te.hours_spent > 0
GROUP BY 1, 2, 3;

-- v_tickets_abertos: vinculado à ORGANIZAÇÃO
-- ────────────────────────────────────────────
CREATE VIEW analytics.v_tickets_abertos AS
SELECT
    t.id                                                               AS ticket_id,
    t.subject,
    t.status,
    t.ticket_type,
    t.category,
    t.urgency,
    COALESCE(t.organization_id, t.client_id)                          AS client_id,
    COALESCE(t.organization_name, o.business_name, '')                AS client_name,
    t.owner_id,
    COALESCE(a.business_name, '')                                     AS owner_name,
    t.owner_team,
    t.created_date,
    NOW() - t.created_date                                            AS tempo_aberto,
    EXTRACT(DAY FROM NOW() - t.created_date)::INTEGER                 AS dias_aberto,
    t.time_spent_total_hours
FROM raw.tickets t
LEFT JOIN raw.organizacoes o ON o.id = COALESCE(t.organization_id, t.client_id)
LEFT JOIN raw.agentes       a ON a.id = t.owner_id
WHERE t.status NOT IN ('Resolved', 'Closed')
  AND t.created_date IS NOT NULL;

-- v_etl_historico (sem mudança de lógica)
-- ─────────────────────────────────────────
CREATE VIEW analytics.v_etl_historico AS
SELECT
    id, started_at, finished_at, status, records_in, full_load, error_msg,
    CASE WHEN finished_at IS NOT NULL
         THEN EXTRACT(EPOCH FROM (finished_at - started_at))::INTEGER
    END AS duracao_segundos
FROM raw.etl_log
ORDER BY started_at DESC;

-- v_alerta_consumo: usa ORGANIZAÇÃO
-- ───────────────────────────────────
CREATE VIEW analytics.v_alerta_consumo AS
SELECT
    r.client_id,
    r.client_name,
    cv.plano_nome,
    cv.horas_contratadas,
    r.horas_mes_atual                                  AS horas_consumidas,
    r.tickets_mes_atual                                AS qtd_tickets,
    cv.horas_contratadas - r.horas_mes_atual           AS horas_disponiveis,
    CASE WHEN cv.horas_contratadas > 0
         THEN ROUND((r.horas_mes_atual / cv.horas_contratadas * 100)::numeric, 1)
    END                                                AS pct_consumo,
    CASE
        WHEN cv.horas_contratadas IS NULL              THEN 'SEM_CONTRATO'
        WHEN r.horas_mes_atual >= cv.horas_contratadas THEN 'ESTOURADO'
        WHEN r.horas_mes_atual >= cv.horas_contratadas * 0.8 THEN 'CRITICO'
        WHEN r.horas_mes_atual >= cv.horas_contratadas * 0.6 THEN 'ATENCAO'
        ELSE 'NORMAL'
    END                                                AS status_consumo,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM')                   AS mes_referencia
FROM analytics.v_resumo_mes_atual r
LEFT JOIN analytics.v_contrato_vigente cv ON cv.client_id = r.client_id;

-- v_historico_consumo: usa ORGANIZAÇÃO
-- ──────────────────────────────────────
CREATE VIEW analytics.v_historico_consumo AS
SELECT
    cm.ano_mes,
    cm.client_id,
    cm.client_name,
    cv.plano_nome,
    cv.horas_contratadas,
    cm.horas_consumidas,
    cm.qtd_tickets,
    cm.qtd_lancamentos,
    CASE WHEN cv.horas_contratadas > 0
         THEN ROUND((cm.horas_consumidas / cv.horas_contratadas * 100)::numeric, 1)
    END AS pct_consumo,
    CASE
        WHEN cv.horas_contratadas IS NULL              THEN 'SEM_CONTRATO'
        WHEN cm.horas_consumidas >= cv.horas_contratadas THEN 'ESTOURADO'
        WHEN cm.horas_consumidas >= cv.horas_contratadas * 0.8 THEN 'CRITICO'
        WHEN cm.horas_consumidas >= cv.horas_contratadas * 0.6 THEN 'ATENCAO'
        ELSE 'NORMAL'
    END AS status_consumo
FROM analytics.v_consumo_mensal cm
LEFT JOIN analytics.v_contrato_vigente cv ON cv.client_id = cm.client_id;

-- v_produtividade_detalhada: métricas expandidas por agente
-- ──────────────────────────────────────────────────────────
CREATE VIEW analytics.v_produtividade_detalhada AS
WITH base AS (
    SELECT
        pa.ano_mes,
        pa.agent_id,
        pa.agent_name,
        COALESCE(a.team, '')             AS team,
        pa.horas_lancadas,
        pa.qtd_tickets_atendidos         AS qtd_tickets,
        pa.qtd_clientes_atendidos        AS qtd_clientes,
        CASE WHEN pa.qtd_tickets_atendidos > 0
             THEN ROUND((pa.horas_lancadas / pa.qtd_tickets_atendidos)::numeric, 2)
        END AS media_horas_por_ticket,
        CASE WHEN pa.horas_lancadas > 0
             THEN ROUND((pa.qtd_tickets_atendidos / pa.horas_lancadas)::numeric, 2)
        END AS tickets_por_hora
    FROM analytics.v_produtividade_agentes pa
    LEFT JOIN raw.agentes a ON a.id = pa.agent_id
),
totais_mes AS (
    SELECT ano_mes, SUM(horas_lancadas) AS total_horas_time
    FROM base
    GROUP BY ano_mes
)
SELECT
    b.*,
    CASE WHEN tm.total_horas_time > 0
         THEN ROUND((b.horas_lancadas / tm.total_horas_time * 100)::numeric, 1)
    END AS pct_horas_time
FROM base b
LEFT JOIN totais_mes tm USING (ano_mes);

-- v_top_tickets_mes: usa ORGANIZAÇÃO
-- ────────────────────────────────────
CREATE VIEW analytics.v_top_tickets_mes AS
SELECT
    t.id                                                               AS ticket_id,
    t.subject,
    t.status,
    t.category,
    t.urgency,
    COALESCE(t.organization_id, t.client_id)                          AS client_id,
    COALESCE(t.organization_name, o.business_name, '')                AS client_name,
    t.owner_id,
    COALESCE(a.business_name, '')                                     AS owner_name,
    t.created_date,
    t.time_spent_total_hours,
    COALESCE(te_mes.horas_mes_atual, 0)                               AS horas_mes_atual
FROM raw.tickets t
LEFT JOIN raw.organizacoes o ON o.id = COALESCE(t.organization_id, t.client_id)
LEFT JOIN raw.agentes       a ON a.id = t.owner_id
LEFT JOIN (
    SELECT ticket_id, ROUND(SUM(hours_spent)::numeric, 2) AS horas_mes_atual
    FROM raw.time_entries
    WHERE DATE_TRUNC('month', entry_date) = DATE_TRUNC('month', CURRENT_DATE)
    GROUP BY ticket_id
) te_mes ON te_mes.ticket_id = t.id
WHERE te_mes.horas_mes_atual > 0;

-- v_sugestoes_upgrade: usa ORGANIZAÇÃO
-- ──────────────────────────────────────
CREATE VIEW analytics.v_sugestoes_upgrade AS
WITH historico AS (
    SELECT
        hc.client_id,
        hc.client_name,
        hc.horas_contratadas,
        AVG(hc.horas_consumidas)   AS media_horas_6m,
        MAX(hc.pct_consumo)        AS pico_consumo_pct,
        COUNT(*)                   AS meses_com_dados,
        SUM(CASE WHEN hc.status_consumo IN ('ESTOURADO','CRITICO') THEN 1 ELSE 0 END) AS meses_estourados
    FROM analytics.v_historico_consumo hc
    WHERE hc.ano_mes >= TO_CHAR((CURRENT_DATE - INTERVAL '6 months')::DATE, 'YYYY-MM')
    GROUP BY hc.client_id, hc.client_name, hc.horas_contratadas
),
scores AS (
    SELECT client_id, score_total
    FROM analytics.score_clientes
)
SELECT
    h.client_id,
    h.client_name,
    h.horas_contratadas                                              AS horas_contratadas_atual,
    ROUND(h.media_horas_6m::numeric, 1)                             AS media_horas_6m,
    h.meses_estourados,
    h.meses_com_dados,
    ROUND(h.pico_consumo_pct::numeric, 1)                           AS pico_consumo_pct,
    CEIL(h.media_horas_6m * 1.2 / 5) * 5                           AS horas_sugeridas,
    COALESCE(s.score_total, 0)                                      AS score_total,
    CASE
        WHEN h.meses_estourados >= 2 THEN 'URGENTE'
        WHEN h.media_horas_6m > h.horas_contratadas * 0.9 THEN 'RECOMENDADO'
        WHEN h.media_horas_6m > h.horas_contratadas * 0.75 THEN 'SUGERIDO'
        ELSE 'OPCIONAL'
    END AS risco,
    CONCAT(
        'Consumo médio de ', ROUND(h.media_horas_6m::numeric,1), 'h em ',
        h.meses_com_dados, ' meses | Pico: ', ROUND(h.pico_consumo_pct::numeric,0), '% | ',
        h.meses_estourados, ' mês(es) estourado(s)'
    ) AS justificativa
FROM historico h
LEFT JOIN scores s ON s.client_id = h.client_id
WHERE h.media_horas_6m > h.horas_contratadas * 0.6
  AND h.meses_com_dados >= 2
ORDER BY h.meses_estourados DESC, h.media_horas_6m DESC;

-- =============================================================================
-- NOVAS VIEWS — KPIs adicionais
-- =============================================================================

-- v_produtividade_agente_resumo: visão consolidada por agente (mês atual + histórico)
-- ──────────────────────────────────────────────────────────────────────────────────
CREATE VIEW analytics.v_produtividade_agente_resumo AS
SELECT
    a.id                                                               AS agent_id,
    a.business_name                                                    AS agent_name,
    COALESCE(a.team, '')                                               AS team,
    -- Mês atual
    COALESCE(ROUND(ma.horas_mes::numeric, 2), 0)                      AS horas_mes_atual,
    COALESCE(ma.tickets_mes, 0)                                        AS tickets_mes_atual,
    COALESCE(ma.clientes_mes, 0)                                       AS clientes_mes_atual,
    CASE WHEN COALESCE(ma.horas_mes, 0) > 0
         THEN ROUND((ma.tickets_mes / ma.horas_mes)::numeric, 2)
    END                                                                AS tickets_por_hora_mes,
    CASE WHEN COALESCE(ma.tickets_mes, 0) > 0
         THEN ROUND((ma.horas_mes / ma.tickets_mes)::numeric, 2)
    END                                                                AS media_horas_por_ticket_mes,
    -- Histórico geral
    COALESCE(ROUND(hist.total_horas::numeric, 2), 0)                  AS total_horas_historico,
    COALESCE(hist.total_tickets, 0)                                    AS total_tickets_historico,
    CASE WHEN COALESCE(hist.total_horas, 0) > 0
         THEN ROUND((hist.total_tickets / hist.total_horas)::numeric, 2)
    END                                                                AS eficiencia_geral
FROM raw.agentes a
LEFT JOIN (
    SELECT
        agent_id,
        SUM(hours_spent)              AS horas_mes,
        COUNT(DISTINCT ticket_id)     AS tickets_mes,
        COUNT(DISTINCT COALESCE(organization_id, client_id)) AS clientes_mes
    FROM raw.time_entries
    WHERE DATE_TRUNC('month', entry_date) = DATE_TRUNC('month', CURRENT_DATE)
      AND hours_spent > 0
    GROUP BY agent_id
) ma ON ma.agent_id = a.id
LEFT JOIN (
    SELECT
        agent_id,
        SUM(hours_spent)              AS total_horas,
        COUNT(DISTINCT ticket_id)     AS total_tickets
    FROM raw.time_entries
    WHERE hours_spent > 0
    GROUP BY agent_id
) hist ON hist.agent_id = a.id
WHERE a.is_active = TRUE
   OR COALESCE(ma.horas_mes, 0) > 0;

-- v_sla_performance: SLA e tempo médio de resolução por organização/mês
-- ──────────────────────────────────────────────────────────────────────
CREATE VIEW analytics.v_sla_performance AS
SELECT
    TO_CHAR(t.created_date, 'YYYY-MM')                                AS ano_mes,
    COALESCE(t.organization_id, t.client_id)                          AS client_id,
    COALESCE(t.organization_name, o.business_name, '')                AS client_name,
    COUNT(*)                                                           AS total_tickets,
    COUNT(t.resolved_date)                                             AS tickets_resolvidos,
    ROUND(AVG(CASE WHEN t.resolved_date IS NOT NULL
        THEN EXTRACT(EPOCH FROM (t.resolved_date - t.created_date)) / 3600.0
    END)::numeric, 2)                                                  AS tmr_horas,
    ROUND(AVG(CASE WHEN t.resolved_date IS NOT NULL
        THEN EXTRACT(EPOCH FROM (t.resolved_date - t.created_date)) / 86400.0
    END)::numeric, 1)                                                  AS tmr_dias,
    COUNT(CASE WHEN t.urgency = 'Urgent' THEN 1 END)                  AS tickets_urgentes,
    COUNT(CASE WHEN t.urgency = 'High'   THEN 1 END)                  AS tickets_alta_prioridade,
    ROUND(
        COUNT(t.resolved_date)::numeric / NULLIF(COUNT(*), 0) * 100, 1
    )                                                                  AS taxa_resolucao_pct
FROM raw.tickets t
LEFT JOIN raw.organizacoes o ON o.id = COALESCE(t.organization_id, t.client_id)
WHERE t.created_date IS NOT NULL
GROUP BY 1, 2, 3;

-- v_retrabalho: taxa de reabertura de tickets por organização/mês
-- ───────────────────────────────────────────────────────────────
CREATE VIEW analytics.v_retrabalho AS
SELECT
    TO_CHAR(t.created_date, 'YYYY-MM')                                AS ano_mes,
    COALESCE(t.organization_id, t.client_id)                          AS client_id,
    COALESCE(t.organization_name, o.business_name, '')                AS client_name,
    COUNT(*)                                                           AS total_tickets,
    COUNT(CASE WHEN t.resolved_date IS NOT NULL
               AND t.status IN ('New', 'InAttendance') THEN 1 END)    AS tickets_reabertos,
    ROUND(
        COUNT(CASE WHEN t.resolved_date IS NOT NULL
                   AND t.status IN ('New', 'InAttendance') THEN 1 END)::numeric
        / NULLIF(COUNT(*), 0) * 100, 1
    )                                                                  AS taxa_retrabalho_pct
FROM raw.tickets t
LEFT JOIN raw.organizacoes o ON o.id = COALESCE(t.organization_id, t.client_id)
WHERE t.created_date IS NOT NULL
GROUP BY 1, 2, 3;
