"""Etapa 11: liga os vídeos individuais de cada palestra (quando o organizador publicar) às palestras da grade.

Uso: python 11_videos_palestras.py <playlist ou canal> [...]  [--gravar]

Lista os vídeos com o yt-dlp (só metadados, sem baixar) e casa cada título com uma palestra pelo título
normalizado e pelos nomes dos palestrantes. Sem --gravar é só ensaio: mostra o mapa, os casos duvidosos e
os vídeos sem palestra. Com --gravar, escreve data/videos_palestras.json {uid: {video_id, titulo, nota}}, que
o 07_exportar_catalogo.py usa para o botão "Assistir" ir direto ao vídeo da palestra (a live fica de reserva).
Casos duvidosos não entram: corrija à mão em data/videos_palestras.json se preciso.
"""

import importlib.util
import json
import re
import subprocess
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

RAIZ = Path(__file__).parent
spec = importlib.util.spec_from_file_location("indexar", RAIZ / "04_indexar.py")
indexar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(indexar)

ACEITA, DUVIDA = 0.8, 0.6  # nota mínima para gravar e para listar como dúvida


def norm(s):
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"latinoware\s*20\d\d", " ", s)  # o nome do evento aparece em todo título
    return " ".join(re.findall(r"[a-z0-9]+", s))


def nota(titulo_video, palestra):
    """Semelhança do título (0 a 1) mais um bônus se o sobrenome de um palestrante aparece no título.
    O título do vídeo é comparado inteiro e por partes ("Latinoware 2026 | Título - Palestrante | Espaço")."""
    v, t = norm(titulo_video), norm(palestra["titulo"])
    partes = [v] + [norm(x) for x in re.split(r"\s[|–-]\s|\|", titulo_video) if norm(x)]
    base = max(max(SequenceMatcher(None, x, t).ratio() for x in partes), 1.0 if t and t in v else 0)
    sobrenomes = {norm(s["nome"]).split()[-1] for s in palestra["palestrantes"] if norm(s["nome"])}
    return min(1.0, base + 0.15 * any(n in v.split() for n in sobrenomes if len(n) > 3))


def casar(videos, palestras):
    """[(video, melhor palestra ou None, nota)], uma palestra por vídeo; keynotes repetidas por sala viram a 1ª."""
    unicas = {}
    for p in palestras:
        unicas.setdefault(norm(p["titulo"]), p)
    saida = []
    for v in videos:
        melhor, n = max(((p, nota(v["titulo"], p)) for p in unicas.values()), key=lambda x: x[1], default=(None, 0))
        saida.append((v, melhor if n >= DUVIDA else None, n))
    return saida


def listar(fonte):
    out = subprocess.run([sys.executable, "-m", "yt_dlp", "--flat-playlist", "--dump-json", fonte],
                         capture_output=True, text=True, check=True).stdout
    return [{"id": d["id"], "titulo": d.get("title", "")} for d in map(json.loads, out.splitlines())]


def main():
    fontes = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not fontes:
        sys.exit(__doc__)
    palestras = json.loads((indexar.DATA / "site" / "palestras.json").read_text())
    videos = [v for f in fontes for v in listar(f)]
    mapa, duvidas, sem = {}, [], []
    for v, p, n in casar(videos, palestras):
        if p and n >= ACEITA:
            mapa[indexar.uid(p)] = {"video_id": v["id"], "titulo": v["titulo"], "nota": round(n, 2)}
        elif p:
            duvidas.append(f"  {n:.2f}  {v['titulo']}  →  {p['titulo']}")
        else:
            sem.append(f"  {v['titulo']}")
    print(f"{len(videos)} vídeos: {len(mapa)} casados, {len(duvidas)} duvidosos, {len(sem)} sem palestra")
    print("duvidosos:", *duvidas, sep="\n") if duvidas else None
    print("sem palestra:", *sem, sep="\n") if sem else None
    if "--gravar" in sys.argv:
        (indexar.DATA / "videos_palestras.json").write_text(json.dumps(mapa, ensure_ascii=False, indent=1))
        print("data/videos_palestras.json gravado; rode make catalogo")
    else:
        print("ensaio: nada gravado (use --gravar)")


if __name__ == "__main__":
    main()
