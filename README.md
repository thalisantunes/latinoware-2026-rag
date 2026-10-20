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
| 6 | `06_avaliar_busca.py` | Search recall on the reference questions (10 fixed in pt/en/es + checked extras); fails below 100%. |

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
- **Optional reranking** of the 32 candidates with `bge-reranker-v2-m3` on the GPU (~0.25 s): `uv sync --extra
  rerank` (always with `--extra rerank`, or a plain `uv sync` removes it) and `RERANK_LOCAL=BAAI/bge-reranker-v2-m3` in `.env`.
- **Answer** with local `gemma4:12b-it-qat`, temperature 0.2, grounded only on the chunks, citing `[n]`
  (chosen by benchmark against qwen3:14b, qwen3.5 and ministral-3: `docs/benchmark-modelos.md`).
- **Question history**: questions and answers are kept for 90 days in a `Pergunta` collection (no IP, no user
  agent) and deleted automatically after that. An identical question (bge-m3 distance ≤ 0.05, same model and index)
  reuses the stored answer, with a "Generate again" button; `/frequentes` lists only questions from a hand-curated list
  (`data/frequentes_aprovadas.json`), since the text typed by visitors becomes public.
- **Usage metrics**: `GET /stats?dias=7` returns anonymous daily counts (Brasília days) (language, reused answers, no-answer, 429,
  errors, p50/p95), one line per question in `data/metricas/` without the question text or IP, kept 90 days;
  `make metricas` appends the weekly line to `STATUS.md`, and `make instalar-timer` schedules it every Monday at
  08:00 (systemd user timer, templates in `deploy/systemd/`; needs `loginctl enable-linger` to run without a session).

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
ollama pull gemma4:12b-it-qat
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
make avaliar      # recall@8 on the reference questions; fails below 100% (also runs after make indexar)
make reverter-indice     # point the aliases back to the previous index version (reindex has no downtime)
make gabarito-candidatos  # suggestions from the history; add only the checked ones to data/gabarito_extra.json, then delete the candidates file
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

