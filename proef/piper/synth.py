"""Computerstem als tweede ijkpunt: Piper spreekt de goede zinnen (deel A–C) in.

Let op: A01/A02 en A03/A04 zijn hetzelfde woord met een ander woordaccent. Piper kent
de betekenis niet en spreekt ze gelijk uit; die paren tellen voor Piper niet mee.
"""
import os
import wave

from piper import PiperVoice

from proef_common import PIPER_RUW, zinnen

STEM = os.environ.get("PIPER_STEM", "/stemmen/sv_SE-nst-medium.onnx")


def main():
    stem = PiperVoice.load(STEM)
    PIPER_RUW.mkdir(parents=True, exist_ok=True)
    n = 0
    for zin_id, r in zinnen().items():
        if r["deel"].startswith("D"):
            continue
        with wave.open(str(PIPER_RUW / f"{zin_id}.wav"), "wb") as wf:
            stem.synthesize_wav(r["zweeds"], wf)
        n += 1
    print(f"{n} zinnen ingesproken in {PIPER_RUW}")


if __name__ == "__main__":
    main()
