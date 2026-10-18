"""Testes. Unitários rodam sempre; os de integração precisam da API no ar (make api)."""

import importlib.util
import os
from pathlib import Path

import httpx
import pytest

RAIZ = Path(__file__).parent.parent
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8765")


def modulo(nome):
    spec = importlib.util.spec_from_file_location(nome.removesuffix(".py"), RAIZ / nome)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


api = modulo("05_api.py")
indexar = modulo("04_indexar.py")

# a mesma pergunta nas três línguas; a resposta deve citar a keynote do maddog sobre Home Assistant
PERGUNTAS = {
    "pt": "Sobre o que foi a palestra do Jon maddog Hall?",
    "en": "What was Jon maddog Hall's talk about?",
    "es": "¿De qué trató la charla de Jon maddog Hall?",
}


@pytest.mark.parametrize("idioma,pergunta", PERGUNTAS.items())
def test_detectar_idioma(idioma, pergunta):
    assert api.detectar_idioma(pergunta) == idioma


@pytest.mark.parametrize("idioma,pergunta", [
    ("en", "Which talks were held in Foz do Iguaçu?"),
    ("es", "¿Qué charlas dio João en Foz do Iguaçu?"),
])
def test_idioma_com_nome_proprio(idioma, pergunta):
    assert api.detectar_idioma(pergunta) == idioma


def test_chave_espaco():
    assert indexar.chave_espaco("Espaço Bolivia – LatinScience") == indexar.chave_espaco("Espaço Bolívia")


def test_janelas_sobreposicao():
    segs = [{"inicio": i, "fim": i + 1, "texto": "palavra " * 50} for i in range(20)]
    janelas = list(indexar.janelas(segs))
    assert len(janelas) > 1
    assert janelas[0][-1] in janelas[1]  # o fim de um pedaço reaparece no começo do seguinte


def api_no_ar():
    try:
        return httpx.get(f"{API_URL}/health", timeout=5).json()["ok"]
    except Exception:
        return False


@pytest.mark.skipif(not api_no_ar(), reason="API fora do ar")
@pytest.mark.parametrize("idioma,pergunta", PERGUNTAS.items())
def test_ask_tres_linguas(idioma, pergunta):
    d = httpx.post(f"{API_URL}/ask", json={"pergunta": pergunta}, timeout=300).json()
    assert d["idioma"] == idioma
    assert api.detectar_idioma(d["resposta"]) == idioma
    assert "home assistant" in d["resposta"].lower()
    assert any("maddog" in f["titulo"].lower() or "maddog" in f["palestrantes"].lower() for f in d["fontes"])
    for f in d["fontes"]:
        assert isinstance(f["links_palestrantes"], list)
        assert all(p["url"].startswith("https://") for p in f["links_palestrantes"])
        assert (f["inicio_video_s"] is None) == (f["fonte"] != "transcricao")


@pytest.mark.skipif(not api_no_ar(), reason="API fora do ar")
def test_idioma_forcado():
    d = httpx.post(f"{API_URL}/ask", json={"pergunta": PERGUNTAS["pt"], "idioma": "en"}, timeout=300).json()
    assert d["idioma"] == "en"
    assert api.detectar_idioma(d["resposta"]) == "en"
