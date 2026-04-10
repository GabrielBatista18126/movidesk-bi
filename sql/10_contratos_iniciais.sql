-- =============================================================================
-- 10_contratos_iniciais.sql
-- Cadastro inicial de contratos com tickets excluídos do cômputo.
--
-- COMO USAR:
--   1. Execute primeiro: SELECT id, business_name FROM raw.organizacoes ORDER BY business_name;
--      para obter os IDs corretos de cada cliente.
--   2. Ajuste horas_contratadas, plano_nome, vigencia_inicio conforme contratos reais.
--   3. Em tickets_excluidos: informe os IDs dos tickets de projeto/gestão separados por vírgula.
--      Ex: '597,1725' — esses tickets NÃO entram no cômputo de consumo do contrato.
-- =============================================================================

-- Primeiro, remove a FK constraint que impede usar organization_id diferente de raw.clientes
-- (organizações são salvas em raw.organizacoes, não em raw.clientes)
ALTER TABLE analytics.contratos
    DROP CONSTRAINT IF EXISTS fk_contrato_cliente;

-- Garante que organization_id existe (já adicionado em 08_refactoring_v2.sql)
ALTER TABLE analytics.contratos
    ADD COLUMN IF NOT EXISTS organization_id   VARCHAR(50),
    ADD COLUMN IF NOT EXISTS tickets_excluidos TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS categorias_excluidas TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS apenas_tipo_servico  TEXT DEFAULT '';

-- ─────────────────────────────────────────────────────────────────────────────
-- Consulta auxiliar para descobrir os IDs das organizações:
-- SELECT id, business_name FROM raw.organizacoes ORDER BY business_name LIMIT 50;
-- ─────────────────────────────────────────────────────────────────────────────

-- Hospital Israelita Albert Einstein (HIAE)
-- Ticket 597  = ticket de projeto/divergência (longa duração, não consumível)
-- Ticket 1725 = ticket de gestão/reuniões (overhead não consumível)
-- Sem esses dois tickets: ~35.93h em março/2026 ≈ 40h do Movidesk ✓
INSERT INTO analytics.contratos (
    client_id, client_name, organization_id,
    plano_nome, horas_contratadas,
    vigencia_inicio, vigencia_fim,
    tickets_excluidos, observacoes
)
SELECT
    o.id,                                 -- usa organization_id como client_id também
    o.business_name,
    o.id,                                 -- organization_id
    'Plano 40h',                          -- ajuste conforme contrato real
    40.0,                                 -- ajuste conforme contrato real
    '2025-01-01',                         -- ajuste conforme data real do contrato
    NULL,                                 -- NULL = ativo sem data fim
    '597,1725',                           -- tickets de projeto/gestão excluídos
    'Tickets 597 (projeto divergência) e 1725 (gestão/reuniões) excluídos do cômputo'
FROM raw.organizacoes o
WHERE o.id = '2034758315'   -- 'Albert Einstein' (não confundir com '1011207196' = Hospital Orion Albert Einstein Goiânia)
LIMIT 1
ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- TEMPLATE para outros clientes (descomente e ajuste):
-- ─────────────────────────────────────────────────────────────────────────────
--
-- INSERT INTO analytics.contratos (
--     client_id, client_name, organization_id,
--     plano_nome, horas_contratadas,
--     vigencia_inicio, vigencia_fim,
--     tickets_excluidos, observacoes
-- )
-- SELECT
--     o.id, o.business_name, o.id,
--     'Plano Xh',     -- nome do plano
--     X.0,            -- horas contratadas
--     'YYYY-MM-DD',   -- início vigência
--     NULL,           -- fim vigência (NULL = sem prazo)
--     '',             -- tickets excluídos (vazio se nenhum)
--     ''              -- observações
-- FROM raw.organizacoes o
-- WHERE o.business_name ILIKE '%nome_cliente%'
-- LIMIT 1
-- ON CONFLICT DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Verificação após inserção:
-- ─────────────────────────────────────────────────────────────────────────────
-- SELECT
--     c.id, c.client_name, c.organization_id, c.plano_nome,
--     c.horas_contratadas, c.vigencia_inicio, c.tickets_excluidos
-- FROM analytics.contratos c
-- ORDER BY c.client_name;
