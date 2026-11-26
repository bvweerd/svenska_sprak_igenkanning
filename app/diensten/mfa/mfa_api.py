"""Montreal Forced Aligner als interne API: één opname uitlijnen en woordgrenzen en keuze-uitspraak teruggeven.

POST {"wav": pad, "id": stuk-id, "tekst": tekst[, "alleen_tijden": true]} → {"woorden": [...], "keuze": [...]}
- woorden: begin en duur per woord (standaarduitlijning), voor „Luister en vergelijk” en de woordtijden van het
  voorbeeld ('alleen_tijden': dan niets anders);
- keuze: bij de woorden uit varianten.tsv (sju, kök, tack …) welke uitspraakvariant MFA koos (tweede uitlijning,
  alleen als zo'n woord in de tekst staat).
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

from gedeeld import DATA, normaliseer, rij_voor_verzoek, serveer, woordenboek_extra
from uitlijning import keuze_uitspraak, lees_varianten, woordgrenzen

WB = Path(os.environ["MFA_ROOT_DIR"]) / "pretrained_models" / "dictionary" / "swedish_mfa.dict"
MAP = DATA / "werk" / "mfa"            # werkmap (wordt bij elke opname overschreven)


def met_extra(naam, basis, aanvulling=""):
    """Het woordenboek plus de G2P-uitspraken van woorden die er niet in staan (app/woordenboek)."""
    MAP.mkdir(parents=True, exist_ok=True)
    pad = MAP / naam
    extra = "".join(f"{w}\t{u}\n" for w, u in woordenboek_extra())
    inhoud = basis + aanvulling + extra
    if not pad.exists() or pad.read_text(encoding="utf-8") != inhoud:
        pad.write_text(inhoud, encoding="utf-8")
    return pad


def varianten_regels():
    regels = [r.split("\t") for r in Path("/app/varianten.tsv").read_text(encoding="utf-8").splitlines()
              if r.strip() and not r.startswith("#")]
    return "".join(f"{r[0]}\t{r[2]}\n" for r in regels)


def varianten_woordenboek():
    return met_extra("woordenboek_varianten.dict", WB.read_text(encoding="utf-8"), varianten_regels())


def lijn_uit(wav, tekst, woordenboek, naam):
    """Eerst 'mfa align_one' (snel); lukt dat niet, dan 'mfa align' op een corpus van één bestand."""
    werk = MAP / naam
    shutil.rmtree(werk, ignore_errors=True)
    corpus = werk / "corpus" / "web"
    corpus.mkdir(parents=True)
    shutil.copy(wav, corpus / "opname.wav")
    (corpus / "opname.lab").write_text(tekst + "\n", encoding="utf-8")
    tg = werk / "opname.TextGrid"
    p = subprocess.run(["mfa", "align_one", str(corpus / "opname.wav"), str(corpus / "opname.lab"),
                        str(woordenboek), "swedish_mfa", str(tg), "--beam", "100", "--retry_beam", "400"],
                       capture_output=True, text=True)
    if tg.exists():
        return tg, "align_one"
    print("align_one lukte niet, terugval op align:", p.stderr[-500:], flush=True)
    subprocess.run(["mfa", "align", str(werk / "corpus"), str(woordenboek), "swedish_mfa", str(werk / "uit"),
                    "--clean", "--overwrite", "--beam", "100", "--retry_beam", "400",
                    "--output_format", "long_textgrid"], check=True, capture_output=True, text=True)
    gevonden = list((werk / "uit").rglob("opname.TextGrid"))
    if not gevonden:
        raise RuntimeError("MFA gaf geen TextGrid")
    return gevonden[0], "align"


def main():
    subprocess.run(["mfa", "server", "start"], capture_output=True)
    var = lees_varianten()
    wb_basis = WB.read_text(encoding="utf-8")

    def analyseer(v):
        t0 = time.perf_counter()
        r = rij_voor_verzoek(v)
        tg_s, methode = lijn_uit(v["wav"], r["zweeds"], met_extra("woordenboek_standaard.dict", wb_basis), "standaard")
        uit = {"woorden": woordgrenzen(tg_s), "keuze": [], "methode": methode}
        # De tweede uitlijning (met varianten) alleen als er een woord uit varianten.tsv in de tekst staat: op een
        # trage server scheelt dat de helft van de tijd.
        if not v.get("alleen_tijden") and set(normaliseer(r["zweeds"]).split()) & set(var):
            tg_v, _ = lijn_uit(v["wav"], r["zweeds"], varianten_woordenboek(), "varianten")
            uit["keuze"] = keuze_uitspraak(tg_v, var)
        return dict(uit, sec=round(time.perf_counter() - t0, 1))

    serveer(analyseer, 8003)


if __name__ == "__main__":
    main()
