# latinoware-2026-rag

Repositório público: só código, docs e testes. `data/` (áudio, transcrições, índices, logs) e `.env` ficam fora do git; nunca comitar
dados do evento, e-mails, IPs, tokens ou nomes de hosts internos. O README é trilíngue (en/es/pt); mudanças de comportamento atualizam os três.

- Idioma de trabalho: português brasileiro, respostas curtas. Comandos Bash com caminho absoluto.
- Pipeline e comandos: `Makefile` (`make weaviate`, `coletar`, `audio`, `transcrever`, `sincronizar`, `indexar` (avalia a busca no fim), `catalogo`, `api`, `avaliar`, `gabarito-candidatos`, `testar`, `benchmark`, `metricas`, `fotos`, `videos-individuais`, `novos-videos`); configuração em `.env` (modelo em `.env.example`, valores sem aspas).
- Testes antes de qualquer PR: `make testar` (= `uv run --with pytest pytest`; 26 testes; usam a API e o Weaviate locais). Estado dos dados: seção "Data status" do README.
- Fluxo: um PR pequeno por item, revisão por 3 modelos, `merge --squash`; nada direto na `main` (o benchmark entrou direto e é o contraexemplo).
- Produção: a API roda na estação (unit de usuário `latinoware-rag-api`, túnel reverso) e serve https://rag.ilove.the.br; `/health` é o smoke. Trocar modelo ou reranker só fora do horário de pico e com aviso na página; a GPU é compartilhada.
- Privacidade: a API guarda pergunta e resposta por 90 dias (coleção `Pergunta`, expurgo automático), nunca IP nem user agent; aviso na página e em ilove.the.br/privacidade/. Fotos e reconhecimento facial: decisão do Thalis (organizador e curador da Latinoware desde 2011) em 2026-10-18: dispensa OK do PTI e consentimento individual; controlador = Thalis, pessoa física (como em ilove.the.br/privacidade/); fotos exibidas só as públicas do Flickr oficial, com crédito e link; vetores faciais fora do git (data/fotos/embeddings, 700) e apagados ao fim (make fotos-limpar); pedido de remoção na página.
- A página estática do RAG no site institucional (repo privado) é copiada à mão a partir deste repo; mudou a UI, avisar a janela do site.
- Roadmap e decisões ficam fora deste repo (roadmap v2 da instituição, seção 3.7).
