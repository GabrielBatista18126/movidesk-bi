-- ════════════════════════════════════════════════════════════════
-- 01_schemas.sql — Criação dos schemas e extensões
-- ════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- para buscas por similaridade em nomes

CREATE SCHEMA IF NOT EXISTS raw;          -- dados brutos da API (nunca deletar)
CREATE SCHEMA IF NOT EXISTS analytics;   -- camada analítica / BI / star schema
