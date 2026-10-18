"""Etapa 9: benchmark de modelos de geração para a RAG (velocidade, VRAM, idioma, citações).

Uso: python 09_benchmark_llm.py modelo1 [modelo2 ...]   (tags do Ollama local)

As 30 perguntas de tests/perguntas_bench.json passam uma vez pela busca e o contexto fica congelado
em data/bench/contextos.json: todos os modelos respondem com os mesmos trechos e o mesmo prompt da API.
Por modelo: 1 aquecimento e EXECUCOES rodadas das 30 perguntas, com stream. Mede tempo até o 1º
token, tempo total, tokens/s (eval_count/eval_duration do Ollama), pico de VRAM (nvidia-smi), idioma
da resposta e se todo [n] citado existe. As respostas da 1ª rodada ficam em data/bench/<modelo>.json
para o juiz de fidelidade (feito fora daqui, cego ao nome do modelo).
Não rode durante uma reindexação: disputa a GPU.
"""

import importlib.util
import json
import re
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).parent
BENCH = RAIZ / "data" / "bench"
EXECUCOES = 3


def modulo(nome):
    spec = importlib.util.spec_from_file_location(nome.removesuffix(".py"), RAIZ / nome)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


indexar = modulo("04_indexar.py")
api = modulo("05_api.py")


def congelar():
    """Busca uma vez e guarda (sistema, usuário, idioma, nº de fontes) de cada pergunta."""
    arq = BENCH / "contextos.json"
    if arq.exists():
        return json.loads(arq.read_text())
    perguntas = json.loads((RAIZ / "tests" / "perguntas_bench.json").read_text())
    contextos = []
    with indexar.conectar() as cli:
        trecho = cli.collections.get("Trecho")
        for p in perguntas:
            trechos = api.selecionar(trecho, p["pergunta"], indexar.embed([p["pergunta"]])[0], 8)
            contexto = "\n\n".join(f"[{i}] {api.cabecalho(t)}\n{t['texto']}" for i, t in enumerate(trechos, 1))
            contextos.append(p | {
                "sistema": api.INSTRUCOES[p["idioma"]], "n_fontes": len(trechos),
                "usuario": f"Trechos:\n{contexto}\n\nPergunta: {p['pergunta']}\n\n{api.LEMBRETE[p['idioma']]}"})
    BENCH.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(contextos, ensure_ascii=False, indent=1))
    return contextos


def gerar(cli, modelo, c):
    """Uma resposta com stream: (texto, tempo até o 1º token, tempo total, tokens/s)."""
    t0, primeiro, partes, fim = time.time(), None, [], {}
    with cli.stream("POST", f"{api.OLLAMA}/api/chat", timeout=600, json={
            "model": modelo, "stream": True, "think": False, "keep_alive": "30m",
            "options": {"temperature": 0.2, "num_ctx": 16384, "num_predict": api.MAX_TOKENS},
            "messages": [{"role": "system", "content": c["sistema"]}, {"role": "user", "content": c["usuario"]}]}) as r:
        r.raise_for_status()
        for linha in r.iter_lines():
            if not linha:
                continue
            d = json.loads(linha)
            pedaco = d.get("message", {}).get("content", "")
            if pedaco and primeiro is None:
                primeiro = time.time() - t0
            partes.append(pedaco)
            if d.get("done"):
                fim = d
    tps = fim.get("eval_count", 0) / (fim.get("eval_duration", 0) / 1e9) if fim.get("eval_duration") else 0
    return api.limpar("".join(partes)), primeiro or 0, time.time() - t0, tps


class PicoVRAM(threading.Thread):
    """Lê a memória usada da GPU a cada 0,5 s e guarda o máximo."""

    def __init__(self):
        super().__init__(daemon=True)
        self.pico, self.parar = 0, threading.Event()

    def run(self):
        while not self.parar.is_set():
            out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True).stdout
            self.pico = max(self.pico, int(out.split()[0]) if out.strip() else 0)
            time.sleep(0.5)


def citacoes_ok(texto, n):
    citadas = [int(x) for grupo in re.findall(r"\[([\d,;\s]+)\]", texto) for x in re.findall(r"\d+", grupo)]
    return all(1 <= x <= n for x in citadas)


def p(valores, q):
    return statistics.quantiles(valores, n=20)[q * 20 // 100 - 1] if len(valores) > 1 else valores[0]


def main():
    contextos = congelar()
    linhas = []
    with httpx.Client() as cli:
        for modelo in sys.argv[1:]:
            print(f"== {modelo}", flush=True)
            gerar(cli, modelo, contextos[0])  # aquecimento: carrega o modelo na GPU
            vram = PicoVRAM()
            vram.start()
            medidas, respostas = [], []
            for rodada in range(EXECUCOES):
                for c in contextos:
                    texto, ttft, total, tps = gerar(cli, modelo, c)
                    medidas.append({"ttft": ttft, "total": total, "tps": tps,
                                    "idioma_ok": api.detectar_idioma(texto) == c["idioma"],
                                    "citacoes_ok": citacoes_ok(texto, c["n_fontes"])})
                    if rodada == 0:
                        respostas.append({"pergunta": c["pergunta"], "tipo": c["tipo"], "resposta": texto})
                print(f"   rodada {rodada + 1}: {statistics.mean(m['total'] for m in medidas[-len(contextos):]):.1f} s em média",
                      flush=True)
            vram.parar.set()
            vram.join()
            resumo = {
                "modelo": modelo, "ttft_p50": p([m["ttft"] for m in medidas], 50),
                "total_p50": p([m["total"] for m in medidas], 50), "total_p95": p([m["total"] for m in medidas], 95),
                "tps": statistics.mean(m["tps"] for m in medidas), "vram_pico_mib": vram.pico,
                "idioma_ok": sum(m["idioma_ok"] for m in medidas) / len(medidas),
                "citacoes_ok": sum(m["citacoes_ok"] for m in medidas) / len(medidas)}
            (BENCH / f"{modelo.replace(':', '_').replace('/', '_')}.json").write_text(
                json.dumps({"resumo": resumo, "respostas": respostas}, ensure_ascii=False, indent=1))
            linhas.append(resumo)
    print("\n| modelo | 1º token p50 | total p50 | total p95 | tokens/s | VRAM pico | idioma | citações |")
    print("|---|---|---|---|---|---|---|---|")
    for r in linhas:
        print(f"| {r['modelo']} | {r['ttft_p50']:.1f} s | {r['total_p50']:.1f} s | {r['total_p95']:.1f} s | "
              f"{r['tps']:.0f} | {r['vram_pico_mib'] / 1024:.1f} GB | {r['idioma_ok']:.0%} | {r['citacoes_ok']:.0%} |")


if __name__ == "__main__":
    main()
