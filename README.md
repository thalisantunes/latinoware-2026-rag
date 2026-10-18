# latinoware-2026-rag

**[English](#english) · [Español](#español) · [Português](#português)**

---

## English

RAG (retrieval + answer generation) over the talks and speakers of **Latinoware 2026**, the
23rd Latin American Congress of Free Software and Open Technologies (Foz do Iguaçu, Brazil,
October 14–16, 2026). It answers in **English, Spanish and Portuguese**: in the language of the
question, or in one you force.

Live at https://ilove.the.br/latinoware/2026/rag/.

This repository contains **code and instructions only**. Videos, audio, transcripts and indexes
are not distributed (see [`data/README.md`](data/README.md)); you rebuild them from the public
sources.

### How it works

```
latinoware.org ──01──> schedule (236 activities) + speakers (168)  ─┐
YouTube (lives) ─02──> m4a audio ─03──> timestamped transcript      ─┼─04──> Weaviate
                                                                     │       (Palestra, Palestrante, Trecho)
question ──05──> bge-m3 embedding ──> hybrid search on Trecho ──> LLM (Ollama) ──> answer + sources
```

| Step | Script | What it does |
|---|---|---|
| 1 | `01_coletar_site.py` | Schedule (the site's SWGE plugin), each activity's details and speakers (WordPress API). Public data only; no e-mails or phone numbers. |
| 2 | `02_baixar_audio.py` | Finds the "Latinoware 2026 - Espaço X - DD/10" lives (Itaipu Parquetec channel) and downloads audio only. |
| 3 | `03_transcrever.py` | faster-whisper `large-v3-turbo` on the GPU, VAD, language detected per segment (lives mix pt/es/en). |
| 4 | `04_indexar.py` | Splits each live by talk using the schedule, builds ~350-word chunks with 60-word overlap, bge-m3 embeddings, loads into Weaviate. |
| 5 | `05_api.py` | FastAPI `POST /ask` and the `web/index.html` page. |
| 6 | `06_avaliar_busca.py` | Search recall on 10 reference questions in pt/en/es. |

Design decisions:

- **bge-m3 embeddings via Ollama.** Multilingual model (pt/en/es in the same vector space), so
  an English question finds a Portuguese excerpt. Through Ollama, API and indexer share the same
  server and the project needs no PyTorch.
- **Vectors provided by the pipeline** (Weaviate without a vectorizer module) and **hybrid
  search** (BM25 + vector, `HYBRID_ALPHA=0.75`). Proper names and acronyms come from BM25;
  paraphrases and other languages from the vector.
- **Live → talk alignment.** Each live covers a whole day of one room. A video instant becomes
  time of day from the live's start, taken in this order: `alinhamento.json` (manual,
  `{"<video_id>": "2026-10-14T08:57:00-03:00"}`; without offset, Brasília time), YouTube's
  `release_timestamp`, or the start of the room's first activity that day (marked
  `alinhamento: estimado`; the page shows "horário estimado"). If a room has two lives on the
  same day with no known start, their chunks get no talk assigned.
- **Answer** with local `qwen3:14b`, temperature 0.2, grounded only on the chunks, citing `[n]`.

### Requirements

- Linux with an NVIDIA GPU with **≥ 12 GB VRAM** (tested on RTX 5060 Ti 16 GB, driver 595).
  Whisper, embeddings and LLM run **in sequence**, not at the same time.
- **CUDA 12 cuBLAS** (`libcublas.so.12`) visible on the system, required by faster-whisper's
  CTranslate2. Without it: `uv pip install nvidia-cublas-cu12` and point `LD_LIBRARY_PATH` to
  `.venv/lib/python3.12/site-packages/nvidia/cublas/lib`. cuDNN was not needed in our tests.
