# data/ (fora do git)

Tudo aqui é gerado pelos scripts e **não vai para o repositório**:

| Caminho | Gerado por | Conteúdo |
|---|---|---|
| `site/palestras.json`, `site/palestrantes.json` | `01_coletar_site.py` | grade e palestrantes de latinoware.org |
| `videos.json`, `audio/` | `02_baixar_audio.py` | metadados das lives e áudio (m4a) |
| `transcricoes/` | `03_transcrever.py` | transcrições Whisper com timestamps |
| `weaviate/` | `docker compose` | índice vetorial |
| `logs/` | execuções em segundo plano | logs |

Por quê: as palestras, as gravações e os textos do site têm direitos autorais dos
palestrantes e da organização do evento. O repositório distribui só o código que
reconstrói o índice a partir das fontes públicas. Transcrições e índices não são
redistribuídos: a API usa as transcrições como contexto para gerar a resposta, mas devolve
só título, palestrante e link para o vídeo no instante citado.

Exceção: `web/catalogo.json` (gerado por `07_exportar_catalogo.py`, `make catalogo`) fica no
repositório. Ele traz só metadados da grade (título, horário, espaço, palestrantes com link),
um resumo curto de até 280 caracteres com link para o texto completo no site e o link para o
instante da palestra na live. Sem bios, sem resumo completo e sem transcrição.
