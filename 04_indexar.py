"""Etapa 4: monta chunks, gera embeddings bge-m3 (Ollama) e carrega no Weaviate.

Coleções (recriadas a cada execução):
- Palestra: uma por atividade da grade
- Palestrante: uma por pessoa
- Trecho: unidade de busca da RAG. Inclui resumos de palestras, bios de palestrantes e,
  quando houver transcrição, pedaços de ~350 palavras (com sobreposição) de cada palestra,
  com link para o vídeo no instante certo (?t=).

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
MIN_FALA = 10  # palavras transcritas por minuto da janela para a palestra contar como gravada
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


def uid(p):
    """id da grade não é único (keynotes repetem por sala): a chave junta id e espaço."""
    return f"{p['id']}@{chave_espaco(p['espaco'])}"


def url_video(video_id, t):
    return f"https://youtu.be/{video_id}?t={t}"


def live_do_espaco(v, palestras, videos, manual):
    """Palestras do espaço e dia da live, e o instante em que a live começou."""
    do_dia = [p for p in palestras if p["inicio"].startswith(v["data"])
              and chave_espaco(p["espaco"]) == chave_espaco(v["espaco"])]
    lives_no_dia = sum(1 for x in videos if x["data"] == v["data"]
                       and chave_espaco(x["espaco"]) == chave_espaco(v["espaco"]))
    return do_dia, *inicio_da_live(v, do_dia, manual, lives_no_dia)


def alinhar_palestras(palestras, videos, manual, inicios=True):
    """{uid: video_id, t_inicio, t_fim, alinhamento, url_video} das palestras que caem dentro de uma live.

    Com transcrição, exige MIN_FALA palavras por minuto na janela: keynotes da grade repetem em todas as salas,
    mas só algumas lives transmitiram o áudio; nas outras o trecho é silêncio ou música.
    A grade atrasa: com inicios=True, o instante vem de alinhamento.json ("<uid>": segundos, correção
    manual) ou de data/inicios.json (08_sincronizar_inicio.py, lido da transcrição), quando houver.
    """
    alinhadas = {}
    for v in videos:
        do_dia, t0, fonte = live_do_espaco(v, palestras, videos, manual)
        if not t0 or not v.get("duracao"):
            continue
        arq = DATA / "transcricoes" / f"{v['id']}.json"
        segs = json.loads(arq.read_text())["segmentos"] if arq.exists() else None
        for p in do_dia:
            ini = int((datetime.fromisoformat(p["inicio"]) - t0).total_seconds())
            fim = int((datetime.fromisoformat(p["fim"]) - t0).total_seconds())
            ini, fim = max(ini, 0), min(fim, v["duracao"])  # começou antes da live: vale a parte gravada
            anterior = alinhadas.get(uid(p))
            # duas lives no mesmo espaço e dia: fica a que gravou mais da palestra
            palavras = sum(len(s["texto"].split()) for s in segs if ini <= s["inicio"] < fim) if segs else 0
            fala = segs is None or palavras >= MIN_FALA * (fim - ini) / 60
            if fala and fim > ini and (not anterior or fim - ini > anterior["t_fim"] - anterior["t_inicio"]):
                alinhadas[uid(p)] = {"video_id": v["id"], "t_inicio": ini, "t_fim": fim,
                                     "alinhamento": fonte, "url_video": url_video(v["id"], ini)}
    if inicios:
        lidos = carregar_json(DATA / "inicios.json", {})
        for u, a in alinhadas.items():
            candidatos = [(manual.get(u), "manual")]
            if lidos.get(u, {}).get("video_id") == a["video_id"]:
                candidatos.append((lidos[u]["t"], "transcricao"))
            # o primeiro válido vence: manual fora do vídeo não descarta o lido da transcrição
            t, como = next(((t, c) for t, c in candidatos if isinstance(t, int) and 0 <= t < a["t_fim"]), (None, None))
            if t is not None:
                a.update(t_inicio=t, alinhamento=como, url_video=url_video(a["video_id"], t))
    return alinhadas


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


def trechos_de_transcricao(palestras, videos, manual, alinhadas=None):
    trechos, relatorio = [], []
    for v in videos:
        arq = DATA / "transcricoes" / f"{v['id']}.json"
        if not arq.exists():
            continue
        segs = json.loads(arq.read_text())["segmentos"]
        do_dia, t0, fonte = live_do_espaco(v, palestras, videos, manual)
        relatorio.append({"video": v["id"], "titulo": v["titulo"], "alinhamento": fonte,
                          "palestras_no_espaco": len(do_dia)})
        # janela de cada palestra em segundos do vídeo; com início real (transcrição ou manual) a janela
        # anda junto, senão os minutos de atraso iriam para a palestra anterior
        faixas = []
        for p in do_dia if t0 else []:
            ini = (datetime.fromisoformat(p["inicio"]) - t0).total_seconds()
            fim = (datetime.fromisoformat(p["fim"]) - t0).total_seconds()
            a = (alinhadas or {}).get(uid(p))
            if a and a["video_id"] == v["id"] and a["alinhamento"] in ("transcricao", "manual"):
                fim, ini = fim + a["t_inicio"] - max(ini, 0), a["t_inicio"]
            faixas.append((ini, fim, p))
        por_palestra = {}
        for s in segs:
            # sobreposição (anterior atrasou): vale a que começou por último
            dona = max(((i, p) for i, f, p in faixas if i <= s["inicio"] < f), key=lambda x: x[0], default=(0, None))[1]
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
                    "url": url_video(v["id"], ini),
                    "url_video": url_video(v["id"], ini),
                    "alinhamento": fonte or "",
                })
    return trechos, relatorio


def main():
    palestras = json.loads((DATA / "site" / "palestras.json").read_text())
    pessoas = json.loads((DATA / "site" / "palestrantes.json").read_text())
    videos = carregar_json(DATA / "videos.json", [])
    manual = carregar_json(RAIZ / "alinhamento.json", {})

    alinhadas = alinhar_palestras(palestras, videos, manual)
    print(f"palestras com vídeo: {len(alinhadas)} de {len(palestras)}")
    por_url, video_de = {}, {}
    for p in palestras:
        for s in p["palestrantes"]:
            por_url.setdefault(s["url"], []).append(p["titulo"])
            a = alinhadas.get(uid(p))
            # bio leva à palestra da pessoa com mais tempo gravado (não ao check-in de 1 min)
            if a and a["t_fim"] - a["t_inicio"] > video_de.get(s["url"], (0, ""))[0]:
                video_de[s["url"]] = (a["t_fim"] - a["t_inicio"], a["url_video"])

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
            "url": p["url"], "url_video": alinhadas.get(uid(p), {}).get("url_video", ""), "alinhamento": "",
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
            "video_id": "", "inicio_video_s": 0, "url": s["url"], "url_video": video_de.get(s["url"], (0, ""))[1],
            "alinhamento": "",
        })
    transcritos, relatorio = trechos_de_transcricao(palestras, videos, manual, alinhadas)
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
                                                   "palestrantes", "url", "video_id", "alinhamento")]
                                       + [Property(name="t_inicio", data_type=DataType.INT),
                                          Property(name="t_fim", data_type=DataType.INT),
                                          Property(name="url_video", data_type=DataType.TEXT,
                                                   index_searchable=False, index_filterable=False)])
        col_s = cli.collections.create("Palestrante", vector_config=Configure.Vectors.self_provided(),
                                       properties=[texto(n) for n in ("nome", "bio", "organizacao",
                                                   "pais", "url", "palestras")])
        col_t = cli.collections.create("Trecho", vector_config=Configure.Vectors.self_provided(),
                                       properties=[texto(n) for n in ("texto", "fonte", "palestra_id",
                                                   "palestra_titulo", "palestrantes", "idioma_original",
                                                   "espaco", "inicio", "video_id", "url", "alinhamento")]
                                       + [Property(name="inicio_video_s", data_type=DataType.INT),
                                          # só para exibir: fora da busca BM25 (URLs e nomes repetidos)
                                          Property(name="links_palestrantes", data_type=DataType.TEXT,
                                                   index_searchable=False, index_filterable=False),
                                          Property(name="url_video", data_type=DataType.TEXT,
                                                   index_searchable=False, index_filterable=False)])
        with col_p.batch.fixed_size(200) as b:
            for p, vec in zip(palestras, vet_palestras):
                b.add_object(properties={
                    "pid": p["id"], "titulo": p["titulo"], "resumo": p["resumo"], "trilha": p["trilha"],
                    "espaco": p["espaco"], "inicio": p["inicio"], "fim": p["fim"],
                    "idioma": p.get("idioma", ""), "tipo": p["tipo"], "url": p["url"],
                    "palestrantes": ", ".join(s["nome"] for s in p["palestrantes"])}
                    | alinhadas.get(uid(p), {}), vector=vec)
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
