"""Botão "Ouvir" (voz do navegador) na página e no componente, num Chromium sem rede com speechSynthesis simulado.

Precisa do Playwright e do Chromium dele (make testar já traz o pacote; o navegador: uv run --with playwright==1.63.0
playwright install chromium); sem o navegador instalado, os testes são pulados.
"""

from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

WEB = Path(__file__).parent.parent / "web"
ORIGEM = "http://rag.teste"
RESPOSTA = "O maddog falou sobre Home Assistant [1]. Também citou automação residencial [1, 2]! Fim."
FRASES = ["O maddog falou sobre Home Assistant.", "Também citou automação residencial!", "Fim."]
FONTES = [{"n": 1, "fonte": "resumo", "titulo": "Home Assistant", "url": "https://latinoware.org/a", "inicio": "2026-10-14T10:00"},
          {"n": 2, "fonte": "resumo", "titulo": "Automação", "url": "https://latinoware.org/b", "inicio": "2026-10-14T11:00"}]

# voz falsa: guarda cada fala; o teste decide quando ela termina (window.__fim()) ou falha (window.__erro(tipo)).
# cancel() termina a fala atual como o Chrome (onerror "interrupted") ou, com CANCELA=onend, como Safari e Firefox.
VOZ_FALSA = """
window.__falas = []; window.__chamadas = [];
let atual = null;
class Fala { constructor(t) { this.text = t; } }
const ss = {
  paused: false,
  getVoices: () => [],
  speak(u) { atual = u; __falas.push({ text: u.text, lang: u.lang, rate: u.rate }); setTimeout(() => u.onstart?.()); },
  cancel() { __chamadas.push("cancel"); const u = atual; atual = null;
    if (u) setTimeout(() => "CANCELA" === "onend" ? u.onend?.() : u.onerror?.({ error: "interrupted" })); },
  pause() { __chamadas.push("pause"); this.paused = true; }, resume() { __chamadas.push("resume"); this.paused = false; },
};
window.__fim = () => { const u = atual; atual = null; u?.onend?.(); };
window.__erro = (tipo) => { const u = atual; atual = null; u?.onerror?.({ error: tipo }); };
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
        if not Path(p.chromium.executable_path).exists():
            pytest.skip("Chromium do Playwright não instalado")
        b = p.chromium.launch()  # instalado e não abre: é falha, não pulo
        yield b
        b.close()


def abrir(navegador, caminho="/", idioma="pt", voz=VOZ_FALSA, embed_attr="", resposta=RESPOSTA):
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
            return rota.fulfill(json={"resposta": resposta, "idioma": idioma, "fontes": FONTES})
        arquivo = WEB / (nome.strip("/") or "index.html")
        if not arquivo.is_file():
            return rota.fulfill(status=404, body="")
        tipo = {".html": "text/html", ".js": "text/javascript", ".json": "application/json"}.get(arquivo.suffix)
        return rota.fulfill(body=arquivo.read_bytes(), content_type=tipo or "application/octet-stream")

    pagina.route(f"{ORIGEM}/**", servir)
    pagina.goto(ORIGEM + caminho)
    return pagina


def perguntar(pagina, pergunta="O que o maddog apresentou?"):
    pagina.fill("#q", pergunta)
    pagina.click("#b")
    pagina.wait_for_selector(".partilha")


def falas(pagina):
    return pagina.evaluate("window.__falas")


def chamadas(pagina, nome):
    return pagina.evaluate("window.__chamadas").count(nome)


def controles_escondidos(pagina):
    assert pagina.locator(".ouvir > span").count() == 1
    return pagina.locator(".ouvir > span").evaluate("s => s.hidden")


def foco_aria_pressed(pagina):
    return pagina.evaluate("document.activeElement.getAttribute('aria-pressed')")


@pytest.mark.parametrize("cancela", ["onerror", "onend"])  # cancel() à moda do Chrome e à moda de Safari/Firefox
def test_ouvir_resposta_na_pagina(navegador, cancela):
    pagina = abrir(navegador, voz=VOZ_FALSA.replace("CANCELA", cancela))
    perguntar(pagina)
    ouvir = pagina.get_by_role("button", name="Ouvir resposta")
    assert ouvir.get_attribute("aria-pressed") == "false"
    assert falas(pagina) == []  # nada de autoplay
    assert controles_escondidos(pagina)

    ouvir.click()
    assert ouvir.get_attribute("aria-pressed") == "true"
    assert not controles_escondidos(pagina)
    assert falas(pagina) == [{"text": FRASES[0], "lang": "pt-BR", "rate": 1}]  # sem [n]

    pagina.get_by_role("button", name="Pausar").click()
    assert chamadas(pagina, "pause") == 1
    resumes = chamadas(pagina, "resume")
    pagina.get_by_label("Velocidade").select_option("1.5")  # pausado: não volta a falar sozinho
    assert len(falas(pagina)) == 1
    pagina.get_by_role("button", name="Continuar").click()
    assert chamadas(pagina, "resume") == resumes + 1

    pagina.get_by_label("Velocidade").select_option("1.25")  # recomeça a frase atual na velocidade nova
    pagina.wait_for_timeout(50)  # a fala cancelada termina depois e não pode avançar a fila
    assert falas(pagina)[1:] == [{"text": FRASES[0], "lang": "pt-BR", "rate": 1.25}]

    pagina.get_by_role("button", name="Pausar").focus()
    for frase in FRASES[1:]:
        pagina.evaluate("window.__fim()")
        assert falas(pagina)[-1]["text"] == frase
    pagina.evaluate("window.__fim()")  # acabou: volta ao estado inicial, com o foco no Ouvir
    assert ouvir.get_attribute("aria-pressed") == "false"
    assert controles_escondidos(pagina)
    assert foco_aria_pressed(pagina) == "false"

    ouvir.click()
    pagina.get_by_role("button", name="Parar").click()
    assert ouvir.get_attribute("aria-pressed") == "false"
    assert foco_aria_pressed(pagina) == "false"
    pagina.wait_for_timeout(50)
    assert falas(pagina)[-1]["text"] == FRASES[0] and len(falas(pagina)) == 5  # parar não puxa a próxima frase
    pagina.close()


def test_nova_pergunta_cala_a_anterior(navegador):
    pagina = abrir(navegador)
    perguntar(pagina)
    pagina.get_by_role("button", name="Ouvir resposta").click()
    antes = chamadas(pagina, "cancel")
    perguntar(pagina, "Outra pergunta?")
    assert chamadas(pagina, "cancel") > antes
    assert pagina.get_by_role("button", name="Ouvir resposta").get_attribute("aria-pressed") == "false"
    pagina.close()


def test_erro_de_voz_esconde_o_botao(navegador):
    pagina = abrir(navegador)
    perguntar(pagina)
    ouvir = pagina.get_by_role("button", name="Ouvir resposta")
    ouvir.click()
    pagina.evaluate("window.__erro('audio-busy')")  # passageiro: para, mas o botão fica
    assert ouvir.get_attribute("aria-pressed") == "false" and ouvir.is_visible()
    ouvir.click()
    ouvir.focus()
    pagina.evaluate("window.__erro('voice-unavailable')")
    assert pagina.locator(".ouvir").evaluate("c => c.hidden")
    assert pagina.evaluate("document.activeElement.textContent") == "Copiar resposta"  # o foco não cai no body
    pagina.close()


def test_token_longo_nao_perde_texto(navegador):
    longo = "https://exemplo.org/" + "a" * 330
    pagina = abrir(navegador, resposta=f"Veja {longo} agora [1].")
    perguntar(pagina)
    pagina.get_by_role("button", name="Ouvir resposta").click()
    for _ in range(3):
        pagina.evaluate("window.__fim()")
    assert " ".join(f["text"] for f in falas(pagina)).replace(longo[:200] + " ", longo[:200]) == f"Veja {longo} agora."
    pagina.close()


def test_ouvir_resumo_em_ingles(navegador):
    pagina = abrir(navegador, idioma="en")
    pagina.evaluate("""document.dispatchEvent(new CustomEvent("perguntar", { cancelable: true,
        detail: { pergunta: "Summarize the talk", palestra_id: "x" } }))""")
    pagina.wait_for_selector(".partilha")
    pagina.get_by_role("button", name="Listen to summary").click()
    assert falas(pagina)[0] == {"text": FRASES[0], "lang": "en", "rate": 1}
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
        assert falas(pagina) == [{"text": FRASES[0], "lang": "pt-BR", "rate": 1}]
    pagina.close()


def test_resumo_com_ia_no_componente(navegador):
    pagina = abrir(navegador, "/embed.html", idioma="es")
    pagina.locator("latinoware-catalogo .perg").first.click()
    pagina.get_by_role("button", name="Escuchar resumen").click()
    assert falas(pagina) == [{"text": FRASES[0], "lang": "es", "rate": 1}]
    pagina.close()
