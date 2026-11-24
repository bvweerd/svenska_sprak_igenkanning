"""Minimale testpagina: opnemen in de browser, opslaan in opnames/, analyseren met de drie
API's (whisper, klanken, mfa) en feedback teruggeven. Alleen voor de proef, niet voor de site.

Feedback in lagen: eerst het oordeel (verstaan? goede uitspraakvariant gekozen?), dan informatie
(klankherkenner, toonhoogte, klinkerduur) en onderaan de ruwe resultaten.
"""
import json
import os
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from proef_common import OPNAMES, WERK, bewerkingen, normaliseer, zinnen

API = {
    "whisper": os.environ.get("WHISPER_API", "http://whisper-api:8001"),
    "klanken": os.environ.get("KLANKEN_API", "http://klanken-api:8002"),
    "mfa": os.environ.get("MFA_API", "http://mfa-api:8003"),
}
HIER = Path(__file__).parent
EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3",
       "audio/wav": "wav", "audio/x-wav": "wav", "audio/aac": "aac"}
# Bedoelde uitspraak bij de woorden met woordaccent; overige variantwoorden: 'goed'.
DOEL_ACCENT = {"A01": "accent1", "A02": "accent2", "A03": "accent1", "A04": "accent2", "D06": "accent2"}
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
        doel = DOEL_ACCENT.get(zin_id, "goed") if k["woord"] in ("anden", "tanken") else "goed"
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
            self._stuur(200, [dict(r, opgenomen=i in opgenomen) for i, r in zinnen().items()])
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
        wav = archief / f"{zin_id}-{stempel}.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(bron), "-ac", "1", "-ar", "16000",
                        "-sample_fmt", "s16", str(wav)], check=True)

        t0 = time.perf_counter()
        with ThreadPoolExecutor(3) as pool:
            taken = {naam: pool.submit(vraag, naam, wav, zin_id) for naam in API}
            res = {naam: t.result() for naam, t in taken.items()}
        oordeel, regels = feedback(zin_id, rijen[zin_id], res)
        uit = {"id": zin_id, "oordeel": oordeel, "feedback": regels, "resultaten": res,
               "sec": round(time.perf_counter() - t0, 1)}
        (archief / f"{zin_id}-{stempel}.json").write_text(json.dumps(uit, ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
        self._stuur(200, uit)

    def log_message(self, fmt, *args):
        print(self.address_string(), fmt % args, flush=True)


if __name__ == "__main__":
    print("Testpagina op http://localhost:8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
