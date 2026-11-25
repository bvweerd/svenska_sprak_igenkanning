"""Minimale testpagina: opnemen in de browser, opslaan in opnames/, analyseren met de drie
API's (whisper, klanken, mfa) en feedback teruggeven. Alleen voor de proef, niet voor de site.

Feedback in lagen: eerst het oordeel (verstaan? goede uitspraakvariant gekozen?), dan informatie
(klankherkenner, toonhoogte, klinkerduur) en onderaan de ruwe resultaten.
"""
import json
import os
import re
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from proef_common import (klank_oordeel, lees_klank_varianten, KLANK_MODELLEN, OPNAMES, SCORE_KLANKEN, WERK, bewerkingen, doel_variant, lees_ijking,
                          normaliseer, ruwe_score, score_onderdelen, vergelijk, zet_om, zinnen)
from coach import ARCHIEF, eigen_wav, eindoordeel, niets_gehoord, geschiedenis, kies_tips, oude_analyse, patronen, voorbeeld_wav, woordtijden

API = {
    "whisper": os.environ.get("WHISPER_API", "http://whisper-api:8001"),
    "klanken": os.environ.get("KLANKEN_API", "http://klanken-api:8002"),
    "mfa": os.environ.get("MFA_API", "http://mfa-api:8003"),
}
HIER = Path(__file__).parent
EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3",
       "audio/wav": "wav", "audio/x-wav": "wav", "audio/aac": "aac"}
MELODIEWOORDEN = {"anden", "tanken", "barnen", "parken"}
LENGTEWOORDEN = {"glas", "glass", "tak", "tack", "vit", "vitt"}


def lees_toelichting():
    uit = {}
    for regel in (HIER / "varianten.tsv").read_text(encoding="utf-8").splitlines():
        if regel.strip() and not regel.startswith("#"):
            d = regel.split("\t")
            uit[(d[0], d[1])] = d[3] if len(d) > 3 else d[2]
    return uit


TOELICHTING = lees_toelichting()


