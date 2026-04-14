"""
init_db.py — Executa todas as migrations SQL em ordem, apenas uma vez cada.

Sem dependência do dashboard/Streamlit: usa psycopg2 direto para que possa
rodar em containers enxutos (Railway/Render) antes do app subir.

Resilience features:
  - Retry logic with exponential backoff (up to MAX_RETRIES attempts).
  - Graceful exit (code 0) when the database is unreachable after all retries,
    so the Streamlit app can still start and serve the UI.
  - Set SKIP_DB_INIT=1 to bypass database initialisation entirely.
"""
import logging
import os
import re
import sys
import time
from pathlib import Path

import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] init_db — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"

# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF_SECONDS = 2  # doubles on each attempt: 2, 4, 8, 16, 32

_CREATE_LEDGER = """
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def _conn_kwargs() -> dict:
    """Build psycopg2 connection kwargs, always forcing TCP mode via an explicit host.

    Priority:
      1. Individual DB_* variables (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
      2. DATABASE_URL fallback — host is extracted and re-injected to guarantee TCP

    Raises ValueError if required variables are missing or if host cannot be
    determined (which would cause psycopg2 to fall back to a Unix socket).
    """
    host = os.getenv("DB_HOST", "")
    port = os.getenv("DB_PORT", "")
    dbname = os.getenv("DB_NAME", "")
    user = os.getenv("DB_USER", "")
    password = os.getenv("DB_PASSWORD", "")

    # Prefer individual variables — they are the most reliable on Railway.
    if host and dbname and user and password:
        kwargs = {
            "host":     host,
            "port":     int(port) if port else 5432,
            "dbname":   dbname,
            "user":     user,
            "password": password,
        }
        logger.info(
            "Conectando via variáveis DB_*: host=%s port=%s dbname=%s user=%s",
            kwargs["host"], kwargs["port"], kwargs["dbname"], kwargs["user"],
        )
        return kwargs

    # Fall back to DATABASE_URL, but parse it so we can enforce an explicit host.
    url = os.getenv("DATABASE_URL", "")
    if url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            parsed_host = parsed.hostname or ""
            parsed_port = parsed.port or 5432
            parsed_dbname = (parsed.path or "").lstrip("/")
            parsed_user = parsed.username or ""
            parsed_password = parsed.password or ""

            missing = [k for k, v in {
                "host": parsed_host,
                "dbname": parsed_dbname,
                "user": parsed_user,
                "password": parsed_password,
            }.items() if not v]
            if missing:
                raise ValueError(
                    f"DATABASE_URL está incompleta — campos ausentes: {missing}"
                )

            kwargs = {
                "host":     parsed_host,
                "port":     parsed_port,
                "dbname":   parsed_dbname,
                "user":     parsed_user,
                "password": parsed_password,
            }
            logger.info(
                "Conectando via DATABASE_URL: host=%s port=%s dbname=%s user=%s",
                kwargs["host"], kwargs["port"], kwargs["dbname"], kwargs["user"],
            )
            return kwargs
        except Exception as exc:
            raise ValueError(f"Falha ao interpretar DATABASE_URL: {exc}") from exc

    # Neither individual vars nor DATABASE_URL are usable.
    missing_vars = [
        v for v in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
        if not os.getenv(v)
    ]
    raise ValueError(
        "Nenhuma configuração de banco encontrada. "
        f"Configure DATABASE_URL ou as variáveis: {missing_vars}"
    )


def _connect_with_retry(kw: dict) -> "psycopg2.connection":
    """Attempt to open a psycopg2 connection with exponential backoff.

    Tries up to MAX_RETRIES times. Raises the last psycopg2 error if every
    attempt fails so the caller can decide how to handle it.
    """
    delay = INITIAL_BACKOFF_SECONDS
    last_exc: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(
            "Tentativa de conexão %d/%d (host=%s port=%s dbname=%s)...",
            attempt, MAX_RETRIES, kw["host"], kw["port"], kw["dbname"],
        )
        try:
            conn = psycopg2.connect(**kw)
            logger.info("Conexão estabelecida com sucesso na tentativa %d.", attempt)
            return conn
        except psycopg2.OperationalError as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                logger.warning(
                    "Falha na tentativa %d/%d: %s — aguardando %ds antes de tentar novamente.",
                    attempt, MAX_RETRIES, exc, delay,
                )
                time.sleep(delay)
                delay *= 2  # exponential backoff
            else:
                logger.warning(
                    "Falha na tentativa %d/%d: %s — sem mais tentativas.",
                    attempt, MAX_RETRIES, exc,
                )

    raise last_exc  # type: ignore[misc]


def _ordem(path: Path) -> int:
    m = re.match(r"(\d+)_", path.name)
    return int(m.group(1)) if m else 9999


def main() -> None:
    # Allow operators to skip DB init entirely (e.g. when running locally
    # without a database, or when the schema is managed externally).
    if os.getenv("SKIP_DB_INIT", "").strip().lower() in {"1", "true", "yes"}:
        logger.info("SKIP_DB_INIT está definido — inicialização do banco ignorada.")
        return

    files = sorted(SQL_DIR.glob("*.sql"), key=_ordem)
    if not files:
        logger.warning("Nenhum .sql encontrado em %s", SQL_DIR)
        return

    try:
        kw = _conn_kwargs()
    except ValueError as exc:
        logger.warning(
            "Configuração de banco ausente ou inválida: %s — "
            "inicialização ignorada; o app será iniciado sem o banco.",
            exc,
        )
        return

    try:
        conn = _connect_with_retry(kw)
    except Exception as exc:
        logger.warning(
            "Banco de dados indisponível após %d tentativas: %s — "
            "o app será iniciado sem a inicialização do banco. "
            "Execute 'python scripts/init_db.py' manualmente quando o banco estiver acessível.",
            MAX_RETRIES, exc,
        )
        return

    with conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_LEDGER)
            cur.execute("SELECT filename FROM public.schema_migrations")
            aplicadas = {row[0] for row in cur.fetchall()}
        conn.commit()

        pendentes = [f for f in files if f.name not in aplicadas]
        if not pendentes:
            logger.info("Banco já atualizado — %d migrations aplicadas.", len(aplicadas))
            return

        logger.info("Aplicando %d migrations pendentes...", len(pendentes))
        for f in pendentes:
            logger.info("→ %s", f.name)
            sql = f.read_text(encoding="utf-8")
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO public.schema_migrations (filename) VALUES (%s)",
                        (f.name,),
                    )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                logger.error("Falha em %s: %s", f.name, exc)
                raise
        logger.info("Migrations OK.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.error("Erro inesperado durante a inicialização do banco: %s", exc)
        # Exit with 0 so the start command chain (&&) continues and Streamlit
        # can still serve the UI even when the database is unavailable.
        sys.exit(0)
