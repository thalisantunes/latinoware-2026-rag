# latinoware-2026-rag

Repositório público: só código, docs e testes. `data/` (áudio, transcrições, índices, logs) e `.env` ficam fora do git; nunca comitar
dados do evento, e-mails, IPs, tokens ou nomes de hosts internos. O README é trilíngue (en/es/pt); mudanças de comportamento atualizam os três.

- Idioma de trabalho: português brasileiro, respostas curtas. Comandos Bash com caminho absoluto.
- Pipeline e comandos: `Makefile` (`make weaviate`, `coletar`, `audio`, `transcrever`, `indexar`, `catalogo`, `api`, `avaliar`); configuração em `.env` (modelo em `.env.example`, valores sem aspas).
- Testes antes de qualquer PR: `uv run pytest` (26 testes; usam a API e o Weaviate locais). Estado dos dados e etapas: `STATUS.md`.
- Fluxo: um PR pequeno por item, revisão por 3 modelos, `merge --squash`; nada direto na `main` (o benchmark entrou direto e é o contraexemplo).
- Produção: a API roda na estação (unit de usuário `latinoware-rag-api`, túnel reverso) e serve https://rag.ilove.the.br; `/health` é o smoke. Trocar modelo ou reranker só fora do horário de pico e com aviso na página; a GPU é compartilhada.
- Privacidade: a API não grava pergunta, IP nem user agent até o item RAG-4 do roadmap (cache sem IP, 90 dias); qualquer coleta nova sai depois do aviso de privacidade do site. Fotos e reconhecimento facial só com OK escrito do organizador.
- A cópia estática da página do RAG em `rede-cidades/web/public/latinoware/2026/rag/` é feita à mão a partir deste repo; mudou a UI, avisar a janela do site.
- Roadmap e decisões: `instituicao/ROADMAP-v2-2026-10-18.md` (seção 3.7), fora deste repo.
