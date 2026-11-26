"""MFA als API voor de webpagina: één opname uitlijnen (standaard en met varianten) en meteen
keuze-uitspraak, duur en toonhoogte bepalen (zelfde code als de batchstap 'prosodie')."""
import os
import shutil
import subprocess
import time
from pathlib import Path

from analyse import analyseer_opname, f0_kenmerken, lees_varianten
from proef_common import WERK, rij_voor_verzoek, serveer, woordenboek_extra, zinnen

import numpy as np

WB = Path(os.environ["MFA_ROOT_DIR"]) / "pretrained_models" / "dictionary" / "swedish_mfa.dict"
MAP = WERK / "web" / "mfa"


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
    rijen_tsv = zinnen()

    def analyseer(v):
        t0 = time.perf_counter()
        r = rij_voor_verzoek(v, rijen_tsv)
        wb_s = met_extra("woordenboek_standaard.dict", wb_basis)
        tg_s, methode = lijn_uit(v["wav"], r["zweeds"], wb_s, "standaard")
        # Alleen woordtijden nodig (de voorbeeldstem van de productieversie): de variantuitlijning overslaan.
        if v.get("alleen_tijden"):
            _, woorden, _, _ = analyseer_opname("web", v.get("id", ""), r["deel"][0], v["wav"], tg_s, tg_s, var)
            return {"woorden": [{"woord": w["woord"], "start": w["start"], "duur_ms": w["duur_ms"]} for w in woorden],
                    "methode": methode, "sec": round(time.perf_counter() - t0, 1)}
        tg_v, _ = lijn_uit(v["wav"], r["zweeds"], varianten_woordenboek(), "varianten")
        keuze, woorden, klinkers, stem = analyseer_opname("web", v.get("id", ""), r["deel"][0], v["wav"],
                                                          tg_s, tg_v, var)
        ref = float(np.median(stem)) if len(stem) else None
        woorden = [f0_kenmerken(w, ref) for w in woorden]
        return {"keuze": keuze, "woorden": woorden, "klinkers": klinkers,
                "methode": methode, "sec": round(time.perf_counter() - t0, 1)}

    serveer(analyseer, 8003)


if __name__ == "__main__":
    main()
