"""
auth.py — Autenticação passwordless por código OTP enviado por e-mail.

Fluxo:
  1. enviar_codigo(email)   → gera OTP 6 dígitos, grava hash, envia e-mail
  2. validar_codigo(email, code) → confere hash, marca como usado, cria/atualiza usuário
  3. get_user(email), is_admin(email), listar_usuarios(), etc.

Regras:
  - Apenas e-mails @rivio.com.br são aceitos.
  - Código expira em 10 minutos.
  - Guardamos apenas o hash SHA-256 do código (nunca em texto).
  - Se SMTP não estiver configurado, imprime o código no terminal (modo dev).
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import text

from dashboard.db import _engine
from etl import config
from etl.alerts import _send_email

logger = logging.getLogger(__name__)

EMAIL_DOMAIN = "@rivio.com.br"
CODE_TTL_MIN = 10


# ─── Validação ────────────────────────────────────────────────────

def email_permitido(email: str) -> bool:
    """Aceita apenas e-mails do domínio @rivio.com.br (case-insensitive)."""
    if not email:
        return False
    return email.strip().lower().endswith(EMAIL_DOMAIN)


def _normalizar_email(email: str) -> str:
    return email.strip().lower()


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _gerar_codigo() -> str:
    """Gera OTP de 6 dígitos usando secrets (cryptographically secure)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _smtp_configurado() -> bool:
    placeholders = {"seu@email.com", "senha_do_email", "", None}
    return (
        config.SMTP_USER not in placeholders
        and config.SMTP_PASS not in placeholders
    )


# ─── Envio de código ──────────────────────────────────────────────

def enviar_codigo(email: str) -> tuple[bool, str]:
    """
    Gera um código OTP, grava o hash no banco e envia por e-mail.

    Retorna (ok, mensagem_para_ui).
    Em modo dev (SMTP não configurado), imprime o código no log e na mensagem.
    """
    email = _normalizar_email(email)
    if not email_permitido(email):
        return False, "Somente e-mails @rivio.com.br são aceitos."

    code = _gerar_codigo()
    code_hash = _hash(code)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MIN)

    with _engine().begin() as conn:
        # Invalida códigos anteriores não usados deste e-mail
        conn.execute(
            text("""
                UPDATE analytics.auth_codes
                SET used = TRUE
                WHERE email = :email AND used = FALSE
            """),
            {"email": email},
        )
        conn.execute(
            text("""
                INSERT INTO analytics.auth_codes (email, code_hash, expires_at)
                VALUES (:email, :hash, :exp)
            """),
            {"email": email, "hash": code_hash, "exp": expires_at},
        )

    if _smtp_configurado():
        subject = "Movidesk BI — Seu código de acesso"
        body = f"""
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:0 auto">
          <h2 style="color:#7c3aed">🔐 Código de acesso — Movidesk BI</h2>
          <p>Use o código abaixo para entrar no dashboard.
             Ele expira em <strong>{CODE_TTL_MIN} minutos</strong>.</p>
          <div style="background:#1e1e2e;color:#fff;padding:20px;border-radius:8px;
                      text-align:center;font-size:32px;letter-spacing:8px;
                      font-weight:bold;margin:20px 0;font-family:monospace">
            {code}
          </div>
          <p style="color:#888;font-size:12px">
            Se você não solicitou este código, ignore este e-mail.
          </p>
          <p style="color:#888;font-size:11px;margin-top:24px;border-top:1px solid #eee;padding-top:10px">
            Movidesk BI · Desenvolvido por Gabriel Furtado
          </p>
        </div>
        """
        _send_email(subject, body, to_override=email)
        logger.info("Código enviado para %s", email)
        return True, f"Código enviado para {email}."

    # Modo dev: mostra o código
    logger.warning("SMTP não configurado — código DEV para %s: %s", email, code)
    return True, f"[modo dev] Código: {code}"


# ─── Validação de código ──────────────────────────────────────────

def validar_codigo(email: str, code: str, nome: str | None = None) -> tuple[bool, str]:
    """
    Confere o código. Se válido:
      - marca o código como usado
      - cria/atualiza o usuário em analytics.usuarios
      - atualiza ultimo_login
    """
    email = _normalizar_email(email)
    code = (code or "").strip()

    if not email_permitido(email):
        return False, "Somente e-mails @rivio.com.br são aceitos."
    if not code.isdigit() or len(code) != 6:
        return False, "Código inválido (deve ter 6 dígitos)."

    code_hash = _hash(code)

    with _engine().begin() as conn:
        row = conn.execute(
            text("""
                SELECT id
                FROM analytics.auth_codes
                WHERE email = :email
                  AND code_hash = :hash
                  AND used = FALSE
                  AND expires_at > NOW()
                ORDER BY id DESC
                LIMIT 1
            """),
            {"email": email, "hash": code_hash},
        ).first()

        if row is None:
            return False, "Código incorreto ou expirado."

        conn.execute(
            text("UPDATE analytics.auth_codes SET used = TRUE WHERE id = :id"),
            {"id": row[0]},
        )

        # Cria ou atualiza usuário. Se for primeiro login, usa o nome passado (se houver).
        conn.execute(
            text("""
                INSERT INTO analytics.usuarios (email, nome, ultimo_login)
                VALUES (:email, :nome, NOW())
                ON CONFLICT (email) DO UPDATE SET
                    ultimo_login = NOW(),
                    nome = COALESCE(analytics.usuarios.nome, EXCLUDED.nome),
                    is_ativo = TRUE
            """),
            {"email": email, "nome": nome},
        )

    return True, "Autenticado com sucesso."


# ─── Consultas ────────────────────────────────────────────────────

def get_user(email: str) -> dict | None:
    if not email:
        return None
    email = _normalizar_email(email)
    with _engine().connect() as conn:
        row = conn.execute(
            text("""
                SELECT email, nome, is_admin, is_ativo, criado_em, ultimo_login
                FROM analytics.usuarios
                WHERE email = :email
            """),
            {"email": email},
        ).mappings().first()
    return dict(row) if row else None


def is_admin(email: str) -> bool:
    user = get_user(email)
    return bool(user and user.get("is_admin") and user.get("is_ativo"))


def listar_usuarios() -> pd.DataFrame:
    with _engine().connect() as conn:
        return pd.read_sql(
            text("""
                SELECT email, nome, is_admin, is_ativo, criado_em, ultimo_login
                FROM analytics.usuarios
                ORDER BY is_admin DESC, email
            """),
            conn,
        )


def set_admin(email: str, admin: bool) -> None:
    with _engine().begin() as conn:
        conn.execute(
            text("UPDATE analytics.usuarios SET is_admin = :a WHERE email = :e"),
            {"a": admin, "e": _normalizar_email(email)},
        )


def set_ativo(email: str, ativo: bool) -> None:
    with _engine().begin() as conn:
        conn.execute(
            text("UPDATE analytics.usuarios SET is_ativo = :a WHERE email = :e"),
            {"a": ativo, "e": _normalizar_email(email)},
        )


def remover_usuario(email: str) -> None:
    with _engine().begin() as conn:
        conn.execute(
            text("DELETE FROM analytics.usuarios WHERE email = :e"),
            {"e": _normalizar_email(email)},
        )
