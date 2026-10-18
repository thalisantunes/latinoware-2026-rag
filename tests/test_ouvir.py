"""Botão "Ouvir" (voz do navegador) na página e no componente, num Chromium sem rede com speechSynthesis simulado.

Precisa do Playwright e do Chromium dele (make testar já traz o pacote; o navegador: uv run --with playwright==1.63.0
playwright install chromium); sem eles, os testes são pulados.
"""

import json
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

WEB = Path(__file__).parent.parent / "web"
ORIGEM = "http://rag.teste"
RESPOSTA = "O maddog falou sobre Home Assistant [1]. Também citou automação residencial [1, 2]! Fim."
FONTES = [{"n": 1, "fonte": "resumo", "titulo": "Home Assistant", "url": "https://latinoware.org/a", "inicio": "2026-10-14T10:00"},
          {"n": 2, "fonte": "resumo", "titulo": "Automação", "url": "https://latinoware.org/b", "inicio": "2026-10-14T11:00"}]

# voz falsa: guarda cada fala; o teste decide quando ela termina (window.__fim())
VOZ_FALSA = """
window.__falas = []; window.__chamadas = [];
let atual = null;
class Fala { constructor(t) { this.text = t; } }
const ss = {
  getVoices: () => [],
  speak(u) { atual = u; __falas.push({ text: u.text, lang: u.lang, rate: u.rate }); },
  cancel() { __chamadas.push("cancel"); const u = atual; atual = null; if (u) setTimeout(() => u.onerror?.({ error: "interrupted" })); },
  pause() { __chamadas.push("pause"); }, resume() { __chamadas.push("resume"); },
};
window.__fim = () => { const u = atual; atual = null; u?.onend?.(); };
Object.defineProperty(window, "speechSynthesis", { value: ss, configurable: true });
Object.defineProperty(window, "SpeechSynthesisUtterance", { value: Fala, configurable: true });
"""
SEM_VOZ = 'Object.defineProperty(window, "speechSynthesis", { value: undefined, configurable: true });'

EMBED = f"""<!doctype html><html lang="pt-BR"><meta charset="utf-8"><body>
<script src="./latinoware-catalogo.js" defer></script>
<latinoware-catalogo src="./catalogo.json" api="{ORIGEM}" OUVIR></latinoware-catalogo></body></html>"""


@pytest.fixture(scope="module")
def navegador():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:
            pytest.skip(f"Chromium do Playwright indisponível: {e}")
        yield b
        b.close()


def abrir(navegador, caminho="/", idioma="pt", voz=VOZ_FALSA, embed_attr=""):
    pagina = navegador.new_page()
    pagina.add_init_script(voz)

    def servir(rota):
        nome = rota.request.url.removeprefix(ORIGEM).split("?")[0]
        if nome == "/embed.html":
            return rota.fulfill(body=EMBED.replace("OUVIR", embed_attr), content_type="text/html")
        if nome == "/health":
            return rota.fulfill(json={"ok": True, "modelo": "teste", "reranker": None})
        if nome == "/frequentes":
            return rota.fulfill(json=[])
        if nome == "/ask/stream":
            return rota.fulfill(status=404, body="")
        if nome == "/ask":
            return rota.fulfill(json={"resposta": RESPOSTA, "idioma": idioma, "fontes": FONTES})
        arquivo = WEB / (nome.strip("/") or "index.html")
        tipo = {".html": "text/html", ".js": "text/javascript", ".json": "application/json"}[arquivo.suffix]
        return rota.fulfill(body=arquivo.read_bytes(), content_type=tipo)

    pagina.route(f"{ORIGEM}/**", servir)
    pagina.goto(ORIGEM + caminho)
    return pagina


def perguntar(pagina):
    pagina.fill("#q", "O que o maddog apresentou?")
    pagina.click("#b")
    pagina.wait_for_selector(".partilha")


def falas(pagina):
    return pagina.evaluate("window.__falas")


def test_ouvir_resposta_na_pagina(navegador):
    pagina = abrir(navegador)
    perguntar(pagina)
    ouvir = pagina.get_by_role("button", name="Ouvir resposta")
    assert ouvir.get_attribute("aria-pressed") == "false"
    assert falas(pagina) == []  # nada de autoplay
    assert not pagina.get_by_role("button", name="Parar").is_visible()

    ouvir.click()
    assert ouvir.get_attribute("aria-pressed") == "true"
    f = falas(pagina)
    assert f == [{"text": "O maddog falou sobre Home Assistant.", "lang": "pt-BR", "rate": 1}]  # sem [n]

    pagina.get_by_role("button", name="Pausar").click()
    assert pagina.evaluate("window.__chamadas").count("pause") == 1
    pagina.get_by_role("button", name="Continuar").click()
    assert pagina.evaluate("window.__chamadas").count("resume") >= 2

    pagina.get_by_label("Velocidade").select_option("1.5")  # recomeça a frase atual na velocidade nova
    assert falas(pagina)[-1] == {"text": "O maddog falou sobre Home Assistant.", "lang": "pt-BR", "rate": 1.5}

    pagina.evaluate("window.__fim()")
    assert falas(pagina)[-1]["text"] == "Também citou automação residencial!"
    pagina.evaluate("window.__fim()")
    assert falas(pagina)[-1]["text"] == "Fim."
    pagina.evaluate("window.__fim()")  # acabou: volta ao estado inicial
    assert ouvir.get_attribute("aria-pressed") == "false"
    assert not pagina.get_by_role("button", name="Parar").is_visible()

    ouvir.click()
    pagina.get_by_role("button", name="Parar").click()
    assert ouvir.get_attribute("aria-pressed") == "false"
    assert pagina.evaluate("document.activeElement.getAttribute('aria-pressed')") == "false"  # foco volta ao Ouvir
    pagina.close()


def test_ouvir_resumo_em_ingles(navegador):
    pagina = abrir(navegador, idioma="en")
    pagina.evaluate("""document.dispatchEvent(new CustomEvent("perguntar", { cancelable: true,
        detail: { pergunta: "Summarize the talk", palestra_id: "x" } }))""")
    pagina.wait_for_selector(".partilha")
    ouvir = pagina.get_by_role("button", name="Listen to summary")
    ouvir.click()
    assert falas(pagina)[0]["lang"] == "en"
    pagina.close()


def test_sem_voz_sem_botao(navegador):
    pagina = abrir(navegador, voz=SEM_VOZ)
    perguntar(pagina)
    assert pagina.locator(".ouvir").count() == 0
    assert pagina.get_by_role("button", name="Copiar resposta").is_visible()
    pagina.close()


@pytest.mark.parametrize("attr, botoes", [("", 1), ('ouvir="false"', 0)])
def test_componente(navegador, attr, botoes):
    pagina = abrir(navegador, "/embed.html", embed_attr=attr)
    pagina.locator("latinoware-catalogo textarea").fill("O que o maddog apresentou?")
    pagina.locator("latinoware-catalogo .ia button[type=submit]").click()
    pagina.get_by_role("button", name="Copiar resposta").wait_for()
    assert pagina.get_by_role("button", name="Ouvir resposta").count() == botoes
    if botoes:
        pagina.get_by_role("button", name="Ouvir resposta").click()
        assert falas(pagina)[0]["text"] == "O maddog falou sobre Home Assistant."
    pagina.close()


def test_resumo_com_ia_no_componente(navegador):
    pagina = abrir(navegador, "/embed.html")
    pagina.locator("latinoware-catalogo .perg").first.click()
    pagina.get_by_role("button", name="Ouvir resumo").wait_for()
    pagina.close()
