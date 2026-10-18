"""Testes. Unitários rodam sempre; os de integração precisam da API no ar (make api)."""

import importlib.util
import json
import os
import re
from collections import Counter
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


def test_video():
    assert api.video("https://youtu.be/q-_OQ5ww5iw?t=4078") == ("q-_OQ5ww5iw", 4078)
    assert api.video("") == (None, None)
    assert api.video(None) == (None, None)


def test_chave_espaco():
    assert indexar.chave_espaco("Espaço Bolivia – LatinScience") == indexar.chave_espaco("Espaço Bolívia")


def test_janelas_sobreposicao():
    segs = [{"inicio": i, "fim": i + 1, "texto": "palavra " * 50} for i in range(20)]
    janelas = list(indexar.janelas(segs))
    assert len(janelas) > 1
    assert janelas[0][-1] in janelas[1]  # o fim de um pedaço reaparece no começo do seguinte


def test_alinhar_palestras():
    def palestra(pid, inicio, fim):
        return {"id": pid, "espaco": "Espaço Brasil", "inicio": f"2026-10-14T{inicio}:00-03:00",
                "fim": f"2026-10-14T{fim}:00-03:00"}
    palestras = [palestra("dentro", "10:00", "10:50"), palestra("antes", "08:00", "08:50"),
                 palestra("depois", "13:00", "13:50")]
    # live começou 09:00 BRT (12:00 UTC) e durou 3 h
    videos = [{"id": "abc", "espaco": "Espaço Brasil", "data": "2026-10-14", "duracao": 3 * 3600,
               "inicio_live": 1791979200}]
    a = indexar.alinhar_palestras(palestras, videos, {})
    assert list(a) == ["dentro@brasil"]
    assert a["dentro@brasil"] == {"video_id": "abc", "t_inicio": 3600, "t_fim": 6600,
                                  "alinhamento": "youtube", "url_video": "https://youtu.be/abc?t=3600"}
    # segunda live curta no mesmo dia, das 10:40 às 11:00: a palestra fica com a live longa
    videos.append({"id": "curta", "espaco": "Espaço Brasil", "data": "2026-10-14", "duracao": 1200,
                   "inicio_live": 1791979200 + 6000})
    assert indexar.alinhar_palestras(palestras, videos, {})["dentro@brasil"]["video_id"] == "abc"


def test_alinhar_exige_fala(tmp_path, monkeypatch):
    # live com transcrição: só a palestra com fala na janela fica alinhada
    monkeypatch.setattr(indexar, "DATA", tmp_path)
    (tmp_path / "transcricoes").mkdir()
    fala = [{"inicio": 3600 + i * 10, "texto": "palavra " * 20} for i in range(300)]  # 10:00-10:50
    (tmp_path / "transcricoes" / "abc.json").write_text(json.dumps({"segmentos": fala}))
    palestras = [{"id": p, "espaco": "Espaço Brasil", "inicio": f"2026-10-14T{h}:00:00-03:00",
                  "fim": f"2026-10-14T{h}:50:00-03:00"} for p, h in (("falada", "10"), ("muda", "11"))]
    videos = [{"id": "abc", "espaco": "Espaço Brasil", "data": "2026-10-14", "duracao": 4 * 3600,
               "inicio_live": 1791979200}]
    assert list(indexar.alinhar_palestras(palestras, videos, {})) == ["falada@brasil"]


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
        assert f["url_video"] is None or f["url_video"].startswith("https://youtu.be/")
        assert (f["url_video"] is None) == (f["video_id"] is None) == (f["video_t"] is None)
    # nenhuma palestra ocupa mais trechos de transcrição que o limite
    contagem = Counter((re.sub(r"\W", "", f["titulo"].lower()), f["inicio"])
                       for f in d["fontes"] if f["fonte"] == "transcricao" and f["palestra_id"])
    assert max(contagem.values(), default=0) <= api.MAX_POR_PALESTRA


@pytest.mark.skipif(not api_no_ar(), reason="API fora do ar")
def test_idioma_forcado():
    d = httpx.post(f"{API_URL}/ask", json={"pergunta": PERGUNTAS["pt"], "idioma": "en"}, timeout=300).json()
    assert d["idioma"] == "en"
    assert api.detectar_idioma(d["resposta"]) == "en"


@pytest.mark.skipif(not api_no_ar(), reason="API fora do ar")
def test_ask_stream():
    eventos = []
    with httpx.stream("POST", f"{API_URL}/ask/stream", json={"pergunta": PERGUNTAS["pt"]}, timeout=300) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        for linha in r.iter_lines():
            if linha.startswith("event: "):
                eventos.append(linha[7:])
            elif linha.startswith("data: "):
                ultimo = json.loads(linha[6:])
    sem_tokens = [e for e in eventos if e != "token"]
    # com reranker ligado há a etapa "reordenando" antes das fontes
    assert sem_tokens in (["etapa", "fontes", "etapa", "fim"], ["etapa", "etapa", "fontes", "etapa", "fim"])
    assert eventos.count("token") > 1
    assert "home assistant" in ultimo["resposta"].lower()


