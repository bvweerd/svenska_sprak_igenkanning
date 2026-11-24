"""Vraag 2 en 3 op de MFA-uitlijning.

1. Keuze-uitspraak (map varianten/): welke uitspraak uit varianten.tsv koos MFA per doelwoord?
2. Duur (map standaard/): duur van elk woord en elke klinker (lang/kort).
3. Toonhoogte: F0 per woord in halve tonen t.o.v. de mediaan van de spreker, aantal toppen
   (woordaccent 2 heeft in Centraal-Zweeds meestal twee toppen, accent 1 één).
"""
import os
import re
from pathlib import Path

import numpy as np
import parselmouth
from praatio import textgrid

from proef_common import MFA_UIT, RESULTATEN, bewerkingen, opnames, schrijf_csv, zin_voor, zinnen

VARIANTEN = Path(os.environ.get("VARIANTEN", "/app/varianten.tsv"))
KLINKER = re.compile(r"[aeiouyåäöɑɛɪʏʉɵœøæɔʊ]")
TOP_HALVE_TONEN = float(os.environ.get("TOP_HALVE_TONEN", "1.5"))


def lees_varianten():
    var = {}
    for regel in VARIANTEN.read_text(encoding="utf-8").splitlines():
        if regel.startswith("#") or not regel.strip():
            continue
        delen = regel.split("\t")
        var.setdefault(delen[0], []).append((delen[1], delen[2]))
    return var


def tiers(pad):
    tg = textgrid.openTextgrid(str(pad), includeEmptyIntervals=False)
    woorden = klanken = None
    for naam in tg.tierNames:
        if naam.endswith("words"):
            woorden = tg.getTier(naam).entries
        elif naam.endswith("phones"):
            klanken = tg.getTier(naam).entries
    return woorden or [], klanken or []


def klanken_in(klanken, start, eind):
    return [k for k in klanken if k.start >= start - 1e-4 and k.end <= eind + 1e-4]


def f0_reeks(wav):
    snd = parselmouth.Sound(str(wav))
    pitch = snd.to_pitch(time_step=0.01, pitch_floor=75, pitch_ceiling=500)
    return pitch.xs(), pitch.selected_array["frequency"]


def halve_tonen(f0, ref):
    return 12 * np.log2(f0 / ref)


def toppen(waarden, drempel):
    """Lokale maxima die minstens 'drempel' boven het dal aan beide kanten uitsteken."""
    n, uit = len(waarden), 0
    for i in range(1, n - 1):
        if waarden[i] >= waarden[i - 1] and waarden[i] > waarden[i + 1]:
            links = waarden[:i].min() if i else waarden[i]
            rechts = waarden[i + 1:].min()
            if waarden[i] - max(links, rechts) >= drempel:
                uit += 1
    return uit


def analyseer_opname(spreker, zin_id, deel, wav, pad_s, pad_v, var):
    """Eén opname: (keuze, woorden, klinkers). Woorden houden _f0/_t voor f0_kenmerken."""
    tijden, f0 = f0_reeks(wav)
    keuze, woorden_uit, klinkers_uit = [], [], []

    # 1. keuze-uitspraak
    if pad_v and Path(pad_v).exists():
        woorden, klanken = tiers(pad_v)
        for w in woorden:
            if w.label in var:
                gekozen = " ".join(k.label for k in klanken_in(klanken, w.start, w.end))
                # Exacte match, anders de dichtstbijzijnde variant.
                label, afst = min(((lab, bewerkingen(u.split(), gekozen.split())[0])
                                   for lab, u in var[w.label]), key=lambda x: x[1])
                keuze.append({"spreker": spreker, "id": zin_id, "deel": deel,
                              "woord": w.label, "gekozen": label, "exact": int(afst == 0),
                              "klanken": gekozen})

    # 2. en 3. duur en toonhoogte
    if pad_s and Path(pad_s).exists():
        woorden, klanken = tiers(pad_s)
        for w in woorden:
            ks = klanken_in(klanken, w.start, w.end)
            masker = (tijden >= w.start) & (tijden <= w.end) & (f0 > 0)
            woorden_uit.append({"spreker": spreker, "id": zin_id, "deel": deel,
                                "woord": w.label, "start": round(w.start, 3),
                                "duur_ms": round(1000 * (w.end - w.start)),
                                "klanken": " ".join(k.label for k in ks),
                                "_f0": f0[masker], "_t": tijden[masker]})
            for k in ks:
                if KLINKER.search(k.label):
                    klinkers_uit.append({"spreker": spreker, "id": zin_id, "woord": w.label,
                                         "klinker": k.label, "lang_volgens_wb": int("ː" in k.label),
                                         "duur_ms": round(1000 * (k.end - k.start)),
                                         "aandeel_woord": round((k.end - k.start) / max(w.end - w.start, 1e-3), 2)})
    else:
        print("geen TextGrid:", pad_s)
    return keuze, woorden_uit, klinkers_uit, f0[f0 > 0]


