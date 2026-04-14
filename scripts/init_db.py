"""
init_db.py — Executa todas as migrations SQL em ordem, apenas uma vez cada.

Sem dependência do dashboard/Streamlit: usa psycopg2 direto para que possa
rodar em containers enxutos (Railway/Render) antes do app subir.
"""
import logging
import os
import re
import sys
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


def _ordem(path: Path) -> int:
    m = re.match(r"(\d+)_", path.name)
    return int(m.group(1)) if m else 9999


def main() -> None:
    files = sorted(SQL_DIR.glob("*.sql"), key=_ordem)
    if not files:
        logger.warning("Nenhum .sql encontrado em %s", SQL_DIR)
        return

    kw = _conn_kwargs()
    with psycopg2.connect(**kw) as conn:
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
    except (KeyError, ValueError) as exc:
        logger.error("Erro de configuração: %s", exc)
        sys.exit(1)
