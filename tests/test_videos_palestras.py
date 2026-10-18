"""11_videos_palestras.py com títulos sintéticos (sem YouTube)."""

import importlib.util
from pathlib import Path

RAIZ = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("videos", RAIZ / "11_videos_palestras.py")
videos = importlib.util.module_from_spec(spec)
spec.loader.exec_module(videos)

PALESTRAS = [
    {"id": "1", "espaco": "Espaço Brasil", "titulo": "Embarcados em Grandes Eventos",
     "palestrantes": [{"nome": "Thalis Antunes de Souza"}]},
    {"id": "2", "espaco": "Espaço Paraguai", "titulo": "Do Inferno ao Shell", "palestrantes": [{"nome": "Julio Cezar Neves"}]},
    # keynote repetida em outra sala: vira uma só
    {"id": "3", "espaco": "Espaço Peru", "titulo": "Do Inferno ao Shell", "palestrantes": [{"nome": "Julio Cezar Neves"}]},
]


def test_casar():
    achados = videos.casar([
        {"id": "a", "titulo": "Latinoware 2026 | Embarcados em grandes eventos - Thalis Antunes"},
        {"id": "b", "titulo": "Do inferno ao shell | Espaço Paraguai"},
        {"id": "c", "titulo": "Encerramento e sorteios"},
    ], PALESTRAS)
    assert [(v["id"], p and p["id"], n >= videos.ACEITA) for v, p, n in achados] == [
        ("a", "1", True), ("b", "2", True), ("c", None, False)]


def test_sobrenome_ajuda_quando_titulo_e_parecido():
    p = PALESTRAS[1]
    assert videos.nota("Inferno no shell - Neves", p) > videos.nota("Inferno no shell - Silva", p)


def test_mapear_replica_titulo_e_desempata():
    palestras = PALESTRAS + [{"id": "4", "espaco": "Espaço Brasil", "titulo": "Do Inferno ao Shell",
                              "palestrantes": [{"nome": "Julio Cezar Neves"}]}]
    achados = [({"id": "x", "titulo": "Do inferno ao shell"}, PALESTRAS[1], 1.0),
               ({"id": "y", "titulo": "Do inferno ao shell (reupload)"}, PALESTRAS[1], 0.9)]
    mapa, duvidas, _ = videos.mapear(achados, palestras)
    assert {u: m["video_id"] for u, m in mapa.items()} == {"2@paraguai": "x", "3@peru": "x", "4@brasil": "x"}
    assert duvidas == []


def test_titulo_curto_nao_casa_com_tudo():
    p = {"titulo": "IA", "palestrantes": []}
    assert videos.nota("Latinoware 2026 | Uma palestra longa sobre IA e outras coisas", p) < videos.ACEITA


def test_empate_nao_grava():
    achados = [({"id": "x", "titulo": "Do inferno ao shell"}, PALESTRAS[1], 0.9),
               ({"id": "y", "titulo": "Do inferno ao shell!"}, PALESTRAS[1], 0.9)]
    mapa, duvidas, _ = videos.mapear(achados, PALESTRAS)
    assert mapa == {} and len(duvidas) == 1
