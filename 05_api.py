"""Etapa 5: API da RAG. POST /ask {"pergunta": "...", "idioma": "pt|en|es" (opcional), "k": 8}
POST /ask/stream: o mesmo corpo, resposta em SSE (eventos etapa, fontes, token, fim, erro).

Fluxo: embute a pergunta (bge-m3) -> busca híbrida (BM25 + vetor) na coleção Trecho ->
monta contexto numerado -> LLM responde no idioma da pergunta, citando [n].

LLM: Ollama local (LLM_MODEL, padrão gemma4:12b-it-qat). Com LLM_API_KEY definida, usa um provedor
externo compatível com a API OpenAI (LLM_BASE_URL + LLM_MODEL).
"""

import asyncio
import json
import logging
import os
import re
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import uvicorn
import weaviate
from weaviate.classes.config import Configure, DataType, Property, Tokenization
from weaviate.classes.query import Filter, MetadataQuery, Sort
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemma4:12b-it-qat")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
ALPHA = float(os.environ.get("HYBRID_ALPHA", 0.75))  # 0 = só BM25, 1 = só vetor
# reranker opcional (bge-reranker-v2-m3): na GPU desta máquina (RERANK_LOCAL, modelo do Hugging Face;
# precisa de `uv sync --extra rerank`) ou num serviço no formato Jina/Cohere (RERANK_URL)
RERANK_LOCAL = os.environ.get("RERANK_LOCAL", "")
RERANK_URL = os.environ.get("RERANK_URL", "")
RERANK_MODEL = os.environ.get("RERANK_MODEL", "bge-reranker-v2-m3")
# no serviço em CPU o reranker leva ~0,4 s por trecho: só os primeiros RERANK_TOP, com o texto cortado;
# na GPU (RERANK_LOCAL) vão todos os candidatos inteiros (~0,25 s para 32)
RERANK_TOP = int(os.environ.get("RERANK_TOP", 16))
_reranker, _trava_reranker = None, threading.Lock()  # _reranker = False: a carga falhou, não tenta de novo
# histórico de perguntas (coleção Pergunta): sem IP nem user agent; reaproveita resposta de pergunta igual
# (distância bge-m3 ≤ CACHE_DIST: variações de pontuação e caixa ficam abaixo de 0,03; perguntas diferentes
# medidas ficaram acima de 0,09) e apaga o que tiver mais de RETENCAO_DIAS
CACHE_DIST = float(os.environ.get("CACHE_DIST", 0.05))
RETENCAO_DIAS = int(os.environ.get("RETENCAO_DIAS", 90))
SEM_PALESTRA = "-"  # pergunta geral (não é "Resumo com IA" de uma palestra)
ARQ_VERSAO = Path(__file__).parent / "data" / "versao_indice.txt"


def versao_indice():
    """Lida a cada pergunta: depois de `make indexar` o cache antigo deixa de valer mesmo sem reiniciar a API."""
    return ARQ_VERSAO.read_text().strip() if ARQ_VERSAO.exists() else "0"
CORS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "https://ilove.the.br,https://www.ilove.the.br,https://rede-cidades.pages.dev,https://latinoware.org,https://www.latinoware.org,http://localhost:8765").split(",")]
MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", 800))
# sem limite, uma palestra longa e bem transcrita ocupava 7 das 8 fontes
MAX_POR_PALESTRA = int(os.environ.get("MAX_POR_PALESTRA", 2))
# a GPU atende poucas gerações por vez; acima disso a API responde 429 em vez de enfileirar
GERACOES = asyncio.Semaphore(int(os.environ.get("MAX_CONCORRENCIA", 2)))
log = logging.getLogger("uvicorn.error")

