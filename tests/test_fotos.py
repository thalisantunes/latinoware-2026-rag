"""10_fotos.py sem rostos reais: vetores sintéticos e arquivos temporários."""

import importlib.util
import json
import subprocess
from pathlib import Path

RAIZ = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("fotos", RAIZ / "10_fotos.py")
fotos = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fotos)


def test_distancia():
    assert fotos.distancia([1, 0], [2, 0]) == 0
    assert round(fotos.distancia([1, 0], [0, 1]), 6) == 1


def test_calibrar_avisa_quando_pessoas_diferentes_ficam_abaixo_do_limiar(capsys, monkeypatch):
    monkeypatch.setattr(fotos, "LIMIAR", 0.45)
    fotos.calibrar({"a": [1, 0], "b": [1, 0.1], "c": None})  # a e b quase iguais: distância ~0,005
    assert "aviso" in capsys.readouterr().out


def test_exportar_so_aprovados(tmp_path, monkeypatch):
    monkeypatch.setattr(fotos, "FOTOS", tmp_path)
    monkeypatch.setattr(fotos, "RAIZ", tmp_path)
    (tmp_path / "web").mkdir()
    foto = {"id": "f1", "url_pagina": "https://www.flickr.com/photos/x/f1/", "url_thumb": "https://live.staticflickr.com/q.jpg",
            "autor": "PTI", "licenca": "4", "album": "Latinoware 2026"}
    (tmp_path / "flickr.json").write_text(json.dumps({"f1": foto, "f2": foto | {"id": "f2"}}))
    (tmp_path / "casamentos.json").write_text(json.dumps({
        "pares": [{"palestrante_id": "7", "foto_id": "f1", "distancia": 0.3}],
        "duvidas": [{"palestrante_id": "7", "foto_id": "f2", "distancia": 0.5}]}))
    (tmp_path / "revisao.json").write_text(json.dumps({"7:f1": True, "7:f2": False}))
    fotos.exportar()
    saida = json.loads((tmp_path / "web" / "fotos.json").read_text())
    assert saida["palestrantes"] == [{"palestrante_id": "7", "fotos": [foto | {"licenca_nome": "CC BY 2.0"}]}]


def test_nenhum_vetor_facial_no_git():
    versionados = subprocess.run(["git", "-C", str(RAIZ), "ls-files"], capture_output=True, text=True).stdout.split()
    assert not [f for f in versionados if f.startswith("data/fotos") or f.endswith((".npy", ".npz", ".pkl"))]


def test_casar_filtra_plateia_e_deduplica(tmp_path, monkeypatch, capsys):
    for nome, valor in (("FOTOS", tmp_path), ("REFS", tmp_path / "refs"), ("FLICKR", tmp_path / "fl"),
                        ("VETORES", tmp_path / "vet")):
        monkeypatch.setattr(fotos, nome, valor)
    (tmp_path / "referencias.json").write_text(json.dumps({"7": {"arquivo": "7.jpg"}, "8": {"arquivo": "8.jpg"}}))
    (tmp_path / "flickr.json").write_text(json.dumps({"f1": {}}))
    rostos = {"7.jpg": [([1, 0, 0], 100)], "8.jpg": [([0, 1, 0], 100)],
              # foto f1: o palestrante 7 no palco e no telão (dois rostos grandes) e o 8 pequeno ao fundo
              "f1.jpg": [([1, 0.05, 0], 100), ([1, 0.02, 0], 90), ([0, 1, 0], 10)]}
    monkeypatch.setattr(fotos, "vetores_de", lambda caminho: rostos[Path(caminho).name])
    fotos.casar()
    casados = json.loads((tmp_path / "casamentos.json").read_text())
    assert [(p["palestrante_id"], p["foto_id"]) for p in casados["pares"]] == [("7", "f1")]
    assert casados["duvidas"] == []
    assert oct((tmp_path / "vet").stat().st_mode)[-3:] == "700"
    assert oct((tmp_path / "vet" / "flickr.npy").stat().st_mode)[-3:] == "600"
    assert fotos.carregar("flickr")["f1"] == rostos["f1.jpg"]


def test_coletar_album_pagina(tmp_path, monkeypatch):
    monkeypatch.setattr(fotos, "FLICKR", tmp_path)
    paginas = {1: [{"id": "a", "url_m": "m", "url_q": "q", "license": "4"}], 2: [{"id": "b", "url_m": "m", "license": "0"}]}

    class Cliente:
        def get(self, url, params=None):
            class R:
                def json(self_):
                    return {"stat": "ok", "photoset": {"photo": paginas[params["page"]], "pages": 2, "owner": "pti",
                                                       "ownername": "PTI", "title": "Latinoware 2026"}}
            return R()

    monkeypatch.setattr(fotos, "baixar", lambda cli, url, destino: destino.write_bytes(b"x"))
    coletadas = {"a": {}}  # já vista: não baixa de novo
    assert fotos.coletar_album(Cliente(), "chave", "https://www.flickr.com/photos/pti/albums/72177720300000000", coletadas) == 1
    assert coletadas["b"]["url_pagina"] == "https://www.flickr.com/photos/pti/b/" and coletadas["b"]["autor"] == "PTI"