def vraag(naam, wav, zin_id):
    data = json.dumps({"wav": str(wav), "id": zin_id}).encode()
    req = urllib.request.Request(API[naam], data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.load(resp)
    except Exception as e:  # noqa: BLE001
        return {"fout": f"{naam}: {e}"}


def woord_oordeel(zin_id, r, res):
    """Per woord van de zin: goed / let op / fout, met uitleg. Combineert drie bronnen:
    Whisper (is het woord verstaan, hoe zeker), de klankherkenner (welke klanken van dít woord
    afwijken) en MFA (juiste uitspraakvariant bij de doelwoorden)."""
    weergave = r["zweeds"].split()
    # Elk getoond woord (met leestekens) → de genormaliseerde woorden waar het voor staat.
    norm = [normaliseer(w).split() for w in weergave]
    verwacht = [w for ws in norm for w in ws]
    info = [{"fouten": [], "let_op": []} for _ in verwacht]

    wh = res.get("whisper", {})
    if "herkend" in wh:
        herkend = normaliseer(wh["herkend"]).split()
        zeker = []   # zekerheid per genormaliseerd herkend woord (Whisper geeft het per eigen woord)
        for stuk in str(wh.get("woorden", "")).split():
            tekst, _, p = stuk.rpartition(":")
            zeker += [float(p)] * len(normaliseer(tekst).split())
        if len(zeker) != len(herkend):
            zeker = [None] * len(herkend)
        _, ops = bewerkingen(verwacht, herkend)
        i = j = 0
        for soort, a, b in ops:
            if soort == "I":
                if i < len(info):
                    info[i]["let_op"].append(f"daarvoor hoorde Whisper nog „{b}”")
                j += 1
                continue
            if soort == "=":
                p = zeker[j]
                if p is not None and p < 0.5:
                    info[i]["let_op"].append(f"Whisper twijfelde (zekerheid {round(100 * p)}%)")
            elif soort == "S":
                info[i]["fouten"].append(f"Whisper verstond „{b}”")
            else:
                info[i]["fouten"].append("Whisper hoorde dit woord niet")
            i += 1
            j += soort != "D"

    kl = res.get("klanken", {}).get(SCORE_KLANKEN, {})
    var = lees_klank_varianten().get(SCORE_KLANKEN)   # geleerd uit moedertaalsprekers (batch)
    pw = kl.get("per_woord") or []
    if len(pw) == len(verwacht):
        for i, w in enumerate(pw):
            if w["score"] is None or not w["fouten"]:
                continue
            status, tekst = klank_oordeel(w, var)
            if tekst:
                (info[i]["fouten"] if status == "fout" else info[i]["let_op"]).append(tekst)

    for k in res.get("mfa", {}).get("keuze", []):
        doel = doel_variant(zin_id, k["woord"])
        if k["gekozen"] != doel and k["woord"] in verwacht:
            i = verwacht.index(k["woord"])
            uitleg = TOELICHTING.get((k["woord"], k["gekozen"]), k["gekozen"])
            info[i]["fouten"].append(f"klonk als {uitleg}; bedoeld: {TOELICHTING.get((k['woord'], doel), doel)}")

    uit, i = [], 0
    for tekst, ws in zip(weergave, norm):
        delen = info[i:i + len(ws)]
        i += len(ws)
        fouten = [x for d in delen for x in d["fouten"]]
        let_op = [x for d in delen for x in d["let_op"]]
        uit.append({"tekst": tekst, "status": "fout" if fouten else "let_op" if let_op else "goed",
                    "uitleg": fouten + let_op})
    return uit


def feedback(zin_id, r, res):
    regels = []
    wh = res.get("whisper", {})
    if "herkend" in wh:
        verwacht, herkend = normaliseer(r["zweeds"]).split(), normaliseer(wh["herkend"]).split()
        if verwacht == herkend:
            regels.append(("goed", "verstaan", f"Verstaan: “{wh['herkend']}”"))
        else:
            _, ops = bewerkingen(verwacht, herkend)
            verschil = ", ".join(
                f"„{a}” werd „{b}”" if s == "S" else f"„{a}” ontbreekt" if s == "D" else f"„{b}” extra"
                for s, a, b in ops if s != "=")
            regels.append(("fout", "verstaan", f"Verstaan: “{wh['herkend']}” ({verschil})"))
    mfa = res.get("mfa", {})
    for k in mfa.get("keuze", []):
        doel = doel_variant(zin_id, k["woord"])
        uitleg_doel = TOELICHTING.get((k["woord"], doel), doel)
        if k["gekozen"] == doel:
            regels.append(("goed", "uitspraak", f"{k['woord']}: {uitleg_doel}"))
        else:
            uitleg = TOELICHTING.get((k["woord"], k["gekozen"]), k["gekozen"])
            regels.append(("fout", "uitspraak", f"{k['woord']}: klonk als {uitleg}; bedoeld: {uitleg_doel}"))
    kl = res.get("klanken", {}).get("xlsr300m-sv")
    if kl and "herkend" in kl:
        tekst = (f"verschillen met de verwachte klanken: {kl['verschillen']}" if kl["verschillen"]
                 else "geen verschil met de verwachte klanken")
        regels.append(("info", "klanken", f"Klankherkenner hoorde [{kl['herkend']}]; {tekst}"))
    for w in mfa.get("woorden", []):
        if w["woord"] in MELODIEWOORDEN and w.get("f0_toppen") != "":
            regels.append(("info", "melodie", f"{w['woord']}: {w['f0_toppen']} top(pen) in de toonhoogte "
                                              f"(accent 2 heeft er meestal twee, accent 1 één)"))
    gezien = set()
    for k in mfa.get("klinkers", []):
        if k["woord"] in LENGTEWOORDEN and k["woord"] not in gezien:
            gezien.add(k["woord"])
            regels.append(("info", "lengte", f"{k['klinker']} in {k['woord']}: {k['duur_ms']} ms "
                                             f"({round(100 * float(k['aandeel_woord']))}% van het woord)"))
    for naam, v in res.items():
        if isinstance(v, dict) and "fout" in v:
            regels.append(("info", "systeem", f"Analyse mislukt: {v['fout']}"))
    oordelen = [s for s, *_ in regels if s in ("goed", "fout")]
    oordeel = "fout" if "fout" in oordelen else "goed" if oordelen else "onbekend"
    return oordeel, [{"soort": s, "bron": b, "tekst": t} for s, b, t in regels]


def analyseer(zin_id, rij, wav, geluid, microfoon, archiefnaam):
    """Analyseert een (schoongemaakte, 16 kHz) opname met de drie API's en bewaart de uitkomst als
    werk/web/archief/<archiefnaam>.json. Voor nieuwe opnames en om een mislukte analyse over te doen."""
    t0 = time.perf_counter()
    with ThreadPoolExecutor(3) as pool:
        taken = {naam: pool.submit(vraag, naam, wav, zin_id) for naam in API}
        res = {naam: t.result() for naam, t in taken.items()}
    oordeel, regels = feedback(zin_id, rij, res)
    # Score: dezelfde berekening als de batch, vergeleken met de laatste ijking (werk/score_ijking.json).
    wh, kl, mfa = res.get("whisper", {}), res.get("klanken", {}), res.get("mfa", {})
    ijking = lees_ijking()
    modellen = KLANK_MODELLEN
    onderdelen = score_onderdelen(wh if "fout" not in wh else None,
                                  {m: kl.get(m) for m in modellen if isinstance(kl.get(m), dict)},
                                  mfa.get("keuze"), zin_id, native_per=(ijking or {}).get("native_per"))
    score = {**vergelijk(ruwe_score(onderdelen), ijking),
             "onderdelen": {n: round(100 * v) for n, v in onderdelen.items()}}
    # Opnamekwaliteit: blijft er na het schoonmaken veel brom over, of is het erg zacht, dan zeggen we dat.
    if geluid["veel_brom"]:
        regels.insert(0, {"soort": "fout", "bron": "opname",
                          "tekst": f"Veel laag bromgeluid in de opname ({geluid['brom_db']} dB, je stem "
                                   f"{geluid['spraak_db']} dB): dat maakt de analyse onbetrouwbaar. Houd de "
                                   "microfoon iets opzij van je mond (niet ervoor) en zet ventilatoren uit."})
    if geluid["zacht"]:
        regels.insert(0, {"soort": "fout", "bron": "opname",
                          "tekst": "De opname is erg zacht: spreek wat luider of zet de microfoon harder."})
    try:
        woorden = woord_oordeel(zin_id, rij, res)
    except Exception as e:  # noqa: BLE001 — per woord is extra; de rest van de uitslag gaat voor
        print("woord_oordeel mislukt:", repr(e), flush=True)
        woorden = []
    # Gebruikersvriendelijke laag (coach.py): één oordeel in woorden, hoogstens twee tips, woordtijden om
    # te luisteren en vergelijken, en terugkerende patronen over je opnames.
    try:
        pat = patronen()
        tips = kies_tips(zin_id, rij, res, TOELICHTING, pat)
        tijden = woordtijden(zin_id, rij, res)
        if len(tijden) == len(woorden):
            woorden = [dict(w, **t) for w, t in zip(woorden, tijden)]
    except Exception as e:  # noqa: BLE001 — de coachlaag is extra; de rest van de uitslag gaat voor
        print("coach mislukt:", repr(e), flush=True)
        pat, tips = [], []
    if niets_gehoord(wh, geluid):
        tips = []   # bij een stille opname zijn tips onzin
    kop, zin, soort = eindoordeel(score, wh if "fout" not in wh else None, tips, geluid)
    uit = {"id": zin_id, "oordeel": oordeel, "eindoordeel": {"kop": kop, "zin": zin, "soort": soort},
           "tips": tips, "patronen": pat, "score": score, "woorden": woorden, "feedback": regels,
           "audio": {"eigen": f"/api/audio/{wav.name}",
                     "voorbeeld": f"/api/voorbeeld/{zin_id}" if voorbeeld_wav(zin_id) else None},
           "geluid": geluid, "microfoon": microfoon, "resultaten": res,
           "sec": round(time.perf_counter() - t0, 1)}
    (ARCHIEF / f"{archiefnaam}.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1), encoding="utf-8")
    return uit


class Handler(BaseHTTPRequestHandler):
    def _stuur(self, code, body, soort="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", soort)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        pad = urlparse(self.path).path
        if pad in ("/", "/index.html"):
            self._stuur(200, (HIER / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif pad == "/api/zinnen":
            opgenomen = {p.stem.upper() for p in OPNAMES.glob("*.*")}
            self._stuur(200, [dict(r, opgenomen=i in opgenomen, voorbeeld=voorbeeld_wav(i) is not None)
                              for i, r in zinnen().items()])
        elif pad == "/api/patronen":
            self._stuur(200, patronen())
        elif m := re.fullmatch(r"/api/geschiedenis/([A-Z]\d\d)", pad):
            self._stuur(200, geschiedenis(m.group(1), zinnen().get(m.group(1)), TOELICHTING))
        elif m := re.fullmatch(r"/api/analyse/([A-Z]\d\d-\d{8}-\d{6})", pad):
            # Een eerdere opname terugkijken: de bewaarde analyse, aangevuld met de nieuwere feedbacklaag.
            naam = m.group(1)
            if not (ARCHIEF / f"{naam}.json").exists():
                return self._stuur(404, {"fout": "geen analyse"})
            rij = zinnen().get(naam[:3])
            oud = json.loads((ARCHIEF / f"{naam}.json").read_text(encoding="utf-8"))
            wav = eigen_wav(naam)
            # Mislukt (bv. opgenomen terwijl de analyses nog niet klaar waren): nu opnieuw analyseren.
            opnieuw = (oud.get("score") or {}).get("ruw") is None and rij is not None and wav is not None
            if opnieuw:
                analyseer(naam[:3], rij, wav, oud.get("geluid") or {"veel_brom": False, "zacht": False},
                          oud.get("microfoon") or {}, naam)
            self._stuur(200, dict(oude_analyse(naam, rij, TOELICHTING), opnieuw_geanalyseerd=opnieuw))
        elif m := re.fullmatch(r"/api/audio/([A-Z]\d\d-\d{8}-\d{6}(?:-16k)?\.wav)", pad):
            # Je eigen opname (schoongemaakt, 16 kHz): de woordtijden van MFA horen bij dit bestand.
            f = ARCHIEF / m.group(1)
            self._stuur(200, f.read_bytes(), "audio/wav") if f.exists() else self._stuur(404, {"fout": "geen opname"})
        elif m := re.fullmatch(r"/api/voorbeeld/([A-Z]\d\d)", pad):
            f = voorbeeld_wav(m.group(1))
            self._stuur(200, f.read_bytes(), "audio/wav") if f else self._stuur(404, {"fout": "geen voorbeeld"})
        elif pad == "/api/status":
            uit = {}
            for naam, url in API.items():
                try:
                    urllib.request.urlopen(url, timeout=2).read()
                    uit[naam] = True
                except Exception:  # noqa: BLE001
                    uit[naam] = False
            self._stuur(200, uit)
        else:
            self._stuur(404, {"fout": "niet gevonden"})

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != "/api/opname":
            return self._stuur(404, {"fout": "niet gevonden"})
        zin_id = parse_qs(url.query).get("id", [""])[0].upper()
        rijen = zinnen()
        if zin_id not in rijen:
            return self._stuur(400, {"fout": f"onbekende id {zin_id}"})
        audio = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        # Welke microfoon de browser gebruikte (naam, kanalen, samplerate, piekniveau): voor controle achteraf.
        try:
            from urllib.parse import unquote
            microfoon = json.loads(unquote(self.headers.get("X-Microfoon", "")) or "{}")
        except ValueError:
            microfoon = {}
        if len(audio) < 1000:
            return self._stuur(400, {"fout": "opname is leeg"})
        ext = EXT.get(self.headers.get("Content-Type", "").split(";")[0].strip(), "webm")

        # Bewaren: opnames/<ID>.<ext> (laatste versie, voor de batchproef) + archief in werk/.
        for oud in OPNAMES.glob(f"{zin_id}.*"):
            oud.unlink()
        (OPNAMES / f"{zin_id}.{ext}").write_bytes(audio)
        stempel = time.strftime("%Y%m%d-%H%M%S")
        archief = WERK / "web" / "archief"
        archief.mkdir(parents=True, exist_ok=True)
        bron = archief / f"{zin_id}-{stempel}.{ext}"
        bron.write_bytes(audio)
        wav = archief / f"{zin_id}-{stempel}-16k.wav"  # eigen naam: de upload kan zelf een .wav zijn
        geluid = zet_om(bron, wav)   # 16 kHz mono; plof bij het aanzetten en brom onder 80 Hz eruit

        uit = analyseer(zin_id, rijen[zin_id], wav, geluid, microfoon, f"{zin_id}-{stempel}")
        self._stuur(200, uit)

    def log_message(self, fmt, *args):
        print(self.address_string(), fmt % args, flush=True)


if __name__ == "__main__":
    print("Testpagina op http://localhost:8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
