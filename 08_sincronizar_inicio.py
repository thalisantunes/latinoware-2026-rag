"""Etapa 8: acha o início real de cada palestra na live, pela transcrição.

A grade atrasa (às vezes 5 a 10 min), então o link pelo horário da grade cai no palco vazio.
Para cada palestra com vídeo, o LLM local lê a transcrição em blocos de 1 min ao redor do
horário da grade e aponta o bloco em que o apresentador anuncia a palestra ou o palestrante
começa a falar. Sem resposta confiável, fica o horário da grade.

Saída: data/inicios.json {uid: {"video_id", "t", "t_grade", "bloco"}}, lido por 04_indexar.py e
07_exportar_catalogo.py. Correções manuais: alinhamento.json com "<uid>": segundos.
Rode com a API parada ou fora do horário de uso: ocupa a GPU por alguns minutos.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import httpx

RAIZ = Path(__file__).parent
spec = importlib.util.spec_from_file_location("indexar", RAIZ / "04_indexar.py")
indexar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(indexar)

LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3:14b")
ANTES, DEPOIS = 10, 30  # blocos de 1 min antes e depois do horário da grade
# mais longe que isso da grade, o LLM costuma ter achado o 2º trabalho de uma sessão técnica
LIMITE = 600

INSTRUCAO = (
    "Você recebe a transcrição de uma transmissão ao vivo de um congresso, em blocos numerados de 1 minuto, "
    "e o título e os palestrantes de uma atividade da programação. Ache o bloco em que essa atividade "
    "começa: o apresentador anuncia a atividade ou o palestrante, ou o palestrante começa a falar. Em "
    "sessões com vários trabalhos, é a abertura da sessão. Ignore o fim da atividade anterior, avisos, "
    "intervalos e música. Responda só JSON: {\"bloco\": n}, ou {\"bloco\": -1} se a atividade não começa "
    "em nenhum bloco.")


def blocos(segs, ini):
    """Texto de cada minuto de [ini - ANTES min, ini + DEPOIS min); o bloco 0 começa em ini - ANTES min."""
    inicio = ini - ANTES * 60
    textos = [[] for _ in range(ANTES + DEPOIS)]
    for s in segs:
        k = int((s["inicio"] - inicio) // 60)
        if 0 <= k < len(textos):
            textos[k].append(s["texto"].strip())
    return inicio, [" ".join(t)[:600] for t in textos]


def perguntar(cli, p, textos):
    nomes = ", ".join(s["nome"] for s in p["palestrantes"])
    corpo = "\n".join(f"[{k}] {t or '(sem fala)'}" for k, t in enumerate(textos))
    r = cli.post(f"{indexar.OLLAMA}/api/chat", timeout=300, json={
        "model": LLM_MODEL, "stream": False, "think": False, "format": "json",
        "options": {"temperature": 0, "num_ctx": 16384},
        "messages": [{"role": "system", "content": INSTRUCAO},
                     {"role": "user", "content": f"Atividade: {p['titulo']}\nPalestrantes: {nomes}\n"
                                                 f"Pela programação, começaria no bloco {ANTES}.\n\n{corpo}"}]})
    r.raise_for_status()
    try:
        bloco = int(json.loads(r.json()["message"]["content"])["bloco"])
    except (ValueError, KeyError, TypeError):
        return None
    # bloco sem fala não é início; fora da faixa é resposta inválida
    return bloco if 0 <= bloco < len(textos) and textos[bloco] else None


def primeira_fala(segs, ini):
    """Se a grade cai em silêncio, o início é a primeira fala depois dela (até LIMITE); senão, a grade."""
    if any(ini <= s["inicio"] < ini + 60 for s in segs):
        return None
    return next((int(s["inicio"]) for s in segs if ini <= s["inicio"] < ini + LIMITE), None)


def main():
    data = indexar.DATA
    palestras = json.loads((data / "site" / "palestras.json").read_text())
    videos = json.loads((data / "videos.json").read_text())
    por_uid = {indexar.uid(p): p for p in palestras}
    alinhadas = indexar.alinhar_palestras(palestras, videos, {}, inicios=False)
    saida, segs = {}, {}
    with httpx.Client() as cli:
        for u, a in sorted(alinhadas.items()):
            arq = data / "transcricoes" / f"{a['video_id']}.json"
            if not arq.exists():
                continue
            s = segs.setdefault(a["video_id"], json.loads(arq.read_text())["segmentos"])
            inicio, textos = blocos(s, a["t_inicio"])
            bloco = perguntar(cli, por_uid[u], textos)
            t, como = None, "llm"
            if bloco is not None:  # primeira fala do bloco escolhido
                t = max(0, int(min(x["inicio"] for x in s if inicio + bloco * 60 <= x["inicio"] < inicio + (bloco + 1) * 60)))
            if t is None or abs(t - a["t_inicio"]) > LIMITE:
                t, como = primeira_fala(s, a["t_inicio"]), "primeira_fala"
            if t is None:
                print(f"  {u}: sem início claro, fica a grade ({a['t_inicio']} s)")
                continue
            saida[u] = {"video_id": a["video_id"], "t": t, "t_grade": a["t_inicio"], "como": como, "bloco": bloco}
            print(f"  {u}: grade {a['t_inicio']} s -> {t} s ({t - a['t_inicio']:+d} s, {como})")
    (data / "inicios.json").write_text(json.dumps(saida, ensure_ascii=False, indent=1))
    print(f"inicios.json: {len(saida)} de {len(alinhadas)} palestras com início lido da transcrição")
    sys.exit(0 if saida else 1)


if __name__ == "__main__":
    main()
