"""Etapa 10: fotos dos palestrantes no evento (álbuns do Flickr oficial), por reconhecimento facial.

Uso (precisa de `uv sync --extra fotos --extra rerank`):
  python 10_fotos.py referencias              baixa a foto de cada palestrante do site latinoware.org
  python 10_fotos.py pasta <dir> <álbum>      registra os originais enviados pelo organizador para um álbum
  python 10_fotos.py feed <álbum>             liga as fotos locais às do Flickr (link e miniatura) e avisa as novas
  python 10_fotos.py casar                    rostos das fotos novas x referências; limiar calibrado
  python 10_fotos.py exportar                 web/fotos.json só com os pares aprovados em data/fotos/revisao.json
  python 10_fotos.py limpar                   apaga os vetores faciais (fim do casamento)

<álbum> é a URL do álbum no Flickr. Autor e licença de cada álbum vêm de data/fotos/albuns.json:
{"<id do álbum>": {"autor": "Itaipu Parquetec", "licenca": "4"}} (códigos de licença em LICENCAS).
Sem API do Flickr (não há mais chave gratuita): o feed público do álbum (sem chave) traz só as 20 fotos mais
recentes, com link e miniatura; é usado para ligar foto local à página dela no Flickr (o título no Flickr é o
nome do arquivo original) e para avisar quando o álbum ganhou fotos novas.

Regras (decisão do Thalis, curador da Latinoware; biometria é dado sensível, LGPD art. 11):
- vetores faciais só em data/fotos/embeddings/ (fora do git, permissão 700), apagados por `make fotos-limpar`;
- publicamos só miniatura e link da foto no Flickr oficial, com autor e licença; nada de re-hospedar;
- todo par passa por revisão humana (data/fotos/revisao.json) antes de ir para web/fotos.json;
- canal de remoção: privacidade@ilove.the.br.
"""

import json
import os

# o TensorFlow do DeepFace não compila para a RTX 5060 Ti (Blackwell, sm_120): roda em CPU (~1 s por foto)
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

RAIZ = Path(__file__).parent
FOTOS = RAIZ / "data" / "fotos"
REFS = FOTOS / "palestrantes"
IMAGENS = (".jpg", ".jpeg", ".png", ".webp")
VETORES = FOTOS / "embeddings"
MODELO, DETECTOR = "ArcFace", "retinaface"
# distância cosseno ArcFace; o limiar sai da calibração (percentil baixo entre pessoas diferentes)
LIMIAR = float(os.environ.get("FOTOS_LIMIAR", 0.45))
DUVIDA = float(os.environ.get("FOTOS_DUVIDA", 0.55))  # entre LIMIAR e DUVIDA: vai para a lista de dúvidas
# códigos de licença do Flickr (flickr.photos.licenses.getInfo)
LICENCAS = {"0": "Todos os direitos reservados", "1": "CC BY-NC-SA 2.0", "2": "CC BY-NC 2.0", "3": "CC BY-NC-ND 2.0",
            "4": "CC BY 2.0", "5": "CC BY-SA 2.0", "6": "CC BY-ND 2.0", "7": "Sem restrições de direitos conhecidas",
            "8": "Obra do governo dos EUA", "9": "CC0", "10": "Domínio público"}


def baixar(cli, url, destino):
    """Grava só se a resposta for uma imagem; erro HTTP ou página de erro não viram foto."""
    r = cli.get(url)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image/"):
        raise ValueError(f"{url}: não é imagem ({r.headers.get('content-type')})")
    destino.write_bytes(r.content)


