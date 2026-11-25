"""Zet opnames om naar 16 kHz mono wav en schrijft per opname een .lab met de verwachte tekst.

Bronnen:
  opnames/<id>.<ext>             → spreker 'ik'
  opnames/<spreker>/<id>.<ext>   → die spreker (meer sprekers later)
  opnames/extern/<bron>/<naam>.<ext> + <naam>.txt
                                 → spreker 'extern-<bron>' (moedertaalsprekers, tekst uit .txt)
  werk/piper_ruw/<id>.wav        → spreker 'piper'
"""
import re
import shutil
import subprocess
import sys

from proef_common import ANKER, ANKER_RUW, CORPUS, EXTERN, OPNAMES, PIPER_RUW, Cache, inhoud_hash, zet_om, zinnen

AUDIO = {".wav", ".m4a", ".mp4", ".mp3", ".ogg", ".opus", ".flac", ".aac", ".webm", ".3gp", ".amr"}


def bronnen():
    if OPNAMES.exists():
        for p in sorted(OPNAMES.iterdir()):
            if p.is_file() and p.suffix.lower() in AUDIO:
                yield "ik", p
            elif p.is_dir() and p.name == "extern":
                for bron in sorted(q for q in p.iterdir() if q.is_dir()):
                    for q in sorted(bron.iterdir()):
                        if q.suffix.lower() in AUDIO:
                            yield EXTERN + bron.name, q
            elif p.is_dir() and not p.name.startswith("."):
                for q in sorted(p.iterdir()):
                    if q.suffix.lower() in AUDIO:
                        yield p.name, q
    if PIPER_RUW.exists():
        for p in sorted(PIPER_RUW.glob("*.wav")):
            yield "piper", p
    if ANKER_RUW.exists():
        for p in sorted(ANKER_RUW.glob("*.wav")):
            yield ANKER, p


def main():
    rijen = zinnen()
    # Alleen nieuwe of gewijzigde opnames omzetten; wat er niet meer is, gaat aan het eind weg. Ongewijzigde
    # wav's blijven byte voor byte gelijk, zodat de volgende stappen hun cache kunnen gebruiken.
    # (zet_om staat in proef_common: verander je die, verhoog dan ANALYSE_VERSIE.)
    cache = Cache("prep", __file__)
    gewenst = set()
    gedaan, onbekend, plofjes = 0, [], []
    extern = 0

    def al_klaar(bron, doel, tekst):
        gewenst.update({doel, doel.with_suffix(".lab")})
        sleutel = inhoud_hash(bron, tekst, str(doel.relative_to(CORPUS)))
        if cache.get(sleutel) is not None and doel.exists() and doel.with_suffix(".lab").exists():
            return True, sleutel
        return False, sleutel
    for spreker, bron in bronnen():
        if spreker.startswith(EXTERN):
            txt = bron.with_suffix(".txt")
            if not txt.exists():
                onbekend.append(f"{bron} (geen .txt met de tekst)")
                continue
            naam = re.sub(r"[^A-Za-z0-9_-]", "_", bron.stem)
            doel = CORPUS / spreker / f"{naam}.wav"
            tekst = txt.read_text(encoding="utf-8").strip()
            extern += 1
            klaar, sleutel = al_klaar(bron, doel, tekst)
            if klaar:
                continue
            doel.parent.mkdir(parents=True, exist_ok=True)
            zet_om(bron, doel)   # zelfde schoonmaak als eigen opnames (brom eruit), voor een eerlijke ijking
            doel.with_suffix(".lab").write_text(tekst + "\n", encoding="utf-8")
            cache.put(sleutel, True)
            continue
        zin_id = bron.stem.upper()
        if zin_id not in rijen:
            onbekend.append(str(bron))
            continue
        doel = CORPUS / spreker / f"{zin_id}.wav"
        gedaan += 1
        klaar, sleutel = al_klaar(bron, doel, rijen[zin_id]["zweeds"])
        if klaar:
            continue
        doel.parent.mkdir(parents=True, exist_ok=True)
        info = zet_om(bron, doel)   # 16 kHz mono; plof bij het aanzetten en brom onder 80 Hz eruit
        if info["plof_weggehaald"] or info["veel_brom"]:
            plofjes.append(f"{spreker}/{zin_id}" + (" (plof weg)" if info["plof_weggehaald"] else "")
                           + (f" (veel brom: {info['brom_db']} dB tegen spraak {info['spraak_db']} dB)"
                              if info["veel_brom"] else ""))
        # MFA krijgt de verwachte (goede) zin: bij een D-opname is dat juist de test.
        doel.with_suffix(".lab").write_text(rijen[zin_id]["zweeds"] + "\n", encoding="utf-8")
        cache.put(sleutel, True)
    # Opnames die er niet meer zijn (of een andere naam kregen): uit het corpus.
    for f in list(CORPUS.rglob("*")) if CORPUS.exists() else []:
        if f.is_file() and f.suffix in (".wav", ".lab") and f not in gewenst:
            f.unlink()
    for d in list(CORPUS.iterdir()) if CORPUS.exists() else []:
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    cache.bewaar()
    print(f"{gedaan} eigen/Piper-opnames en {extern} externe fragmenten voorbereid in {CORPUS}")
    if plofjes:
        print("Schoongemaakt:", *plofjes, sep="\n  ")
    if onbekend:
        print("Overgeslagen (naam is geen id uit testzinnen.tsv):", *onbekend, sep="\n  ")
    gedaan_ik = {p.stem for p in (CORPUS / "ik").glob("*.wav")}
    ontbrekend = sorted(set(rijen) - gedaan_ik)
    if ontbrekend:
        print(f"Nog niet opgenomen ({len(ontbrekend)}):", " ".join(ontbrekend))
    if gedaan + extern == 0:
        sys.exit("Geen opnames gevonden. Zet bestanden in opnames/ (bv. opnames/A01.wav).")


if __name__ == "__main__":
    main()
