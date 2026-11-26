"""Voorbeeldstem: Meta MMS-TTS Zweeds (facebook/mms-tts-swe, CC BY-NC 4.0), gebruikt door app/voorbeeld/maak.py.

Piper zegt de sj-klank vaak verkeerd (proef: Whisper verstond bij Piper-NST maar 10 van de 23 sj/tj-woorden, bij
MMS 20 van de 23). MMS leert van letters en audio.

MMS kent geen leestekens (de tokenizer gooit . , ? ! weg) en leest een zin dus in één adem. Daarom per zinsdeel
ingesproken en aan elkaar gezet met een pauze: kort bij een komma, langer bij een punt. Een vraag klinkt nog
steeds als een mededeling. Heel korte stukjes ("Och du?") komen er bij MMS bijna stil uit; die gaan bij het
stuk ervoor.
"""
import re

import numpy as np
import torch

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