def referencias():
    """Foto principal (wp-post-image) da página de cada palestrante."""
    REFS.mkdir(parents=True, exist_ok=True)
    pessoas = json.loads((RAIZ / "data" / "site" / "palestrantes.json").read_text())
    refs, faltam = {}, []
    with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "latinoware-2026-rag"}) as cli:
        for s in pessoas:
            html = cli.get(s["url"]).text
            m = re.search(r'<img[^>]+src="([^"]+)"[^>]*class="[^"]*wp-post-image', html) or \
                re.search(r'<img[^>]+class="[^"]*wp-post-image[^"]*"[^>]+src="([^"]+)"', html)
            if not m:
                faltam.append(s["nome"])
                continue
            foto = urljoin(s["url"], m[1])  # src relativo ou com ?ver= também vale
            destino = REFS / f"{s['id']}{Path(urlparse(foto).path).suffix.lower() or '.jpg'}"
            try:
                if not destino.exists():
                    baixar(cli, foto, destino)
            except (httpx.HTTPError, ValueError) as e:  # uma foto ruim não derruba as outras
                faltam.append(f"{s['nome']} ({e})")
                continue
            refs[str(s["id"])] = {"url_foto": foto, "arquivo": destino.name}
    (FOTOS / "referencias.json").write_text(json.dumps(refs, ensure_ascii=False, indent=1))
    print(f"referências: {len(refs)} de {len(pessoas)} palestrantes; sem foto: {len(faltam)}")


def id_album(url):
    m = re.search(r"/(?:albums|sets)/(\d{10,})", url or "")
    if not m:
        sys.exit(f"URL de álbum do Flickr inválida: {url!r} (esperado .../albums/<id>)")
    return m[1]


def pasta(diretorio, album):
    """Registra cada foto da pasta (originais do organizador) no álbum: arquivo local, autor e licença do álbum.
    Link e miniatura ficam no álbum até o `feed` achar a página da foto no Flickr."""
    aid = id_album(album)
    albuns = json.loads((FOTOS / "albuns.json").read_text()) if (FOTOS / "albuns.json").exists() else {}
    if aid not in albuns:
        sys.exit(f"falta o álbum {aid} em data/fotos/albuns.json (autor e licença para o crédito)")
    arq = FOTOS / "flickr.json"
    fotos = json.loads(arq.read_text()) if arq.exists() else {}
    antes, vistos = len(fotos), {}
    for f in sorted(Path(diretorio).rglob("*")):
        if f.suffix.lower() not in IMAGENS:
            continue
        rel = f.relative_to(diretorio).with_suffix("").as_posix()  # subpastas entram no id
        fid = f"{aid}:{rel}"
        if fid in vistos:  # mesmo nome com extensão diferente: ficaria uma só
            print(f"aviso: {f} e {vistos[fid]} têm o mesmo nome; renomeie um deles")
            continue
        vistos[fid] = f
        entrada = fotos.setdefault(fid, {"id": fid, "titulo": f.stem, "album": aid, "autor": albuns[aid]["autor"],
                                         "licenca": albuns[aid]["licenca"], "url_pagina": album, "url_thumb": None})
        entrada["arquivo"] = str(f.resolve())  # pasta movida: o caminho novo vale, o link do Flickr fica
    arq.write_text(json.dumps(fotos, ensure_ascii=False, indent=1))
    print(f"pasta: {len(fotos) - antes} fotos novas registradas, {len(fotos)} no total")


def feed(album):
    """Feed público do álbum (sem chave, 20 mais recentes): liga foto local à página e miniatura no Flickr pelo
    título (= nome do arquivo) e lista as fotos do Flickr que ainda não estão na pasta."""
    aid = id_album(album)
    with httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "latinoware-2026-rag"}) as cli:
        m = re.search(r'"nsid":"(\d+@N\d+)"', cli.get(album).text)
        if not m:
            sys.exit(f"não achei o dono do álbum na página {album}")
        nsid = m[1]
        r = cli.get("https://www.flickr.com/services/feeds/photoset.gne",
                    params={"set": aid, "nsid": nsid, "format": "json", "nojsoncallback": 1})
        r.raise_for_status()
    arq = FOTOS / "flickr.json"
    fotos = json.loads(arq.read_text()) if arq.exists() else {}
    por_titulo = {}
    for f in fotos.values():
        if "titulo" in f:
            por_titulo.setdefault((f["album"], f["titulo"]), []).append(f)
    ligadas, novas = 0, []
    # o feed do Flickr escapa apóstrofo como \' (JSON inválido)
    for item in json.loads(r.text.replace("\\'", "'"))["items"]:
        titulo = Path(item["title"]).stem if Path(item["title"]).suffix.lower() in IMAGENS else item["title"]
        locais = por_titulo.get((aid, titulo), [])
        if not locais:
            novas.append(titulo)
            continue
        if len(locais) > 1:  # mesmo nome em subpastas: não dá para saber qual é
            print(f"aviso: {len(locais)} fotos locais chamadas {titulo}; nenhuma ligada")
            continue
        local = locais[0]
        if local["url_thumb"] is None:
            local["url_pagina"] = item["link"].split("/in/")[0].rstrip("/") + "/"
            local["url_thumb"] = item["media"]["m"].replace("_m.", "_q.")  # miniatura quadrada 150 px
            ligadas += 1
    arq.write_text(json.dumps(fotos, ensure_ascii=False, indent=1))
    print(f"feed: {ligadas} fotos ligadas ao Flickr; {len(novas)} do Flickr ainda fora da pasta"
          + (f": {', '.join(novas)}" if novas else ""))


