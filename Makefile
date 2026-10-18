# Pipeline completo: make tudo. Cada etapa pode rodar sozinha.
-include .env
export

PY = uv run python

.PHONY: tudo weaviate coletar audio transcrever sincronizar indexar catalogo api testar avaliar benchmark fotos fotos-limpar videos-individuais novos-videos metricas gabarito-candidatos
# catalogo antes de indexar: não depende do índice e fica pronto mesmo se a avaliação da busca falhar
tudo: weaviate coletar audio transcrever sincronizar catalogo indexar

weaviate:
	docker compose up -d

coletar:
	$(PY) 01_coletar_site.py

audio:
	$(PY) 02_baixar_audio.py

transcrever:
	$(PY) 03_transcrever.py

sincronizar:
	$(PY) 08_sincronizar_inicio.py

# depois de indexar, a avaliação de busca: falha se o recall cair abaixo de 100%
indexar:
	$(PY) 04_indexar.py
	$(PY) 06_avaliar_busca.py

catalogo:
	$(PY) 07_exportar_catalogo.py

api:
	$(PY) 05_api.py

avaliar:
	$(PY) 06_avaliar_busca.py

# sugestões de perguntas do histórico para o gabarito (conferir à mão antes de usar)
gabarito-candidatos:
	$(PY) 06_avaliar_busca.py --candidatos

# modelos do Ollama local a comparar; ex.: make benchmark MODELOS="qwen3:14b gemma4:12b-it-qat"
MODELOS ?= qwen3:14b
benchmark:
	$(PY) 09_benchmark_llm.py $(MODELOS)

testar:
	uv run --with pytest pytest -q tests/

# fotos dos palestrantes (ver 10_fotos.py): make fotos PASTA=<originais do PTI> ALBUM=<url do álbum no Flickr>
FOTOS = uv run --extra fotos --extra rerank python 10_fotos.py
fotos:
	$(FOTOS) referencias
	$(if $(PASTA),$(if $(ALBUM),$(FOTOS) pasta "$(PASTA)" "$(ALBUM)",$(error PASTA precisa de ALBUM=<url do álbum>)))
	$(if $(ALBUM),$(FOTOS) feed "$(ALBUM)")
	$(FOTOS) casar

# apaga os vetores faciais quando o casamento final terminar
fotos-limpar:
	$(FOTOS) limpar

# vídeos individuais das palestras (uma URL por vez): ensaio com make videos-individuais PLAYLIST="<url>";
# grava com GRAVAR=1
videos-individuais:
	$(PY) 11_videos_palestras.py "$(PLAYLIST)" $(if $(GRAVAR),--gravar)

# vídeos novos (ex.: os do Espaço Iguaçu, quando a reivindicação da SME cair): baixa, transcreve e reindexa;
# make novos-videos VIDEOS="9Dck3H7xOGE GSUcnRPFDpE KGIWmBq2t_A" (os ids que ainda não aparecem nas listagens)
novos-videos:
	$(PY) 02_baixar_audio.py $(foreach v,$(VIDEOS),"$(v)")
	$(MAKE) transcrever sincronizar catalogo indexar

# linha semanal de uso (anônima) no STATUS.md
metricas:
	$(PY) 12_metricas.py >> STATUS.md
	tail -1 STATUS.md
