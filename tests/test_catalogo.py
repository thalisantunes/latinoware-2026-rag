"""Invariantes de web/catalogo.json (gerado por make catalogo e commitado)."""

import importlib.util
import json
from pathlib import Path

RAIZ = Path(__file__).parent.parent
CATALOGO = json.loads((RAIZ / "web" / "catalogo.json").read_text())

spec = importlib.util.spec_from_file_location("exportar", RAIZ / "07_exportar_catalogo.py")
exportar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exportar)


def test_contagens():
    palestras = CATALOGO["palestras"]
    assert CATALOGO["versao"] == exportar.VERSAO
    assert len(palestras) == 236
    assert len({p["uid"] for p in palestras}) == 236
    assert len(CATALOGO["palestrantes"]) == 168
    assert sum(p["url_video"] is not None for p in palestras) >= 63


def test_video_coerente():
    duracao = {v["id"]: v["duracao_s"] for v in CATALOGO["videos"]}
    for p in CATALOGO["palestras"]:
        assert (p["url_video"] is None) == (p["video_id"] is None)
        if p["video_id"]:
            assert 0 <= p["t_inicio"] < duracao[p["video_id"]]
            assert p["url_video"] == f"https://youtu.be/{p['video_id']}?t={p['t_inicio']}"


def test_sem_texto_longo():
    for p in CATALOGO["palestras"]:
        assert len(p["resumo_curto"]) <= exportar.RESUMO_MAX
        assert p["url_site"].startswith("https://latinoware.org/")
        assert all(s["url"].startswith("https://") for s in p["palestrantes"])
    chaves = {"id", "nome", "url", "organizacao", "pais", "palestras"}
    assert all(set(s) == chaves for s in CATALOGO["palestrantes"])


def test_palestrante_ligado():
    urls = {s["url"] for s in CATALOGO["palestrantes"]}
    # 3 pessoas da grade não têm página de palestrante no site
    assert len({s["url"] for p in CATALOGO["palestras"] for s in p["palestrantes"]} - urls) <= 3
    assert exportar.nome_curto("Alessandro de Oliveira Faria (Cabelo)") == ("alessandro", "faria")


def test_resumo_curto():
    assert exportar.resumo_curto("curto  e\nlimpo") == "curto e limpo"
    longo = exportar.resumo_curto("palavra " * 100)
    assert len(longo) <= exportar.RESUMO_MAX and longo.endswith("palavra…")
