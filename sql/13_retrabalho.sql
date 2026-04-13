-- ════════════════════════════════════════════════════════════════
-- 13_retrabalho.sql — Análise de retrabalho e recorrência (Fase 4)
-- ════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS pg_trgm;


-- ── View: tickets reabertos ─────────────────────────────────────
-- Como não temos histórico completo de status, usamos reopenedIn
-- (campo do Movidesk populado quando o ticket é reaberto).
CREATE OR REPLACE VIEW analytics.v_tickets_reabertos AS
SELECT
    t.id                                          AS ticket_id,
    t.subject,
    t.status,
    COALESCE(t.organization_name, '-')            AS cliente,
    t.category,
    t.urgency,
    t.created_date,
    t.resolved_date,
    t.reopened_date,
    t.time_spent_total_hours                      AS horas_gastas,
    CASE
        WHEN t.resolved_date IS NOT NULL AND t.reopened_date IS NOT NULL
             AND t.reopened_date > t.resolved_date
        THEN ROUND(EXTRACT(EPOCH FROM (t.reopened_date - t.resolved_date))/86400.0, 1)
    END                                            AS dias_apos_resolucao
FROM raw.tickets t
WHERE t.reopened_date IS NOT NULL
ORDER BY t.reopened_date DESC;


-- ── View: problemas recorrentes (por cliente + categoria) ────────
CREATE OR REPLACE VIEW analytics.v_problemas_recorrentes AS
SELECT
    COALESCE(t.organization_name, '-')            AS cliente,
    COALESCE(NULLIF(t.category, ''), 'Sem categoria') AS categoria,
    COUNT(*)                                       AS qtd_tickets,
    ROUND(SUM(t.time_spent_total_hours)::numeric, 1) AS horas_totais,
    ROUND(
        (SUM(t.time_spent_total_hours)::numeric
         / NULLIF(COUNT(*), 0)),
        2
    )                                              AS horas_por_ticket,
    MAX(t.created_date)::date                      AS ultimo_ocorrido
FROM raw.tickets t
WHERE t.created_date >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY cliente, categoria
HAVING COUNT(*) >= 3
ORDER BY qtd_tickets DESC, horas_totais DESC;


-- ── View: assuntos similares (trigram) ──────────────────────────
-- Agrupa tickets cujo subject é >= 50% similar a outro já no grupo,
-- usando similaridade trigram do pg_trgm.
-- Simplificação: trazemos os N subjects mais frequentes (substring)
CREATE OR REPLACE VIEW analytics.v_subjects_frequentes AS
SELECT
    LOWER(REGEXP_REPLACE(COALESCE(t.subject, ''), '\s+', ' ', 'g')) AS subject_norm,
    COUNT(*)                                                          AS qtd,
    COUNT(DISTINCT t.organization_id)                                 AS clientes_distintos,
    ROUND(SUM(t.time_spent_total_hours)::numeric, 1)                  AS horas_totais
FROM raw.tickets t
WHERE t.created_date >= CURRENT_DATE - INTERVAL '90 days'
  AND t.subject IS NOT NULL
GROUP BY subject_norm
HAVING COUNT(*) >= 2
ORDER BY qtd DESC, horas_totais DESC
LIMIT 50;

COMMENT ON VIEW analytics.v_subjects_frequentes IS
    'Assuntos de ticket que se repetem nos últimos 90 dias';
