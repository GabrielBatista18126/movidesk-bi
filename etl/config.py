"""
config.py — Centraliza toda configuração via variáveis de ambiente.
Carrega o .env automaticamente se existir.
"""
import os
import logging
from pathlib import Path
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
_DATABASE_URL = os.getenv("DATABASE_URL", "")
if _DATABASE_URL:
    from urllib.parse import urlparse
    _u = urlparse(_DATABASE_URL)
    DB_CONFIG = {
        "host":     _u.hostname,
        "port":     _u.port or 5432,
        "dbname":   (_u.path or "/").lstrip("/"),
        "user":     _u.username,
        "password": _u.password,
    }
else:
    DB_CONFIG = {
        "host":     os.getenv("DB_HOST",     "localhost"),
        "port":     int(os.getenv("DB_PORT", "5432")),
        "dbname":   os.environ["DB_NAME"],
        "user":     os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }

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
