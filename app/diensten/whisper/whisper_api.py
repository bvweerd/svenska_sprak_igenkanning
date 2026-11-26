"""Wát zeg je? KB-Whisper (KBLab) via faster-whisper op de CPU, als interne API voor de webserver.

POST {"wav": pad (16 kHz mono), "id": stuk-id, "tekst": verwachte tekst} → herkende tekst, woordfoutpercentage
t.o.v. de tekst en de zekerheid per woord.
"""
import os
import time
import wave

import numpy as np
from faster_whisper import WhisperModel

from gedeeld import foutpercentage, normaliseer, rij_voor_verzoek, serveer

MAP = os.environ.get("WHISPER_MAP", "/modellen")
MAAT = os.environ.get("WHISPER_API_MODEL", "small")
THREADS = int(os.environ.get("WHISPER_THREADS", "0"))  # 0 = alle kernen


def lees_wav(pad):
    """16 kHz mono 16-bit wav (gemaakt door de webserver) → float32-array. Zelf inlezen voorkomt
    versieproblemen met PyAV in faster-whisper."""
    with wave.open(str(pad), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1, f"{pad}: geen 16 kHz mono"
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def analyseer(model, wav, r):
    t0 = time.perf_counter()
    # Geen vorige tekst als context: elke opname staat los.
    segmenten, _ = model.transcribe(lees_wav(wav), language="sv", beam_size=5, condition_on_previous_text=False,
                                    word_timestamps=True, vad_filter=False)
    segmenten = list(segmenten)
    herkend = " ".join(s.text.strip() for s in segmenten).strip()
    woorden = [w for s in segmenten for w in (s.words or [])]
    return {
        "model": f"kb-whisper-{MAAT}", "id": r["id"], "verwacht": r["zweeds"], "herkend": herkend,
        "wer_verwacht": round(foutpercentage(normaliseer(r["zweeds"]).split(), normaliseer(herkend).split()), 3),
        "laagste_woordzekerheid": round(min((w.probability for w in woorden), default=0), 3),
        "woorden": " ".join(f"{w.word.strip()}:{w.probability:.2f}" for w in woorden),
        "sec": round(time.perf_counter() - t0, 2),
    }


def main():
    model = WhisperModel(f"{MAP}/kb-whisper-{MAAT}", device="cpu", compute_type="int8", cpu_threads=THREADS)
    serveer(lambda v: analyseer(model, v["wav"], rij_voor_verzoek(v)), 8001)


if __name__ == "__main__":
    main()
