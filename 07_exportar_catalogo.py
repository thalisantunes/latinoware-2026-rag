"""Etapa 7: exporta web/catalogo.json, o catálogo público de palestras usado pela página e pelo
componente <latinoware-catalogo>. Não precisa do Weaviate.

Traz só metadados, resumo curto (até 280 caracteres, com link para o texto no site) e o link
para o instante da palestra na live. Bios, resumos completos e transcrições ficam de fora.
"""

import importlib.util
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).parent
spec = importlib.util.spec_from_file_location("indexar", RAIZ / "04_indexar.py")
indexar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(indexar)

VERSAO = 1  # igual à VERSAO de web/latinoware-catalogo.js
RESUMO_MAX = 280


def resumo_curto(texto):
    texto = " ".join(texto.split())
    if len(texto) <= RESUMO_MAX:
        return texto
    return texto[:RESUMO_MAX - 1].rsplit(" ", 1)[0].rstrip(".,;:") + "…"


def nome_curto(nome):
    """'Cesar Augusto de Azambuja Brod' e 'Cesar Brod' viram ('cesar', 'brod')."""
    s = unicodedata.normalize("NFD", re.sub(r"\(.*?\)", "", nome)).encode("ascii", "ignore").decode().lower().split()
    return (s[0], s[-1]) if s else ()


def main():
    data = indexar.DATA
    palestras = json.loads((data / "site" / "palestras.json").read_text())
    pessoas = json.loads((data / "site" / "palestrantes.json").read_text())
    videos = indexar.carregar_json(data / "videos.json", [])
    manual = indexar.carregar_json(RAIZ / "alinhamento.json", {})
    if not palestras:
        sys.exit("grade vazia: rode make coletar")
    alinhadas = indexar.alinhar_palestras(palestras, videos, manual)
    duracao = {v["id"]: v["duracao"] for v in videos}
    # foto pública de cada palestrante no site (10_fotos.py referencias); o componente faz hotlink
    fotos = indexar.carregar_json(data / "fotos" / "referencias.json", {})
    transcritos = {v["id"] for v in videos if (data / "transcricoes" / f"{v['id']}.json").exists()}
    if len(transcritos) < len(videos):
        # sem transcrição não dá para saber se a live transmitiu o áudio de cada palestra
        print(f"aviso: {len(videos) - len(transcritos)} lives sem transcrição; keynotes podem apontar para sala sem áudio")

    saida = []
    for p in sorted(palestras, key=lambda p: (p["inicio"], p["espaco"], p["titulo"])):
        a = alinhadas.get(indexar.uid(p), {})
        if a and not 0 <= a["t_inicio"] < duracao[a["video_id"]]:
            sys.exit(f"{indexar.uid(p)}: t_inicio fora do vídeo")
        saida.append({
            "uid": indexar.uid(p), "id": p["id"], "titulo": " ".join(p["titulo"].split()).strip("'\"“”‘’ ."),
            "tipo": p["tipo"], "trilha": p["trilha"], "espaco": p["espaco"],
            "data": p["inicio"][:10], "hora_inicio": p["inicio"][11:16], "hora_fim": p["fim"][11:16],
            "idioma": p.get("idioma", ""), "resumo_curto": resumo_curto(p["resumo"]), "url_site": p["url"],
            "palestrantes": [{"nome": s["nome"], "url": s["url"]} for s in p["palestrantes"]],
            "video_id": a.get("video_id"), "t_inicio": a.get("t_inicio"), "t_fim": a.get("t_fim"),
            "url_video": a.get("url_video"), "alinhamento": a.get("alinhamento"),
            "transcrito": a.get("video_id") in transcritos,
        })

    # a grade às vezes aponta para outra URL da mesma pessoa (slug do nome x swge-<hash>)
    por_nome = {nome_curto(s["nome"]): s["url"] for s in pessoas}
    urls = {s["url"] for s in pessoas}
    uids_de = {}
    for p in saida:
        for s in p["palestrantes"]:
            if s["url"] not in urls:
                s["url"] = por_nome.get(nome_curto(s["nome"]), s["url"])
            uids_de.setdefault(s["url"], []).append(p["uid"])
    catalogo = {
        "versao": VERSAO,
        "evento": {"nome": "Latinoware", "ano": int(palestras[0]["inicio"][:4]), "site": "https://latinoware.org",
                   "datas": sorted({p["data"] for p in saida}),
                   "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        "videos": [{"id": v["id"], "titulo": v["titulo"], "espaco": v["espaco"], "data": v["data"],
                    "duracao_s": v["duracao"], "inicio_live": v.get("inicio_live"),
                    "url": f"https://youtu.be/{v['id']}"} for v in videos],
        "palestras": saida,
        "palestrantes": [{"id": s["id"], "nome": s["nome"], "url": s["url"], "organizacao": s["organizacao"],
                          "pais": s["pais"], "palestras": uids_de.get(s["url"], []),
                          "foto": fotos.get(str(s["id"]), {}).get("url_foto")} for s in pessoas],
    }
    destino = RAIZ / "web" / "catalogo.json"
    destino.write_text(json.dumps(catalogo, ensure_ascii=False, separators=(",", ":")) + "\n")
    com_video = sum(p["url_video"] is not None for p in saida)
    print(f"{destino.name}: {len(saida)} palestras ({com_video} com vídeo), {len(pessoas)} palestrantes, "
          f"{destino.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
