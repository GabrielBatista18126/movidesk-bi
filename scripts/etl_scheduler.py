"""
etl_scheduler.py — Roda o ETL incremental a cada N minutos em background.

Uso:
  python scripts/etl_scheduler.py              → a cada 5 min (padrão)
  python scripts/etl_scheduler.py --interval 3 → a cada 3 min
  python scripts/etl_scheduler.py --full       → full load a cada ciclo

Para rodar em background no Windows:
  start /B pythonw scripts/etl_scheduler.py
"""
import argparse
import logging
import sys
import time
from pathlib import Path

# Garante que a raiz do projeto está no path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s → %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scheduler")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=5, help="Intervalo em minutos")
    parser.add_argument("--full", action="store_true", help="Full load a cada ciclo")
    args = parser.parse_args()

    interval_sec = args.interval * 60
    logger.info("Scheduler iniciado: ETL %s a cada %d min",
                "full" if args.full else "incremental", args.interval)

    while True:
        try:
            from etl.main import run
            run(full_load=args.full)
        except SystemExit:
            # etl.main chama sys.exit(1) em falha — não queremos parar o scheduler
            logger.warning("ETL falhou neste ciclo, tentando novamente em %d min", args.interval)
        except Exception as exc:
            logger.error("Erro inesperado: %s", exc)

        logger.info("Próxima execução em %d min...", args.interval)
        time.sleep(interval_sec)


if __name__ == "__main__":
    main()
