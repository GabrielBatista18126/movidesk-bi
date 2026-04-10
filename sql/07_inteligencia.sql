-- ════════════════════════════════════════════════════════════════
-- 07_inteligencia.sql — Tabelas para previsões ML e scores
--                       Populadas pelo etl/ml.py após cada ETL
-- ════════════════════════════════════════════════════════════════

-- ── Previsões de consumo ─────────────────────────────────────────
-- Projeção de horas até o fim do mês para cada cliente com contrato.
CREATE TABLE IF NOT EXISTS analytics.previsoes_consumo (
    id                  SERIAL          PRIMARY KEY,
    client_id           VARCHAR(50)     NOT NULL,
    client_name         VARCHAR(255),
    mes_referencia      CHAR(7)         NOT NULL,           -- "YYYY-MM"
    horas_ate_agora     NUMERIC(10, 2)  NOT NULL,           -- consumo real até hoje
    horas_previstas_fim NUMERIC(10, 2)  NOT NULL,           -- projeção até fim do mês
    horas_contratadas   NUMERIC(8,  2),                     -- limite do contrato
    pct_previsto        NUMERIC(6,  1),                     -- % previsto sobre contrato
    vai_estourar        BOOLEAN         NOT NULL DEFAULT FALSE,
    dias_ate_fim_mes    SMALLINT        NOT NULL,
    metodo              VARCHAR(50)     NOT NULL DEFAULT 'linear',
    gerado_em           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_previsao UNIQUE (client_id, mes_referencia)
);

COMMENT ON TABLE  analytics.previsoes_consumo                      IS 'Projeção de consumo até fim do mês por cliente';
COMMENT ON COLUMN analytics.previsoes_consumo.horas_previstas_fim  IS 'Projeção baseada na taxa diária atual do mês';
COMMENT ON COLUMN analytics.previsoes_consumo.vai_estourar         IS 'true se a projeção ultrapassa horas_contratadas';
COMMENT ON COLUMN analytics.previsoes_consumo.metodo               IS 'Algoritmo usado: linear | media_movel | prophet';

CREATE INDEX IF NOT EXISTS idx_prev_client    ON analytics.previsoes_consumo(client_id);
CREATE INDEX IF NOT EXISTS idx_prev_mes       ON analytics.previsoes_consumo(mes_referencia);
CREATE INDEX IF NOT EXISTS idx_prev_estouro   ON analytics.previsoes_consumo(vai_estourar);


-- ── Score de clientes ────────────────────────────────────────────
-- Pontuação composta 0–100 que indica risco de problemas futuros.
-- Recalculada a cada execução do ETL.
CREATE TABLE IF NOT EXISTS analytics.score_clientes (
    id                      SERIAL          PRIMARY KEY,
    client_id               VARCHAR(50)     NOT NULL,
    client_name             VARCHAR(255),
    score_total             NUMERIC(5, 1)   NOT NULL,       -- 0=ótimo, 100=crítico
    classificacao           VARCHAR(20)     NOT NULL,       -- BAIXO | MEDIO | ALTO | CRITICO

    -- Componentes do score (0–100 cada)
    score_historico_estouro NUMERIC(5, 1)   NOT NULL DEFAULT 0,  -- meses estourados / total
    score_tendencia         NUMERIC(5, 1)   NOT NULL DEFAULT 0,  -- crescimento mês a mês
    score_volatilidade      NUMERIC(5, 1)   NOT NULL DEFAULT 0,  -- variação irregular
    score_urgencia_tickets  NUMERIC(5, 1)   NOT NULL DEFAULT 0,  -- % tickets urgentes/altos

    -- Contexto
    meses_analisados        SMALLINT,
    meses_estourados        SMALLINT,
    media_consumo_pct       NUMERIC(6, 1),
    tendencia_pct_mes       NUMERIC(8, 2),                  -- crescimento % por mês
    gerado_em               TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_score_cliente UNIQUE (client_id)
);

COMMENT ON TABLE  analytics.score_clientes            IS 'Score de risco por cliente — 0=saudável, 100=crítico';
COMMENT ON COLUMN analytics.score_clientes.score_total IS 'Média ponderada dos componentes de risco';
COMMENT ON COLUMN analytics.score_clientes.classificacao IS 'BAIXO(<25) | MEDIO(25-50) | ALTO(50-75) | CRITICO(>75)';

CREATE INDEX IF NOT EXISTS idx_score_client ON analytics.score_clientes(client_id);
CREATE INDEX IF NOT EXISTS idx_score_class  ON analytics.score_clientes(classificacao);


-- ── Sugestões de upgrade ─────────────────────────────────────────
-- Gerada automaticamente com base no score e histórico de consumo.
CREATE OR REPLACE VIEW analytics.v_sugestoes_upgrade AS
WITH consumo_medio AS (
    SELECT
        hc.client_id,
        hc.client_name,
        AVG(hc.horas_consumidas)                    AS media_horas_consumidas,
        MAX(hc.horas_contratadas)                   AS horas_contratadas_atual,
        COUNT(*)                                    AS meses_com_dados,
        SUM(CASE WHEN hc.pct_consumo > 100 THEN 1 ELSE 0 END) AS meses_estourados,
        MAX(hc.pct_consumo)                         AS pico_consumo_pct
    FROM analytics.v_historico_consumo hc
    WHERE hc.ano_mes >= (CURRENT_DATE - INTERVAL '6 months')::DATE
    GROUP BY 1, 2
    HAVING COUNT(*) >= 2
)
SELECT
    cm.client_id,
    cm.client_name,
    cm.horas_contratadas_atual,
    ROUND(cm.media_horas_consumidas::NUMERIC, 1)                AS media_horas_6m,
    cm.meses_estourados,
    cm.meses_com_dados,
    ROUND(cm.pico_consumo_pct::NUMERIC, 0)                      AS pico_consumo_pct,
    -- Sugestão: 20% acima da média de consumo, arredondado para múltiplo de 5
    CEIL((cm.media_horas_consumidas * 1.2) / 5)::INTEGER * 5    AS horas_sugeridas,
    sc.score_total,
    sc.classificacao                                            AS risco,
    CASE
        WHEN cm.meses_estourados >= 2 THEN 'URGENTE — recorrência de estouro'
        WHEN cm.media_horas_consumidas > cm.horas_contratadas_atual * 0.9
             THEN 'RECOMENDADO — consumo médio próximo do limite'
        WHEN sc.score_total > 50 THEN 'SUGERIDO — risco elevado detectado'
        ELSE 'OPCIONAL — crescimento gradual observado'
    END                                                         AS justificativa
FROM consumo_medio cm
JOIN analytics.score_clientes sc ON sc.client_id = cm.client_id
WHERE cm.media_horas_consumidas > cm.horas_contratadas_atual * 0.75
   OR cm.meses_estourados >= 1
ORDER BY cm.meses_estourados DESC, cm.media_horas_consumidas DESC;

COMMENT ON VIEW analytics.v_sugestoes_upgrade IS
    'Clientes candidatos a upgrade de plano com horas sugeridas e justificativa';
