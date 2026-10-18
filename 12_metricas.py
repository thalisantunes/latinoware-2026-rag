"""Linha semanal de uso para o STATUS.md (make metricas), a partir de data/metricas/ (sem a API no ar)."""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

spec = importlib.util.spec_from_file_location("api", Path(__file__).parent / "05_api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

fim = datetime.now(timezone.utc).date()
eventos = []
for i in range(7):
    arq = api.METRICAS / f"{fim - timedelta(days=i)}.jsonl"
    if arq.exists():
        eventos += [json.loads(linha) for linha in arq.read_text().splitlines() if linha]
r = api.resumo(eventos)
idiomas = ", ".join(f"{k} {v}" for k, v in sorted(r["idiomas"].items()))
print(f"- uso, 7 dias até {fim}: {r['perguntas']} perguntas ({idiomas or 'nenhuma'}); reaproveitadas "
      f"{r['reaproveitadas']}; resumos {r['resumos']}; sem resposta {r['sem_resposta']}; 429 {r['ocupado_429']}; "
      f"erros {r['erros']}; tempo p50 {r['p50_s']} s, p95 {r['p95_s']} s")
