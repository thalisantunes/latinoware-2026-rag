"""Botão "Ouvir" (voz do navegador) na página e no componente, num Chromium sem rede com speechSynthesis simulado.

Precisa do Playwright e do Chromium dele (make testar já traz o pacote; o navegador: uv run --with playwright==1.63.0
playwright install chromium); sem o navegador instalado, os testes são pulados.
"""

import json
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


def abrir(navegador, caminho="/", idioma="pt", voz=VOZ_FALSA, embed_attr="", resposta=RESPOSTA, fontes=FONTES, sem_ia=False, stream=None):
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
            if stream is None:
                return rota.fulfill(status=404, body="")
            return rota.fulfill(body=stream, content_type="text/event-stream")
        if nome == "/ask":
            return rota.fulfill(json={"resposta": resposta, "idioma": idioma, "fontes": fontes} | ({"sem_ia": True} if sem_ia else {}))
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


URL = "https://youtu.be/0WgTllmf2B4?t=11300"
FONTES3 = FONTES + [{"n": 3, "fonte": "resumo", "titulo": "Outra", "url": "https://latinoware.org/c", "inicio": "2026-10-14T12:00"}]


def numeros_no_painel(pagina):
    return pagina.eval_on_selector_all(".fontes .chip[id^=fonte-]", "els => els.map(e => e.id)")


def test_painel_so_com_fontes_citadas_e_numeracao_original(navegador):
    pagina = abrir(navegador, resposta="Veja [2]. Fim.", fontes=FONTES3)
    perguntar(pagina)
    assert numeros_no_painel(pagina) == ["fonte-2"]
    assert pagina.locator(".fontes .chip b").all_inner_texts() == ["[2]"]


def test_painel_some_sem_citacao_e_so_busca_mostra_tudo(navegador):
    pagina = abrir(navegador, resposta="Sem citar nada.", fontes=FONTES3)
    perguntar(pagina)
    assert pagina.locator("#saida h2").count() == 0 and pagina.locator(".fontes").count() == 0
    pagina = abrir(navegador, resposta="Aviso sem citações.", fontes=FONTES3, sem_ia=True)
    pagina.fill("#q", "pergunta")
    pagina.click("#b")
    pagina.wait_for_selector(".fontes")
    assert numeros_no_painel(pagina) == ["fonte-1", "fonte-2", "fonte-3"]


def test_painel_no_stream_so_aparece_no_fim_e_filtrado(navegador):
    def ev(nome, dados):
        return f"event: {nome}\ndata: {json.dumps(dados)}\n\n"
    corpo = (ev("etapa", {"etapa": "buscando"}) + ev("fontes", {"fontes": FONTES3, "idioma": "pt"}) + ev("token", {"t": "Veja [3]."})
             + ev("fim", {"resposta": "Veja [3].", "idioma": "pt", "reaproveitada": False}))
    pagina = abrir(navegador, stream=corpo)
    perguntar(pagina)
    assert numeros_no_painel(pagina) == ["fonte-3"]


def test_url_de_gravacao_vira_link_e_o_ouvir_nao_a_le(navegador):
    texto = f"Assista em {URL}. Também https://evil.example/x e <b>html</b> [1]."
    pagina = abrir(navegador, resposta=texto, fontes=FONTES)
    perguntar(pagina)
    links = pagina.locator(".resposta a:not(.cit)")
    assert links.count() == 1 and links.get_attribute("href") == URL and links.inner_text() == URL
    assert links.get_attribute("target") == "_blank" and "noopener" in links.get_attribute("rel")
    resposta = pagina.locator(".resposta").inner_text()
    assert "https://evil.example/x" in resposta and "<b>html</b>" in resposta  # texto puro, sem link nem HTML
    assert pagina.locator(".resposta b").count() == 0 and pagina.locator(".resposta a[href*=evil]").count() == 0
    pagina.get_by_role("button", name="Ouvir resposta").click()
    assert "youtu" not in falas(pagina)[0]["text"] and "link na página" in falas(pagina)[0]["text"]


@pytest.mark.parametrize("citacao", ["[1-3]", "[1–3]", "[1, 2 e 3]", "[1, 2 and 3]", "[1, 2 y 3]"])
def test_painel_e_links_entendem_intervalo_e_e(navegador, citacao):
    pagina = abrir(navegador, resposta=f"Veja {citacao}.", fontes=FONTES3)
    perguntar(pagina)
    assert numeros_no_painel(pagina) == ["fonte-1", "fonte-2", "fonte-3"]
    assert pagina.locator(".resposta a.cit").all_inner_texts() == ["1", "2", "3"]


def test_citacao_nao_entendida_mostra_todas_as_fontes(navegador):
    pagina = abrir(navegador, resposta="Veja [1 a 3] e [2].", fontes=FONTES3)
    perguntar(pagina)
    assert numeros_no_painel(pagina) == ["fonte-1", "fonte-2", "fonte-3"]  # rede de segurança: nunca nenhuma por engano


def test_grupo_misto_liga_so_os_numeros_validos(navegador):
    pagina = abrir(navegador, resposta="Veja [2, 9].", fontes=FONTES3)
    perguntar(pagina)
    assert numeros_no_painel(pagina) == ["fonte-2"] and pagina.locator(".resposta a.cit").all_inner_texts() == ["2"]


def test_url_sem_lixo_no_href_e_ouvir_mantem_a_pontuacao(navegador):
    texto = f"Veja **{URL}** e ({URL}), ou “{URL}”, depois `{URL}`. Fim {URL}."
    pagina = abrir(navegador, resposta=texto)
    perguntar(pagina)
    hrefs = pagina.eval_on_selector_all(".resposta a:not(.cit)", "els => els.map(e => e.getAttribute('href'))")
    assert hrefs == [URL] * 5
    pagina.get_by_role("button", name="Ouvir resposta").click()
    assert falas(pagina)[0]["text"] == "Veja **link na página** e (link na página), ou “link na página”, depois `link na página`."


def test_ouvir_preserva_ponto_depois_da_url(navegador):
    pagina = abrir(navegador, resposta=f"Assista em {URL}. Fim.")
    perguntar(pagina)
    pagina.get_by_role("button", name="Ouvir resposta").click()
    assert falas(pagina)[0]["text"] == "Assista em link na página."


def test_copiar_sem_fontes_exibidas_nao_leva_bloco_vazio(navegador):
    pagina = abrir(navegador, resposta="Sem citar nada.", fontes=FONTES3)
    perguntar(pagina)
    pagina.evaluate("window.__copiado = null; Object.defineProperty(navigator, 'clipboard', { value: { writeText: (t) => { window.__copiado = t; return Promise.resolve(); } }, configurable: true })")
    pagina.get_by_role("button", name="Copiar resposta").click()
    pagina.wait_for_function("window.__copiado !== null")
    copiado = pagina.evaluate("window.__copiado")
    assert copiado.endswith("Sem citar nada.") and "Fontes" not in copiado
