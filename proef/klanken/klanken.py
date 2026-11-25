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
from pathlib import Path

import soundfile as sf
import torch
from transformers import AutoProcessor, Wav2Vec2ForCTC

from proef_common import (Cache, inhoud_hash, KLANK_PER_WOORD, KLANK_VARIANTEN, RESULTATEN, bewerkingen, leer_varianten, foutpercentage, normaliseer, opnames, ops_tekst,
                          schrijf_csv, serveer, zin_voor, zinnen)

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


def woord_klanken(tekst, wb):
    """Per woord de verwachte (grove) klanken: [(woord, [klank, ...]), ...]; leeg als het woord onbekend is."""
    return [(w, [g for g in (grof(k) for k in wb.get(w, [])) if g]) for w in normaliseer(tekst).split()]


def verwacht_mfa(tekst, wb):
    return [k for _, ks in woord_klanken(tekst, wb) for k in ks]


def per_woord(woorden, ops):
    """Verdeelt de klank-uitlijning over de woorden: welke klanken van welk woord afwijken.
    ops komt van bewerkingen(verwacht, herkend); verwacht = alle klanken van woorden achter elkaar."""
    eigenaar = [i for i, (_, ks) in enumerate(woorden) for _ in ks]   # woordnummer per verwachte klank
    uit = [{"woord": w, "verwacht": " ".join(ks), "herkend": [], "fouten": [], "goed": 0, "n": len(ks)}
           for w, ks in woorden]

    def grens(pos):
        """Woorden rond de grens vóór verwachte klank pos: (vorig woord, onbekende woorden ertussen, volgend)."""
        vorig = eigenaar[pos - 1] if pos > 0 else -1
        volgend = eigenaar[pos] if pos < len(eigenaar) else len(woorden)
        return vorig, [i for i in range(vorig + 1, volgend) if not woorden[i][1]], volgend

    def plaats(i, b, als_fout):
        uit[i]["herkend"].append(b)
        if als_fout:
            uit[i]["fouten"].append({"soort": "extra", "gehoord": b})
            uit[i]["n"] += 1

    pos, wachtend = 0, []   # wachtend: extra klanken op een woordgrens, nog niet toegewezen
    for soort, a, b in ops:
        if soort == "I":
            vorig, onbekend, volgend = grens(pos)
            if onbekend:                       # klanken van een woord dat niet in het woordenboek staat
                plaats(onbekend[0], b, False)
            elif 0 <= vorig == (eigenaar[pos] if pos < len(eigenaar) else None):
                plaats(vorig, b, True)        # midden in een woord
            else:
                wachtend.append(b)             # op de grens: hangt af van wat er volgt
            continue
        i = eigenaar[pos]
        if wachtend:
            # Gaat het volgende woord meteen mis, dan hoort de extra klank daarbij; anders bij het vorige.
            vorig = eigenaar[pos - 1] if pos > 0 else i
            doel = i if soort != "=" or pos == 0 else vorig
            for x in wachtend:
                plaats(doel, x, True)
            wachtend = []
        pos += 1
        if soort == "=":
            uit[i]["herkend"].append(b)
            uit[i]["goed"] += 1
        elif soort == "S":
            uit[i]["herkend"].append(b)
            uit[i]["fouten"].append({"soort": "anders", "verwacht": a, "gehoord": b})
        else:
            uit[i]["fouten"].append({"soort": "weg", "verwacht": a})
    for x in wachtend:                         # extra klanken aan het eind
        if eigenaar:
            plaats(eigenaar[-1], x, True)
    for u in uit:
        u["herkend"] = " ".join(u["herkend"])
        goed, n = u.pop("goed"), u.pop("n")
        u["score"] = round(goed / n, 2) if u["verwacht"] and n else None   # None: niet in het woordenboek
    return uit


def verwacht_espeak(tekst, stem="sv"):
    uit = subprocess.run(["espeak-ng", "-v", stem, "-q", "--ipa", "--sep=_", tekst],
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
    woorden = woord_klanken(r["zweeds"], wb)
    verwacht = [k for _, ks in woorden for k in ks]
    _, ops = bewerkingen(verwacht, herkend)
    return {
        "model": naam, "spreker": spreker, "id": zin_id, "deel": r["deel"][0],
        "zin": r["zweeds"],
        "verwacht": " ".join(verwacht), "herkend": " ".join(herkend),
        "herkend_ruw": " ".join(ruw), "espeak": verwacht_espeak(r["zweeds"]),
        "per": round(foutpercentage(verwacht, herkend), 3),
        "verschillen": ops_tekst(ops), "sec": round(sec, 2),
        "per_woord": per_woord(woorden, ops),
    }


def main():
    torch.set_num_threads(os.cpu_count() or 2)
    wb = lees_woordenboek()
    rijen_tsv = zinnen()
    uit = []
    cache = Cache("klanken", __file__)   # alleen nieuwe of gewijzigde opnames opnieuw analyseren
    wb_hash = inhoud_hash(Path(WOORDENBOEK))
    for naam, pad in MODELLEN.items():
        geladen = None                    # model pas laden als er iets te doen is
        for spreker, zin_id, wav in opnames():
            r = zin_voor(spreker, zin_id, rijen_tsv)
            sleutel = inhoud_hash(wav, r["zweeds"], naam, wb_hash)
            rij = cache.get(sleutel)
            if rij is None:
                geladen = geladen or (Wav2Vec2ForCTC.from_pretrained(pad).eval(), AutoProcessor.from_pretrained(pad))
                rij = analyseer(naam, *geladen, wb, spreker, zin_id, wav, r)
                cache.put(sleutel, rij)
                print(f"{naam:14} {spreker:6} {zin_id}  {rij['herkend']}   [{rij['verschillen']}]", flush=True)
            uit.append(dict(rij, spreker=spreker, id=zin_id))
    cache.bewaar()
    # Per woord bewaren (voor controle achteraf) en uit de moedertaalsprekers leren welke afwijkingen van de
    # woordenboek-uitspraak normaal zijn; de webpagina en het verslag gebruiken die bij het oordeel per woord.
    import json
    KLANK_PER_WOORD.write_text(json.dumps({f"{r['spreker']}|{r['id']}|{r['model']}": r["per_woord"] for r in uit},
                                          ensure_ascii=False), encoding="utf-8")
    varianten = leer_varianten((r["spreker"], r["model"], r["per_woord"]) for r in uit)
    KLANK_VARIANTEN.write_text(json.dumps(varianten, ensure_ascii=False, indent=1), encoding="utf-8")
    for m, v in varianten.items():
        print(f"{m}: {len(v['anders'])} normale verwisselingen, {len(v['weg'])} weglatingen, "
              f"{len(v['extra'])} extra klanken (uit {v['n_woorden']} woorden van moedertaalsprekers)")
    # per_woord is voor de webpagina; in de CSV alleen de woorden met afwijkende klanken, leesbaar.
    for rij in uit:
        rij["woorden_afwijkend"] = " ".join(f"{w['woord']}:{w['score']}" for w in rij.pop("per_woord")
                                            if w["score"] is not None and w["score"] < 1)
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