INSTRUCOES = {
    "pt": ("Você responde perguntas sobre a Latinoware 2026 (Foz do Iguaçu, 14 a 16 de outubro "
           "de 2026) usando SOMENTE os trechos numerados abaixo. Responda em português do Brasil. "
           "Cite as fontes com [n]. Se os trechos não trazem a resposta, diga que não encontrou "
           "essa informação nas palestras indexadas. Se o trecho que responde não tem palestrante "
           "identificado, diga isso, informe o espaço e o dia e sugira ouvir o vídeo a partir do "
           "instante que aparece no cabeçalho do trecho (escreva o horário, por exemplo 3:54:33)."),
    "en": ("You answer questions about Latinoware 2026 (Foz do Iguaçu, Brazil, October 14-16, "
           "2026) using ONLY the numbered excerpts below, which may be in Portuguese. Answer in "
           "English. Cite sources as [n]. If the excerpts do not contain the answer, say you could "
           "not find it in the indexed talks. If the excerpt that answers has no identified speaker, "
           "say so, give the room and the day, and suggest listening to the video from the time shown "
           "in the excerpt header (write the actual time, e.g. 3:54:33)."),
    "es": ("Respondes preguntas sobre Latinoware 2026 (Foz do Iguaçu, Brasil, 14 al 16 de octubre "
           "de 2026) usando SOLO los fragmentos numerados abajo, que pueden estar en portugués. "
           "Responde en español. Cita las fuentes con [n]. Si los fragmentos no contienen la "
           "respuesta, di que no la encontraste en las charlas indexadas. Si el fragmento que "
           "responde no tiene ponente identificado, dilo, indica el espacio y el día y sugiere "
           "escuchar el video desde el instante que aparece en el encabezado del fragmento (escribe la "
           "hora, por ejemplo 3:54:33)."),
}
RESUMO = {
    "pt": ("Você resume uma palestra da Latinoware 2026 usando SOMENTE os trechos numerados abaixo (resumo do "
           "site e transcrição do vídeo, em ordem). Responda em português do Brasil: um parágrafo de 3 a 6 "
           "frases e depois 3 pontos principais em lista. Cite as fontes pelo número, ex.: [1], [3]. Se só houver o resumo do site, "
           "diga que a palestra não tem gravação transcrita e resuma o que o site informa."),
    "en": ("You summarize a Latinoware 2026 talk using ONLY the numbered excerpts below (the website abstract "
           "and the video transcript, in order), which may be in Portuguese. Answer in English: one paragraph "
           "of 3 to 6 sentences, then 3 key points as a list. Cite sources by number, e.g. [1], [3]. If there is only the website "
           "abstract, say the talk has no transcribed recording and summarize what the website says."),
    "es": ("Resumes una charla de Latinoware 2026 usando SOLO los fragmentos numerados abajo (resumen del sitio "
           "y transcripción del video, en orden), que pueden estar en portugués. Responde en español: un "
           "párrafo de 3 a 6 frases y luego 3 puntos principales en lista. Cita las fuentes por número, p. ej. [1], [3]. Si solo "
           "hay el resumen del sitio, di que la charla no tiene grabación transcrita y resume lo que dice el sitio."),
}
# lembrete no fim do prompt: com a pergunta em outra língua, só a instrução de sistema não basta
LEMBRETE = {"pt": "Responda em português do Brasil.", "en": "Answer in English.",
            "es": "Responde en español."}

# palavras frequentes e exclusivas de cada língua, para detectar o idioma da pergunta
MARCAS = {
    "pt": {"não", "você", "vocês", "quem", "qual", "quais", "palestra", "palestras", "palestrante",
           "sobre", "foi", "uma", "das", "dos", "na", "no", "em", "é", "são", "teve", "falou", "o que",
           "como", "onde", "quando", "também", "isso", "ele", "ela"},
    "es": {"qué", "quién", "quiénes", "cuál", "cuáles", "charla", "charlas", "ponente", "ponentes",
           "habló", "es", "el", "los", "las", "del", "una", "en", "sobre", "hubo", "cómo", "dónde",
           "cuándo", "también", "eso", "y"},
    "en": {"what", "who", "which", "talk", "talks", "speaker", "speakers", "about", "was", "were",
           "the", "a", "an", "is", "are", "did", "how", "where", "when", "of", "and", "in", "on"},
}


def detectar_idioma(texto):
    t = texto.lower()
    palavras = re.findall(r"[\wáéíóúâêôàüãõçñ]+", t)
    pontos = {lang: sum(p in marcas for p in palavras) for lang, marcas in MARCAS.items()}
    # ã/õ/ç e ñ/¿/¡ só desempatam: nomes como "Iguaçu" ou "João" aparecem em qualquer língua
    pontos["pt"] += 0.5 * bool(re.search(r"[ãõç]", t))
    pontos["es"] += 0.5 * bool(re.search(r"[ñ¿¡]", t))
    melhor = max(pontos, key=pontos.get)
    return melhor if pontos[melhor] > 0 else "pt"


