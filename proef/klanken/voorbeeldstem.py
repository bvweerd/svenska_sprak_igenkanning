"""Voorbeeldstem: de zinnen ingesproken door Meta MMS-TTS Zweeds (facebook/mms-tts-swe, CC BY-NC 4.0).

Eerder deed Piper (sv_SE-nst) dit, maar alle Piper-stemmen leerden Zweeds via espeak-klanksymbolen en zeggen de
sj-klank vaak verkeerd: Whisper verstond bij Piper-NST maar 10 van de 23 sj/tj-woorden (*sken*, *sju*,
*stjärnor* …), bij MMS 20 van de 23 (README, „Voorbeeldstem”). MMS leert van letters en audio.
Komt in werk/piper_ruw (de oude naam; de batch noemt de spreker nog 'piper').

MMS kent geen leestekens (de tokenizer gooit . , ? ! weg) en leest een zin dus in één adem. Daarom per zinsdeel
ingesproken en aan elkaar gezet met een pauze: kort bij een komma, langer bij een punt. Een vraag klinkt nog
steeds als een mededeling. Heel korte stukjes ("Och du?") komen er bij MMS bijna stil uit; die gaan bij het
stuk ervoor.

  python voorbeeldstem.py      alleen nieuwe of gewijzigde zinnen (werk/piper_ruw/_teksten.json)
"""
import json
import re

import numpy as np

import soundfile as sf
import torch
from transformers import AutoTokenizer, VitsModel

from proef_common import PIPER_RUW, zinnen

MODEL = "/modellen/mms-tts-swe"
STEM = "mms-tts-swe+pauzes2"      # staat in de lijst: een andere stem of werkwijze → alles opnieuw
PAUZE = {",": 0.25, ";": 0.3, ":": 0.3, ".": 0.5, "!": 0.5, "?": 0.5}   # seconden stilte na het leesteken
MIN_WOORDEN = 3                  # kortere zinsdelen gaan bij het vorige (of volgende) stuk


def zinsdelen(tekst):
    """[(stuk, pauze erna)]: de tekst gesplitst op leestekens, korte stukjes samengevoegd."""
    delen = [(m.group(1).strip(), PAUZE.get(m.group(2)[:1], 0.0))
             for m in re.finditer(r"([^,;:.!?]+)([,;:.!?]*)", tekst) if m.group(1).strip()]
    uit = []
    for stuk, pauze in delen:
        if uit and len(stuk.split()) < MIN_WOORDEN:
            uit[-1] = (f"{uit[-1][0]} {stuk}", pauze)       # zonder pauze ertussen, wel die van dit stuk erna
        elif uit and len(uit[-1][0].split()) < MIN_WOORDEN:
            uit[-1] = (f"{uit[-1][0]} {stuk}", pauze)       # te kort eerste stuk: bij dit stuk
        else:
            uit.append((stuk, pauze))
    return uit


def knip_stilte(golf, sr, marge=0.04):
    """MMS zet zelf stilte voor en na elk stuk; weg ermee, anders wordt elke pauze ruim een halve seconde langer."""
    n = int(0.01 * sr)
    energie = np.sqrt(np.convolve(golf ** 2, np.ones(n) / n, mode="same"))
    luid = np.flatnonzero(energie > 0.03 * energie.max())
    if not len(luid):
        return golf
    return golf[max(0, luid[0] - int(marge * sr)):luid[-1] + int(marge * sr)]


def spreek(model, tok, tekst):
    golven, delen = [], zinsdelen(tekst)
    delen[-1] = (delen[-1][0], 0.1)       # aan het eind geen lange stilte
    for stuk, pauze in delen:
        torch.manual_seed(1)      # VITS heeft ruis in de uitspraak: vaste seed, herhaalbaar
        with torch.no_grad():
            golf = model(**tok(stuk, return_tensors="pt")).waveform[0].numpy()
        if np.sqrt((golf ** 2).mean()) < 0.02:
            print(f"  let op: bijna stil zinsdeel „{stuk}”")
        golven.append(knip_stilte(golf, model.config.sampling_rate))
        golven.append(np.zeros(int(pauze * model.config.sampling_rate), dtype=np.float32))
    return np.concatenate(golven)


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
            golf = spreek(model, tok, rijen[zin_id]["zweeds"])
            sf.write(str(PIPER_RUW / f"{zin_id}.wav"), golf, model.config.sampling_rate)
    lijst.write_text(json.dumps(nieuw, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Voorbeeldstem (MMS): {len(doen)} zinnen (nieuw of gewijzigd) ingesproken in {PIPER_RUW}")


if __name__ == "__main__":
    main()
