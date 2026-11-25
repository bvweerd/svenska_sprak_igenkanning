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

from proef_common import ANKER, ANKER_RUW, CORPUS, EXTERN, OPNAMES, PIPER_RUW, zet_om, zinnen

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
    # Elke keer opnieuw opbouwen: weggehaalde of vervangen opnames mogen niet blijven meetellen.
    shutil.rmtree(CORPUS, ignore_errors=True)
    gedaan, onbekend, plofjes = 0, [], []
    extern = 0
    for spreker, bron in bronnen():
        if spreker.startswith(EXTERN):
            txt = bron.with_suffix(".txt")
            if not txt.exists():
                onbekend.append(f"{bron} (geen .txt met de tekst)")
                continue
            naam = re.sub(r"[^A-Za-z0-9_-]", "_", bron.stem)
            doel = CORPUS / spreker / f"{naam}.wav"
            doel.parent.mkdir(parents=True, exist_ok=True)
            zet_om(bron, doel)   # zelfde schoonmaak als eigen opnames (brom eruit), voor een eerlijke ijking
            doel.with_suffix(".lab").write_text(txt.read_text(encoding="utf-8").strip() + "\n",
                                                encoding="utf-8")
            extern += 1
            continue
        zin_id = bron.stem.upper()
        if zin_id not in rijen:
            onbekend.append(str(bron))
            continue
        doel = CORPUS / spreker / f"{zin_id}.wav"
        doel.parent.mkdir(parents=True, exist_ok=True)
        info = zet_om(bron, doel)   # 16 kHz mono; plof bij het aanzetten en brom onder 80 Hz eruit
        if info["plof_weggehaald"] or info["veel_brom"]:
            plofjes.append(f"{spreker}/{zin_id}" + (" (plof weg)" if info["plof_weggehaald"] else "")
                           + (f" (veel brom: {info['brom_db']} dB tegen spraak {info['spraak_db']} dB)"
                              if info["veel_brom"] else ""))
        # MFA krijgt de verwachte (goede) zin: bij een D-opname is dat juist de test.
        doel.with_suffix(".lab").write_text(rijen[zin_id]["zweeds"] + "\n", encoding="utf-8")
        gedaan += 1
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
