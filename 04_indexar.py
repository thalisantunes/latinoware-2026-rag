"""Etapa 4: monta chunks, gera embeddings bge-m3 (Ollama) e carrega no Weaviate.

Coleções (recriadas a cada execução):
- Palestra: uma por atividade da grade
- Palestrante: uma por pessoa
- Trecho: unidade de busca da RAG. Inclui resumos de palestras, bios de palestrantes e,
  quando houver transcrição, pedaços de ~350 palavras (com sobreposição) de cada palestra,
  com link para o vídeo no instante certo (&t=).

Alinhamento live -> grade: cada live é um dia inteiro de um espaço. O instante t do vídeo
vira hora do dia com o início da live, tirado nesta ordem de:
alinhamento.json (manual) > release_timestamp do YouTube > início da primeira atividade
do espaço no dia (estimado, marcado como tal). Se o espaço tem mais de uma live no dia e
falta o início real, a estimativa seria errada para todas: os trechos ficam fora da grade.
"""

import json
import os
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import weaviate
from weaviate.classes.config import Configure, DataType, Property

RAIZ = Path(__file__).parent
DATA = RAIZ / "data"
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
PALAVRAS, SOBREPOSICAO = 350, 60
IDIOMA = {"Português": "pt", "Inglês": "en", "Espanhol": "es"}
BRT = timezone(timedelta(hours=-3))


def conectar():
    return weaviate.connect_to_local(port=int(os.environ.get("WEAVIATE_HTTP_PORT", 18080)),
                                     grpc_port=int(os.environ.get("WEAVIATE_GRPC_PORT", 15051)))


def embed(textos):
    vetores = []
    for i in range(0, len(textos), 32):
        r = httpx.post(f"{OLLAMA}/api/embed", json={"model": EMBED_MODEL, "input": textos[i:i + 32]},
                       timeout=300)
        r.raise_for_status()
        vetores += r.json()["embeddings"]
    return vetores


def chave_espaco(nome):
    """'Espaço Bolivia – LatinScience' e 'Espaço Bolívia' viram 'bolivia'."""
    s = unicodedata.normalize("NFD", nome).encode("ascii", "ignore").decode().lower()
    return s.removeprefix("espaco").strip().split()[0] if s.strip() else ""


def carregar_json(caminho, padrao):
    return json.loads(caminho.read_text()) if caminho.exists() else padrao


def inicio_da_live(video, palestras_do_dia, manual, lives_no_dia):
    if video["id"] in manual:
        inicio = datetime.fromisoformat(manual[video["id"]])
        return (inicio if inicio.tzinfo else inicio.replace(tzinfo=BRT)), "manual"
    if video.get("inicio_live"):
        return datetime.fromtimestamp(video["inicio_live"], BRT), "youtube"
    if palestras_do_dia and lives_no_dia == 1:
        return min(datetime.fromisoformat(p["inicio"]) for p in palestras_do_dia), "estimado"
    return None, None


def links(palestrantes):
    return json.dumps([{"nome": s["nome"], "url": s["url"]} for s in palestrantes], ensure_ascii=False)


def janelas(segmentos):
    """Agrupa segmentos em pedaços de ~PALAVRAS palavras com SOBREPOSICAO palavras repetidas."""
    pedaco, n, novos = [], 0, 0
    for s in segmentos:
        pedaco.append(s)
        novos += 1
        n += len(s["texto"].split())
        if n >= PALAVRAS:
            yield pedaco
            novos = 0
            mantidos, m = [], 0
            for x in reversed(pedaco):
                if m >= SOBREPOSICAO:
                    break
                mantidos.insert(0, x)
                m += len(x["texto"].split())
            pedaco, n = mantidos, m
    if novos and n > 20:  # sem segmentos novos, a sobra já foi indexada no pedaço anterior
        yield pedaco


def trechos_de_transcricao(palestras, videos, manual):
    trechos, relatorio = [], []
    for v in videos:
        arq = DATA / "transcricoes" / f"{v['id']}.json"
        if not arq.exists():
            continue
        segs = json.loads(arq.read_text())["segmentos"]
        do_dia = [p for p in palestras if p["inicio"].startswith(v["data"])
                  and chave_espaco(p["espaco"]) == chave_espaco(v["espaco"])]
        lives_no_dia = sum(1 for x in videos if x["data"] == v["data"]
                           and chave_espaco(x["espaco"]) == chave_espaco(v["espaco"]))
        t0, fonte = inicio_da_live(v, do_dia, manual, lives_no_dia)
        relatorio.append({"video": v["id"], "titulo": v["titulo"], "alinhamento": fonte,
                          "palestras_no_espaco": len(do_dia)})
        por_palestra = {}
        for s in segs:
            hora = t0 + timedelta(seconds=s["inicio"]) if t0 else None
            dona = next((p for p in do_dia if hora and datetime.fromisoformat(p["inicio"]) <= hora
                         < datetime.fromisoformat(p["fim"])), None)
            por_palestra.setdefault(dona["id"] if dona else None, []).append(s)
        por_id = {p["id"]: p for p in do_dia}
        for pid, ss in por_palestra.items():
            p = por_id.get(pid)
            for janela in janelas(ss):
                ini = int(janela[0]["inicio"])
                trechos.append({
                    "texto": " ".join(x["texto"] for x in janela),
                    "fonte": "transcricao",
                    "palestra_id": pid or "",
                    "palestra_titulo": p["titulo"] if p else f"{v['espaco']} {v['data']} (fora da grade)",
                    "palestrantes": ", ".join(x["nome"] for x in p["palestrantes"]) if p else "",
                    "links_palestrantes": links(p["palestrantes"]) if p else "[]",
                    "idioma_original": IDIOMA.get(p.get("idioma"), "") if p else "",
                    "espaco": v["espaco"],
                    "inicio": p["inicio"] if p else v["data"],
                    "video_id": v["id"],
                    "inicio_video_s": ini,
                    "url": f"{v['url']}&t={ini}s",
                    "alinhamento": fonte or "",
                })
    return trechos, relatorio


