-- ════════════════════════════════════════════════════════════════
-- 16_usuarios.sql — Autenticação por e-mail + código (passwordless)
-- ════════════════════════════════════════════════════════════════

-- ── Tabela de usuários ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics.usuarios (
    email          VARCHAR(255) PRIMARY KEY,
    nome           VARCHAR(255),
    is_admin       BOOLEAN      NOT NULL DEFAULT FALSE,
    is_ativo       BOOLEAN      NOT NULL DEFAULT TRUE,
    criado_em      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    ultimo_login   TIMESTAMPTZ
);

COMMENT ON TABLE analytics.usuarios IS
    'Usuários autorizados a acessar o dashboard. Apenas e-mails @rivio.com.br.';


-- ── Tabela de códigos de autenticação (OTP) ────────────────────
-- Um código por tentativa. Expira em 10 min. Guarda hash, não o código em texto.
CREATE TABLE IF NOT EXISTS analytics.auth_codes (
    id          SERIAL       PRIMARY KEY,
    email       VARCHAR(255) NOT NULL,
    code_hash   VARCHAR(128) NOT NULL,
    expires_at  TIMESTAMPTZ  NOT NULL,
    used        BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_auth_codes_email
    ON analytics.auth_codes(email, used, expires_at DESC);

COMMENT ON TABLE analytics.auth_codes IS
    'Códigos OTP de 6 dígitos enviados por e-mail. Hash SHA-256.';


-- ── Seed do admin ──────────────────────────────────────────────
INSERT INTO analytics.usuarios (email, nome, is_admin)
VALUES ('gabriel.furtado@rivio.com.br', 'Gabriel Furtado', TRUE)
ON CONFLICT (email) DO UPDATE SET
    is_admin = TRUE,
    is_ativo = TRUE;
