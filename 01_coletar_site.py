"""Etapa 1: coleta a grade e os palestrantes da Latinoware 2026 em latinoware.org.

Fontes (todas públicas):
- grade: https://latinoware.org/programacao-latinoware/ (cartões do plugin SWGE)
- detalhe de cada atividade: /wp-json/swge-stats/v1/activity-modal
- palestrantes: /wp-json/wp/v2/palestrante + página pública de cada um

Saída: data/site/palestras.json e data/site/palestrantes.json.
Guarda só o que a RAG usa entre o que o site publica: nada de e-mail, telefone ou redes sociais.
"""

import json
import re
import sys
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

BASE = "https://latinoware.org"
OUT = Path(__file__).parent / "data" / "site"
HEADERS = {"User-Agent": "latinoware-2026-rag/0.1 (+https://github.com/thalisantunes/latinoware-2026-rag)"}
PAUSA = 0.3  # segundos entre requisições, para não pesar no site

client = httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True)


def get(url, **params):
    for tentativa in range(3):
        try:
            r = client.get(url, params=params)
            r.raise_for_status()
            time.sleep(PAUSA)
            return r
        except httpx.HTTPError:
            if tentativa == 2:
                raise
            time.sleep(2 * (tentativa + 1))


def texto(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def coletar_grade():
    soup = BeautifulSoup(get(f"{BASE}/programacao-latinoware/").text, "html.parser")
    palestras = []
    for card in soup.select("div.activity.schedule-card"):
        coluna = card.find_parent("div", class_="col-activity")
        botao = card.select_one("button.button-modal")
        palestras.append({
            "id": card["id"].removeprefix("activity-card-"),
            "atividade_id": botao["data-swge-activity-id"],
            "agenda_id": botao["data-swge-schedule-key"],
            "titulo": texto(card.select_one(".wrap-activity")),
            "tipo": card.get("data-type", ""),
            "trilha": card.get("data-track", ""),
            "espaco": texto(coluna.select_one("h6")) if coluna else "",
            "inicio": card.get("data-schedule-start", ""),
            "fim": card.get("data-schedule-end", ""),
        })
    return palestras


def detalhar(p):
    html = get(f"{BASE}/wp-json/swge-stats/v1/activity-modal",
               activity=p["atividade_id"], schedule=p["agenda_id"]).json()["html"]
    m = BeautifulSoup(html, "html.parser")
    titulo = m.select_one(".schedule-modal-title")
    if titulo:  # o cartão da grade às vezes vem truncado com ".."
        p["titulo"] = texto(titulo)
    blocos = m.select(".swge-description-block")
    p["resumo"] = "\n".join(texto(b) for b in blocos) or texto(m.select_one(".schedule-modal-description"))
    p["palestrantes"] = [
        {"nome": texto(a), "url": a["href"]} for a in m.select(".schedule-modal-speaker a")
    ] or [{"nome": texto(s), "url": ""} for s in m.select(".schedule-modal-speaker")]
    for det in m.select(".schedule-modal-detail"):
        rotulo = texto(det.select_one(".label")).rstrip(":").lower()
        valor = texto(det.select_one(".value"))
        if rotulo == "idioma":
            p["idioma"] = valor
        elif rotulo == "tipo de apresentação":
            p["formato"] = valor
    p["url"] = f"{BASE}/programacao-latinoware/#activity-card-{p['id']}"


def coletar_palestrantes():
    pessoas, pagina = [], 1
    while True:
        r = get(f"{BASE}/wp-json/wp/v2/palestrante", per_page=100, page=pagina)
        pessoas += r.json()
        if pagina >= int(r.headers.get("X-WP-TotalPages", 1)):
            break
        pagina += 1
    saida = []
    for i, d in enumerate(pessoas, 1):
        if i % 25 == 0:
            print(f"  palestrantes {i}/{len(pessoas)}", flush=True)
        s = BeautifulSoup(get(d["link"]).text, "html.parser")
        org_link = s.find("span", string=re.compile("Empresa", re.I))
        org_el = org_link.find_parent("div").find("a") if org_link else None
        bandeira = s.select_one("img.mt-country-flag")
        saida.append({
            "id": d["id"],
            "nome": BeautifulSoup(d["title"]["rendered"], "html.parser").get_text(),
            "url": d["link"],
            "bio": texto(BeautifulSoup(d["content"]["rendered"], "html.parser")),
            "organizacao": (org_el.img.get("alt", "") if org_el and org_el.img else texto(org_el)) if org_el else "",
            "organizacao_url": org_el["href"] if org_el else "",
            "pais": bandeira.get("alt", "") if bandeira else "",
            "categorias": [texto(a) for a in s.select("article header a.mt-single-speaker-category")],
        })
    return saida


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    palestras = coletar_grade()
    print(f"grade: {len(palestras)} atividades")
    if not palestras:
        sys.exit("grade vazia: o layout de latinoware.org mudou? Nada foi gravado.")
    for i, p in enumerate(palestras, 1):
        detalhar(p)
        if i % 25 == 0:
            print(f"  detalhes {i}/{len(palestras)}", flush=True)
    (OUT / "palestras.json").write_text(json.dumps(palestras, ensure_ascii=False, indent=1))

    palestrantes = coletar_palestrantes()
    (OUT / "palestrantes.json").write_text(json.dumps(palestrantes, ensure_ascii=False, indent=1))

    sem_resumo = sum(1 for p in palestras if not p["resumo"])
    print(f"palestras: {len(palestras)} (sem resumo: {sem_resumo}); palestrantes: {len(palestrantes)}")


if __name__ == "__main__":
    main()
