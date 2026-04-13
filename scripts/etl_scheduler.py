"""
etl_scheduler.py — Roda o ETL incremental a cada N minutos em background
                   e dispara o digest diário às 8h.

Uso:
  python scripts/etl_scheduler.py              → ETL a cada 5 min + digest 08:00
  python scripts/etl_scheduler.py --interval 3 → a cada 3 min
  python scripts/etl_scheduler.py --full       → full load a cada ciclo

Para rodar em background no Windows:
  start /B pythonw scripts/etl_scheduler.py
"""
import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

# Garante que a raiz do projeto está no path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s → %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")


_DIGEST_HOUR = 8
_ultimo_digest: date | None = None


def _maybe_run_digest():
    """Roda o digest diário se for a janela das 08:00 e ainda não rodou hoje."""
    global _ultimo_digest
    agora = datetime.now()
    if agora.hour != _DIGEST_HOUR:
        return
    if _ultimo_digest == agora.date():
        return
    try:
        from scripts.daily_digest import main as digest_main
        logger.info("Disparando digest diário (08:00)...")
        digest_main()
        _ultimo_digest = agora.date()
    except Exception as exc:
        logger.error("Digest diário falhou: %s", exc)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=5, help="Intervalo em minutos")
    parser.add_argument("--full", action="store_true", help="Full load a cada ciclo")
    args = parser.parse_args()

    interval_sec = args.interval * 60
    logger.info("Scheduler iniciado: ETL %s a cada %d min | digest diário às %02d:00",
                "full" if args.full else "incremental", args.interval, _DIGEST_HOUR)

    while True:
        try:
            from etl.main import run
            run(full_load=args.full)
        except SystemExit:
            logger.warning("ETL falhou neste ciclo, tentando novamente em %d min", args.interval)
        except Exception as exc:
            logger.error("Erro inesperado: %s", exc)

        _maybe_run_digest()

        logger.info("Próxima execução em %d min...", args.interval)
        time.sleep(interval_sec)


if __name__ == "__main__":
    main()
