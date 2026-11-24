"""Zet opnames om naar 16 kHz mono wav en schrijft per opname een .lab met de verwachte tekst.

Bronnen:
  opnames/<id>.<ext>             → spreker 'ik'
  opnames/<spreker>/<id>.<ext>   → die spreker (meer sprekers later)
  opnames/extern/<bron>/<naam>.<ext> + <naam>.txt
                                 → spreker 'extern-<bron>' (moedertaalsprekers, tekst uit .txt)
  werk/piper_ruw/<id>.wav        → spreker 'piper'
"""
import re
import subprocess
import sys

from proef_common import CORPUS, EXTERN, OPNAMES, PIPER_RUW, zinnen

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


def main():
    rijen = zinnen()
    gedaan, onbekend = 0, []
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
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(bron),
                            "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(doel)], check=True)
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
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(bron),
             "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(doel)],
            check=True)
        # MFA krijgt de verwachte (goede) zin: bij een D-opname is dat juist de test.
        doel.with_suffix(".lab").write_text(rijen[zin_id]["zweeds"] + "\n", encoding="utf-8")
        gedaan += 1
    print(f"{gedaan} eigen/Piper-opnames en {extern} externe fragmenten voorbereid in {CORPUS}")
    if onbekend:
        print("Overgeslagen (naam is geen id uit testzinnen.tsv):", *onbekend, sep="\n  ")
    ontbrekend = sorted(set(rijen) - {p.stem for p in (CORPUS / "ik").glob("*.wav")}) \
        if (CORPUS / "ik").exists() else sorted(rijen)
    if ontbrekend:
        print(f"Nog niet opgenomen ({len(ontbrekend)}):", " ".join(ontbrekend))
    if gedaan + extern == 0:
        sys.exit("Geen opnames gevonden. Zet bestanden in opnames/ (bv. opnames/A01.wav).")


if __name__ == "__main__":
    main()
