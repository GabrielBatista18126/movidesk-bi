"""
init_db.py — Executa todas as migrations SQL em ordem, apenas uma vez cada.

Usa a tabela public.schema_migrations para rastrear quais arquivos
já foram aplicados. Isso torna o init idempotente entre deploys (Railway,
Render, local) sem tentar re-rodar CREATEs que alteram tipos de views.
"""
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.db import _engine

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


def _ordem(path: Path) -> int:
    m = re.match(r"(\d+)_", path.name)
    return int(m.group(1)) if m else 9999


def main() -> None:
    files = sorted(SQL_DIR.glob("*.sql"), key=_ordem)
    if not files:
        logger.warning("Nenhum .sql encontrado em %s", SQL_DIR)
        return

    engine = _engine()

    # Garante o ledger.
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(_CREATE_LEDGER)
        raw.commit()
        cur.execute("SELECT filename FROM public.schema_migrations")
        aplicadas = {row[0] for row in cur.fetchall()}
        cur.close()
    finally:
        raw.close()

    pendentes = [f for f in files if f.name not in aplicadas]
    if not pendentes:
        logger.info("Banco já atualizado — %d migrations aplicadas.", len(aplicadas))
        return

    logger.info("Aplicando %d migrations pendentes...", len(pendentes))
    for f in pendentes:
        logger.info("→ %s", f.name)
        sql = f.read_text(encoding="utf-8")
        raw = engine.raw_connection()
        try:
            cur = raw.cursor()
            cur.execute(sql)
            cur.execute(
                "INSERT INTO public.schema_migrations (filename) VALUES (%s)",
                (f.name,),
            )
            raw.commit()
            cur.close()
        except Exception as exc:
            raw.rollback()
            logger.error("Falha em %s: %s", f.name, exc)
            raise
        finally:
            raw.close()
    logger.info("Migrations OK.")


if __name__ == "__main__":
    main()
