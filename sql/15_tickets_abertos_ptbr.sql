-- ════════════════════════════════════════════════════════════════
-- 15_tickets_abertos_ptbr.sql — Corrige v_tickets_abertos para
-- filtrar também os status em português (Fechado, Resolvido, Cancelado).
-- ════════════════════════════════════════════════════════════════
CREATE OR REPLACE VIEW analytics.v_tickets_abertos AS
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
WHERE t.status NOT IN (
        'Resolved', 'Closed', 'Canceled', 'Cancelled',
        'Fechado', 'Resolvido', 'Cancelado'
    )
  AND t.created_date IS NOT NULL;

COMMENT ON VIEW analytics.v_tickets_abertos IS
    'Tickets em aberto: exclui Resolved/Closed/Canceled (en) e Fechado/Resolvido/Cancelado (pt-BR)';
