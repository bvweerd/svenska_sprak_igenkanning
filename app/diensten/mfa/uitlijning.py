"""Wat MFA's uitlijning (TextGrid) zegt over één opname:
1. keuze-uitspraak (uitlijning met varianten): welke uitspraak uit varianten.tsv koos MFA per doelwoord?
2. woordgrenzen (standaarduitlijning): begin en duur van elk woord, voor „Luister en vergelijk”.
(De proef bepaalde hier ook toonhoogte en klinkerduur; de trainer gebruikt die niet.)
"""
import os
from pathlib import Path

from praatio import textgrid

from gedeeld import bewerkingen

VARIANTEN = Path(os.environ.get("VARIANTEN", "/app/varianten.tsv"))


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


def keuze_uitspraak(pad_v, var):
    """Per doelwoord de variant die MFA koos (exacte match, anders de dichtstbijzijnde)."""
    uit = []
    woorden, klanken = tiers(pad_v)
    for w in woorden:
        if w.label in var:
            gekozen = " ".join(k.label for k in klanken_in(klanken, w.start, w.end))
            label, afst = min(((lab, bewerkingen(u.split(), gekozen.split())[0]) for lab, u in var[w.label]),
                              key=lambda x: x[1])
            uit.append({"woord": w.label, "gekozen": label, "exact": int(afst == 0), "klanken": gekozen})
    return uit


def woordgrenzen(pad_s):
    """[{woord, start, duur_ms, klanken}] uit de standaarduitlijning (ook '<eps>' voor een pauze)."""
    woorden, klanken = tiers(pad_s)
    return [{"woord": w.label, "start": round(w.start, 3), "duur_ms": round(1000 * (w.end - w.start)),
             "klanken": " ".join(k.label for k in klanken_in(klanken, w.start, w.end))} for w in woorden]
