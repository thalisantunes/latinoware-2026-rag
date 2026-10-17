# latinoware-2026-rag

RAG (busca + geração de resposta) sobre as palestras e os palestrantes da
**Latinoware 2026**, o 23º Congresso Latino-americano de Software Livre e Tecnologias Abertas
(Foz do Iguaçu, 14 a 16 de outubro de 2026). Responde em **português, inglês e espanhol**: na
língua da pergunta ou na que você forçar.

Este repositório tem **só código e instruções**. Vídeos, áudios, transcrições e índices não são
distribuídos (veja [`data/README.md`](data/README.md)); você os reconstrói a partir das fontes
públicas.

> **English.** RAG over the talks and speakers of Latinoware 2026 (Foz do Iguaçu, Brazil,
> Oct 14–16, 2026). Scrapes the public schedule and speaker pages from latinoware.org,
> transcribes the YouTube recordings with faster-whisper on a local GPU, stores chunks in
> Weaviate (hybrid BM25 + vector search, bge-m3 embeddings) and answers with a local LLM via
> Ollama, in the language of the question (pt/en/es) or a forced one. Code only: no videos,
> transcripts or indexes are redistributed. Run `make tudo`, then `make api`.
>
> **Español.** RAG sobre las charlas y ponentes de Latinoware 2026 (Foz do Iguaçu, Brasil, 14
> al 16 de octubre de 2026). Extrae la programación y los ponentes de latinoware.org, transcribe
> las grabaciones de YouTube con faster-whisper en GPU local, guarda los fragmentos en Weaviate
> (búsqueda híbrida BM25 + vectores, embeddings bge-m3) y responde con un LLM local vía Ollama,
> en el idioma de la pregunta (pt/en/es) o en uno forzado. Solo código: no se redistribuyen
> videos, transcripciones ni índices. Ejecuta `make tudo` y luego `make api`.

## Como funciona

```
latinoware.org ──01──> grade (236 atividades) + palestrantes (168)  ─┐
YouTube (lives) ─02──> áudio m4a ─03──> transcrição com timestamps ─┼─04──> Weaviate
                                                                     │       (Palestra, Palestrante, Trecho)
pergunta ──05──> embedding bge-m3 ──> busca híbrida em Trecho ──> LLM (Ollama) ──> resposta + fontes
```

| Etapa | Script | O que faz |
|---|---|---|
| 1 | `01_coletar_site.py` | Grade (plugin SWGE do site), detalhe de cada atividade e palestrantes (API do WordPress). Só dados públicos; nada de e-mail ou telefone. |
| 2 | `02_baixar_audio.py` | Acha as lives "Latinoware 2026 - Espaço X - DD/10" (canal Itaipu Parquetec) e baixa só o áudio. |
| 3 | `03_transcrever.py` | faster-whisper `large-v3-turbo` na GPU, VAD, idioma detectado por segmento (as lives misturam pt/es/en). |
| 4 | `04_indexar.py` | Corta cada live por palestra usando a grade, gera pedaços de ~350 palavras com sobreposição de 60, embeddings bge-m3 e carrega no Weaviate. |
| 5 | `05_api.py` | API FastAPI `POST /ask` e a página `web/index.html`. |
| 6 | `06_avaliar_busca.py` | Recall da busca com 10 perguntas-gabarito em pt/en/es. |

Decisões:

- **Embeddings bge-m3 via Ollama.** Modelo multilíngue (pt/en/es no mesmo espaço vetorial),
  então uma pergunta em inglês acha um trecho em português. Pelo Ollama, a API e o indexador
  usam o mesmo servidor e o projeto não precisa de PyTorch.
- **Vetores fornecidos pelo pipeline** (Weaviate sem módulo de vetorização) e **busca híbrida**
  (BM25 + vetor, `HYBRID_ALPHA=0.75`). Nomes próprios e siglas vêm do BM25; paráfrases e
  outras línguas, do vetor.
- **Alinhamento live → palestra.** Cada live cobre um dia inteiro de um espaço. O instante do
  vídeo vira hora do dia a partir do início da live, tirado nesta ordem: `alinhamento.json`
  (manual, `{"<video_id>": "2026-10-14T08:57:00-03:00"}`; sem fuso, vale o de Brasília),
  `release_timestamp` do YouTube, ou o início da primeira atividade do espaço no dia (marcado
  `alinhamento: estimado`, e a página mostra "horário estimado"). Se o espaço tem duas lives no
  mesmo dia sem início conhecido, os trechos ficam sem palestra atribuída.
- **Resposta** com `qwen3:14b` local, temperatura 0,2, só com base nos trechos, citando `[n]`.

## Requisitos

- Linux com GPU NVIDIA de **≥ 12 GB de VRAM** (testado em RTX 5060 Ti 16 GB, driver 595).
  Whisper, embeddings e LLM rodam **em sequência**, não ao mesmo tempo.
