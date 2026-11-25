"""MFA-uitlijning alleen voor nieuwe of gewijzigde opnames; de rest komt uit eerdere runs.

Een uiting is 'gewijzigd' als de wav, de tekst (.lab) of de woordenboekregels van haar woorden anders zijn
dan bij de vorige run (werk/cache/mfa.json). Die uitingen gaan in een tijdelijk corpus door 'mfa align'; de
TextGrids en de scores per uiting (alignment_analysis.csv) worden samengevoegd met de bestaande. TextGrids
van opnames die er niet meer zijn, gaan weg.

Kanttekening: MFA past het akoestisch model per spreker aan op de opnames in de run. Bij een gedeeltelijke run
gebeurt dat op minder opnames; de uitlijning kan daardoor iets anders uitvallen dan bij een volledige run.
Alles opnieuw: verwijder werk/cache/mfa.json.

  python incrementeel.py <uitmap>     (verwacht woordenboek_standaard.dict en woordenboek_varianten.dict daarin)
"""
import csv
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from proef_common import CORPUS, RESULTATEN, Cache, inhoud_hash

UIT = Path(sys.argv[1])
RUNS = ("standaard", "varianten")


def lees_wb(pad):
    wb = {}
    for regel in pad.read_text(encoding="utf-8").splitlines():
        if regel.strip():
            wb.setdefault(regel.split("\t", 1)[0], []).append(regel)
    return wb


def main():
    wbs = {run: lees_wb(UIT / f"woordenboek_{run}.dict") for run in RUNS}
    cache = Cache("mfa", __file__)
    uitingen, te_doen = {}, []
    for lab in sorted(CORPUS.glob("*/*.lab")):
        wav = lab.with_suffix(".wav")
        if not wav.exists():
            continue
        spreker, uid = lab.parent.name, lab.stem
        woorden = sorted(set(re.findall(r"\w+", lab.read_text(encoding="utf-8").lower())))
        regels = "\n".join(r for run in RUNS for w in woorden for r in wbs[run].get(w, ["?" + w]))
        sleutel = inhoud_hash(wav, lab, regels)
        uitingen[(spreker, uid)] = sleutel
        klaar = all((UIT / run / spreker / f"{uid}.TextGrid").exists() for run in RUNS)
        if not (klaar and cache.get(sleutel) is not None):
            te_doen.append((spreker, uid, wav, lab))

    # TextGrids van opnames die er niet meer zijn: weg.
    for run in RUNS:
        for tg in (UIT / run).glob("*/*.TextGrid") if (UIT / run).exists() else []:
            if (tg.parent.name, tg.stem) not in uitingen:
                tg.unlink()
        for d in (UIT / run).iterdir() if (UIT / run).exists() else []:
            if d.is_dir() and not any(d.iterdir()):   # spreker zonder opnames meer
                d.rmdir()

    print(f"MFA: {len(uitingen) - len(te_doen)} uitingen ongewijzigd, {len(te_doen)} uit te lijnen", flush=True)
    nieuw_analyse = {run: [] for run in RUNS}
    if te_doen:
        tijdelijk = UIT.parent / "mfa_nieuw"
        shutil.rmtree(tijdelijk, ignore_errors=True)
        for spreker, uid, wav, lab in te_doen:
            d = tijdelijk / "corpus" / spreker
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy(wav, d / wav.name)
            shutil.copy(lab, d / lab.name)
        for run in RUNS:
            print(f"== MFA align ({run}, {len(te_doen)} uitingen)", flush=True)
            # Ruime beam: een foute uitspraak moet nog steeds uitgelijnd worden, niet overgeslagen.
            subprocess.run(["mfa", "align", str(tijdelijk / "corpus"), str(UIT / f"woordenboek_{run}.dict"),
                            "swedish_mfa", str(tijdelijk / run), "--clean", "--overwrite",
                            "--output_format", "long_textgrid", "--beam", "100", "--retry_beam", "400",
                            "--num_jobs", os.environ.get("MFA_JOBS", "2")], check=True)
            for tg in (tijdelijk / run).glob("*/*.TextGrid"):
                doel = UIT / run / tg.parent.name / tg.name
                doel.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(tg, doel)
            ana = tijdelijk / run / "alignment_analysis.csv"
            if ana.exists():
                with open(ana, encoding="utf-8", newline="") as f:
                    nieuw_analyse[run] = list(csv.DictReader(f))
        shutil.rmtree(tijdelijk, ignore_errors=True)

    # Scores per uiting samenvoegen: oude rijen van ongewijzigde uitingen + nieuwe rijen.
    opnieuw = {(s, u) for s, u, _, _ in te_doen}
    RESULTATEN.mkdir(parents=True, exist_ok=True)
    for run in RUNS:
        pad = UIT / run / "alignment_analysis.csv"
        oud = []
        if pad.exists():
            with open(pad, encoding="utf-8", newline="") as f:
                oud = [r for r in csv.DictReader(f)
                       if (r.get("speaker"), r.get("file")) in uitingen and (r.get("speaker"), r.get("file")) not in opnieuw]
        rijen = oud + nieuw_analyse[run]
        if rijen:
            velden = list(dict.fromkeys(k for r in rijen for k in r))
            for doel in (pad, RESULTATEN / f"mfa_{run}.csv"):
                doel.parent.mkdir(parents=True, exist_ok=True)
                with open(doel, "w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, velden)
                    w.writeheader()
                    w.writerows(rijen)

    # Alleen in de cache wat nu echt in beide runs een TextGrid heeft (mislukte uitlijning: volgende keer opnieuw).
    for (spreker, uid), sleutel in uitingen.items():
        if all((UIT / run / spreker / f"{uid}.TextGrid").exists() for run in RUNS) and sleutel not in cache.nieuw:
            cache.put(sleutel, True)
    cache.bewaar()


if __name__ == "__main__":
    main()
