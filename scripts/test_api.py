"""Testa variações de expand para encontrar a sintaxe correta."""
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TOKEN = os.getenv("MOVIDESK_TOKEN", "").strip()
BASE = os.getenv("MOVIDESK_BASE_URL", "https://api.movidesk.com/public/v1").rstrip("/")

if not TOKEN or TOKEN == "SEU_TOKEN_AQUI":
    raise SystemExit("Configure MOVIDESK_TOKEN no arquivo .env antes de rodar este teste.")

testes = [
    # Simplificado: apenas expand sem select aninhado
    ("Expand simples actions+timeAppointments",
     f"{BASE}/tickets?token={TOKEN}&$select=id,subject&$expand=actions($expand=timeAppointments)&$top=3"),

    # Sem select dentro do expand
    ("Clients sem select interno",
     f"{BASE}/tickets?token={TOKEN}&$select=id,subject&$expand=clients&$top=2"),

    # Owner sem select
    ("Owner sem select",
     f"{BASE}/tickets?token={TOKEN}&$select=id,subject&$expand=owner&$top=2"),

    # Tudo junto
    ("Tudo junto sem selects internos",
     f"{BASE}/tickets?token={TOKEN}&$select=id,subject,status,type,category,urgency,createdDate,lastUpdate,resolvedIn,closedIn,ownerTeam&$expand=clients,owner,actions($expand=timeAppointments)&$top=2"),
]

for nome, url in testes:
    r = requests.get(url, headers={"Accept": "application/json"})
    print(f"\n[{nome}]")
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        if data:
            t = data[0]
            keys = list(t.keys())
            print(f"Ticket keys: {keys}")
            if "actions" in t and t["actions"]:
                a = t["actions"][0]
                print(f"Action keys: {list(a.keys())}")
                if a.get("timeAppointments"):
                    print(f"TimeAppt keys: {list(a['timeAppointments'][0].keys())}")
                    print(f"TimeAppt: {a['timeAppointments'][0]}")
                else:
                    print("Nenhum timeAppointment nesta action")
            if "clients" in t and t["clients"]:
                print(f"Client: {t['clients'][0]}")
    else:
        print(r.text[:200])