class Pergunta(BaseModel):
    pergunta: str = Field(min_length=3, max_length=1000)
    idioma: str | None = Field(default=None, pattern="^(pt|en|es)$")
    k: int = Field(default=8, ge=1, le=12)
    # "Resumo com IA" de uma palestra: usa só os trechos dela, sem busca
    palestra_id: str | None = Field(default=None, pattern=r"^[\w-]{1,40}$")
    novo: bool = False  # "Gerar de novo": ignora a resposta guardada


@asynccontextmanager
async def lifespan(app):
    app.state.wv = weaviate.connect_to_local(port=int(os.environ.get("WEAVIATE_HTTP_PORT", 18080)),
                                             grpc_port=int(os.environ.get("WEAVIATE_GRPC_PORT", 15051)))
    app.state.http = httpx.AsyncClient(timeout=180)
    if RERANK_LOCAL:  # carrega na subida, não na primeira pergunta (download de ~2 GB na 1ª vez)
        app.state.carga_reranker = asyncio.create_task(asyncio.to_thread(reranker_local))  # referência evita o GC
    try:  # sem histórico a API segue respondendo, só não reaproveita
        preparar_historico(app.state.wv)
    except Exception:
        log.exception("histórico de perguntas indisponível")
    app.state.expurgo = asyncio.create_task(expurgar_sempre())  # referência evita o GC
    yield
    app.state.expurgo.cancel()
    app.state.wv.close()
    await app.state.http.aclose()


