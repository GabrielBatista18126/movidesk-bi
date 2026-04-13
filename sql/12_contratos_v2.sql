-- ════════════════════════════════════════════════════════════════
-- 12_contratos_v2.sql — Módulo robusto de contratos (Fase 3)
-- Adiciona tipo de contrato, rollover, hora extra e dia de corte
-- ════════════════════════════════════════════════════════════════

ALTER TABLE analytics.contratos
    ADD COLUMN IF NOT EXISTS tipo_contrato    VARCHAR(30)  NOT NULL DEFAULT 'mensal_fixo',
    ADD COLUMN IF NOT EXISTS rollover_horas   BOOLEAN      NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS hora_extra_valor NUMERIC(10, 2),
    ADD COLUMN IF NOT EXISTS dia_corte        SMALLINT     NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS ativo            BOOLEAN      NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN analytics.contratos.tipo_contrato IS
    'mensal_fixo | banco_horas_mensal | banco_horas_trimestral';
COMMENT ON COLUMN analytics.contratos.rollover_horas IS
    'Se TRUE, horas não utilizadas acumulam para o período seguinte';
COMMENT ON COLUMN analytics.contratos.hora_extra_valor IS
    'Valor cobrado por hora excedente (R$/hora)';
COMMENT ON COLUMN analytics.contratos.dia_corte IS
    'Dia do mês em que o ciclo reinicia (1 = primeiro dia do mês)';


-- ── View: saldo do contrato (considera dia de corte) ────────────
CREATE OR REPLACE VIEW analytics.v_saldo_contrato AS
WITH ciclo AS (
    SELECT
        c.id                                                           AS contrato_id,
        COALESCE(c.organization_id, c.client_id)                       AS client_id,
        c.client_name,
        c.plano_nome,
        c.horas_contratadas,
        c.vigencia_inicio,
        c.vigencia_fim,
        c.tipo_contrato,
        c.rollover_horas,
        c.hora_extra_valor,
        c.dia_corte,
        CASE
            WHEN EXTRACT(DAY FROM CURRENT_DATE) >= c.dia_corte
            THEN MAKE_DATE(
                EXTRACT(YEAR FROM CURRENT_DATE)::int,
                EXTRACT(MONTH FROM CURRENT_DATE)::int,
                c.dia_corte
            )
            ELSE (MAKE_DATE(
                EXTRACT(YEAR FROM CURRENT_DATE)::int,
                EXTRACT(MONTH FROM CURRENT_DATE)::int,
                c.dia_corte
            ) - INTERVAL '1 month')::date
        END AS ciclo_inicio
    FROM analytics.contratos c
    WHERE c.ativo = TRUE
      AND c.vigencia_inicio <= CURRENT_DATE
      AND (c.vigencia_fim IS NULL OR c.vigencia_fim >= CURRENT_DATE)
),
consumo AS (
    SELECT
        ci.contrato_id,
        COALESCE(SUM(te.hours_spent), 0) AS horas_consumidas
    FROM ciclo ci
    LEFT JOIN raw.tickets t
        ON COALESCE(t.organization_id, t.client_id) = ci.client_id
    LEFT JOIN raw.time_entries te
        ON te.ticket_id = t.id
       AND te.entry_date >= ci.ciclo_inicio
       AND te.entry_date <  (ci.ciclo_inicio + INTERVAL '1 month')
    GROUP BY ci.contrato_id
)
SELECT
    ci.contrato_id,
    ci.client_id,
    ci.client_name,
    ci.plano_nome,
    ci.tipo_contrato,
    ci.horas_contratadas,
    ci.ciclo_inicio,
    (ci.ciclo_inicio + INTERVAL '1 month' - INTERVAL '1 day')::date AS ciclo_fim,
    ROUND(c.horas_consumidas::numeric, 2)                           AS horas_consumidas,
    ROUND(GREATEST(ci.horas_contratadas - c.horas_consumidas, 0)::numeric, 2) AS horas_saldo,
    ROUND(GREATEST(c.horas_consumidas - ci.horas_contratadas, 0)::numeric, 2) AS horas_excedentes,
    ci.hora_extra_valor,
    ROUND(
        (GREATEST(c.horas_consumidas - ci.horas_contratadas, 0)
         * COALESCE(ci.hora_extra_valor, 0))::numeric, 2
    )                                                                AS faturamento_excedente,
    ROUND((100.0 * c.horas_consumidas / NULLIF(ci.horas_contratadas, 0))::numeric, 1) AS pct_utilizado,
    ci.rollover_horas,
    ci.dia_corte
FROM ciclo ci
JOIN consumo c ON c.contrato_id = ci.contrato_id
ORDER BY pct_utilizado DESC NULLS LAST;

COMMENT ON VIEW analytics.v_saldo_contrato IS
    'Saldo do ciclo atual de cada contrato vigente (considera dia de corte)';
