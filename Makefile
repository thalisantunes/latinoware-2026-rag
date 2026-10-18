# Pipeline completo: make tudo. Cada etapa pode rodar sozinha.
-include .env
export

PY = uv run python

.PHONY: tudo weaviate coletar audio transcrever sincronizar indexar catalogo api testar avaliar
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

testar:
	uv run --with pytest pytest -q tests/