app = FastAPI(title="Latinoware 2026 RAG", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"])


async def embed(texto):
    r = await app.state.http.post(f"{OLLAMA}/api/embed", json={"model": EMBED_MODEL, "input": texto})
    r.raise_for_status()
    return r.json()["embeddings"][0]


async def pedacos(sistema, usuario):
    """Texto da resposta em pedaços, à medida que o LLM gera."""
    mensagens = [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]
    if LLM_API_KEY:
        async with app.state.http.stream("POST", f"{LLM_BASE_URL}/chat/completions",
                                         headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                                         json={"model": LLM_MODEL, "messages": mensagens, "temperature": 0.2,
                                               "max_tokens": MAX_TOKENS, "stream": True}) as r:
            r.raise_for_status()
            async for linha in r.aiter_lines():
                if linha.startswith("data: ") and linha != "data: [DONE]":
                    d = json.loads(linha[6:])
                    if "error" in d:  # erro no meio do stream chega com HTTP 200
                        raise RuntimeError(d["error"])
                    escolhas = d.get("choices") or [{}]
                    yield escolhas[0].get("delta", {}).get("content") or ""
        return
    async with app.state.http.stream("POST", f"{OLLAMA}/api/chat", json={
            "model": LLM_MODEL, "messages": mensagens, "stream": True, "think": False,
            "options": {"temperature": 0.2, "num_ctx": 16384, "num_predict": MAX_TOKENS}}) as r:
        r.raise_for_status()
        async for linha in r.aiter_lines():
            if linha:
                d = json.loads(linha)
                if "error" in d:
                    raise RuntimeError(d["error"])
                yield d.get("message", {}).get("content", "")


async def gerar(sistema, usuario):
    return "".join([p async for p in pedacos(sistema, usuario)])


def limpar(resposta):
    return re.sub(r"<think>.*?</think>", "", resposta, flags=re.S).strip()


def links(valor):
    try:
        return json.loads(valor or "[]")
    except ValueError:
        return []


def video(url):
    """(video_id, segundos) de https://youtu.be/<id>?t=<s>; (None, None) sem vídeo."""
    m = re.fullmatch(r"https://youtu\.be/([\w-]+)\?t=(\d+)", url or "")
    return (m[1], int(m[2])) if m else (None, None)


def da_palestra(palestra_id, k):
    """Resumo do site primeiro e transcrição em ordem de tempo; acima de k, pedaços espalhados pela palestra."""
    res = app.state.wv.collections.get("Trecho").query.fetch_objects(
        filters=Filter.by_property("palestra_id").equal(palestra_id), limit=200)
    objs = [o.properties for o in res.objects]
    resumos = [t for t in objs if t["fonte"] == "resumo"][:1]  # keynote repete o resumo por sala
    falas = sorted((t for t in objs if t["fonte"] == "transcricao"), key=lambda t: t["inicio_video_s"])
    vagas = k - len(resumos)
    if len(falas) > vagas:
        falas = [falas[i * len(falas) // vagas] for i in range(vagas)]
    return resumos + falas


def candidatos(trecho, pergunta, vetor, k):
    """Busca híbrida com folga (k*4), sem repetições."""
    res = trecho.query.hybrid(query=pergunta, vector=vetor, alpha=ALPHA, limit=k * 4)
    # keynotes são transmitidas em vários espaços: o mesmo resumo aparece repetido na grade
    vistos, unicos = set(), []
    for o in res.objects:
        t = o.properties
        chave = (re.sub(r"\W", "", t["palestra_titulo"].lower()), t["palestrantes"]) if t["fonte"] == "resumo" else t["texto"]
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(t)
    return unicos


def reranker_local():
    """CrossEncoder em fp16 na GPU, carregado na primeira pergunta (~2 GB baixados na primeira vez)."""
    global _reranker
    with _trava_reranker:
        if _reranker is None:
            try:
                import torch
                from sentence_transformers import CrossEncoder
                _reranker = CrossEncoder(RERANK_LOCAL, device="cuda", max_length=512,
                                         model_kwargs={"dtype": torch.float16})
            except Exception:
                log.exception("reranker local não carregou (falta `uv sync --extra rerank`?); segue sem ele")
                _reranker = False
        return _reranker


def reordenar(pergunta, trechos):
    """Ordena pelo reranker; se ele falhar, segue a ordem da busca (o /ask nunca cai por isso)."""
    topo, resto = (trechos, []) if RERANK_LOCAL else (trechos[:RERANK_TOP], trechos[RERANK_TOP:])
    if not (RERANK_LOCAL or RERANK_URL) or len(topo) < 2:
        return trechos
    if RERANK_LOCAL:
        modelo = reranker_local()
        if not modelo:
            return trechos
        try:
            with _trava_reranker:  # uma inferência por vez na GPU
                notas = modelo.predict([(pergunta, f"{t['palestra_titulo']}\n{t['texto']}") for t in topo])
            return [t for _, t in sorted(zip(notas, topo), key=lambda x: -x[0])] + resto
        except Exception:
            log.exception("reranker local indisponível; segue sem reordenar")
            return trechos
    try:
        r = httpx.post(RERANK_URL, timeout=30, json={
            "model": RERANK_MODEL, "query": pergunta,
            "documents": [f"{t['palestra_titulo']}\n{t['texto']}"[:600] for t in topo]})
        r.raise_for_status()
        ordem = sorted(r.json()["results"], key=lambda x: -x["relevance_score"])
        if sorted(x["index"] for x in ordem) != list(range(len(topo))):  # parcial, repetido ou fora da faixa
            raise ValueError(f"reranker devolveu {len(ordem)} índices para {len(topo)} trechos")
        return [topo[x["index"]] for x in ordem] + resto
    except Exception:
        log.exception("reranker indisponível; segue sem reordenar")
        return trechos


def limitar(trechos, k):
    """Até MAX_POR_PALESTRA transcrições por palestra (título + horário, pois palestra_id repete entre
    salas); resumo, bio e trecho fora da grade passam sempre."""
    por_palestra, saida = {}, []
    for t in trechos:
        if t["fonte"] == "transcricao" and t["palestra_id"]:
            palestra = (re.sub(r"\W", "", t["palestra_titulo"].lower()), t["inicio"])
            if por_palestra.get(palestra, 0) >= MAX_POR_PALESTRA:
                continue
            por_palestra[palestra] = por_palestra.get(palestra, 0) + 1
        saida.append(t)
    return saida[:k]


def selecionar(trecho, pergunta, vetor, k):
    """Busca, reordenação e corte em k; também usada por 06_avaliar_busca.py."""
    return limitar(reordenar(pergunta, candidatos(trecho, pergunta, vetor, k)), k)


def usa_historico(q):
    """k não entra na chave do histórico: só vale para o k padrão, o que a página usa."""
    return not q.novo and q.k == Pergunta.model_fields["k"].default


async def ja_respondida(q):
    """Resposta guardada de pergunta igual, procurada antes de pegar vaga na GPU (não recebe 429 à toa)."""
    if not usa_historico(q):
        return None
    try:
        return await asyncio.to_thread(do_historico, q, q.idioma or detectar_idioma(q.pergunta), await embed(q.pergunta))
    except Exception:
        log.exception("falha no histórico; segue sem ele")
        return None


@app.post("/ask")
async def ask(q: Pergunta):
    if guardada := await ja_respondida(q):
        return guardada
    if GERACOES.locked():
        raise HTTPException(429, "muitas perguntas ao mesmo tempo; tente de novo em instantes")
    async with GERACOES:
        return await responder(q)


def preparar_historico(wv):
    if wv.collections.exists("Pergunta"):
        return
    texto = lambda n: Property(name=n, data_type=DataType.TEXT)  # noqa: E731
    # campos de filtro com igualdade exata (tokenização "field"); a de palavras recusa valores curtos
    chave = lambda n: Property(name=n, data_type=DataType.TEXT, tokenization=Tokenization.FIELD,  # noqa: E731
                               index_searchable=False)
    wv.collections.create("Pergunta", vector_config=Configure.Vectors.self_provided(), properties=[
        texto("pergunta"), chave("idioma"), texto("resposta"),
        Property(name="fontes", data_type=DataType.TEXT, index_searchable=False, index_filterable=False),
        chave("modelo"), chave("palestra_id"), chave("versao_indice"),
        Property(name="criado_em", data_type=DataType.DATE), Property(name="reutilizacoes", data_type=DataType.INT)])


def expurgar():
    limite = datetime.now(timezone.utc) - timedelta(days=RETENCAO_DIAS)
    r = app.state.wv.collections.get("Pergunta").data.delete_many(where=Filter.by_property("criado_em").less_than(limite))
    if r.successful:
        log.info(f"histórico: {r.successful} perguntas com mais de {RETENCAO_DIAS} dias apagadas")


async def expurgar_sempre():
    while True:
        try:
            await asyncio.to_thread(expurgar)
        except Exception:
            log.exception("falha no expurgo do histórico")
        await asyncio.sleep(24 * 3600)


def filtro_igual(q, idioma):
    """Só reaproveita no mesmo idioma, modelo, índice e palestra (resumo de uma palestra é outra pergunta)."""
    return (Filter.by_property("idioma").equal(idioma) & Filter.by_property("modelo").equal(LLM_MODEL)
            & Filter.by_property("versao_indice").equal(versao_indice())
            & Filter.by_property("palestra_id").equal(q.palestra_id or SEM_PALESTRA))


def do_historico(q, idioma, vetor):
    col = app.state.wv.collections.get("Pergunta")
    res = col.query.near_vector(vetor, limit=1, distance=CACHE_DIST, filters=filtro_igual(q, idioma),
                                return_metadata=MetadataQuery(distance=True))
    if not res.objects:
        return None
    o = res.objects[0]
    col.data.update(o.uuid, properties={"reutilizacoes": o.properties["reutilizacoes"] + 1})
    return {"resposta": o.properties["resposta"], "idioma": idioma, "fontes": json.loads(o.properties["fontes"]),
            "reaproveitada": True, "criado_em": o.properties["criado_em"].isoformat()}


def guardar(q, idioma, vetor, resposta, fontes):
    if not (resposta and fontes):  # sem resposta não há o que reaproveitar
        return
    col = app.state.wv.collections.get("Pergunta")
    # "Gerar de novo" substitui a resposta guardada da mesma pergunta (e herda a contagem de reaproveitamentos)
    iguais = col.query.near_vector(vetor, limit=10, distance=CACHE_DIST, filters=filtro_igual(q, idioma)).objects
    vezes = sum(o.properties["reutilizacoes"] for o in iguais)
    for o in iguais:
        col.data.delete_by_id(o.uuid)
    col.data.insert(vector=vetor, properties={
        "pergunta": q.pergunta, "idioma": idioma, "resposta": resposta, "fontes": json.dumps(fontes),
        "modelo": LLM_MODEL, "palestra_id": q.palestra_id or SEM_PALESTRA, "versao_indice": versao_indice(),
        "criado_em": datetime.now(timezone.utc), "reutilizacoes": vezes})


async def lembrar(q, idioma, vetor, resposta, fontes):
    if vetor is None or q.k != Pergunta.model_fields["k"].default:
        return
    try:  # o histórico nunca derruba a resposta
        await asyncio.to_thread(guardar, q, idioma, vetor, resposta, fontes)
    except Exception:
        log.exception("falha ao guardar no histórico")


def hms(s):
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


def cabecalho(t):
    if t["fonte"] != "transcricao":
        return f"{t['palestra_titulo']} | {t['palestrantes']} | fonte: {t['fonte']}"
    quando = f"{t['espaco']}, dia {t['inicio'][8:10]}/{t['inicio'][5:7]}, vídeo a partir de {hms(t['inicio_video_s'])}"
    if not t["palestra_id"]:  # fora da grade: sem título nem palestrante, o modelo inventava um
        return f"trecho de vídeo sem palestra nem palestrante identificados | {quando}"
    return f"{t['palestra_titulo']} | {t['palestrantes']} | transcrição: {quando}"


async def passos(q):
    """Prepara a resposta em passos: ("etapa", nome) para o stream e, no fim, ("cache", resposta guardada) ou
    ("pronto", (idioma, prompt, fontes, vetor)). A geração fica para quem chama."""
    idioma = q.idioma or detectar_idioma(q.pergunta)
    try:
        vetor = await embed(q.pergunta)
    except Exception:
        log.exception("falha no embedding")
        if not q.palestra_id:  # a busca precisa do vetor; o resumo de uma palestra não (segue sem histórico)
            raise HTTPException(503, "busca indisponível") from None
        vetor = None
    if usa_historico(q) and vetor is not None:
        try:
            guardada = await asyncio.to_thread(do_historico, q, idioma, vetor)
        except Exception:
            log.exception("falha no histórico; segue sem ele")
            guardada = None
        if guardada:
            yield "cache", guardada
            return
    try:
        if q.palestra_id:
            trechos = await asyncio.to_thread(da_palestra, q.palestra_id, max(q.k, 12))
        else:
            achados = await asyncio.to_thread(candidatos, app.state.wv.collections.get("Trecho"), q.pergunta,
                                              vetor, q.k)
            if RERANK_LOCAL or RERANK_URL:
                yield "etapa", "reordenando"
                achados = await asyncio.to_thread(reordenar, q.pergunta, achados)
            trechos = limitar(achados, q.k)
    except Exception:
        log.exception("falha na busca")
        raise HTTPException(503, "busca indisponível") from None
    if q.palestra_id and not trechos:  # sem trechos o LLM inventaria um resumo
        raise HTTPException(404, "palestra sem trechos indexados")
    contexto = "\n\n".join(f"[{i}] {cabecalho(t)}\n{t['texto']}" for i, t in enumerate(trechos, 1))
    prompt = ((RESUMO if q.palestra_id else INSTRUCOES)[idioma], f"Trechos:\n{contexto}\n\nPergunta: {q.pergunta}\n\n{LEMBRETE[idioma]}")
    # transcrições servem de contexto, mas não são devolvidas: só título, autor e link com tempo
    fontes = [{"n": i, "titulo": t["palestra_titulo"], "palestrantes": t["palestrantes"],
               "links_palestrantes": links(t.get("links_palestrantes")),
               "fonte": t["fonte"], "espaco": t["espaco"], "inicio": t["inicio"], "url": t["url"],
               "url_video": t.get("url_video") or None, "video_id": video(t.get("url_video"))[0],
               "video_t": video(t.get("url_video"))[1], "alinhamento": t["alinhamento"],
               "palestra_id": t["palestra_id"] or None,
               "inicio_video_s": t["inicio_video_s"] if t["video_id"] else None}
              for i, t in enumerate(trechos, 1)]
    yield "pronto", (idioma, prompt, fontes, vetor)


async def preparar(q):
    async for tipo, valor in passos(q):
        if tipo in ("pronto", "cache"):
            return tipo, valor


async def responder(q):
    tipo, valor = await preparar(q)
    if tipo == "cache":
        return valor
    idioma, prompt, fontes, vetor = valor
    try:
        resposta = limpar(await gerar(*prompt))
    except Exception:
        log.exception("falha no LLM")
        raise HTTPException(503, "gerador de respostas indisponível") from None
    await lembrar(q, idioma, vetor, resposta, fontes)
    return {"resposta": resposta, "idioma": idioma, "fontes": fontes, "reaproveitada": False}


def sse(evento, dados):
    return f"event: {evento}\ndata: {json.dumps(dados, ensure_ascii=False)}\n\n"


@app.post("/ask/stream")
async def ask_stream(q: Pergunta):
    if guardada := await ja_respondida(q):
        async def reaproveitar():
            yield sse("etapa", {"etapa": "reaproveitando"})
            yield sse("fontes", {"fontes": guardada["fontes"], "idioma": guardada["idioma"]})
            yield sse("fim", guardada)
        return StreamingResponse(reaproveitar(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
    if GERACOES.locked():
        raise HTTPException(429, "muitas perguntas ao mesmo tempo; tente de novo em instantes")
    # o corpo do stream só roda depois do handler: a vaga é tomada aqui, senão o 429 nunca dispara
    await GERACOES.acquire()
    vaga = [True]  # liberar() roda no fim do corpo e no background: só a primeira vez solta

    def liberar():
        if vaga:
            vaga.pop()
            GERACOES.release()

    async def eventos():
        try:
            yield sse("etapa", {"etapa": "buscando"})
            try:
                async for tipo, valor in passos(q):
                    if tipo == "etapa":
                        yield sse("etapa", {"etapa": valor})
                    elif tipo == "cache":  # pergunta igual já respondida: sem GPU
                        yield sse("etapa", {"etapa": "reaproveitando"})
                        yield sse("fontes", {"fontes": valor["fontes"], "idioma": valor["idioma"]})
                        yield sse("fim", valor)
                        return
                    else:
                        idioma, prompt, fontes, vetor = valor
            except HTTPException as e:
                yield sse("erro", {"status": e.status_code, "detalhe": e.detail})
                return
            yield sse("fontes", {"fontes": fontes, "idioma": idioma})
            if not fontes:  # nada achado: não ocupa a GPU
                yield sse("fim", {"resposta": "", "idioma": idioma})
                return
            yield sse("etapa", {"etapa": "escrevendo", "modelo": LLM_MODEL})
            resposta = []
            try:
                async for p in pedacos(*prompt):
                    if p:
                        resposta.append(p)
                        yield sse("token", {"t": p})
            except Exception:
                log.exception("falha no LLM")
                yield sse("erro", {"status": 503, "detalhe": "gerador de respostas indisponível"})
                return
            texto = limpar("".join(resposta))
            await lembrar(q, idioma, vetor, texto, fontes)
            yield sse("fim", {"resposta": texto, "idioma": idioma, "reaproveitada": False})
        finally:
            liberar()

    # sem buffer no caminho (proxy/túnel), para os tokens chegarem na hora
    # background libera a vaga se o corpo nunca chegar a ser iterado
    return StreamingResponse(eventos(), media_type="text/event-stream", background=BackgroundTask(liberar),
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/frequentes")
def frequentes(idioma: str = "pt"):
    """As 8 perguntas mais reaproveitadas. Texto livre de quem perguntou vira público, então só aparecem as que estão
    em data/frequentes_aprovadas.json (lista curada à mão) e, além disso, feitas 3+ vezes, curtas e sem cara de dado
    pessoal (e-mail, telefone, documento). Sem a lista, nada aparece."""
    if idioma not in INSTRUCOES:
        raise HTTPException(422, "idioma deve ser pt, en ou es")
    try:
        res = app.state.wv.collections.get("Pergunta").query.fetch_objects(
            limit=30, sort=Sort.by_property("reutilizacoes", ascending=False),
        filters=Filter.by_property("idioma").equal(idioma) & Filter.by_property("versao_indice").equal(versao_indice())
        & Filter.by_property("palestra_id").equal(SEM_PALESTRA) & Filter.by_property("reutilizacoes").greater_or_equal(2))
    except Exception:
        log.exception("falha ao listar perguntas frequentes")
        return []
    arq = Path(__file__).parent / "data" / "frequentes_aprovadas.json"
    aprovadas = {norma(p) for p in json.loads(arq.read_text())} if arq.exists() else set()
    pessoal = re.compile(r"@|\d[\d .-]{5,}\d")
    return [{"pergunta": o.properties["pergunta"], "vezes": o.properties["reutilizacoes"] + 1} for o in res.objects
            if norma(o.properties["pergunta"]) in aprovadas and len(o.properties["pergunta"]) <= 120
            and not pessoal.search(o.properties["pergunta"])][:8]


def norma(pergunta):
    return " ".join(re.findall(r"\w+", pergunta.lower()))


@app.get("/health")
def health():
    return {"ok": app.state.wv.is_ready(), "modelo": LLM_MODEL, "reranker": (RERANK_LOCAL if _reranker is not False else None) or (RERANK_MODEL if RERANK_URL else None)}


# página, componente e catálogo; montado por último para não engolir /ask e /health
app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="web")


if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("API_HOST", "0.0.0.0"), port=int(os.environ.get("API_PORT", 8765)))
