"""
init_db.py - Executa todas as migrations SQL em ordem, apenas uma vez cada.

Sem dependencia do dashboard/Streamlit: usa psycopg2 direto para que possa
rodar em containers enxutos (Railway/Render) antes do app subir.
"""
import logging
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import psycopg2

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] init_db - %(message)s",
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


def _build_kwargs_from_url(database_url: str) -> dict:
    parsed = urlparse(database_url.strip())
    kwargs = {
        "host": parsed.hostname or "",
        "port": parsed.port or 5432,
        "dbname": (parsed.path or "").lstrip("/"),
        "user": parsed.username or "",
        "password": parsed.password or "",
    }
    missing = [k for k in ("host", "dbname", "user") if not kwargs[k]]
    if missing:
        raise ValueError(
            "DATABASE_URL incompleta - campos ausentes: "
            f"{missing}. Esperado: postgresql://user:pass@host:port/db"
        )
    return kwargs


def _conn_kwargs() -> tuple[dict, str]:
    # 1) Preferencia por URL completa (ambientes PaaS)
    database_url = _first_env(
        "DATABASE_URL",
        "DATABASE_PRIVATE_URL",
        "DATABASE_PUBLIC_URL",
        "POSTGRES_URL",
        "POSTGRESQL_URL",
    )
    if database_url:
        return _build_kwargs_from_url(database_url), "DATABASE_URL"

    # 2) Variaveis padrao PG*
    pg_host = _first_env("PGHOST", "POSTGRES_HOST")
    pg_name = _first_env("PGDATABASE", "POSTGRES_DB")
    pg_user = _first_env("PGUSER", "POSTGRES_USER")
    pg_pass = _first_env("PGPASSWORD", "POSTGRES_PASSWORD")
    pg_port = _first_env("PGPORT", "POSTGRES_PORT")
    if pg_host and pg_name and pg_user:
        return {
            "host": pg_host,
            "port": _as_int(pg_port, 5432),
            "dbname": pg_name,
            "user": pg_user,
            "password": pg_pass,
        }, "PG*"

    # 3) Variaveis DB_* legadas
    db_host = _first_env("DB_HOST")
    db_name = _first_env("DB_NAME")
    db_user = _first_env("DB_USER")
    db_pass = os.getenv("DB_PASSWORD", "")
    db_port = os.getenv("DB_PORT")
    if db_host and db_name and db_user:
        return {
            "host": db_host,
            "port": _as_int(db_port, 5432),
            "dbname": db_name,
            "user": db_user,
            "password": (db_pass or "").strip(),
        }, "DB_*"

    missing = [
        v
        for v in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
        if not os.getenv(v)
    ]
    raise ValueError(
        "Nenhuma configuracao de banco encontrada. "
        f"Configure DATABASE_URL ou as variaveis: {missing}"
    )


def _connect_with_retry(kw: dict):
    retries = _as_int(os.getenv("DB_CONNECT_RETRIES"), 12)
    delay = float(os.getenv("DB_CONNECT_DELAY", "5"))
    last_exc = None

    for attempt in range(1, retries + 1):
        try:
            return psycopg2.connect(**kw)
        except psycopg2.OperationalError as exc:
            last_exc = exc
            if attempt == retries:
                raise
            logger.warning(
                "Banco indisponivel (tentativa %d/%d). Nova tentativa em %.1fs: %s",
                attempt,
                retries,
                delay,
                exc,
            )
            time.sleep(delay)

    raise last_exc


def _ordem(path: Path) -> int:
    m = re.match(r"(\d+)_", path.name)
    return int(m.group(1)) if m else 9999


def main() -> None:
    files = sorted(SQL_DIR.glob("*.sql"), key=_ordem)
    if not files:
        logger.warning("Nenhum .sql encontrado em %s", SQL_DIR)
        return

    kw, source = _conn_kwargs()
    logger.info(
        "Conectando via %s: host=%s port=%s dbname=%s user=%s",
        source,
        kw.get("host"),
        kw.get("port"),
        kw.get("dbname"),
        kw.get("user"),
    )

    with _connect_with_retry(kw) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_LEDGER)
            cur.execute("SELECT filename FROM public.schema_migrations")
            aplicadas = {row[0] for row in cur.fetchall()}
        conn.commit()

        pendentes = [f for f in files if f.name not in aplicadas]
        if not pendentes:
            logger.info("Banco ja atualizado - %d migrations aplicadas.", len(aplicadas))
            return

        logger.info("Aplicando %d migrations pendentes...", len(pendentes))
        for f in pendentes:
            logger.info("-> %s", f.name)
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
        logger.error("Erro de configuracao: %s", exc)
        sys.exit(1)
