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
    url = os.getenv("DATABASE_URL", "")
    if url:
        return {"dsn": url}
    return {
        "host":     os.getenv("DB_HOST", "localhost"),
        "port":     int(os.getenv("DB_PORT", "5432")),
        "dbname":   os.environ["DB_NAME"],
        "user":     os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }


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
    except KeyError as exc:
        logger.error("Variável de ambiente ausente: %s. Configure DATABASE_URL ou DB_*.", exc)
        sys.exit(1)