@pytest.mark.skipif(not api_no_ar(), reason="API fora do ar")
def test_trecho_fora_da_grade():
    # o trecho que responde não tem palestra alinhada: a resposta deve dar espaço, dia e instante
    d = httpx.post(f"{API_URL}/ask", json={"pergunta": "Quem falou sobre Nova Porteirinha?"}, timeout=300).json()
    assert any(f["fonte"] == "transcricao" and f["palestra_id"] is None and f["url_video"] for f in d["fontes"])
    assert re.search(r"\b\d:\d{2}:\d{2}\b", d["resposta"])
    assert "paraguai" in d["resposta"].lower()
    assert "fora da grade" not in d["resposta"].lower()


def test_inicio_lido_e_manual(tmp_path, monkeypatch):
    # a grade diz 10:00 (t=3600); a transcrição mostra o início real em t=3800; o manual vence os dois
    monkeypatch.setattr(indexar, "DATA", tmp_path)
    palestras = [{"id": "p", "espaco": "Espaço Brasil", "inicio": "2026-10-14T10:00:00-03:00",
                  "fim": "2026-10-14T10:50:00-03:00"}]
    videos = [{"id": "abc", "espaco": "Espaço Brasil", "data": "2026-10-14", "duracao": 4 * 3600,
               "inicio_live": 1791979200}]
    (tmp_path / "inicios.json").write_text(json.dumps({"p@brasil": {"video_id": "abc", "t": 3800}}))
    a = indexar.alinhar_palestras(palestras, videos, {})["p@brasil"]
    assert (a["t_inicio"], a["alinhamento"], a["url_video"]) == (3800, "transcricao", "https://youtu.be/abc?t=3800")
    assert indexar.alinhar_palestras(palestras, videos, {}, inicios=False)["p@brasil"]["t_inicio"] == 3600
    assert indexar.alinhar_palestras(palestras, videos, {"p@brasil": 3700})["p@brasil"]["t_inicio"] == 3700


def test_primeira_fala():
    sinc = modulo("08_sincronizar_inicio.py")
    segs = [{"inicio": 100, "fim": 130, "texto": "x"}, {"inicio": 400, "fim": 420, "texto": "y"}]
    assert sinc.primeira_fala(segs, 200) == 400      # grade em silêncio: primeira fala depois
    assert sinc.primeira_fala(segs, 90) is None      # grade já com fala: fica a grade
    assert sinc.primeira_fala(segs, 110) is None     # fala começou antes e segue depois da grade


@pytest.mark.skipif(not api_no_ar(), reason="API fora do ar")
def test_resumo_da_palestra():
    # "Resumo com IA": só trechos da palestra pedida, resumo do site primeiro e transcrição em ordem
    d = httpx.post(f"{API_URL}/ask", timeout=300, json={
        "pergunta": "Resuma a palestra \"Tecnologia, Energia e Comunidade\"", "palestra_id": "772-1742"}).json()
    assert {f["palestra_id"] for f in d["fontes"]} == {"772-1742"}
    assert d["fontes"][0]["fonte"] == "resumo" and len(d["fontes"]) > 2
    tempos = [f["inicio_video_s"] for f in d["fontes"][1:]]
    assert tempos == sorted(tempos)
    assert d["resposta"].strip()
    assert httpx.post(f"{API_URL}/ask", json={"pergunta": "abc", "palestra_id": "x y"}).status_code == 422
    assert httpx.post(f"{API_URL}/ask", json={"pergunta": "abc", "palestra_id": "nao-existe"}).status_code == 404


def test_reordenar(monkeypatch):
    trechos = [{"palestra_titulo": f"t{i}", "texto": "x"} for i in range(4)]
    monkeypatch.setattr(api, "RERANK_URL", "http://reranker")
    monkeypatch.setattr(api, "RERANK_TOP", 3)

    class Resposta:
        def raise_for_status(self):
            pass

        def json(self):  # o reranker prefere o 3º, depois o 1º e o 2º
            return {"results": [{"index": 0, "relevance_score": 0.5}, {"index": 1, "relevance_score": -1},
                                {"index": 2, "relevance_score": 2}]}

    monkeypatch.setattr(api.httpx, "post", lambda *a, **k: Resposta())
    assert [t["palestra_titulo"] for t in api.reordenar("q", trechos)] == ["t2", "t0", "t1", "t3"]

    class Parcial(Resposta):
        def json(self):  # só 1 dos 3 índices: não dá para confiar, segue a ordem da busca
            return {"results": [{"index": 2, "relevance_score": 2}]}

    monkeypatch.setattr(api.httpx, "post", lambda *a, **k: Parcial())
    assert api.reordenar("q", trechos) == trechos

    def falha(*a, **k):
        raise api.httpx.ConnectError("fora do ar")

    monkeypatch.setattr(api.httpx, "post", falha)
    assert api.reordenar("q", trechos) == trechos  # sem reranker, segue a ordem da busca
