-- ════════════════════════════════════════════════════════════════
-- 17_usuarios_senha.sql — Troca OTP por autenticação com senha
--
-- Remove tabela analytics.auth_codes (OTP não é mais usado).
-- Adiciona password_hash (bcrypt) e must_change_password em usuarios.
-- Define senha temporária para o admin inicial.
-- ════════════════════════════════════════════════════════════════

-- ── Dropa tabela de OTP ────────────────────────────────────────
DROP TABLE IF EXISTS analytics.auth_codes;

-- ── Novas colunas de senha ─────────────────────────────────────
ALTER TABLE analytics.usuarios
    ADD COLUMN IF NOT EXISTS password_hash        VARCHAR(255),
    ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN analytics.usuarios.password_hash IS
    'Hash bcrypt da senha (nunca em texto).';
COMMENT ON COLUMN analytics.usuarios.must_change_password IS
    'TRUE se o usuário precisa trocar a senha no próximo login.';


-- ── Seed da senha do admin inicial ─────────────────────────────
-- Senha temporária: Rivio@2026  (trocar no 1º acesso)
UPDATE analytics.usuarios
SET password_hash        = '$2b$12$GZHuJCSPM4LMbfL3MQ1emexEy7Is/agEAHrXMifjl6dRcjkIHYMTW',
    must_change_password = TRUE
WHERE email = 'gabriel.furtado@rivio.com.br';
