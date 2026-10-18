"""Etapa 2: encontra as gravações da Latinoware 2026 no YouTube e baixa só o áudio.

As gravações são lives de dia inteiro, uma por espaço e dia, publicadas pelo canal
Itaipu Parquetec com títulos "Latinoware 2026 - Espaço <Sala> - DD/10".

Saída: data/videos.json (metadados) e data/audio/<id>.m4a.
Uso: python 02_baixar_audio.py [--so-metadados] [<id de vídeo ou URL de vídeo/playlist> ...]

O YouTube pode pedir login ("Sign in to confirm you're not a bot") conforme o IP.
Nesse caso, rode com YTDLP_COOKIES_BROWSER=chrome (ou chrome:Perfil, firefox...), que lê os
cookies direto do navegador, ou com YTDLP_COOKIES=/caminho/cookies.txt (formato Netscape).
Sem cookies, o script grava só os metadados.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

DATA = Path(__file__).parent / "data"
AUDIO = DATA / "audio"
YTDLP = [sys.executable, "-m", "yt_dlp", "--js-runtimes", "node", "--sleep-requests", "1"]
CANAL_ID = "UCNYfFA05lPFYMdB1kUkhKcA"  # Itaipu Parquetec, que transmitiu as lives
CANAL = f"https://www.youtube.com/channel/{CANAL_ID}"
# playlists oficiais da Latinoware 2026 (uma por dia) no canal do Itaipu Parquetec
PLAYLISTS = ["PLHC5slR1VDy4", "PLVG4LGm089OA", "PLZtK9mf5VVtE"]
# a busca do YouTube varia entre chamadas; ela complementa a listagem do canal
FONTES = [f"{CANAL}/streams", f"{CANAL}/videos", "ytsearch50:Latinoware 2026 - Espaço"] + [
    f"ytsearch50:Latinoware 2026 Espaço {d}/10" for d in (14, 15, 16)] + [
    f"https://www.youtube.com/playlist?list={p}" for p in PLAYLISTS]
TITULO = re.compile(r"Latinoware 2026 - Espaço (?P<espaco>.+?) - (?P<dia>\d{2})/10")


def cookies():
    if b := os.environ.get("YTDLP_COOKIES_BROWSER"):
        return ["--cookies-from-browser", b]
    c = os.environ.get("YTDLP_COOKIES")
    return ["--cookies", c] if c else []


def descobrir(extras=()):
    """Lives do canal oficial nas fontes fixas e nas extras (ids de vídeo ou URLs de vídeo/playlist passados na
    linha de comando, para vídeos que ainda não aparecem nas listagens)."""
    videos = {}
    avulsas = [e if "/" in e else f"https://www.youtube.com/watch?v={e}" for e in extras]
    for fonte in FONTES + avulsas:
        r = subprocess.run(YTDLP + ["--flat-playlist", "--dump-json", "--playlist-end", "200", fonte],
                           capture_output=True, text=True)
        out = r.stdout
        if fonte in avulsas and not out.strip():  # id avulso bloqueado, privado ou errado: avisa em vez de sumir
            print(f"  {fonte}: {(r.stderr.strip().splitlines() or ['sem resultado'])[-1]}")
        for linha in out.splitlines():
            d = json.loads(linha)
            m = TITULO.search(d.get("title") or "")  # vídeo privado vem sem título
            # só vídeos do canal oficial; a busca pode trazer reenvios de terceiros
            if m and (fonte.startswith(CANAL) or d.get("channel_id") == CANAL_ID):
                videos[d["id"]] = {
                    "id": d["id"],
                    "titulo": d["title"],
                    "espaco": "Espaço " + m["espaco"].strip(),
                    "data": f"2026-10-{m['dia']}",
                    "duracao": d.get("duration"),
                    "url": f"https://youtu.be/{d['id']}",
                }
    return sorted(videos.values(), key=lambda v: (v["data"], v["espaco"], v["id"]))


def completar(v):
    """Pega o início real da live (release_timestamp), usado para alinhar com a grade."""
    r = subprocess.run(YTDLP + cookies() + ["--skip-download", "--dump-json", v["url"]],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return r.stderr.strip().splitlines()[-1] if r.stderr else "erro"
    d = json.loads(r.stdout)
    v["inicio_live"] = d.get("release_timestamp")  # "timestamp" é o upload, não o início da live
    v["capitulos"] = d.get("chapters") or []
    return None


def baixar(v):
    destino = AUDIO / f"{v['id']}.m4a"
    if destino.exists():
        return None
    # m4a nativo do YouTube: o ffmpeg só copia; recodificar opus -> aac roda em ~1x tempo real
    r = subprocess.run(YTDLP + cookies() + ["-x", "--audio-format", "m4a", "-f", "bestaudio[ext=m4a]/bestaudio",
                                            "-o", str(AUDIO / "%(id)s.%(ext)s"), v["url"]],
                       capture_output=True, text=True)
    return None if r.returncode == 0 else (r.stderr.strip().splitlines() or ["erro"])[-1]


def main():
    AUDIO.mkdir(parents=True, exist_ok=True)
    antigos = {}
    if (DATA / "videos.json").exists():
        antigos = {v["id"]: v for v in json.loads((DATA / "videos.json").read_text())}
    extras = [a for a in sys.argv[1:] if a != "--so-metadados"]  # id de vídeo pode começar com "-"
    if desconhecidas := [a for a in extras if a.startswith("--")]:
        sys.exit(f"opção desconhecida: {' '.join(desconhecidas)} (só existe --so-metadados)")
    # campo vazio na listagem (ex.: duração de vídeo privado) não apaga o que já se sabia
    videos = [antigos.get(v["id"], {}) | {k: x for k, x in v.items() if x is not None} for v in descobrir(extras)]
    # vídeo que entrou por id avulso e não aparece nas listagens continua no arquivo
    achados = {v["id"] for v in videos}
    videos += [v for vid, v in antigos.items() if vid not in achados]
    print(f"{len(videos)} lives encontradas")

    so_metadados = "--so-metadados" in sys.argv
    erros = 0
    for v in videos:
        erro = None if v.get("inicio_live") else completar(v)
        if not erro and not so_metadados:
            erro = baixar(v)
        v["audio"] = (AUDIO / f"{v['id']}.m4a").exists()
        # bloqueado (reivindicação) ou privado: listado, mas não dá para assistir; não vira link no catálogo
        v["indisponivel"] = bool(erro and re.search(r"unavailable|private", erro, re.I)) and not v["audio"]
        if erro:
            erros += 1
            print(f"  {v['id']} {v['titulo']}: {erro}")
        (DATA / "videos.json").write_text(json.dumps(videos, ensure_ascii=False, indent=1))

    print(f"áudios em disco: {sum(v['audio'] for v in videos)}/{len(videos)}; erros: {erros}")
    if erros and not cookies():
        print("dica: o YouTube pode estar pedindo login; veja YTDLP_COOKIES_BROWSER no README")


if __name__ == "__main__":
    main()
