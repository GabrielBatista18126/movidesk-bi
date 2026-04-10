-- ════════════════════════════════════════════════════════════════
-- 04_contratos.sql — Tabela de contratos e carga inicial
--
-- Esta tabela é mantida MANUALMENTE (ou via planilha/import).
-- O ETL lê ela para verificar estouro de horas dos clientes.
-- ════════════════════════════════════════════════════════════════

-- ── Tabela principal ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics.contratos (
    id                  SERIAL          PRIMARY KEY,
    client_id           VARCHAR(50)     NOT NULL,
    client_name         VARCHAR(255),                   -- denormalizado para facilitar relatórios
    plano_nome          VARCHAR(100),                   -- ex: "Plano Basic 20h", "Plano Pro 50h"
    horas_contratadas   NUMERIC(8, 2)   NOT NULL,
    vigencia_inicio     DATE            NOT NULL,
    vigencia_fim        DATE,                           -- NULL = contrato ativo sem data fim
    valor_mensal        NUMERIC(10, 2),                 -- opcional, para ROI
    observacoes         TEXT,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_contrato_cliente FOREIGN KEY (client_id)
        REFERENCES raw.clientes(id) ON DELETE RESTRICT
);

COMMENT ON TABLE  analytics.contratos                   IS 'Contratos de horas mensais por cliente — mantido manualmente';
COMMENT ON COLUMN analytics.contratos.client_id         IS 'ID do cliente no Movidesk';
COMMENT ON COLUMN analytics.contratos.horas_contratadas IS 'Horas mensais contratadas pelo cliente';
COMMENT ON COLUMN analytics.contratos.vigencia_inicio   IS 'Data de início da vigência do contrato';
COMMENT ON COLUMN analytics.contratos.vigencia_fim      IS 'Data de fim (NULL = sem prazo definido)';
COMMENT ON COLUMN analytics.contratos.plano_nome        IS 'Nome comercial do plano';

CREATE INDEX IF NOT EXISTS idx_contratos_client_id ON analytics.contratos(client_id);
CREATE INDEX IF NOT EXISTS idx_contratos_vigencia  ON analytics.contratos(vigencia_inicio, vigencia_fim);


-- ── View: contrato vigente por cliente ───────────────────────────
-- Sempre retorna o contrato mais recente e ativo por cliente.
-- É esta view que o ETL e os dashboards devem usar.
CREATE OR REPLACE VIEW analytics.v_contrato_vigente AS
SELECT DISTINCT ON (client_id)
    id                  AS contrato_id,
    client_id,
    client_name,
    plano_nome,
    horas_contratadas,
    vigencia_inicio,
    vigencia_fim
FROM analytics.contratos
WHERE vigencia_inicio <= CURRENT_DATE
  AND (vigencia_fim IS NULL OR vigencia_fim >= CURRENT_DATE)
ORDER BY client_id, vigencia_inicio DESC;

COMMENT ON VIEW analytics.v_contrato_vigente IS
    'Contrato ativo mais recente por cliente — usado pelo ETL e dashboards';


-- ── Exemplo de carga inicial (substitua pelos dados reais) ───────
-- Descomente e ajuste com os client_ids reais do seu Movidesk.
-- Os IDs devem existir em raw.clientes antes de inserir.
--
-- INSERT INTO analytics.contratos
--     (client_id, client_name, plano_nome, horas_contratadas, vigencia_inicio)
-- VALUES
--     ('123',  'Empresa Alpha Ltda',    'Plano 20h',  20.0, '2025-01-01'),
--     ('456',  'Beta Soluções S.A.',    'Plano 40h',  40.0, '2025-01-01'),
--     ('789',  'Gamma Tech',            'Plano 10h',  10.0, '2025-03-01');
