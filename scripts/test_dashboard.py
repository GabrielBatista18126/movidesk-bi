import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

mods = [
    "dashboard.db",
    "dashboard._pages.visao_geral",
    "dashboard._pages.consumo",
    "dashboard._pages.alertas",
    "dashboard._pages.produtividade",
    "dashboard._pages.tickets",
    "dashboard._pages.inteligencia",
    "dashboard._pages.etl_monitor",
]
for m in mods:
    try:
        __import__(m)
        print(f"OK: {m}")
    except Exception as e:
        print(f"ERRO: {m} -> {e}")
