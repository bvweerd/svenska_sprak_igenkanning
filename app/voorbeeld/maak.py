"""Voorbeeldstem voor alle oefenstukken: een achtergrondtaak die de processor niet overbelast.

Per stuk: MMS-TTS Zweeds (met pauzes bij leestekens: diensten/klanken/voorbeeldstem.py) →
data/voorbeeld/<stuk>.wav, daarna de woordtijden via de MFA-API → data/voorbeeld/<stuk>.json.
- 1 thread, laagste prioriteit (nice 19), en een container met 1 kern (docker-compose.yml);
- wacht zolang er een opname geanalyseerd wordt of in de wachtrij staat (de gebruikers gaan voor);
- alleen nieuwe of gewijzigde stukken (de tekst staat in de .json); voorbeelden van verdwenen stukken gaan weg;
- eerst de teksten van de A-site, dan de B-site, de woordenschat als laatste.
"""
import json
import os
import time
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from transformers import AutoTokenizer, VitsModel

from voorbeeldstem import MODEL, STEM, spreek

DATA = Path(os.environ.get("DATA", "/data"))
TEKSTEN = Path(os.environ.get("TEKSTEN", "/teksten/teksten.json"))
UIT = DATA / "voorbeeld"
WEB = os.environ.get("WEB", "http://web:8080")
MFA = os.environ.get("MFA_API", "http://mfa-api:8003")
OPNIEUW_NA = int(os.environ.get("OPNIEUW_NA", 100))   # stukken per run (zie onder)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def lees(pad):
    try:
        return json.loads(pad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def te_doen():
    d = lees(TEKSTEN)
    if not d or not d.get("teksten"):
        # Geen (leesbare) teksten: niets doen en zeker niets opruimen (anders gaan alle voorbeelden weg).
        log(f"geen teksten in {TEKSTEN}; even wachten")
        return [], 0
    volgorde = sorted(d["teksten"], key=lambda t: (t["soort"] == "woordenschat", t["site"], t["hoofdstuk"]))
    stukken = [s for t in volgorde for s in t["stukken"]]
    ids = {s["id"] for s in stukken}
    for f in UIT.glob("*.*"):                      # stukken die niet meer bestaan
        if f.stem not in ids:
            f.unlink(missing_ok=True)
    doen = []
    for s in stukken:
        j = lees(UIT / f"{s['id']}.json")
        if not j or j.get("tekst") != s["tekst"] or j.get("stem") != STEM or not (UIT / f"{s['id']}.wav").exists():
            doen.append((s, "wav"))
        elif j.get("woorden") is None and time.time() - j.get("geprobeerd", 0) > 600:
            doen.append((s, "tijden"))             # uitlijnen mislukte eerder: na 10 minuten nog eens
    return doen, len(stukken)


def wacht_op_rust():
    """Zolang er geanalyseerd wordt (of de webserver nog niet bereikbaar is): wachten."""
    while True:
        try:
            with urllib.request.urlopen(f"{WEB}/api/wachtrij", timeout=5) as r:
                w = json.load(r)
            if not w["lengte"] and not w["bezig"]:
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(10)


def tijden(wav, stuk):
    data = json.dumps({"wav": str(wav), "id": stuk["id"], "tekst": stuk["tekst"], "alleen_tijden": True}).encode()
    req = urllib.request.Request(MFA, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        d = json.load(r)
    if "fout" in d:
        raise RuntimeError(d["fout"])
    return [[w["start"], round(w["start"] + w["duur_ms"] / 1000, 3), w["woord"]] for w in d["woorden"]
            if w["woord"] not in ("", "<eps>", "<unk>")]          # <eps>: de pauzes bij leestekens


def main():
    os.nice(19)
    torch.set_num_threads(1)
    UIT.mkdir(parents=True, exist_ok=True)
    model = tok = None
    gedaan = 0
    while True:
        doen, totaal = te_doen()
        if not doen:
            time.sleep(120)
            continue
        log(f"{len(doen)} van {totaal} stukken te doen")
        for stuk, wat in doen[:20]:                # daarna opnieuw kijken (de import kan intussen gedraaid hebben)
            wacht_op_rust()
            wav, j = UIT / f"{stuk['id']}.wav", UIT / f"{stuk['id']}.json"
            t0 = time.time()
            if wat == "wav":
                if model is None:
                    model, tok = VitsModel.from_pretrained(MODEL), AutoTokenizer.from_pretrained(MODEL)
                golf = spreek(model, tok, stuk["tekst"])
                sf.write(str(wav), np.clip(golf, -1, 1), model.config.sampling_rate, subtype="PCM_16")
            info = {"tekst": stuk["tekst"], "stem": STEM, "woorden": None, "geprobeerd": time.time()}
            wacht_op_rust()
            try:
                info["woorden"] = tijden(wav, stuk)
            except Exception as e:  # noqa: BLE001 — het voorbeeld zelf is er wel; de tijden later nog eens
                log(f"{stuk['id']}: uitlijnen mislukt: {e}")
            j.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
            log(f"{stuk['id']}: klaar in {time.time() - t0:.0f} s")
            gedaan += 1
            if gedaan >= OPNIEUW_NA:
                # PyTorch-geheugen versnippert bij steeds andere invoerlengtes en groeit per stuk; Docker start de
                # taak meteen opnieuw (restart: unless-stopped) en hij gaat verder waar hij was.
                log(f"{gedaan} stukken gedaan: opnieuw starten om geheugen vrij te maken")
                return


if __name__ == "__main__":
    main()
