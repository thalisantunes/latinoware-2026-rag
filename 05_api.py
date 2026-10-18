"""Etapa 5: API da RAG. POST /ask {"pergunta": "...", "idioma": "pt|en|es" (opcional), "k": 8}

Fluxo: embute a pergunta (bge-m3) -> busca híbrida (BM25 + vetor) na coleção Trecho ->
monta contexto numerado -> LLM responde no idioma da pergunta, citando [n].

LLM: Ollama local (LLM_MODEL, padrão qwen3:14b). Com LLM_API_KEY definida, usa um provedor
externo compatível com a API OpenAI (LLM_BASE_URL + LLM_MODEL).
"""

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
import weaviate
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "bge-m3")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3:14b")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
ALPHA = float(os.environ.get("HYBRID_ALPHA", 0.75))  # 0 = só BM25, 1 = só vetor
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
           "essa informação nas palestras indexadas."),
    "en": ("You answer questions about Latinoware 2026 (Foz do Iguaçu, Brazil, October 14-16, "
           "2026) using ONLY the numbered excerpts below, which may be in Portuguese. Answer in "
           "English. Cite sources as [n]. If the excerpts do not contain the answer, say you could "
           "not find it in the indexed talks."),
    "es": ("Respondes preguntas sobre Latinoware 2026 (Foz do Iguaçu, Brasil, 14 al 16 de octubre "
           "de 2026) usando SOLO los fragmentos numerados abajo, que pueden estar en portugués. "
           "Responde en español. Cita las fuentes con [n]. Si los fragmentos no contienen la "
           "respuesta, di que no la encontraste en las charlas indexadas."),
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


@asynccontextmanager
async def lifespan(app):
    app.state.wv = weaviate.connect_to_local(port=int(os.environ.get("WEAVIATE_HTTP_PORT", 18080)),
                                             grpc_port=int(os.environ.get("WEAVIATE_GRPC_PORT", 15051)))
    app.state.http = httpx.AsyncClient(timeout=180)
    yield
    app.state.wv.close()
    await app.state.http.aclose()


app = FastAPI(title="Latinoware 2026 RAG", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"])


async def embed(texto):
    r = await app.state.http.post(f"{OLLAMA}/api/embed", json={"model": EMBED_MODEL, "input": texto})
    r.raise_for_status()
    return r.json()["embeddings"][0]


async def gerar(sistema, usuario):
    mensagens = [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]
    if LLM_API_KEY:
        r = await app.state.http.post(f"{LLM_BASE_URL}/chat/completions",
                                      headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                                      json={"model": LLM_MODEL, "messages": mensagens, "temperature": 0.2,
                                            "max_tokens": MAX_TOKENS})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    r = await app.state.http.post(f"{OLLAMA}/api/chat", json={
        "model": LLM_MODEL, "messages": mensagens, "stream": False, "think": False,
        "options": {"temperature": 0.2, "num_ctx": 16384, "num_predict": MAX_TOKENS}})
    r.raise_for_status()
    return r.json()["message"]["content"]


def links(valor):
    try:
        return json.loads(valor or "[]")
    except ValueError:
        return []


def video(url):
    """(video_id, segundos) de https://youtu.be/<id>?t=<s>; (None, None) sem vídeo."""
    m = re.fullmatch(r"https://youtu\.be/([\w-]+)\?t=(\d+)", url or "")
    return (m[1], int(m[2])) if m else (None, None)


def buscar(pergunta, vetor, k):
    return selecionar(app.state.wv.collections.get("Trecho"), pergunta, vetor, k)


def selecionar(trecho, pergunta, vetor, k):
    """Busca híbrida e corte em k; também usada por 06_avaliar_busca.py."""
    res = trecho.query.hybrid(query=pergunta, vector=vetor, alpha=ALPHA, limit=k * 4)
    # keynotes são transmitidas em vários espaços: o mesmo resumo aparece repetido na grade
    vistos, unicos, por_palestra = set(), [], {}
    for o in res.objects:
        t = o.properties
        titulo = re.sub(r"\W", "", t["palestra_titulo"].lower())
        chave = (titulo, t["palestrantes"]) if t["fonte"] == "resumo" else t["texto"]
        # o limite vale para transcrições de uma palestra (título + horário, pois palestra_id
        # repete entre salas); resumo, bio e trecho fora da grade passam sempre
        palestra = (titulo, t["inicio"]) if t["fonte"] == "transcricao" and t["palestra_id"] else chave
        if chave not in vistos and por_palestra.get(palestra, 0) < MAX_POR_PALESTRA:
            vistos.add(chave)
            por_palestra[palestra] = por_palestra.get(palestra, 0) + 1
            unicos.append(t)
    return unicos[:k]


@app.post("/ask")
async def ask(q: Pergunta):
    if GERACOES.locked():
        raise HTTPException(429, "muitas perguntas ao mesmo tempo; tente de novo em instantes")
    async with GERACOES:
        return await responder(q)


async def responder(q):
    idioma = q.idioma or detectar_idioma(q.pergunta)
    try:
        trechos = await asyncio.to_thread(buscar, q.pergunta, await embed(q.pergunta), q.k)
    except Exception:
        log.exception("falha na busca")
        raise HTTPException(503, "busca indisponível") from None
    contexto = "\n\n".join(
        f"[{i}] {t['palestra_titulo']} | {t['palestrantes']} | fonte: {t['fonte']}\n{t['texto']}"
        for i, t in enumerate(trechos, 1))
    try:
        resposta = await gerar(INSTRUCOES[idioma], f"Trechos:\n{contexto}\n\nPergunta: {q.pergunta}\n\n{LEMBRETE[idioma]}")
        resposta = re.sub(r"<think>.*?</think>", "", resposta, flags=re.S).strip()
    except Exception:
        log.exception("falha no LLM")
        raise HTTPException(503, "gerador de respostas indisponível") from None
    # transcrições servem de contexto, mas não são devolvidas: só título, autor e link com tempo
    fontes = [{"n": i, "titulo": t["palestra_titulo"], "palestrantes": t["palestrantes"],
               "links_palestrantes": links(t.get("links_palestrantes")),
               "fonte": t["fonte"], "espaco": t["espaco"], "inicio": t["inicio"], "url": t["url"],
               "url_video": t.get("url_video") or None, "video_id": video(t.get("url_video"))[0],
               "video_t": video(t.get("url_video"))[1], "alinhamento": t["alinhamento"],
               "palestra_id": t["palestra_id"] or None,
               "inicio_video_s": t["inicio_video_s"] if t["video_id"] else None}
              for i, t in enumerate(trechos, 1)]
    return {"resposta": resposta, "idioma": idioma, "fontes": fontes}


@app.get("/health")
def health():
    return {"ok": app.state.wv.is_ready()}


@app.get("/")
def pagina():
    return FileResponse(Path(__file__).parent / "web" / "index.html")


if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("API_HOST", "0.0.0.0"), port=int(os.environ.get("API_PORT", 8765)))
