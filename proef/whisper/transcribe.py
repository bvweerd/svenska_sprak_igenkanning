"""Vraag 1 — wát zeg je? KB-Whisper (KBLab) via faster-whisper, op de CPU.

Per opname: herkende tekst, woordfoutpercentage t.o.v. de verwachte zin én t.o.v. wat er
werkelijk gezegd is (kolom 'gezegd' bij D07/D08), zekerheid per woord en rekentijd.
Een D-opname is 'gevonden' als de herkende tekst afwijkt van de goede zin.

  python transcribe.py           alle opnames, alle maten → resultaten/whisper.csv
  python transcribe.py --server  API voor de webpagina (maat: WHISPER_API_MODEL, standaard small)
"""
import os
import sys
import time
import wave

import numpy as np
from faster_whisper import WhisperModel

from proef_common import (RESULTATEN, Cache, inhoud_hash, foutpercentage, normaliseer, opnames, rij_voor_verzoek,
                          schrijf_csv, serveer, zin_voor, zinnen)

MODELLEN = os.environ.get("WHISPER_MODELLEN", "tiny base small").split()
MAP = os.environ.get("WHISPER_MAP", "/modellen")
THREADS = int(os.environ.get("WHISPER_THREADS", "0"))  # 0 = alle kernen


def laad(maat):
    return WhisperModel(f"{MAP}/kb-whisper-{maat}", device="cpu", compute_type="int8",
                        cpu_threads=THREADS)


def lees_wav(pad):
    """16 kHz mono 16-bit wav (gemaakt door prep of de webpagina) → float32-array.
    Zelf inlezen voorkomt versieproblemen met PyAV in faster-whisper."""
    with wave.open(str(pad), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1, f"{pad}: geen 16 kHz mono"
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def analyseer(model, maat, spreker, zin_id, wav, r):
    t0 = time.perf_counter()
    # Geen vorige tekst als context: elke opname staat los, zoals in een oefening.
    segmenten, _ = model.transcribe(lees_wav(wav), language="sv", beam_size=5,
                                    condition_on_previous_text=False,
                                    word_timestamps=True, vad_filter=False)
    segmenten = list(segmenten)
    sec = time.perf_counter() - t0
    herkend = " ".join(s.text.strip() for s in segmenten).strip()
    woorden = [w for s in segmenten for w in (s.words or [])]
    verwacht = normaliseer(r["zweeds"]).split()
    gezegd = normaliseer(r["gezegd"] or r["zweeds"]).split()
    h = normaliseer(herkend).split()
    return {
        "model": f"kb-whisper-{maat}", "spreker": spreker, "id": zin_id,
        "deel": r["deel"][0], "verwacht": r["zweeds"], "gezegd": r["gezegd"],
        "herkend": herkend,
        "wer_verwacht": round(foutpercentage(verwacht, h), 3),
        "wer_gezegd": round(foutpercentage(gezegd, h), 3),
        "afwijking_gevonden": int(h != verwacht),
        "laagste_woordzekerheid": round(min((w.probability for w in woorden), default=0), 3),
        "woorden": " ".join(f"{w.word.strip()}:{w.probability:.2f}" for w in woorden),
        "sec": round(sec, 2),
    }


def main():
    rijen_tsv = zinnen()
    cache = Cache("whisper", __file__)   # alleen nieuwe of gewijzigde opnames opnieuw transcriberen
    uit = []
    for maat in MODELLEN:
        model = None                      # pas laden als er iets te doen is
        for spreker, zin_id, wav in opnames():
            r = zin_voor(spreker, zin_id, rijen_tsv)
            sleutel = inhoud_hash(wav, r["zweeds"], r["gezegd"], maat)
            rij = cache.get(sleutel)
            if rij is None:
                model = model or laad(maat)
                rij = analyseer(model, maat, spreker, zin_id, wav, r)
                cache.put(sleutel, rij)
                print(f"{maat:6} {spreker:6} {zin_id}  {rij['herkend']}", flush=True)
            uit.append(dict(rij, spreker=spreker, id=zin_id))
    cache.bewaar()
    schrijf_csv(RESULTATEN / "whisper.csv", uit, list(uit[0]) if uit else ["model"])


def server():
    maat = os.environ.get("WHISPER_API_MODEL", "small")
    model = laad(maat)
    rijen_tsv = zinnen()
    serveer(lambda v: analyseer(model, maat, "web", v.get("id", ""), v["wav"], rij_voor_verzoek(v, rijen_tsv)), 8001)


if __name__ == "__main__":
    server() if "--server" in sys.argv else main()
