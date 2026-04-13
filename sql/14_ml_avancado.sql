-- ════════════════════════════════════════════════════════════════
-- 14_ml_avancado.sql — Tabelas para anomalias e previsão de tickets
-- ════════════════════════════════════════════════════════════════

-- ── Tickets previstos próximos 7 dias ──────────────────────────
CREATE TABLE IF NOT EXISTS analytics.previsoes_tickets_7d (
    data_prevista       DATE        NOT NULL,
    tickets_previstos   NUMERIC(8,2),
    media_30d           NUMERIC(8,2),
    tendencia_pct       NUMERIC(6,2),
    gerado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_prev_tickets PRIMARY KEY (data_prevista)
);

COMMENT ON TABLE analytics.previsoes_tickets_7d IS
    'Previsão de volume de tickets para os próximos 7 dias';


-- ── Anomalias de consumo ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics.anomalias_consumo (
    id              SERIAL      PRIMARY KEY,
    client_id       VARCHAR(50) NOT NULL,
    client_name     VARCHAR(255),
    data_detectada  DATE        NOT NULL,
    horas_periodo   NUMERIC(8,2),
    media_historica NUMERIC(8,2),
    desvio_padrao   NUMERIC(8,2),
    z_score         NUMERIC(6,2),
    severidade      VARCHAR(20),
    gerado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_anomalia UNIQUE (client_id, data_detectada)
);

CREATE INDEX IF NOT EXISTS idx_anomalias_data    ON analytics.anomalias_consumo(data_detectada DESC);
CREATE INDEX IF NOT EXISTS idx_anomalias_client  ON analytics.anomalias_consumo(client_id);

COMMENT ON TABLE analytics.anomalias_consumo IS
    'Clientes com consumo anômalo detectado por Z-score (>2.5σ acima da média)';
