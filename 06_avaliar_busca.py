"""Etapa 6: recall da busca híbrida com 10 perguntas-gabarito (sem LLM).

Cada pergunta parafraseia uma palestra (sem copiar o título) em pt, en ou es; conta acerto
se algum dos K primeiros trechos for da palestra esperada (comparando pelo título).
"""

import importlib.util
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location("indexar", Path(__file__).parent / "04_indexar.py")
indexar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(indexar)

K = int(os.environ.get("K", 8))
ALPHA = float(os.environ.get("HYBRID_ALPHA", 0.75))
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


def main():
    acertos = 0
    with indexar.conectar() as cli:
        trecho = cli.collections.get("Trecho")
        for pergunta, esperado in GABARITO:
            vetor = indexar.embed([pergunta])[0]
            res = trecho.query.hybrid(query=pergunta, vector=vetor, alpha=ALPHA, limit=K)
            titulos = [o.properties["palestra_titulo"] for o in res.objects]
            pos = next((i for i, t in enumerate(titulos, 1) if esperado.lower() in t.lower()), None)
            acertos += pos is not None
            print(f"{'OK ' if pos else 'ERR'} pos={pos} | {pergunta}")
    print(f"recall@{K} (alpha={ALPHA}): {acertos}/{len(GABARITO)}")


if __name__ == "__main__":
    main()
