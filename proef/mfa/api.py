"""MFA als API voor de webpagina: één opname uitlijnen (standaard en met varianten) en meteen
keuze-uitspraak, duur en toonhoogte bepalen (zelfde code als de batchstap 'prosodie')."""
import os
import shutil
import subprocess
import time
from pathlib import Path

from analyse import analyseer_opname, f0_kenmerken, lees_varianten
from proef_common import WERK, serveer, zinnen

import numpy as np

WB = Path(os.environ["MFA_ROOT_DIR"]) / "pretrained_models" / "dictionary" / "swedish_mfa.dict"
MAP = WERK / "web" / "mfa"


def varianten_woordenboek():
    MAP.mkdir(parents=True, exist_ok=True)
    pad = MAP / "woordenboek_varianten.dict"
    regels = [r.split("\t") for r in Path("/app/varianten.tsv").read_text(encoding="utf-8").splitlines()
              if r.strip() and not r.startswith("#")]
    pad.write_text(WB.read_text(encoding="utf-8") + "".join(f"{r[0]}\t{r[2]}\n" for r in regels),
                   encoding="utf-8")
    return pad


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
    wb_var = varianten_woordenboek()
    rijen_tsv = zinnen()

    def analyseer(v):
        t0 = time.perf_counter()
        r = rijen_tsv[v["id"]]
        tg_s, methode = lijn_uit(v["wav"], r["zweeds"], WB, "standaard")
        tg_v, _ = lijn_uit(v["wav"], r["zweeds"], wb_var, "varianten")
        keuze, woorden, klinkers, stem = analyseer_opname("web", v["id"], r["deel"][0], v["wav"],
                                                          tg_s, tg_v, var)
        ref = float(np.median(stem)) if len(stem) else None
        woorden = [f0_kenmerken(w, ref) for w in woorden]
        return {"keuze": keuze, "woorden": woorden, "klinkers": klinkers,
                "methode": methode, "sec": round(time.perf_counter() - t0, 1)}

    serveer(analyseer, 8003)


if __name__ == "__main__":
    main()
