"""
config.py — Centraliza toda configuração via variáveis de ambiente.
Carrega o .env automaticamente se existir.
"""
import os
import logging
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

# Carrega .env da raiz do projeto (2 níveis acima deste arquivo)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)


# ─── Movidesk ─────────────────────────────────────────────────────
# Token só é obrigatório no ETL. O dashboard pode subir sem ele
# (nesse caso, "🔄 Atualizar dados" fica indisponível).
MOVIDESK_TOKEN    = os.getenv("MOVIDESK_TOKEN", "")
MOVIDESK_BASE_URL = os.getenv("MOVIDESK_BASE_URL", "https://api.movidesk.com/public/v1")

# ─── PostgreSQL ───────────────────────────────────────────────────
# Suporta tanto DATABASE_URL (Railway/Neon/Heroku) quanto variáveis separadas (local).
def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "")
        if value and value.strip():
            return value.strip()
    return ""


def _as_int(value: str | None, default: int) -> int:
    try:
        return int((value or "").strip())
    except (TypeError, ValueError):
        return default


def _build_db_config() -> tuple[dict, str]:
    database_url = _first_env(
        "DATABASE_URL",
        "DATABASE_PRIVATE_URL",
        "DATABASE_PUBLIC_URL",
        "POSTGRES_URL",
        "POSTGRESQL_URL",
    )
    if database_url:
        parsed = urlparse(database_url)
        return {
            "host": parsed.hostname,
            "port": parsed.port or 5432,
            "dbname": (parsed.path or "/").lstrip("/"),
            "user": parsed.username,
            "password": parsed.password,
        }, "DATABASE_*_URL"

    pg_host = _first_env("PGHOST", "POSTGRES_HOST")
    pg_port = _first_env("PGPORT", "POSTGRES_PORT")
    pg_name = _first_env("PGDATABASE", "POSTGRES_DB")
    pg_user = _first_env("PGUSER", "POSTGRES_USER")
    pg_pass = _first_env("PGPASSWORD", "POSTGRES_PASSWORD")
    if pg_host and pg_name and pg_user:
        return {
            "host": pg_host,
            "port": _as_int(pg_port, 5432),
            "dbname": pg_name,
            "user": pg_user,
            "password": (pg_pass or "").strip(),
        }, "PG*"

    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": _as_int(os.getenv("DB_PORT"), 5432),
        "dbname": os.environ["DB_NAME"],
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }, "DB_*"


DB_CONFIG, DB_CONFIG_SOURCE = _build_db_config()

# ─── ETL ──────────────────────────────────────────────────────────
PAGE_SIZE   = int(os.getenv("PAGE_SIZE",   "50"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "5"))

# ─── Alertas ──────────────────────────────────────────────────────
SMTP_HOST   = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT   = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER   = os.getenv("SMTP_USER", "")
SMTP_PASS   = os.getenv("SMTP_PASS", "")
SMTP_FROM   = os.getenv("SMTP_FROM", "")
ALERT_EMAIL    = os.getenv("ALERT_EMAIL", "")
ALERT_EMAIL_CC = os.getenv("ALERT_EMAIL_CC", "")   # destinatários em cópia (separados por vírgula)
OVERFLOW_THRESHOLD_WARNING  = float(os.getenv("OVERFLOW_THRESHOLD_WARNING",  "60"))  # % para ATENÇÃO
OVERFLOW_THRESHOLD_CRITICAL = float(os.getenv("OVERFLOW_THRESHOLD_CRITICAL", "80"))  # % para CRÍTICO

# ─── Logging ──────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