- **cuBLAS do CUDA 12** (`libcublas.so.12`) visível no sistema, exigido pelo CTranslate2 do
  faster-whisper. Sem ele: `uv pip install nvidia-cublas-cu12` e aponte `LD_LIBRARY_PATH` para
  `.venv/lib/python3.12/site-packages/nvidia/cublas/lib`. Nos testes, o cuDNN não foi necessário.
- Docker com Compose (Weaviate), [Ollama](https://ollama.com) e [uv](https://docs.astral.sh/uv/).
- Node.js no PATH (o yt-dlp usa para o YouTube) e ffmpeg.
- Disco: ~10 GB para os áudios (122 h de lives) e alguns GB para modelos.

```bash
ollama pull bge-m3
ollama pull qwen3:14b
uv sync                 # cria .venv com Python 3.12 e versões travadas em uv.lock
cp .env.example .env    # ajuste portas e modelos se precisar
```

## Uso

```bash
make weaviate     # sobe o Weaviate em 127.0.0.1:18080 (gRPC 15051)
make coletar      # ~10 min (respeita pausa entre requisições)
make audio        # depende da rede; veja "YouTube pedindo login"
make transcrever  # estimativa: 2 a 4 h para as 122 h de áudio [não medido]
make indexar      # ~1 min sem transcrições; alguns minutos com
make api          # http://localhost:8765 (página + API)
make avaliar      # recall@8 das 10 perguntas-gabarito
make testar       # testes; os de integração precisam da API no ar
```

Pergunta pela API:

```bash
curl -s localhost:8765/ask -H 'Content-Type: application/json' \
  -d '{"pergunta": "Who talked about Home Assistant?", "k": 8}'
# {"resposta": "...", "idioma": "en", "fontes": [{"n": 1, "titulo": ..., "url": ...}]}
```

`idioma` (`pt`, `en` ou `es`) força a língua da resposta e `k` (1 a 12) é o número de trechos.
As fontes trazem título, palestrante e link (com `&t=` quando vêm de vídeo), mas não o texto
das transcrições.

Para usar um provedor externo compatível com a API OpenAI em vez do Ollama, defina juntos
`LLM_API_KEY`, `LLM_BASE_URL` e `LLM_MODEL` no `.env`, sem aspas (nunca commite o `.env`).
Nesse modo, **as perguntas e os trechos recuperados são enviados ao provedor**. O `.env` é lido
pelo `make`; rodando os scripts direto, use `uv run --env-file .env python 05_api.py`.

A API aceita até `MAX_CONCORRENCIA` gerações simultâneas (padrão 2) e responde 429 acima
disso. Exposta na internet, ponha também um limite por IP no proxy (Cloudflare, nginx).

### YouTube pedindo login

Em alguns IPs o YouTube responde "Sign in to confirm you're not a bot" e o yt-dlp não baixa
nada. O yt-dlp aceita um `cookies.txt` (formato Netscape) exportado de um navegador logado.
Baixar vídeos pode contrariar os Termos de Serviço do YouTube e uma conta usada assim pode ser
bloqueada: avalie, e faça por sua conta e risco.

```bash
YTDLP_COOKIES=/caminho/cookies.txt make audio
```

Sem cookies, `02_baixar_audio.py` salva só os metadados das lives, e a RAG funciona com os
resumos das palestras e as bios dos palestrantes.

## Estado dos dados (17/10/2026)

- Grade: 236 atividades (229 distintas; keynotes repetem em vários espaços), todas com resumo.
  Idiomas declarados: 208 em português, 24 em inglês, 4 em espanhol.
- Palestrantes: 168 páginas públicas.
- Gravações: 17 lives no canal Itaipu Parquetec (122 h), dos espaços Brasil, Paraguai, Iguaçu,
  Bolívia, Peru e Haiti. Não há gravação dos espaços Equador, Argentina, Uruguai, Chile e das
  oficinas. Não há live do Espaço Brasil em 16/10.
- **Transcrições: pendentes.** Daqui, o YouTube pediu login para baixar o áudio. O índice
  publicado em https://ilove.the.br/latinoware/2026/rag cobre por enquanto resumos e
  palestrantes.

## Aviso legal

Projeto pessoal, sem fins lucrativos e **não oficial**: não tem relação com a organização da
Latinoware nem com o Itaipu Parquetec. Usa só informações públicas. As transcrições servem de
contexto para a busca e não são publicadas nem devolvidas pela API. Palestrante que quiser
remover seus dados ou uma palestra do índice pode abrir uma
[issue](https://github.com/thalisantunes/latinoware-2026-rag/issues). Quem roda o pipeline
responde pelo uso das fontes, incluindo os termos do YouTube.

## Hospedagem

`web/index.html` é estático, sem build. A URL da API fica na constante `API_URL` no topo do
arquivo; servido em `localhost`, ele usa a própria origem. A API escuta em `0.0.0.0:8765` e
aceita CORS das origens em `CORS_ORIGINS`.

## Licença

Código sob [MIT](LICENSE). O conteúdo das palestras pertence aos palestrantes e à organização
da Latinoware.
