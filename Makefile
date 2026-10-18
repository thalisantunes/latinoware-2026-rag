# Pipeline completo: make tudo. Cada etapa pode rodar sozinha.
-include .env
export

PY = uv run python

.PHONY: tudo weaviate coletar audio transcrever sincronizar indexar catalogo api testar avaliar benchmark fotos fotos-limpar
tudo: weaviate coletar audio transcrever sincronizar indexar catalogo

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

indexar:
	$(PY) 04_indexar.py

catalogo:
	$(PY) 07_exportar_catalogo.py

api:
	$(PY) 05_api.py

avaliar:
	$(PY) 06_avaliar_busca.py

# modelos do Ollama local a comparar; ex.: make benchmark MODELOS="qwen3:14b gemma4:12b-it-qat"
MODELOS ?= qwen3:14b
benchmark:
	$(PY) 09_benchmark_llm.py $(MODELOS)

testar:
	uv run --with pytest pytest -q tests/

# fotos dos palestrantes no Flickr oficial (ver 10_fotos.py): make fotos ALBUNS="<url do álbum> ..."
FOTOS = uv run --extra fotos --extra rerank python 10_fotos.py
fotos:
	$(FOTOS) referencias
	$(if $(ALBUNS),$(FOTOS) flickr $(ALBUNS))
	$(FOTOS) casar

# apaga os vetores faciais quando o casamento final terminar
fotos-limpar:
	$(FOTOS) limpar
