-- =============================================================================
-- 09_filtros_consumo.sql
-- Atualiza views de consumo para respeitar tickets_excluidos dos contratos.
--
-- Problema resolvido: Movidesk exclui do cômputo do contrato alguns tickets
-- de projeto/gestão. As views agora replicam esse comportamento via campo
-- analytics.contratos.tickets_excluidos (IDs separados por vírgula).
-- =============================================================================

-- Drop em cascata (ordem: dependentes primeiro)
DROP VIEW IF EXISTS analytics.v_sugestoes_upgrade   CASCADE;
DROP VIEW IF EXISTS analytics.v_alerta_consumo      CASCADE;
DROP VIEW IF EXISTS analytics.v_historico_consumo   CASCADE;
DROP VIEW IF EXISTS analytics.v_consumo_mensal      CASCADE;
DROP VIEW IF EXISTS analytics.v_resumo_mes_atual    CASCADE;

-- Compatibilidade: esta migration usa tickets_excluidos antes da 10_*.
-- Em bases novas, garantimos que a coluna exista neste ponto.
ALTER TABLE analytics.contratos
    ADD COLUMN IF NOT EXISTS tickets_excluidos TEXT DEFAULT '';

-- =============================================================================
-- Helper: função inline para verificar se ticket está excluído do contrato
-- Lógica: para cada time_entry, procura se existe contrato ativo para o cliente
--         naquela data que lista o ticket_id nos excluídos.
-- =============================================================================

-- v_consumo_mensal: histórico mensal por organização, excluindo tickets config.
-- ─────────────────────────────────────────────────────────────────────────────
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
  -- Exclui lançamentos de tickets configurados como não-consumíveis no contrato
  AND NOT EXISTS (
    SELECT 1
    FROM analytics.contratos c
    WHERE COALESCE(c.organization_id, c.client_id) = COALESCE(te.organization_id, te.client_id)
      AND c.vigencia_inicio <= te.entry_date
      AND (c.vigencia_fim IS NULL OR c.vigencia_fim >= te.entry_date)
      AND COALESCE(c.tickets_excluidos, '') <> ''
      AND te.ticket_id::TEXT = ANY(
            string_to_array(REPLACE(COALESCE(c.tickets_excluidos, ''), ' ', ''), ',')
          )
  )
GROUP BY 1, 2, 3;

-- v_resumo_mes_atual: mês atual por organização, excluindo tickets config.
-- ─────────────────────────────────────────────────────────────────────────
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
  AND NOT EXISTS (
    SELECT 1
    FROM analytics.contratos c
    WHERE COALESCE(c.organization_id, c.client_id) = COALESCE(te.organization_id, te.client_id)
      AND c.vigencia_inicio <= te.entry_date
      AND (c.vigencia_fim IS NULL OR c.vigencia_fim >= te.entry_date)
      AND COALESCE(c.tickets_excluidos, '') <> ''
      AND te.ticket_id::TEXT = ANY(
            string_to_array(REPLACE(COALESCE(c.tickets_excluidos, ''), ' ', ''), ',')
          )
  )
GROUP BY 1, 2;

-- v_alerta_consumo: status atual vs contrato (usa v_resumo_mes_atual acima)
-- ──────────────────────────────────────────────────────────────────────────
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
        WHEN cv.horas_contratadas IS NULL                      THEN 'SEM_CONTRATO'
        WHEN r.horas_mes_atual >= cv.horas_contratadas         THEN 'ESTOURADO'
        WHEN r.horas_mes_atual >= cv.horas_contratadas * 0.8   THEN 'CRITICO'
        WHEN r.horas_mes_atual >= cv.horas_contratadas * 0.6   THEN 'ATENCAO'
        ELSE 'NORMAL'
    END                                                AS status_consumo,
    TO_CHAR(CURRENT_DATE, 'YYYY-MM')                   AS mes_referencia
FROM analytics.v_resumo_mes_atual r
LEFT JOIN analytics.v_contrato_vigente cv ON cv.client_id = r.client_id;

-- v_historico_consumo: histórico mensal com status (usa v_consumo_mensal acima)
-- ──────────────────────────────────────────────────────────────────────────────
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
        WHEN cv.horas_contratadas IS NULL                        THEN 'SEM_CONTRATO'
        WHEN cm.horas_consumidas >= cv.horas_contratadas         THEN 'ESTOURADO'
        WHEN cm.horas_consumidas >= cv.horas_contratadas * 0.8   THEN 'CRITICO'
        WHEN cm.horas_consumidas >= cv.horas_contratadas * 0.6   THEN 'ATENCAO'
        ELSE 'NORMAL'
    END AS status_consumo
FROM analytics.v_consumo_mensal cm
LEFT JOIN analytics.v_contrato_vigente cv ON cv.client_id = cm.client_id;

-- v_sugestoes_upgrade: sugestões baseadas no histórico filtrado
-- ─────────────────────────────────────────────────────────────
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
    WHERE hc.ano_mes >= TO_CHAR(CURRENT_DATE - INTERVAL '6 months', 'YYYY-MM')
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