- Docker with Compose (Weaviate), [Ollama](https://ollama.com) and [uv](https://docs.astral.sh/uv/).
- ffmpeg. yt-dlp needs a JavaScript runtime for YouTube: `uv sync` installs Deno in `.venv`
  (Node.js works too, if it is 22 or newer).
- Disk: ~10 GB for audio (122 h of lives) and a few GB for models.

```bash
ollama pull bge-m3
ollama pull qwen3:14b
uv sync                 # creates .venv with Python 3.12 and versions pinned in uv.lock
cp .env.example .env    # adjust ports and models if needed
```

### Usage

```bash
make weaviate     # starts Weaviate on 127.0.0.1:18080 (gRPC 15051)
make coletar      # ~10 min (pauses between requests)
make audio        # network-dependent; see "YouTube asking for sign-in"
make transcrever  # estimate: 2 to 4 h for 122 h of audio [not measured]
make indexar      # ~1 min without transcripts; a few minutes with them
make api          # http://localhost:8765 (page + API)
make avaliar      # recall@8 on the 10 reference questions
make testar       # tests; integration tests need the API running
```

API call:

```bash
curl -s localhost:8765/ask -H 'Content-Type: application/json' \
  -d '{"pergunta": "Who talked about Home Assistant?", "k": 8}'
# {"resposta": "...", "idioma": "en", "fontes": [{"n": 1, "titulo": ..., "url": ...}]}
```

`idioma` (`pt`, `en` or `es`) forces the answer language and `k` (1 to 12) is the number of
chunks. Sources carry title, speaker and link (with `&t=` when from a video), never transcript
text.

To use an external OpenAI-compatible provider instead of Ollama, set `LLM_API_KEY`,
`LLM_BASE_URL` and `LLM_MODEL` together in `.env`, unquoted (never commit `.env`). In this mode
**questions and retrieved chunks are sent to the provider**. `make` reads `.env`; running the
scripts directly, use `uv run --env-file .env python 05_api.py`.

To keep the API up across reboots, use a `systemd --user` unit
(`~/.config/systemd/user/latinoware-rag-api.service`, adjusting paths):

```ini
[Unit]
Description=Latinoware 2026 RAG - API (port 8765)
After=network-online.target ollama.service

[Service]
WorkingDirectory=/path/latinoware-2026-rag
EnvironmentFile=-/path/latinoware-2026-rag/.env
ExecStart=/path/latinoware-2026-rag/.venv/bin/python /path/latinoware-2026-rag/05_api.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now latinoware-rag-api
loginctl enable-linger "$USER"   # start at boot without login
```

Weaviate comes back on its own with Docker (`restart: unless-stopped`).

The API accepts up to `MAX_CONCORRENCIA` simultaneous generations (default 2) and answers 429
beyond that. If exposed to the internet, also add a per-IP limit at the proxy (Cloudflare,
nginx).

#### YouTube asking for sign-in

From some IPs YouTube answers "Sign in to confirm you're not a bot" and yt-dlp downloads
nothing. yt-dlp can read the cookies of a logged-in browser on the same machine
(`YTDLP_COOKIES_BROWSER=chrome`, or `chrome:Profile`, `firefox`...; close YouTube tabs first, or
YouTube rotates the cookies) or a `cookies.txt` (Netscape format) in `YTDLP_COOKIES`.
Downloading videos may breach YouTube's Terms of Service and an account used this way may be
blocked: weigh it, and do it at your own risk.

```bash
YTDLP_COOKIES_BROWSER=chrome make audio
```

Without cookies, `02_baixar_audio.py` saves only the lives' metadata, and the RAG works from
talk abstracts and speaker bios.

### Data status (Oct 17, 2026)

- Schedule: 236 activities (229 distinct; keynotes repeat across rooms), all with an abstract.
  Declared languages: 208 Portuguese, 24 English, 4 Spanish.
- Speakers: 168 public pages.
- Recordings: 17 lives on the Itaipu Parquetec channel (122 h), from the Brasil, Paraguai,
  Iguaçu, Bolívia, Peru and Haiti rooms. No recordings of the Equador, Argentina, Uruguai and
  Chile rooms or the workshops. No Espaço Brasil live on Oct 16.
- Transcripts: 17/17 lives (118 h of audio, about 559k words) with faster-whisper
  large-v3-turbo. Live start times come from YouTube, so excerpts link to the right moment.
  The Espaço Iguaçu lives are mostly waiting music: 3 of them yielded almost no speech.
- Index: 2293 excerpts (236 abstracts, 168 bios, 1889 from transcripts; 89 of these fall
  outside the schedule). Search recall@8 = 9/10.

### Legal notice

Personal, non-profit and **unofficial** project: not affiliated with the Latinoware organizers
or with Itaipu Parquetec. It uses public information only. Transcripts serve as search context
and are neither published nor returned by the API. Speakers who want their data or a talk
removed from the index can open an
[issue](https://github.com/thalisantunes/latinoware-2026-rag/issues). Whoever runs the pipeline
is responsible for how the sources are used, including YouTube's terms.

### Hosting

`web/index.html` is static, no build. The API URL is the `API_URL` constant at the top of the
file; served from `localhost`, it uses its own origin. The API listens on `0.0.0.0:8765` and
accepts CORS from the origins in `CORS_ORIGINS`.

### License

Code under [MIT](LICENSE). Talk content belongs to the speakers and the Latinoware organizers.

---

## Español

RAG (búsqueda + generación de respuestas) sobre las charlas y los ponentes de **Latinoware
2026**, el 23º Congreso Latinoamericano de Software Libre y Tecnologías Abiertas (Foz do Iguaçu,
Brasil, 14 al 16 de octubre de 2026). Responde en **inglés, español y portugués**: en el idioma
de la pregunta o en el que fuerces.

En línea en https://ilove.the.br/latinoware/2026/rag/.

Este repositorio tiene **solo código e instrucciones**. No se distribuyen videos, audios,
transcripciones ni índices (ver [`data/README.md`](data/README.md)); se reconstruyen a partir de
las fuentes públicas.

### Cómo funciona

```
latinoware.org ──01──> programación (236 actividades) + ponentes (168)  ─┐
YouTube (lives) ─02──> audio m4a ─03──> transcripción con timestamps     ─┼─04──> Weaviate
                                                                          │       (Palestra, Palestrante, Trecho)
pregunta ──05──> embedding bge-m3 ──> búsqueda híbrida en Trecho ──> LLM (Ollama) ──> respuesta + fuentes
```

| Paso | Script | Qué hace |
|---|---|---|
| 1 | `01_coletar_site.py` | Programación (plugin SWGE del sitio), detalle de cada actividad y ponentes (API de WordPress). Solo datos públicos; sin correos ni teléfonos. |
| 2 | `02_baixar_audio.py` | Encuentra las lives "Latinoware 2026 - Espaço X - DD/10" (canal Itaipu Parquetec) y descarga solo el audio. |
| 3 | `03_transcrever.py` | faster-whisper `large-v3-turbo` en la GPU, VAD, idioma detectado por segmento (las lives mezclan pt/es/en). |
| 4 | `04_indexar.py` | Corta cada live por charla según la programación, genera fragmentos de ~350 palabras con solapamiento de 60, embeddings bge-m3 y los carga en Weaviate. |
| 5 | `05_api.py` | API FastAPI `POST /ask` y la página `web/index.html`. |
| 6 | `06_avaliar_busca.py` | Recall de la búsqueda con 10 preguntas de referencia en pt/en/es. |

Decisiones:

- **Embeddings bge-m3 vía Ollama.** Modelo multilingüe (pt/en/es en el mismo espacio
  vectorial): una pregunta en español encuentra un fragmento en portugués. Con Ollama, la API y
  el indexador usan el mismo servidor y el proyecto no necesita PyTorch.
- **Vectores provistos por el pipeline** (Weaviate sin módulo de vectorización) y **búsqueda
  híbrida** (BM25 + vector, `HYBRID_ALPHA=0.75`). Nombres propios y siglas vienen del BM25;
  paráfrasis y otros idiomas, del vector.
- **Alineación live → charla.** Cada live cubre un día entero de un espacio. El instante del
  video se convierte en hora del día a partir del inicio de la live, tomado en este orden:
  `alinhamento.json` (manual, `{"<video_id>": "2026-10-14T08:57:00-03:00"}`; sin zona horaria,
  vale la de Brasilia), `release_timestamp` de YouTube, o el inicio de la primera actividad del
  espacio en el día (marcado `alinhamento: estimado`; la página muestra "horário estimado"). Si
  un espacio tiene dos lives el mismo día sin inicio conocido, sus fragmentos quedan sin charla
  asignada.
- **Respuesta** con `qwen3:14b` local, temperatura 0,2, basada solo en los fragmentos, citando
  `[n]`.

### Requisitos

- Linux con GPU NVIDIA de **≥ 12 GB de VRAM** (probado en RTX 5060 Ti 16 GB, driver 595).
  Whisper, embeddings y LLM corren **en secuencia**, no a la vez.
- **cuBLAS de CUDA 12** (`libcublas.so.12`) visible en el sistema, exigido por el CTranslate2
  de faster-whisper. Sin él: `uv pip install nvidia-cublas-cu12` y apunta `LD_LIBRARY_PATH` a
  `.venv/lib/python3.12/site-packages/nvidia/cublas/lib`. En las pruebas no hizo falta cuDNN.
- Docker con Compose (Weaviate), [Ollama](https://ollama.com) y [uv](https://docs.astral.sh/uv/).
- ffmpeg. yt-dlp necesita un runtime JavaScript para YouTube: `uv sync` instala Deno en `.venv`
  (Node.js también sirve, si es 22 o más nuevo).
- Disco: ~10 GB para los audios (122 h de lives) y algunos GB para modelos.

```bash
ollama pull bge-m3
ollama pull qwen3:14b
uv sync                 # crea .venv con Python 3.12 y versiones fijadas en uv.lock
cp .env.example .env    # ajusta puertos y modelos si hace falta
```

### Uso

```bash
make weaviate     # levanta Weaviate en 127.0.0.1:18080 (gRPC 15051)
make coletar      # ~10 min (pausa entre peticiones)
make audio        # depende de la red; ver "YouTube pidiendo inicio de sesión"
make transcrever  # estimación: 2 a 4 h para 122 h de audio [no medido]
make indexar      # ~1 min sin transcripciones; unos minutos con ellas
make api          # http://localhost:8765 (página + API)
make avaliar      # recall@8 de las 10 preguntas de referencia
make testar       # pruebas; las de integración necesitan la API activa
```

Pregunta por la API:

```bash
curl -s localhost:8765/ask -H 'Content-Type: application/json' \
  -d '{"pergunta": "¿Quién habló de Home Assistant?", "k": 8}'
# {"resposta": "...", "idioma": "es", "fontes": [{"n": 1, "titulo": ..., "url": ...}]}
```

`idioma` (`pt`, `en` o `es`) fuerza el idioma de la respuesta y `k` (1 a 12) es el número de
fragmentos. Las fuentes traen título, ponente y enlace (con `&t=` cuando vienen de video), nunca
el texto de las transcripciones.

Para usar un proveedor externo compatible con la API de OpenAI en lugar de Ollama, define juntos
`LLM_API_KEY`, `LLM_BASE_URL` y `LLM_MODEL` en el `.env`, sin comillas (nunca subas el `.env`).
En ese modo **las preguntas y los fragmentos recuperados se envían al proveedor**. `make` lee el
`.env`; corriendo los scripts directamente, usa `uv run --env-file .env python 05_api.py`.

Para mantener la API activa entre reinicios, usa una unit `systemd --user`
(`~/.config/systemd/user/latinoware-rag-api.service`, ajustando las rutas):

```ini
[Unit]
Description=Latinoware 2026 RAG - API (puerto 8765)
After=network-online.target ollama.service

[Service]
WorkingDirectory=/ruta/latinoware-2026-rag
EnvironmentFile=-/ruta/latinoware-2026-rag/.env
ExecStart=/ruta/latinoware-2026-rag/.venv/bin/python /ruta/latinoware-2026-rag/05_api.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now latinoware-rag-api
loginctl enable-linger "$USER"   # para arrancar en el boot sin login
```

Weaviate vuelve solo con Docker (`restart: unless-stopped`).

La API acepta hasta `MAX_CONCORRENCIA` generaciones simultáneas (por defecto 2) y responde 429
por encima de eso. Expuesta a internet, pon también un límite por IP en el proxy (Cloudflare,
nginx).

#### YouTube pidiendo inicio de sesión

Desde algunas IPs YouTube responde "Sign in to confirm you're not a bot" y yt-dlp no descarga
nada. yt-dlp puede leer las cookies de un navegador con sesión iniciada en la misma máquina
(`YTDLP_COOKIES_BROWSER=chrome`, o `chrome:Perfil`, `firefox`...; cierra antes las pestañas de
YouTube, o YouTube rota las cookies) o un `cookies.txt` (formato Netscape) en `YTDLP_COOKIES`. Descargar videos puede contrariar los Términos de Servicio de YouTube y una cuenta
usada así puede ser bloqueada: evalúalo, y hazlo bajo tu propio riesgo.

```bash
YTDLP_COOKIES_BROWSER=chrome make audio
```

Sin cookies, `02_baixar_audio.py` guarda solo los metadatos de las lives, y la RAG funciona con
los resúmenes de las charlas y las biografías de los ponentes.

### Estado de los datos (17/10/2026)

- Programación: 236 actividades (229 distintas; las keynotes se repiten en varios espacios),
  todas con resumen. Idiomas declarados: 208 en portugués, 24 en inglés, 4 en español.
- Ponentes: 168 páginas públicas.
- Grabaciones: 17 lives en el canal Itaipu Parquetec (122 h), de los espacios Brasil, Paraguai,
  Iguaçu, Bolívia, Peru y Haiti. No hay grabación de los espacios Equador, Argentina, Uruguai,
  Chile ni de los talleres. No hay live del Espaço Brasil el 16/10.
- Transcripciones: 17/17 lives (118 h de audio, unas 559 mil palabras) con faster-whisper
  large-v3-turbo. El inicio de cada live viene de YouTube, así que los fragmentos enlazan al
  momento correcto. Las lives del Espaço Iguaçu son casi todo música de espera: 3 de ellas
  casi no tienen habla.
- Índice: 2293 fragmentos (236 resúmenes, 168 bios, 1889 de transcripciones; 89 de ellos fuera
  de la programación). recall@8 de la búsqueda = 9/10.

### Aviso legal

Proyecto personal, sin fines de lucro y **no oficial**: no tiene relación con la organización
de Latinoware ni con Itaipu Parquetec. Usa solo información pública. Las transcripciones sirven
de contexto para la búsqueda y la API no las publica ni las devuelve. Un ponente que quiera
retirar sus datos o una charla del índice puede abrir un
[issue](https://github.com/thalisantunes/latinoware-2026-rag/issues). Quien ejecuta el pipeline
responde por el uso de las fuentes, incluidos los términos de YouTube.

### Alojamiento

`web/index.html` es estático, sin build. La URL de la API está en la constante `API_URL` al
inicio del archivo; servido desde `localhost`, usa su propio origen. La API escucha en
`0.0.0.0:8765` y acepta CORS de los orígenes en `CORS_ORIGINS`.

### Licencia

Código bajo [MIT](LICENSE). El contenido de las charlas pertenece a los ponentes y a la
organización de Latinoware.

---

## Português

RAG (busca + geração de resposta) sobre as palestras e os palestrantes da **Latinoware 2026**,
o 23º Congresso Latino-americano de Software Livre e Tecnologias Abertas (Foz do Iguaçu, 14 a 16
de outubro de 2026). Responde em **inglês, espanhol e português**: na língua da pergunta ou na
que você forçar.

No ar em https://ilove.the.br/latinoware/2026/rag/.

Este repositório tem **só código e instruções**. Vídeos, áudios, transcrições e índices não são
distribuídos (veja [`data/README.md`](data/README.md)); você os reconstrói a partir das fontes
públicas.

### Como funciona

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

### Requisitos

- Linux com GPU NVIDIA de **≥ 12 GB de VRAM** (testado em RTX 5060 Ti 16 GB, driver 595).
  Whisper, embeddings e LLM rodam **em sequência**, não ao mesmo tempo.
- **cuBLAS do CUDA 12** (`libcublas.so.12`) visível no sistema, exigido pelo CTranslate2 do
  faster-whisper. Sem ele: `uv pip install nvidia-cublas-cu12` e aponte `LD_LIBRARY_PATH` para
  `.venv/lib/python3.12/site-packages/nvidia/cublas/lib`. Nos testes, o cuDNN não foi necessário.
- Docker com Compose (Weaviate), [Ollama](https://ollama.com) e [uv](https://docs.astral.sh/uv/).
- ffmpeg. O yt-dlp precisa de um runtime JavaScript para o YouTube: o `uv sync` instala o Deno
  no `.venv` (Node.js também serve, se for 22 ou mais novo).
- Disco: ~10 GB para os áudios (122 h de lives) e alguns GB para modelos.

```bash
ollama pull bge-m3
ollama pull qwen3:14b
uv sync                 # cria .venv com Python 3.12 e versões travadas em uv.lock
cp .env.example .env    # ajuste portas e modelos se precisar
```

### Uso

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
  -d '{"pergunta": "Quem falou sobre Home Assistant?", "k": 8}'
# {"resposta": "...", "idioma": "pt", "fontes": [{"n": 1, "titulo": ..., "url": ...}]}
```

`idioma` (`pt`, `en` ou `es`) força a língua da resposta e `k` (1 a 12) é o número de trechos.
As fontes trazem título, palestrante e link (com `&t=` quando vêm de vídeo), mas não o texto
das transcrições.

Para usar um provedor externo compatível com a API OpenAI em vez do Ollama, defina juntos
`LLM_API_KEY`, `LLM_BASE_URL` e `LLM_MODEL` no `.env`, sem aspas (nunca commite o `.env`).
Nesse modo, **as perguntas e os trechos recuperados são enviados ao provedor**. O `.env` é lido
pelo `make`; rodando os scripts direto, use `uv run --env-file .env python 05_api.py`.

Para manter a API no ar entre reinícios, use uma unit `systemd --user`
(`~/.config/systemd/user/latinoware-rag-api.service`, ajustando os caminhos):

```ini
[Unit]
Description=Latinoware 2026 RAG - API (porta 8765)
After=network-online.target ollama.service

[Service]
WorkingDirectory=/caminho/latinoware-2026-rag
EnvironmentFile=-/caminho/latinoware-2026-rag/.env
ExecStart=/caminho/latinoware-2026-rag/.venv/bin/python /caminho/latinoware-2026-rag/05_api.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now latinoware-rag-api
loginctl enable-linger "$USER"   # para subir no boot sem login
```

O Weaviate volta sozinho com o Docker (`restart: unless-stopped`).

A API aceita até `MAX_CONCORRENCIA` gerações simultâneas (padrão 2) e responde 429 acima
disso. Exposta na internet, ponha também um limite por IP no proxy (Cloudflare, nginx).

#### YouTube pedindo login

Em alguns IPs o YouTube responde "Sign in to confirm you're not a bot" e o yt-dlp não baixa
nada. O yt-dlp lê os cookies de um navegador logado na mesma máquina
(`YTDLP_COOKIES_BROWSER=chrome`, ou `chrome:Perfil`, `firefox`...; feche antes as abas do
YouTube, senão ele troca os cookies) ou um `cookies.txt` (formato Netscape) em `YTDLP_COOKIES`.
Baixar vídeos pode contrariar os Termos de Serviço do YouTube e uma conta usada assim pode ser
bloqueada: avalie, e faça por sua conta e risco.

```bash
YTDLP_COOKIES_BROWSER=chrome make audio
```

Sem cookies, `02_baixar_audio.py` salva só os metadados das lives, e a RAG funciona com os
resumos das palestras e as bios dos palestrantes.

### Estado dos dados (17/10/2026)

- Grade: 236 atividades (229 distintas; keynotes repetem em vários espaços), todas com resumo.
  Idiomas declarados: 208 em português, 24 em inglês, 4 em espanhol.
- Palestrantes: 168 páginas públicas.
- Gravações: 17 lives no canal Itaipu Parquetec (122 h), dos espaços Brasil, Paraguai, Iguaçu,
  Bolívia, Peru e Haiti. Não há gravação dos espaços Equador, Argentina, Uruguai e Chile nem das
  oficinas. Não há live do Espaço Brasil em 16/10.
- Transcrições: 17/17 lives (118 h de áudio, cerca de 559 mil palavras) com faster-whisper
  large-v3-turbo. O início de cada live vem do YouTube, então os trechos levam ao instante
  certo. As lives do Espaço Iguaçu são quase só música de espera: 3 delas quase não têm fala.
- Índice: 2293 trechos (236 resumos, 168 bios, 1889 de transcrições; 89 destes fora da grade).
  recall@8 da busca = 9/10.

### Aviso legal

Projeto pessoal, sem fins lucrativos e **não oficial**: não tem relação com a organização da
Latinoware nem com o Itaipu Parquetec. Usa só informações públicas. As transcrições servem de
contexto para a busca e não são publicadas nem devolvidas pela API. Palestrante que quiser
remover seus dados ou uma palestra do índice pode abrir uma
[issue](https://github.com/thalisantunes/latinoware-2026-rag/issues). Quem roda o pipeline
responde pelo uso das fontes, incluindo os termos do YouTube.

### Hospedagem

`web/index.html` é estático, sem build. A URL da API fica na constante `API_URL` no topo do
arquivo; servido em `localhost`, ele usa a própria origem. A API escuta em `0.0.0.0:8765` e
aceita CORS das origens em `CORS_ORIGINS`.

### Licença

Código sob [MIT](LICENSE). O conteúdo das palestras pertence aos palestrantes e à organização
da Latinoware.
