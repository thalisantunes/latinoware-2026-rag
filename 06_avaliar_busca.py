"""Etapa 6: recall da busca híbrida com 10 perguntas-gabarito (sem LLM).

Cada pergunta parafraseia uma palestra (sem copiar o título) em pt, en ou es; conta acerto
se algum dos K primeiros trechos for da palestra esperada (comparando pelo título).

Sai com erro se o recall não for 100% (roda no fim do `make indexar`). O gabarito cresce com
data/gabarito_extra.json ([[pergunta, trecho do título esperado], ...]), preenchido à mão a partir das
sugestões de `python 06_avaliar_busca.py --candidatos` (perguntas do histórico feitas 2+ vezes, com o título
da 1ª fonte da resposta guardada): só entra o par que uma pessoa conferiu.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path


def modulo(nome):
    spec = importlib.util.spec_from_file_location(nome.removesuffix(".py"), Path(__file__).parent / nome)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


indexar = modulo("04_indexar.py")
api = modulo("05_api.py")  # mesma seleção de trechos da API (dedupe e limite por palestra)

K = int(os.environ.get("K", 8))
GABARITO = [
    ("Quem falou sobre rodar IA localmente sem pagar por token, usando CPU e GPU juntas?", "IA sustentável sem gastos"),
    ("Was there a talk about storing time series data in Postgres?", "TimescaleDB"),
    ("¿Hubo alguna charla sobre una consola de videojuegos brasileña?", "Projeto Lupi"),
    ("Palestra sobre autismo e foco intenso no trabalho", "Hiperfoco"),
    ("Which talk discussed the 3D software Blender coming to phones?", "Blender"),
    ("¿Cómo se usa el software libre en la astrofísica?", "Astrofísica"),
    ("Qual palestra falou de sistemas multiagentes com uma biblioteca brasileira?", "Mangaba"),
    ("How did free software inspire governance at the United Nations?", "Nerd Power"),
    ("Consumo de energia dos data centers e da inteligência artificial", "Energia do Futuro"),
    ("Charla sobre usar herramientas de las big tech para independizarse de ellas", "Ironia das IAs"),
]


def gabarito():
    extra = indexar.DATA / "gabarito_extra.json"
    return GABARITO + [tuple(p) for p in json.loads(extra.read_text())] if extra.exists() else GABARITO


def candidatos():
    """Sugestões para o gabarito (conferir antes de copiar para data/gabarito_extra.json)."""
    from weaviate.classes.query import Filter
    ja = {p for p, _ in gabarito()}
    with indexar.conectar() as cli:
        res = cli.collections.get("Pergunta").query.fetch_objects(limit=200, filters=(
            Filter.by_property("palestra_id").equal(api.SEM_PALESTRA)
            & Filter.by_property("reutilizacoes").greater_or_equal(1)))
    pares = []
    for o in res.objects:
        # 1ª fonte que é palestra (a bio junta os títulos de todas as palestras da pessoa)
        palestras = [f for f in json.loads(o.properties["fontes"]) if f["fonte"] != "bio" and f.get("palestra_id")]
        if o.properties["pergunta"] not in ja and palestras:
            pares.append([o.properties["pergunta"], palestras[0]["titulo"]])
    arq = indexar.DATA / "gabarito_candidatos.json"
    arq.write_text(json.dumps(pares, ensure_ascii=False, indent=1))
    print(f"{len(pares)} candidatos em {arq}: confira cada um e copie os bons para data/gabarito_extra.json")


def main():
    if "--candidatos" in sys.argv:
        return candidatos()
    acertos, perguntas = 0, gabarito()
    with indexar.conectar() as cli:
        trecho = cli.collections.get("Trecho")
        for pergunta, esperado in perguntas:
            vetor = indexar.embed([pergunta])[0]
            titulos = [t["palestra_titulo"] for t in api.selecionar(trecho, pergunta, vetor, K)]
            pos = next((i for i, t in enumerate(titulos, 1) if esperado.lower() in t.lower()), None)
            acertos += pos is not None
            print(f"{'OK ' if pos else 'ERR'} pos={pos} | {pergunta}")
    print(f"recall@{K} (alpha={api.ALPHA}): {acertos}/{len(perguntas)}")
    sys.exit(0 if acertos == len(perguntas) else 1)  # make indexar falha se a busca piorou


if __name__ == "__main__":
    main()