def vetores_de(caminho):
    """Vetores faciais de uma imagem: [(vetor, área do rosto)]; lista vazia se não há rosto.
    Imagem ilegível levanta erro: não é guardada como "sem rosto" e entra de novo na próxima rodada."""
    from deepface import DeepFace
    try:
        faces = DeepFace.represent(str(caminho), model_name=MODELO, detector_backend=DETECTOR, align=True)
    except ValueError as e:
        if "could not be detected" in str(e):
            return []
        raise
    return [(f["embedding"], f["facial_area"]["w"] * f["facial_area"]["h"]) for f in faces]


def guardar(nome, dados):
    import numpy as np
    VETORES.mkdir(parents=True, exist_ok=True)
    VETORES.chmod(0o700)
    arq = VETORES / f"{nome}.npy"
    np.save(arq, np.array(dados, dtype=object), allow_pickle=True)
    arq.chmod(0o600)


def carregar(nome):
    import numpy as np
    arq = VETORES / f"{nome}.npy"
    return np.load(arq, allow_pickle=True).item() if arq.exists() else {}


def distancia(a, b):
    import numpy as np
    a, b = np.asarray(a), np.asarray(b)
    return float(1 - a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def casar():
    refs = json.loads((FOTOS / "referencias.json").read_text())
    fotos = json.loads((FOTOS / "flickr.json").read_text()) if (FOTOS / "flickr.json").exists() else {}
    vet_refs = carregar("referencias")
    for pid, r in refs.items():  # referência: o maior rosto da foto do site
        if pid not in vet_refs:
            faces = vetores_de(REFS / r["arquivo"])
            vet_refs[pid] = max(faces, key=lambda f: f[1])[0] if faces else None
    guardar("referencias", vet_refs)
    vet_fotos = carregar("flickr")
    sem_arquivo = [fid for fid, f in fotos.items() if not f.get("arquivo")]
    if sem_arquivo:
        print(f"aviso: {len(sem_arquivo)} fotos sem arquivo local (rode `pasta`); ficam de fora")
    novas = [fid for fid, f in fotos.items() if fid not in vet_fotos and f.get("arquivo")]  # só fotos não vistas
    try:
        for i, fid in enumerate(novas, 1):
            try:
                vet_fotos[fid] = vetores_de(fotos[fid]["arquivo"])
            except ValueError as e:
                print(f"  {fid}: {e}")
            if i % 50 == 0:  # um erro adiante não perde o que já foi calculado
                guardar("flickr", vet_fotos)
    finally:
        guardar("flickr", vet_fotos)

    calibrar(vet_refs)
    pares, duvidas = [], []
    validos = {pid: v for pid, v in vet_refs.items() if v is not None}
    if not validos:
        sys.exit("nenhuma referência com rosto: rode `referencias` antes")
    for fid, faces in vet_fotos.items():
        maior = max((a for _, a in faces), default=0)
        for vetor, area in faces:
            if area < 0.25 * maior:  # plateia ao fundo: só rostos em foco na foto
                continue
            pid, d = min(((pid, distancia(vetor, ref)) for pid, ref in validos.items()), key=lambda x: x[1])
            if d <= LIMIAR:
                pares.append({"palestrante_id": pid, "foto_id": fid, "distancia": round(d, 3)})
            elif d <= DUVIDA:
                duvidas.append({"palestrante_id": pid, "foto_id": fid, "distancia": round(d, 3)})
    # dois rostos da mesma foto com a mesma pessoa: fica o par de menor distância
    melhor = {}
    for p in sorted(pares + duvidas, key=lambda p: p["distancia"]):
        melhor.setdefault((p["palestrante_id"], p["foto_id"]), p)
    pares = [p for p in melhor.values() if p["distancia"] <= LIMIAR]
    duvidas = [p for p in melhor.values() if p["distancia"] > LIMIAR]
    arq = FOTOS / "casamentos.json"  # quem aparece em qual foto: só o dono da máquina lê
    arq.write_text(json.dumps({"pares": pares, "duvidas": duvidas}, indent=1))
    arq.chmod(0o600)
    print(f"casar: {len(novas)} fotos novas, {len(vet_fotos)} no total; {len(pares)} pares, {len(duvidas)} dúvidas; "
          f"referências com rosto: {len(validos)} de {len(vet_refs)}")
    print("revise em data/fotos/revisao.json: {\"<palestrante_id>:<foto_id>\": true|false}; depois `exportar`")


def calibrar(vet_refs):
    """Sem fotos repetidas da mesma pessoa, mede a distância entre pessoas diferentes: o limiar precisa ficar
    abaixo do menor valor observado (precisão antes de cobertura)."""
    validos = [v for v in vet_refs.values() if v is not None]
    ds = sorted(distancia(a, b) for i, a in enumerate(validos) for b in validos[i + 1:])
    if ds:
        p = lambda q: ds[int(q * (len(ds) - 1))]  # noqa: E731
        print(f"calibração: {len(ds)} pares de pessoas diferentes; menor {ds[0]:.3f}, p0,1% {p(0.001):.3f}, "
              f"p1% {p(0.01):.3f}; limiar {LIMIAR} (dúvida até {DUVIDA})")
        if ds[0] <= LIMIAR:
            print("aviso: há pessoas diferentes abaixo do limiar; reduza FOTOS_LIMIAR")


def exportar():
    """web/fotos.json: só pares aprovados na revisão humana, com crédito e link para o Flickr."""
    fotos = json.loads((FOTOS / "flickr.json").read_text())
    revisao = json.loads((FOTOS / "revisao.json").read_text()) if (FOTOS / "revisao.json").exists() else {}
    casados = json.loads((FOTOS / "casamentos.json").read_text())
    saida = {}
    for p in casados["pares"] + casados["duvidas"]:
        if revisao.get(f"{p['palestrante_id']}:{p['foto_id']}") is True:
            f = fotos[p["foto_id"]]
            saida.setdefault(p["palestrante_id"], []).append({k: f[k] for k in (
                "id", "url_pagina", "url_thumb", "autor", "licenca", "album")} | {
                "licenca_nome": LICENCAS[str(f["licenca"])]})  # código novo do Flickr: falha em vez de omitir
    (RAIZ / "web" / "fotos.json").write_text(json.dumps(
        {"versao": 1, "palestrantes": [{"palestrante_id": k, "fotos": v} for k, v in sorted(saida.items())]},
        ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"fotos.json: {sum(len(v) for v in saida.values())} fotos de {len(saida)} palestrantes")


def limpar():
    import shutil
    shutil.rmtree(VETORES, ignore_errors=True)
    print("vetores faciais apagados")


if __name__ == "__main__":
    comando = sys.argv[1] if len(sys.argv) > 1 else ""
    acoes = {"referencias": referencias, "casar": casar, "exportar": exportar, "limpar": limpar}
    if comando == "pasta" and len(sys.argv) == 4:
        pasta(sys.argv[2], sys.argv[3])
    elif comando == "feed" and len(sys.argv) == 3:
        feed(sys.argv[2])
    elif comando in acoes:
        acoes[comando]()
    else:
        sys.exit(__doc__)