def f0_kenmerken(rij, ref):
    """Vult de F0-kolommen van een woord in (halve tonen t.o.v. ref in Hz)."""
    f0w = rij.pop("_f0")
    tw = rij.pop("_t")
    if len(f0w) >= 5 and ref:
        ht = halve_tonen(f0w, ref)
        glad = np.convolve(ht, np.ones(3) / 3, mode="same")
        rel = (tw - tw[0]) / max(tw[-1] - tw[0], 1e-3)
        punten = np.interp(np.linspace(0, 1, 10), rel, glad)
        rij.update({"f0_toppen": toppen(glad, TOP_HALVE_TONEN),
                    "f0_bereik_ht": round(float(glad.max() - glad.min()), 1),
                    "f0_top_positie": round(float(rel[int(np.argmax(glad))]), 2),
                    "f0_kontoer_ht": " ".join(f"{p:.1f}" for p in punten)})
    else:
        rij.update({"f0_toppen": "", "f0_bereik_ht": "", "f0_top_positie": "", "f0_kontoer_ht": ""})
    return rij


def main():
    var = lees_varianten()
    rijen_tsv = zinnen()
    keuze, woorden_uit, klinkers_uit = [], [], []
    medianen = {}
    for spreker, zin_id, wav in opnames():
        k, w, kl, stem = analyseer_opname(
            spreker, zin_id, zin_voor(spreker, zin_id, rijen_tsv)["deel"][0], wav,
            MFA_UIT / "standaard" / spreker / f"{zin_id}.TextGrid",
            MFA_UIT / "varianten" / spreker / f"{zin_id}.TextGrid", var)
        keuze += k
        woorden_uit += w
        klinkers_uit += kl
        medianen.setdefault(spreker, []).extend(stem.tolist())

    # Referentietoon per spreker: mediaan over al zijn opnames.
    ref = {s: float(np.median(v)) for s, v in medianen.items() if v}
    for rij in woorden_uit:
        f0_kenmerken(rij, ref.get(rij["spreker"]))

    schrijf_csv(RESULTATEN / "mfa_keuze.csv", keuze,
                ["spreker", "id", "deel", "woord", "gekozen", "exact", "klanken"])
    schrijf_csv(RESULTATEN / "prosodie_woorden.csv", woorden_uit, WOORD_VELDEN)
    schrijf_csv(RESULTATEN / "prosodie_klinkers.csv", klinkers_uit,
                ["spreker", "id", "woord", "klinker", "lang_volgens_wb", "duur_ms", "aandeel_woord"])


WOORD_VELDEN = ["spreker", "id", "deel", "woord", "start", "duur_ms", "klanken", "f0_toppen",
                "f0_bereik_ht", "f0_top_positie", "f0_kontoer_ht"]

if __name__ == "__main__":
    main()
