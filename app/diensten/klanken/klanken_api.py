"""Hóé zeg je het? Twee klankherkenners (wav2vec2) schrijven op welke klanken er gezegd zijn, zonder taalmodel dat
de zin 'verbetert'; vergeleken met de verwachte uitspraak uit het swedish_mfa-woordenboek. Interne API.

Beide kanten worden grof gemaakt (zonder lengte, toon, dentaal- en aspiratieteken), omdat de modellen elk een
ander klankenstelsel hebben. Wat overblijft is genoeg voor sj/tj/k, u/y/oe. Het espeak-model kent geen ɧ
(sj-klank); het Zweedse model schrijft die als 'sx'.

POST {"wav": pad, "id": stuk-id, "tekst": tekst} → {model: {herkend, verwacht, per, verschillen, per_woord}}
"""
import os
import re
import time
import unicodedata

import soundfile as sf
import torch
from transformers import AutoProcessor, Wav2Vec2ForCTC

from gedeeld import bewerkingen, foutpercentage, normaliseer, ops_tekst, rij_voor_verzoek, serveer, woordenboek_extra

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


def herken(model, processor, wav):
    audio, sr = sf.read(wav, dtype="float32")
    assert sr == 16000, f"{wav}: verwacht 16 kHz, kreeg {sr}"
    invoer = processor(audio, sampling_rate=16000, return_tensors="pt")
    with torch.inference_mode():
        logits = model(invoer.input_values).logits
    ids = torch.argmax(logits, dim=-1)[0].tolist()
    # Zelf CTC-decoderen: herhalingen samenvoegen, lege tokens weg. Zo blijven klanken van meer tekens (eː, sx)
    # heel, ook bij een tokenizer die alles aan elkaar plakt.
    samen = [i for n, i in enumerate(ids) if n == 0 or i != ids[n - 1]]
    tokens = processor.tokenizer.convert_ids_to_tokens(samen)
    leeg = set(processor.tokenizer.all_special_tokens) | {"|", "<pad>", "<s>", "</s>", "<unk>"}
    return [t for t in tokens if t not in leeg]


def analyseer(model, processor, wb, wav, r):
    t0 = time.perf_counter()
    ruw = herken(model, processor, str(wav))
    herkend = [g for g in (grof(k) for k in ruw) if g]
    woorden = woord_klanken(r["zweeds"], wb)
    verwacht = [k for _, ks in woorden for k in ks]
    _, ops = bewerkingen(verwacht, herkend)
    return {"verwacht": " ".join(verwacht), "herkend": " ".join(herkend), "herkend_ruw": " ".join(ruw),
            "per": round(foutpercentage(verwacht, herkend), 3), "verschillen": ops_tekst(ops),
            "per_woord": per_woord(woorden, ops), "sec": round(time.perf_counter() - t0, 2)}


def main():
    # KLANKEN_THREADS: zoveel kernen als de container krijgt. Meer threads dan kernen maakt het juist trager
    # (gemeten: 16 threads op 2 kernen, 62 s in plaats van ±15 s).
    torch.set_num_threads(int(os.environ.get("KLANKEN_THREADS", 0)) or os.cpu_count() or 2)
    basis = lees_woordenboek()
    modellen = {naam: (Wav2Vec2ForCTC.from_pretrained(pad).eval(), AutoProcessor.from_pretrained(pad))
                for naam, pad in MODELLEN.items()}

    def analyseer_verzoek(v):
        # Woorden die niet in het woordenboek staan (namen in de teksten): uit MFA's G2P (app/woordenboek). Per
        # verzoek opnieuw, zodat een bijgewerkt bestand meteen telt (net als bij MFA); het woordenboek gaat voor.
        extra = {}
        for woord, uitspraak in woordenboek_extra():
            extra.setdefault(woord, uitspraak.split())
        wb = {**extra, **basis}
        r = rij_voor_verzoek(v)
        return {naam: analyseer(m, p, wb, v["wav"], r) for naam, (m, p) in modellen.items()}

    serveer(analyseer_verzoek, 8002)


if __name__ == "__main__":
    main()