def main():
    palestras = json.loads((DATA / "site" / "palestras.json").read_text())
    pessoas = json.loads((DATA / "site" / "palestrantes.json").read_text())
    videos = carregar_json(DATA / "videos.json", [])
    manual = carregar_json(RAIZ / "alinhamento.json", {})

    por_url = {}
    for p in palestras:
        for s in p["palestrantes"]:
            por_url.setdefault(s["url"], []).append(p["titulo"])

    trechos = []
    for p in palestras:
        quando = datetime.fromisoformat(p["inicio"]).strftime("%d/%m/%Y %H:%M")
        nomes = ", ".join(s["nome"] for s in p["palestrantes"])
        trechos.append({
            "texto": f"{p['titulo']}\nPalestrantes: {nomes}\nTrilha: {p['trilha']} | {p['espaco']} | "
                     f"{quando} | Idioma: {p.get('idioma', '')}\n{p['resumo']}",
            "fonte": "resumo", "palestra_id": p["id"], "palestra_titulo": p["titulo"],
            "palestrantes": nomes, "links_palestrantes": links(p["palestrantes"]),
            "idioma_original": IDIOMA.get(p.get("idioma"), ""),
            "espaco": p["espaco"], "inicio": p["inicio"], "video_id": "", "inicio_video_s": 0,
            "url": p["url"], "alinhamento": "",
        })
    for s in pessoas:
        org = f" ({s['organizacao']})" if s["organizacao"] else ""
        titulos = por_url.get(s["url"], [])
        trechos.append({
            "texto": f"{s['nome']}{org}. País: {s['pais']}\n{s['bio']}\nPalestras na Latinoware 2026: "
                     + "; ".join(titulos),
            "fonte": "bio", "palestra_id": "", "palestra_titulo": "; ".join(titulos),
            "palestrantes": s["nome"], "links_palestrantes": links([s]), "idioma_original": "",
            "espaco": "", "inicio": "",
            "video_id": "", "inicio_video_s": 0, "url": s["url"], "alinhamento": "",
        })
    transcritos, relatorio = trechos_de_transcricao(palestras, videos, manual)
    trechos += transcritos
    print(f"trechos: {len(trechos)} (resumos {len(palestras)}, bios {len(pessoas)}, "
          f"transcrição {len(transcritos)})")
    for r in relatorio:
        print(f"  {r['titulo']}: alinhamento {r['alinhamento']}, {r['palestras_no_espaco']} palestras")

    vetores = embed([t["texto"] for t in trechos])
    vet_palestras = vetores[:len(palestras)]
    vet_pessoas = vetores[len(palestras):len(palestras) + len(pessoas)]

    texto = lambda n: Property(name=n, data_type=DataType.TEXT)  # noqa: E731
    with conectar() as cli:
        for nome in ("Palestra", "Palestrante", "Trecho"):
            cli.collections.delete(nome)
        col_p = cli.collections.create("Palestra", vector_config=Configure.Vectors.self_provided(),
                                       properties=[texto(n) for n in ("pid", "titulo", "resumo", "trilha",
                                                   "espaco", "inicio", "fim", "idioma", "tipo",
                                                   "palestrantes", "url")])
        col_s = cli.collections.create("Palestrante", vector_config=Configure.Vectors.self_provided(),
                                       properties=[texto(n) for n in ("nome", "bio", "organizacao",
                                                   "pais", "url", "palestras")])
        col_t = cli.collections.create("Trecho", vector_config=Configure.Vectors.self_provided(),
                                       properties=[texto(n) for n in ("texto", "fonte", "palestra_id",
                                                   "palestra_titulo", "palestrantes", "links_palestrantes", "idioma_original",
                                                   "espaco", "inicio", "video_id", "url", "alinhamento")]
                                       + [Property(name="inicio_video_s", data_type=DataType.INT)])
        with col_p.batch.fixed_size(200) as b:
            for p, vec in zip(palestras, vet_palestras):
                b.add_object(properties={
                    "pid": p["id"], "titulo": p["titulo"], "resumo": p["resumo"], "trilha": p["trilha"],
                    "espaco": p["espaco"], "inicio": p["inicio"], "fim": p["fim"],
                    "idioma": p.get("idioma", ""), "tipo": p["tipo"], "url": p["url"],
                    "palestrantes": ", ".join(s["nome"] for s in p["palestrantes"])}, vector=vec)
        with col_s.batch.fixed_size(200) as b:
            for s, vec in zip(pessoas, vet_pessoas):
                b.add_object(properties={
                    "nome": s["nome"], "bio": s["bio"], "organizacao": s["organizacao"], "pais": s["pais"],
                    "url": s["url"],
                    "palestras": "; ".join(por_url.get(s["url"], []))}, vector=vec)
        with col_t.batch.fixed_size(200) as b:
            for t, vec in zip(trechos, vetores):
                b.add_object(properties=t, vector=vec)
        falhas = 0
        for col in (col_p, col_s, col_t):
            erros = col.batch.failed_objects
            falhas += len(erros)
            print(f"{col.name}: {len(col)} objetos, {len(erros)} falhas")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
