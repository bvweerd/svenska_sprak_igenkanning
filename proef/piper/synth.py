"""Computerstem als tweede ijkpunt: Piper spreekt de goede zinnen (deel A–C) in.

Let op: A01/A02 en A03/A04 zijn hetzelfde woord met een ander woordaccent. Piper kent
de betekenis niet en spreekt ze gelijk uit; die paren tellen voor Piper niet mee.
"""
import os
import wave

from piper import PiperVoice

from proef_common import ANKER_RUW, PIPER_RUW, zinnen

STEM = os.environ.get("PIPER_STEM", "/stemmen/sv_SE-nst-medium.onnx")


def te_doen(map_, rijen):
    """Alleen zinnen die nieuw zijn of waarvan de tekst veranderde (bijgehouden in _teksten.json)."""
    import json
    lijst = map_ / "_teksten.json"
    try:
        oud = json.loads(lijst.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        oud = {}
    nieuw = {i: r["zweeds"] for i, r in rijen.items() if not r["deel"].startswith("D")}
    for weg in set(oud) - set(nieuw):                       # zin verwijderd: opname ook weg
        (map_ / f"{weg}.wav").unlink(missing_ok=True)
    doen = [i for i, t in nieuw.items() if oud.get(i) != t or not (map_ / f"{i}.wav").exists()]
    return doen, lambda: lijst.write_text(json.dumps(nieuw, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    rijen = zinnen()
    # De Zweedse voorbeeldstem doet sinds kort MMS (stap 'voorbeeld', klanken/voorbeeldstem.py): de Piper-stemmen
    # zeggen de sj-klank vaak verkeerd. Deze stap maakt alleen nog het accent-anker.

    # Accent-ankerpunt: dezelfde zinnen met Nederlandse uitspraakregels (espeak-ng, stem 'nl').
    # Zo heeft de score een vast 0-punt ("duidelijk Nederlands accent") naast de moedertaalsprekers (100).
    import subprocess
    ANKER_RUW.mkdir(parents=True, exist_ok=True)
    doen, klaar = te_doen(ANKER_RUW, rijen)
    for zin_id in doen:
        subprocess.run(["espeak-ng", "-v", "nl", "-s", "150", "-w", str(ANKER_RUW / f"{zin_id}.wav"),
                        rijen[zin_id]["zweeds"]], check=True)
    klaar()
    print(f"Accent-anker (Nederlandse uitspraak): {len(doen)} zinnen (nieuw of gewijzigd) in {ANKER_RUW}")


if __name__ == "__main__":
    main()