**Search-only mode** (to free the GPU): `make sem-ia` creates the flag file `data/sem-ia` and unloads the model;
`make com-ia` removes it. While it exists, `/ask`, `/ask/stream` and the MCP tool answer with the most relevant
talks and the `?t=` video links, no generated text (`"sem_ia": true`, and `resposta` holds the notice "AI summary
unavailable right now; see the most relevant talks."), and the page shows the same notice. Already-saved answers are
still served. `LLM_KEEP_ALIVE` (default `10m`) unloads the model from the GPU after it idles.
To generate on another Ollama in the local network, set `OLLAMA_GERACAO_URL` (embedding stays on `OLLAMA_URL`); if it
stops answering, the API falls back to search-only by itself. The URL goes in a file outside the repo, loaded by
systemd with a second `EnvironmentFile=`. That Ollama has no authentication: private network only.

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

### Data status (Oct 18, 2026)

- Schedule: 236 activities (229 distinct; keynotes repeat across rooms), all with an abstract.
  Declared languages: 208 Portuguese, 24 English, 4 Spanish.
- Speakers: 168 public pages.
- Recordings: 17 lives on the Itaipu Parquetec channel (122 h), from the Brasil, Paraguai,
  Iguaçu, Bolívia, Peru and Haiti rooms. No recordings of the Equador, Argentina, Uruguai and
  Chile rooms or the workshops. No Espaço Brasil live on Oct 16.
- Transcripts: 17/17 lives (118 h of audio, about 559k words) with faster-whisper
  large-v3-turbo. Live start times come from YouTube, so excerpts link to the right moment.
  The Espaço Iguaçu lives are mostly waiting music: 3 of them yielded almost no speech.
- Index: 2296 excerpts (236 abstracts, 168 bios, 1892 from transcripts; 93 of these fall
  outside the schedule). Search recall@8 = 10/10.
- Talks with video: 63 of 236. A talk counts as recorded only when the transcript has speech in its window
  (keynotes are listed in every room, but only some lives carried the audio); start times are read from the
  transcript. Three more Espaço Iguaçu lives are blocked on YouTube by a content claim and one is private:
  `make novos-videos VIDEOS="<ids>"` ingests them when released.

### Speaker photos

`make fotos PASTA=<originals> ALBUM=<Flickr album URL>` registers the original photos sent by the organizers
(author and licence per album in `data/fotos/albuns.json`), links them to their Flickr pages through the album's
public feed (no API key; Flickr no longer issues free keys; the feed only lists the 20 most recent photos, so
older ones link to the album without a thumbnail),
and matches faces to the speakers' photos on latinoware.org (DeepFace, CPU). Face vectors stay in
`data/fotos/embeddings/` (outside git) and are deleted with `make fotos-limpar`. Every match is reviewed by a
person before `web/fotos.json` is exported; the page shows the Flickr thumbnail with credit and a removal contact.

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

"Listen" reads the answer aloud ("Listen to summary" for an AI summary) with the browser's own voice
(Web Speech API, no external service): no `[n]` markers, in the answer language, pause/resume/stop and
speed 0.8–1.5. It never autoplays; without speech synthesis in the browser, there is no button.

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
| 6 | `06_avaliar_busca.py` | Recall de la búsqueda con las preguntas de referencia (10 fijas en pt/en/es + extras revisadas); falla por debajo de 100%. |

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
- **Reordenamiento opcional** de los 32 candidatos con `bge-reranker-v2-m3` en la GPU (~0,25 s): `uv sync
  --extra rerank` (siempre con `--extra rerank`, o un `uv sync` simple lo quita) y `RERANK_LOCAL=BAAI/bge-reranker-v2-m3` en el `.env`.
- **Respuesta** con `gemma4:12b-it-qat` local (elegido por benchmark frente a qwen3:14b, qwen3.5 y
  ministral-3: `docs/benchmark-modelos.md`), temperatura 0,2, basada solo en los fragmentos, citando
  `[n]`.
- **Historial de preguntas**: preguntas y respuestas se guardan 90 días en una colección `Pergunta` (sin IP ni
  user agent) y se borran solas después. Una pregunta igual (distancia bge-m3 ≤ 0,05, mismo modelo e índice)
  reutiliza la respuesta guardada, con un botón "Generar de nuevo"; `/frequentes` solo lista preguntas de una lista revisada a mano
  (`data/frequentes_aprovadas.json`), porque el texto que escriben los visitantes se vuelve público.
- **Métricas de uso**: `GET /stats?dias=7` devuelve conteos diarios anónimos (días de Brasilia) (idioma, respuestas reutilizadas, sin
  respuesta, 429, errores, p50/p95), una línea por pregunta en `data/metricas/` sin el texto ni la IP, guardadas
  90 días; `make metricas` agrega la línea semanal al `STATUS.md`, y `make instalar-timer` la programa cada lunes a las
  08:00 (timer de systemd del usuario, plantillas en `deploy/systemd/`; requiere `loginctl enable-linger` para correr sin sesión).

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
ollama pull gemma4:12b-it-qat
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
make avaliar      # recall@8 de las preguntas de referencia; falla por debajo de 100% (también tras make indexar)
make reverter-indice     # vuelve los alias a la versión anterior del índice (reindexar no corta la API)
make gabarito-candidatos  # sugerencias del historial; solo las revisadas van a data/gabarito_extra.json; después, borre el archivo de candidatos
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

**Modo solo búsqueda** (para liberar la GPU): `make sem-ia` crea el archivo-bandera `data/sem-ia` y descarga el
modelo; `make com-ia` lo borra. Mientras exista, `/ask`, `/ask/stream` y la herramienta MCP responden con las charlas
más relevantes y los enlaces `?t=` al video, sin texto generado (`"sem_ia": true`; `resposta` trae el aviso "Resumen
con IA no disponible ahora; mira las charlas más relevantes."), y la página muestra el mismo aviso. Las respuestas ya
guardadas se siguen sirviendo. `LLM_KEEP_ALIVE` (por defecto `10m`) descarga el modelo de la GPU tras un rato inactivo.
Para generar en otro Ollama de la red local, define `OLLAMA_GERACAO_URL` (el embedding sigue en `OLLAMA_URL`); si deja
de responder, la API vuelve sola a solo búsqueda. La URL va en un archivo fuera del repo, cargado por systemd con un
segundo `EnvironmentFile=`. Ese Ollama no tiene autenticación: solo red privada.

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

### Estado de los datos (18/10/2026)

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
- Índice: 2296 fragmentos (236 resúmenes, 168 bios, 1892 de transcripciones; 93 de ellos fuera
  de la programación). recall@8 de la búsqueda = 10/10.
- Charlas con video: 63 de 236. Una charla cuenta como grabada solo si la transcripción tiene habla en su
  ventana (las keynotes figuran en todos los espacios, pero solo algunas lives transmitieron el audio); el
  inicio se lee de la transcripción. Otras tres lives del Espaço Iguaçu están bloqueadas en YouTube por un
  reclamo de contenido y una es privada: `make novos-videos VIDEOS="<ids>"` las incorpora cuando se liberen.

### Fotos de los ponentes

`make fotos PASTA=<originales> ALBUM=<URL del álbum en Flickr>` registra las fotos originales enviadas por la
organización (autor y licencia por álbum en `data/fotos/albuns.json`), las enlaza con su página en Flickr
mediante el feed público del álbum (sin clave de API; Flickr ya no emite claves gratuitas; el feed solo trae
las 20 fotos más recientes, y las anteriores enlazan al álbum sin miniatura) y compara rostros con las fotos de los ponentes en latinoware.org (DeepFace, CPU).
Los vectores faciales quedan en `data/fotos/embeddings/` (fuera de git) y se borran con `make fotos-limpar`.
Cada coincidencia la revisa una persona antes de exportar `web/fotos.json`; la página muestra la miniatura de
Flickr con crédito y un contacto para retirarla.

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

"Escuchar" lee la respuesta en voz alta ("Escuchar resumen" en el resumen con IA) con la voz del propio
navegador (Web Speech API, sin servicio externo): sin las marcas `[n]`, en el idioma de la respuesta,
pausar/continuar/detener y velocidad 0,8–1,5. Nunca empieza solo; sin síntesis de voz en el navegador, no hay botón.

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
| 6 | `06_avaliar_busca.py` | Recall da busca com as perguntas-gabarito (10 fixas em pt/en/es + extras conferidas); falha abaixo de 100%. |

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
- **Reordenação opcional** dos 32 candidatos com `bge-reranker-v2-m3` na GPU (~0,25 s): `uv sync --extra
  rerank` (sempre com `--extra rerank`, senão um `uv sync` simples o remove) e `RERANK_LOCAL=BAAI/bge-reranker-v2-m3` no `.env`.
- **Resposta** com `gemma4:12b-it-qat` local, temperatura 0,2, só com base nos trechos, citando `[n]`
  (escolhido por benchmark contra qwen3:14b, qwen3.5 e ministral-3: `docs/benchmark-modelos.md`).
- **Histórico de perguntas**: perguntas e respostas ficam 90 dias numa coleção `Pergunta` (sem IP nem user
  agent) e são apagadas sozinhas depois. Pergunta igual (distância bge-m3 ≤ 0,05, mesmo modelo e índice)
  reaproveita a resposta guardada, com botão "Gerar de novo"; `/frequentes` só lista perguntas de uma lista revisada à mão
  (`data/frequentes_aprovadas.json`), porque o texto digitado pelos visitantes fica público.
- **Métricas de uso**: `GET /stats?dias=7` devolve contagens diárias anônimas (dias de Brasília) (idioma, respostas reaproveitadas, sem
  resposta, 429, erros, p50/p95), uma linha por pergunta em `data/metricas/` sem o texto nem o IP, guardadas 90
  dias; `make metricas` acrescenta a linha semanal ao `STATUS.md`, e `make instalar-timer` a agenda toda segunda às
  08:00 (timer systemd do usuário, modelos em `deploy/systemd/`; precisa de `loginctl enable-linger` para rodar sem sessão).

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
ollama pull gemma4:12b-it-qat
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
make avaliar      # recall@8 das perguntas-gabarito; falha abaixo de 100% (roda também no make indexar)
make reverter-indice     # volta os alias para a versão anterior do índice (reindexar não derruba a API)
make gabarito-candidatos  # sugestões do histórico; só as conferidas vão para data/gabarito_extra.json; depois, apague o arquivo de candidatos
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

**Modo só busca** (para liberar a GPU): `make sem-ia` cria o arquivo-flag `data/sem-ia` e descarrega o modelo;
`make com-ia` apaga. Enquanto ele existir, `/ask`, `/ask/stream` e a ferramenta do MCP respondem com as palestras
mais relevantes e os links `?t=` do vídeo, sem texto gerado (`"sem_ia": true`; `resposta` traz o aviso "Resumo com IA
indisponível agora; veja as palestras mais relevantes."), e a página mostra o mesmo aviso. Respostas já guardadas
continuam saindo. `LLM_KEEP_ALIVE` (padrão `10m`) descarrega o modelo da GPU depois de um tempo parado.
Para gerar em outro Ollama da rede local, defina `OLLAMA_GERACAO_URL` (o embedding continua no `OLLAMA_URL`); se ele
parar de responder, a API volta sozinha ao modo só busca. A URL fica num arquivo fora do repo, carregado pelo systemd
com um segundo `EnvironmentFile=`. Esse Ollama não tem autenticação: só rede privada.

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

### Estado dos dados (18/10/2026)

- Grade: 236 atividades (229 distintas; keynotes repetem em vários espaços), todas com resumo.
  Idiomas declarados: 208 em português, 24 em inglês, 4 em espanhol.
- Palestrantes: 168 páginas públicas.
- Gravações: 17 lives no canal Itaipu Parquetec (122 h), dos espaços Brasil, Paraguai, Iguaçu,
  Bolívia, Peru e Haiti. Não há gravação dos espaços Equador, Argentina, Uruguai e Chile nem das
  oficinas. Não há live do Espaço Brasil em 16/10.
- Transcrições: 17/17 lives (118 h de áudio, cerca de 559 mil palavras) com faster-whisper
  large-v3-turbo. O início de cada live vem do YouTube, então os trechos levam ao instante
  certo. As lives do Espaço Iguaçu são quase só música de espera: 3 delas quase não têm fala.
- Índice: 2296 trechos (236 resumos, 168 bios, 1892 de transcrições; 93 destes fora da grade).
  recall@8 da busca = 10/10.
- Palestras com vídeo: 63 de 236. A palestra só conta como gravada se a transcrição tem fala na janela dela
  (as keynotes aparecem em todos os espaços, mas só algumas lives transmitiram o áudio); o início vem da
  transcrição. Outras três lives do Espaço Iguaçu estão bloqueadas no YouTube por reivindicação de conteúdo e
  uma é privada: `make novos-videos VIDEOS="<ids>"` as incorpora quando forem liberadas.

### Fotos dos palestrantes

`make fotos PASTA=<originais> ALBUM=<URL do álbum no Flickr>` registra as fotos originais enviadas pela
organização (autor e licença por álbum em `data/fotos/albuns.json`), liga as fotos às páginas delas no Flickr pelo
feed público do álbum (sem chave de API; o Flickr não emite mais chave gratuita; o feed só traz as 20 fotos
mais recentes, e as anteriores ficam com link para o álbum, sem miniatura) e compara os rostos com as fotos dos palestrantes em latinoware.org (DeepFace, CPU). Os vetores
faciais ficam em `data/fotos/embeddings/` (fora do git) e são apagados com `make fotos-limpar`. Cada casamento é
revisado por uma pessoa antes de exportar `web/fotos.json`; a página mostra a miniatura do Flickr com crédito e um
contato para remoção.

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

"Ouvir resposta" lê a resposta em voz alta ("Ouvir resumo" no Resumo com IA) com a voz do próprio
navegador (Web Speech API, sem serviço externo): sem as marcações `[n]`, na língua da resposta,
pausar/continuar/parar e velocidade 0,8–1,5. Nunca começa sozinho; sem síntese de voz no navegador, não há botão.

### Licença

Código sob [MIT](LICENSE). O conteúdo das palestras pertence aos palestrantes e à organização
da Latinoware.
