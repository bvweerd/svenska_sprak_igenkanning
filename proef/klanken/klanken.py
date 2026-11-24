"""Vraag 2 — hóé zeg je het? Een klankherkenner schrijft op welke klanken er gezegd zijn,
zonder taalmodel dat de zin 'verbetert'. Vergelijking met de verwachte uitspraak uit het
swedish_mfa-woordenboek (en ter informatie espeak-ng).

Beide kanten worden grof gemaakt (zonder lengte, toon, dentaal- en aspiratieteken), omdat de
modellen elk een ander klankenstelsel hebben. Wat overblijft is genoeg voor sj/tj/k, u/y/oe.
Let op: het espeak-model kent geen ɧ (sj-klank); het Zweedse model schrijft die als 'sx'.

  python klanken.py           alle opnames, beide modellen → resultaten/klanken.csv
  python klanken.py --server  API voor de webpagina
"""
import os
import re
import subprocess
import sys
import time
import unicodedata

import soundfile as sf
import torch
from transformers import AutoProcessor, Wav2Vec2ForCTC

from proef_common import RESULTATEN, foutpercentage, normaliseer, opnames, ops_tekst, schrijf_csv, serveer, zinnen, bewerkingen

MODELLEN = {
    "xlsr53-espeak": "/modellen/wav2vec2-xlsr-53-espeak-cv-ft",
    "xlsr300m-sv": "/modellen/wav2vec2-xls-r-phoneme-300m-sv",
}
WOORDENBOEK = os.environ.get("WOORDENBOEK", "/modellen/swedish_mfa.dict")

GELIJK = {"sx": "ɧ", "ʃ": "ɧ", "ʈ": "t", "ɖ": "d", "ɳ": "n", "ɭ": "l", "ʋ": "v", "ɐ": "a", "ə": "ɛ"}


def grof(klank):
    """Eén klank grof maken: zonder lengte, toon, klemtoon en diakrieten."""
    k = unicodedata.normalize("NFD", klank)
    k = "".join(c for c in k if not unicodedata.combining(c))
    k = re.sub(r"[ːˑˈˌ˥˦˧˨˩ʰ0-9.:^]", "", k)
    return GELIJK.get(k, k)


def lees_woordenboek():
    wb = {}
    with open(WOORDENBOEK, encoding="utf-8") as f:
        for regel in f:
            delen = regel.rstrip("\n").split("\t")
            if len(delen) >= 2 and delen[0] not in wb:
                wb[delen[0]] = delen[-1].split()
    return wb


def verwacht_mfa(tekst, wb):
    klanken = []
    for w in normaliseer(tekst).split():
        klanken += [grof(k) for k in wb.get(w, [])]
    return [k for k in klanken if k]


def verwacht_espeak(tekst):
    uit = subprocess.run(["espeak-ng", "-v", "sv", "-q", "--ipa", "--sep=_", tekst],
                         capture_output=True, text=True, check=True).stdout
    return " ".join(k for k in re.split(r"[_\s]+", uit) if k)


def herken(model, processor, wav):
    audio, sr = sf.read(wav, dtype="float32")
    assert sr == 16000, f"{wav}: verwacht 16 kHz, kreeg {sr}"
    invoer = processor(audio, sampling_rate=16000, return_tensors="pt")
    with torch.inference_mode():
        logits = model(invoer.input_values).logits
    ids = torch.argmax(logits, dim=-1)[0].tolist()
    # Zelf CTC-decoderen: herhalingen samenvoegen, lege tokens weg. Zo blijven klanken van
    # meer tekens (eː, sx) heel, ook bij een tokenizer die alles aan elkaar plakt.
    samen = [i for n, i in enumerate(ids) if n == 0 or i != ids[n - 1]]
    tokens = processor.tokenizer.convert_ids_to_tokens(samen)
    leeg = set(processor.tokenizer.all_special_tokens) | {"|", "<pad>", "<s>", "</s>", "<unk>"}
    return [t for t in tokens if t not in leeg]


def laad_alle():
    uit = {}
    for naam, pad in MODELLEN.items():
        uit[naam] = (Wav2Vec2ForCTC.from_pretrained(pad).eval(), AutoProcessor.from_pretrained(pad))
    return uit


def analyseer(naam, model, processor, wb, spreker, zin_id, wav, r):
    t0 = time.perf_counter()
    ruw = herken(model, processor, str(wav))
    sec = time.perf_counter() - t0
    herkend = [g for g in (grof(k) for k in ruw) if g]
    verwacht = verwacht_mfa(r["zweeds"], wb)
    _, ops = bewerkingen(verwacht, herkend)
    return {
        "model": naam, "spreker": spreker, "id": zin_id, "deel": r["deel"][0],
        "zin": r["zweeds"],
        "verwacht": " ".join(verwacht), "herkend": " ".join(herkend),
        "herkend_ruw": " ".join(ruw), "espeak": verwacht_espeak(r["zweeds"]),
        "per": round(foutpercentage(verwacht, herkend), 3),
        "verschillen": ops_tekst(ops), "sec": round(sec, 2),
    }


def main():
    torch.set_num_threads(os.cpu_count() or 2)
    wb = lees_woordenboek()
    rijen_tsv = zinnen()
    uit = []
    for naam, (model, processor) in laad_alle().items():
        for spreker, zin_id, wav in opnames():
            rij = analyseer(naam, model, processor, wb, spreker, zin_id, wav, rijen_tsv[zin_id])
            uit.append(rij)
            print(f"{naam:14} {spreker:6} {zin_id}  {rij['herkend']}   [{rij['verschillen']}]", flush=True)
    schrijf_csv(RESULTATEN / "klanken.csv", uit, list(uit[0]) if uit else ["model"])


def server():
    torch.set_num_threads(os.cpu_count() or 2)
    wb = lees_woordenboek()
    rijen_tsv = zinnen()
    modellen = laad_alle()
    serveer(lambda v: {naam: analyseer(naam, m, p, wb, "web", v["id"], v["wav"], rijen_tsv[v["id"]])
                       for naam, (m, p) in modellen.items()}, 8002)


if __name__ == "__main__":
    server() if "--server" in sys.argv else main()
