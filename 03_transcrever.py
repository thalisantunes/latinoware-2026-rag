"""Etapa 3: transcreve os áudios de data/audio/ com faster-whisper na GPU.

Saída: data/transcricoes/<id>.json com segmentos {inicio, fim, texto} em segundos.
As lives misturam palestras em português, espanhol e inglês, então a detecção de idioma
é feita por segmento (multilingual=True). Já transcritos são pulados.
"""

import json
import os
import time
from pathlib import Path

from faster_whisper import BatchedInferencePipeline, WhisperModel

DATA = Path(__file__).parent / "data"
MODELO = os.environ.get("WHISPER_MODEL", "large-v3-turbo")


def main():
    saida = DATA / "transcricoes"
    saida.mkdir(parents=True, exist_ok=True)
    audios = sorted((DATA / "audio").glob("*.m4a"))
    pendentes = [a for a in audios if not (saida / f"{a.stem}.json").exists()]
    print(f"{len(audios)} áudios, {len(pendentes)} a transcrever com {MODELO}")
    if not pendentes:
        return

    modelo = BatchedInferencePipeline(WhisperModel(MODELO, device="cuda", compute_type="float16"))
    for audio in pendentes:
        t0 = time.time()
        segmentos, info = modelo.transcribe(str(audio), batch_size=8, vad_filter=True,
                                            multilingual=True, beam_size=5)
        segs = [{"inicio": round(s.start, 2), "fim": round(s.end, 2), "texto": s.text.strip()}
                for s in segmentos if s.text.strip()]
        tmp = saida / f"{audio.stem}.json.tmp"
        tmp.write_text(json.dumps({"video": audio.stem, "modelo": MODELO, "idioma": info.language,
                                   "duracao": info.duration, "segmentos": segs},
                                  ensure_ascii=False))
        tmp.rename(saida / f"{audio.stem}.json")
        print(f"  {audio.stem}: {len(segs)} segmentos, {info.duration / 60:.0f} min de áudio "
              f"em {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
