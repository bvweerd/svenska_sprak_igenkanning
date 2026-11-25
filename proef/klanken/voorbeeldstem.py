"""Voorbeeldstem: de zinnen ingesproken door Meta MMS-TTS Zweeds (facebook/mms-tts-swe, CC BY-NC 4.0).

Eerder deed Piper (sv_SE-nst) dit, maar alle Piper-stemmen leerden Zweeds via espeak-klanksymbolen en zeggen de
sj-klank vaak verkeerd: Whisper verstond bij Piper-NST maar 10 van de 23 sj/tj-woorden (*sken*, *sju*,
*stjärnor* …), bij MMS 20 van de 23 (README, „Voorbeeldstem”). MMS leert van letters en audio.
Komt in werk/piper_ruw (de oude naam; de batch noemt de spreker nog 'piper').

  python voorbeeldstem.py      alleen nieuwe of gewijzigde zinnen (werk/piper_ruw/_teksten.json)
"""
import json

import soundfile as sf
import torch
from transformers import AutoTokenizer, VitsModel

from proef_common import PIPER_RUW, VOORBEELD_WOORDEN, normaliseer, zinnen

MODEL = "/modellen/mms-tts-swe"
STEM = "mms-tts-swe"      # staat in de lijst: een andere stem → alles opnieuw


def main():
    rijen = zinnen()
    PIPER_RUW.mkdir(parents=True, exist_ok=True)
    lijst = PIPER_RUW / "_teksten.json"
    try:
        oud = json.loads(lijst.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        oud = {}
    nieuw = {i: f"{STEM}: {r['zweeds']}" for i, r in rijen.items() if not r["deel"].startswith("D")}
    for weg in set(oud) - set(nieuw):
        (PIPER_RUW / f"{weg}.wav").unlink(missing_ok=True)
    doen = [i for i, t in nieuw.items() if oud.get(i) != t or not (PIPER_RUW / f"{i}.wav").exists()]
    if doen:
        model, tok = VitsModel.from_pretrained(MODEL), AutoTokenizer.from_pretrained(MODEL)
        for zin_id in doen:
            torch.manual_seed(1)      # VITS heeft ruis in de uitspraak: vaste seed, herhaalbaar
            with torch.no_grad():
                golf = model(**tok(rijen[zin_id]["zweeds"], return_tensors="pt")).waveform[0].numpy()
            sf.write(str(PIPER_RUW / f"{zin_id}.wav"), golf, model.config.sampling_rate)
    lijst.write_text(json.dumps(nieuw, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Voorbeeldstem (MMS): {len(doen)} zinnen (nieuw of gewijzigd) ingesproken in {PIPER_RUW}")

    # Elk woord ook los, voor 'Luister en vergelijk': een stukje uit de zin bevat bij korte woorden (på, ut) ook
    # klanken van de buurwoorden ("enpoi", "duut"), want de woordgrenzen van MFA zijn een paar honderdsten onzeker.
    VOORBEELD_WOORDEN.mkdir(parents=True, exist_ok=True)
    woorden = sorted({w for i, r in rijen.items() if not r["deel"].startswith("D") for w in normaliseer(r["zweeds"]).split()})
    lijst = VOORBEELD_WOORDEN / "_stem.txt"
    if not lijst.exists() or lijst.read_text(encoding="utf-8").strip() != STEM:
        for f in VOORBEELD_WOORDEN.glob("*.wav"):
            f.unlink()
    weg = {f.stem for f in VOORBEELD_WOORDEN.glob("*.wav")} - set(woorden)
    for w in weg:
        (VOORBEELD_WOORDEN / f"{w}.wav").unlink()
    nog = [w for w in woorden if not (VOORBEELD_WOORDEN / f"{w}.wav").exists()]
    if nog:
        model, tok = VitsModel.from_pretrained(MODEL), AutoTokenizer.from_pretrained(MODEL)
        for w in nog:
            torch.manual_seed(1)
            with torch.no_grad():
                golf = model(**tok(w, return_tensors="pt")).waveform[0].numpy()
            sf.write(str(VOORBEELD_WOORDEN / f"{w}.wav"), golf, model.config.sampling_rate)
    lijst.write_text(STEM, encoding="utf-8")
    print(f"Voorbeeldstem (MMS): {len(nog)} losse woorden ingesproken in {VOORBEELD_WOORDEN} ({len(woorden)} in totaal)")


if __name__ == "__main__":
    main()
