"""
auth.py — Autenticação por e-mail + senha (bcrypt).

Regras:
  - Apenas e-mails @rivio.com.br são aceitos.
  - Somente admin cadastra novos usuários (define e-mail, nome, senha inicial).
  - No primeiro login, o usuário é forçado a trocar a senha.
  - Senha é armazenada apenas como hash bcrypt.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import bcrypt
import pandas as pd
from sqlalchemy import text

from dashboard.db import _engine

logger = logging.getLogger(__name__)

EMAIL_DOMAIN = "@rivio.com.br"
MIN_PASSWORD_LEN = 8


# ─── Validação ────────────────────────────────────────────────────

def email_permitido(email: str) -> bool:
    """Aceita apenas e-mails do domínio @rivio.com.br (case-insensitive)."""
    if not email:
        return False
    return email.strip().lower().endswith(EMAIL_DOMAIN)


def _normalizar_email(email: str) -> str:
    return email.strip().lower()


def validar_senha(senha: str) -> tuple[bool, str]:
    """Regras mínimas: 8+ caracteres, com letra e número."""
    if not senha or len(senha) < MIN_PASSWORD_LEN:
        return False, f"A senha precisa ter pelo menos {MIN_PASSWORD_LEN} caracteres."
    if not re.search(r"[A-Za-z]", senha):
        return False, "A senha precisa conter ao menos uma letra."
    if not re.search(r"\d", senha):
        return False, "A senha precisa conter ao menos um número."
    return True, ""


def _hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def _verificar_senha(senha: str, hash_: str) -> bool:
    if not hash_:
        return False
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), hash_.encode("utf-8"))
    except ValueError:
        return False


# ─── Autenticação ─────────────────────────────────────────────────

def autenticar(email: str, senha: str) -> tuple[bool, str, dict | None]:
    """
    Verifica e-mail + senha.

    Retorna (ok, mensagem, user_dict).
    user_dict inclui flag must_change_password para orientar a UI.
    """
    email = _normalizar_email(email)
    if not email_permitido(email):
        return False, "Somente e-mails @rivio.com.br são aceitos.", None
    if not senha:
        return False, "Informe a senha.", None

    user = get_user(email)
    if not user:
        return False, "Usuário ou senha inválidos.", None
    if not user.get("is_ativo"):
        return False, "Seu acesso foi desativado. Fale com o administrador.", None
    if not _verificar_senha(senha, user.get("password_hash") or ""):
        return False, "Usuário ou senha inválidos.", None

    with _engine().begin() as conn:
        conn.execute(
            text("UPDATE analytics.usuarios SET ultimo_login = NOW() WHERE email = :e"),
            {"e": email},
        )
    user["ultimo_login"] = datetime.now(timezone.utc)
    return True, "Autenticado com sucesso.", user


def alterar_senha(email: str, nova_senha: str) -> tuple[bool, str]:
    """Troca a senha e limpa must_change_password."""
    email = _normalizar_email(email)
    ok, msg = validar_senha(nova_senha)
    if not ok:
        return False, msg
    hash_ = _hash_senha(nova_senha)
    with _engine().begin() as conn:
        conn.execute(
            text("""
                UPDATE analytics.usuarios
                SET password_hash = :h,
                    must_change_password = FALSE
                WHERE email = :e
            """),
            {"h": hash_, "e": email},
        )
    return True, "Senha alterada com sucesso."


# ─── Gestão de usuários (admin) ───────────────────────────────────

def criar_usuario(
    email: str,
    nome: str | None,
    senha_inicial: str,
    is_admin: bool = False,
) -> tuple[bool, str]:
    """Cria usuário já com senha inicial e must_change_password=TRUE."""
    email = _normalizar_email(email)
    if not email_permitido(email):
        return False, f"Somente e-mails {EMAIL_DOMAIN} são aceitos."
    if get_user(email):
        return False, "Já existe um usuário com este e-mail."
    ok, msg = validar_senha(senha_inicial)
    if not ok:
        return False, msg

    hash_ = _hash_senha(senha_inicial)
    with _engine().begin() as conn:
        conn.execute(
            text("""
                INSERT INTO analytics.usuarios
                    (email, nome, password_hash, is_admin, must_change_password)
                VALUES (:e, :n, :h, :a, TRUE)
            """),
            {"e": email, "n": (nome or "").strip() or None, "h": hash_, "a": is_admin},
        )
    return True, f"Usuário {email} criado. Ele precisará trocar a senha no 1º acesso."


def resetar_senha(email: str, nova_senha: str) -> tuple[bool, str]:
    """Admin reseta senha de outro usuário; força troca no próximo login."""
    email = _normalizar_email(email)
    ok, msg = validar_senha(nova_senha)
    if not ok:
        return False, msg
    hash_ = _hash_senha(nova_senha)
    with _engine().begin() as conn:
        conn.execute(
            text("""
                UPDATE analytics.usuarios
                SET password_hash = :h,
                    must_change_password = TRUE
                WHERE email = :e
            """),
            {"h": hash_, "e": email},
        )
    return True, "Senha resetada. O usuário precisará trocá-la no próximo acesso."


# ─── Consultas ────────────────────────────────────────────────────

def get_user(email: str) -> dict | None:
    if not email:
        return None
    email = _normalizar_email(email)
    with _engine().connect() as conn:
        row = conn.execute(
            text("""
                SELECT email, nome, is_admin, is_ativo, criado_em, ultimo_login,
                       password_hash, must_change_password
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
                SELECT email, nome, is_admin, is_ativo,
                       criado_em, ultimo_login, must_change_password
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
