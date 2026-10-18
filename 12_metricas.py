"""Linha semanal de uso para o STATUS.md (make metricas), a partir de data/metricas/ (sem a API no ar)."""

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

spec = importlib.util.spec_from_file_location("api", Path(__file__).parent / "05_api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

fim = datetime.now(api.BRT).date() - timedelta(days=1)  # 7 dias completos até ontem (segunda a domingo no timer)
eventos = [e for i in range(7) for e in api.ler_metricas(fim - timedelta(days=i))]
r = api.resumo(eventos)
idiomas = ", ".join(f"{k} {v}" for k, v in sorted(r["idiomas"].items()))
print(f"- uso, 7 dias até {fim}: {r['perguntas']} perguntas ({idiomas or 'nenhuma'}); reaproveitadas "
      f"{r['reaproveitadas']}; resumos {r['resumos']}; sem resposta {r['sem_resposta']}; 429 {r['ocupado_429']}; "
      f"desistências {r['desistencias']}; erros {r['erros']}; tempo p50 {r['p50_s']} s, p95 {r['p95_s']} s")
