"""Uitspraaktrainer Zweeds (productieversie): oefenstukken van de A- en B-site voorlezen, opnemen en feedback.

- Teksten: data/teksten.json (app/importeer).
- Voorbeeldstem: data/voorbeeld/<stuk>.wav + .json met woordtijden (app/voorbeeld, een achtergrondtaak).
- Opnames per gebruiker: data/opnames/<gebruiker>/<stuk>__<stempel>.{webm|m4a|…} (origineel), -16k.wav
  (schoongemaakt), .meta.json (tekst, microfoon) en .json (analyse); index.json houdt per opname het oordeel bij.
- Eén wachtrij, één analyse tegelijk, de drie analyses na elkaar: zo blijft de lichte server bruikbaar.
"""
import json
import os
import queue
import re
import threading
import time
import traceback
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from coach import eindoordeel, kies_tips, niets_gehoord, patronen, score_van, woordtijden, zet_namen
from proef_common import (SCORE_KLANKEN, bewerkingen, doel_variant, klank_oordeel, lees_klank_varianten,
                          normaliseer, zet_om)

DATA = Path(os.environ.get("PROEF_DATA", "/data"))
TEKSTEN = DATA / "teksten.json"
OPNAMES = DATA / "opnames"
VOORBEELD = DATA / "voorbeeld"
CADDY_ROOT = Path(os.environ.get("CADDY_ROOT", "/caddy/caddy/pki/authorities/local/root.crt"))
HIER = Path(__file__).parent
API = {  # volgorde = volgorde van analyseren
    "whisper": os.environ.get("WHISPER_API", "http://whisper-api:8001"),
    "klanken": os.environ.get("KLANKEN_API", "http://klanken-api:8002"),
    "mfa": os.environ.get("MFA_API", "http://mfa-api:8003"),
}
EXT = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/mpeg": "mp3",
       "audio/wav": "wav", "audio/x-wav": "wav", "audio/aac": "aac"}
NAAM = re.compile(r"[A-Za-z0-9-]+__\d{8}-\d{6}")
PATROON_STUKKEN = 30      # patronen over de laatste opname van zoveel recent geoefende stukken


def slug(t):
    import unicodedata
    t = unicodedata.normalize("NFKD", t.lower())
    return re.sub(r"[^a-z0-9]+", "-", "".join(c for c in t if not unicodedata.combining(c))).strip("-")


GEBRUIKERS = {slug(n): n.strip() for n in os.environ.get("GEBRUIKERS", "Gebruiker 1,Gebruiker 2").split(",") if n.strip()}


def lees_toelichting():
    uit = {}
    for regel in (HIER / "varianten.tsv").read_text(encoding="utf-8").splitlines():
        if regel.strip() and not regel.startswith("#"):
            d = regel.split("\t")
            uit[(d[0], d[1])] = d[3] if len(d) > 3 else d[2]
    return uit


TOELICHTING = lees_toelichting()


# ---------- teksten (opnieuw ingelezen als de import draaide) ----------

class Teksten:
    def __init__(self):
        self.mtime, self.data, self.stukken, self.lock = None, {"teksten": []}, {}, threading.Lock()

    def ververs(self):
        with self.lock:
            try:
                m = TEKSTEN.stat().st_mtime
            except OSError:
                return
            if m == self.mtime:
                return
            self.data = json.loads(TEKSTEN.read_text(encoding="utf-8"))
            self.stukken = {}
            for t in self.data["teksten"]:
                for i, s in enumerate(t["stukken"]):
                    self.stukken[s["id"]] = dict(s, tekst_id=t["id"], nr=i + 1, van=len(t["stukken"]))
            zet_namen(s["tekst"] for s in self.stukken.values())
            self.mtime = m

    def stuk(self, stuk_id):
        self.ververs()
        return self.stukken.get(stuk_id)


TEKST = Teksten()


def rij(stuk):
    return {"id": stuk["id"], "zweeds": stuk["tekst"]}


# ---------- voorbeeldstem ----------

def voorbeeld(stuk):
    """(wav, woordtijden) van de voorbeeldstem, als die bij de huidige tekst hoort; anders (None, [])."""
    j, w = VOORBEELD / f"{stuk['id']}.json", VOORBEELD / f"{stuk['id']}.wav"
    try:
        d = json.loads(j.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, []
    if d.get("tekst") != stuk["tekst"] or not w.exists():
        return None, []
    return w, [tuple(x) for x in d.get("woorden") or [] if x[2] not in ("", "<eps>", "<unk>")]   # <eps> = pauze


_voortgang_vb = {"t": 0, "uit": None}


def voorbeeld_voortgang():
    if time.time() - _voortgang_vb["t"] > 60:
        TEKST.ververs()
        klaar = sum(voorbeeld(s)[0] is not None for s in TEKST.stukken.values())
        _voortgang_vb.update(t=time.time(), uit={"klaar": klaar, "totaal": len(TEKST.stukken)})
    return _voortgang_vb["uit"]


# ---------- opslag per gebruiker ----------

def map_van(gebruiker):
    m = OPNAMES / gebruiker
    m.mkdir(parents=True, exist_ok=True)
    return m


_index_lock = threading.Lock()


def lees_index(gebruiker):
    try:
        return json.loads((map_van(gebruiker) / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def zet_in_index(gebruiker, naam, waarden):
    with _index_lock:
        idx = lees_index(gebruiker)
        idx[naam] = dict(idx.get(naam, {}), **waarden)
        pad = map_van(gebruiker) / "index.json"
        tmp = pad.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
        tmp.replace(pad)


def tijd_van(naam):
    s = naam.split("__")[1]
    return f"{s[6:8]}-{s[4:6]}-{s[:4]} {s[9:11]}:{s[11:13]}"


def recente_analyses(gebruiker):
    """De resultaten van de laatste opname van de recentst geoefende stukken (voor de patronen)."""
    idx = lees_index(gebruiker)
    laatste = {}
    for naam in sorted(idx):
        if idx[naam].get("klaar"):
            laatste[idx[naam]["stuk"]] = naam
    uit = []
    for naam in sorted(laatste.values())[-PATROON_STUKKEN:]:
        try:
            uit.append(json.loads((map_van(gebruiker) / f"{naam}.json").read_text(encoding="utf-8"))["resultaten"])
        except (OSError, ValueError, KeyError):
            pass
    return uit


# ---------- analyse ----------

def vraag(naam, wav, stuk):
    data = json.dumps({"wav": str(wav), "id": stuk["id"], "tekst": stuk["tekst"]}).encode()
    req = urllib.request.Request(API[naam], data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=1800) as resp:
            return json.load(resp)
    except Exception as e:  # noqa: BLE001
        return {"fout": f"{naam}: {e}"}


def woord_oordeel(stuk_id, r, res):
    """Per woord: goed / let op / fout, met uitleg (Whisper, klankherkenner, MFA). Zoals in de proef."""
    weergave = r["zweeds"].split()
    norm = [normaliseer(w).split() for w in weergave]
    verwacht = [w for ws in norm for w in ws]
    info = [{"fouten": [], "let_op": []} for _ in verwacht]
    wh = res.get("whisper", {})
    if "herkend" in wh:
        herkend = normaliseer(wh["herkend"]).split()
        zeker = []
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
    var = lees_klank_varianten().get(SCORE_KLANKEN)
    pw = res.get("klanken", {}).get(SCORE_KLANKEN, {}).get("per_woord") or []
    if len(pw) == len(verwacht):
        for i, w in enumerate(pw):
            if w["score"] is None or not w["fouten"]:
                continue
            status, tekst = klank_oordeel(w, var)
            if tekst:
                (info[i]["fouten"] if status == "fout" else info[i]["let_op"]).append(tekst)
    for k in res.get("mfa", {}).get("keuze", []):
        doel = doel_variant(stuk_id, k["woord"])
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


def meldingen_geluid(geluid):
    uit = []
    if geluid.get("zacht"):
        uit.append("De opname is erg zacht: spreek wat luider of zet de microfoon harder.")
    if geluid.get("veel_brom"):
        uit.append(f"Veel laag bromgeluid in de opname ({geluid['brom_db']} dB, je stem {geluid['spraak_db']} dB): "
                   "dat maakt de analyse onbetrouwbaar. Houd de microfoon iets opzij van je mond en zet "
                   "ventilatoren uit.")
    return uit


def analyseer(gebruiker, naam):
    """Analyseert een opname (de drie API's na elkaar) en bewaart <naam>.json en het oordeel in de index."""
    m = map_van(gebruiker)
    meta = json.loads((m / f"{naam}.meta.json").read_text(encoding="utf-8"))
    stuk = {"id": meta["stuk"], "tekst": meta["tekst"]}
    wav = m / f"{naam}-16k.wav"
    t0 = time.perf_counter()
    res = {}
    for api in API:
        WACHTRIJ.bezig = {"gebruiker": gebruiker, "naam": naam, "stap": api}
        res[api] = vraag(api, wav, stuk)
    r = rij(stuk)
    score = score_van(stuk["id"], res)
    wh = res.get("whisper", {})
    try:
        woorden = woord_oordeel(stuk["id"], r, res)
    except Exception:  # noqa: BLE001 — per woord is extra
        traceback.print_exc()
        woorden = []
    try:
        tips = [] if niets_gehoord(wh, meta.get("geluid")) else \
            kies_tips(stuk["id"], r, res, TOELICHTING, patronen(recente_analyses(gebruiker)))
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        tips = []
    kop, zin, soort = eindoordeel(score, wh if "fout" not in wh else None, tips, meta.get("geluid"))
    uit = {"naam": naam, "stuk": stuk["id"], "tekst": stuk["tekst"], "tijd": tijd_van(naam),
           "eindoordeel": {"kop": kop, "zin": zin, "soort": soort}, "tips": tips, "score": score,
           "woorden": woorden, "meldingen": meldingen_geluid(meta.get("geluid") or {}),
           "fouten": [v["fout"] for v in res.values() if isinstance(v, dict) and "fout" in v],
           "microfoon": meta.get("microfoon"), "resultaten": res, "sec": round(time.perf_counter() - t0, 1)}
    (m / f"{naam}.json").write_text(json.dumps(uit, ensure_ascii=False), encoding="utf-8")
    zet_in_index(gebruiker, naam, {"stuk": stuk["id"], "klaar": True, "kop": kop, "soort": soort,
                                   "schaal": score.get("gelijkenis"), "tijd": tijd_van(naam)})
    print(f"[analyse] {gebruiker}/{naam}: {kop} ({score.get('gelijkenis')}) in {uit['sec']} s", flush=True)


def met_audio(gebruiker, d):
    """Een bewaarde analyse, aangevuld met de woordtijden van het voorbeeld (dat kan later gemaakt zijn) en de
    adressen van de audio."""
    stuk = {"id": d["stuk"], "tekst": d["tekst"]}
    huidig = TEKST.stuk(d["stuk"])
    wav_vb, tijden_vb = voorbeeld(huidig) if huidig and huidig["tekst"] == d["tekst"] else (None, [])
    tijden = woordtijden(rij(stuk), d.get("resultaten", {}), tijden_vb)
    if len(tijden) == len(d.get("woorden") or []):
        d["woorden"] = [dict(w, **t) for w, t in zip(d["woorden"], tijden)]
    d["audio"] = {"eigen": f"/api/{gebruiker}/audio/{d['naam']}-16k.wav",
                  "voorbeeld": f"/api/voorbeeld/{d['stuk']}" if wav_vb else None}
    d.pop("resultaten", None)       # groot, en de pagina heeft het niet nodig
    return d


class Wachtrij:
    """Eén analyse tegelijk. Na een herstart gaan opnames zonder analyse vanzelf weer in de rij."""

    def __init__(self):
        self.q, self.lijst, self.bezig, self.lock = queue.Queue(), [], None, threading.Lock()

    def zet(self, gebruiker, naam):
        with self.lock:
            if (gebruiker, naam) not in self.lijst:
                self.lijst.append((gebruiker, naam))
                self.q.put((gebruiker, naam))

    def plek(self, gebruiker, naam):
        with self.lock:
            return self.lijst.index((gebruiker, naam)) + 1 if (gebruiker, naam) in self.lijst else None

    def werk(self):
        while True:
            gebruiker, naam = self.q.get()
            try:
                analyseer(gebruiker, naam)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                zet_in_index(gebruiker, naam, {"klaar": False, "fout": repr(e)})
            finally:
                with self.lock:
                    self.lijst.remove((gebruiker, naam))
                    self.bezig = None

    def herstel(self):
        for g in GEBRUIKERS:
            m = map_van(g)
            for meta in sorted(m.glob("*.meta.json")):
                naam = meta.name[:-len(".meta.json")]
                if not (m / f"{naam}.json").exists():
                    self.zet(g, naam)


WACHTRIJ = Wachtrij()


# ---------- http ----------

CERT_PAGINA = """<!doctype html><html lang="nl"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Certificaat</title><style>body{font:16px/1.5 system-ui,sans-serif;max-width:40rem;margin:0 auto;padding:1rem}
a.knop{display:inline-block;padding:.6rem 1rem;background:#2463eb;color:#fff;border-radius:.4rem;text-decoration:none}
li{margin:.3rem 0}</style>
<h1>Certificaat vertrouwen (eenmalig per apparaat)</h1>
<p>De trainer draait met een eigen certificaat. Browsers geven de microfoon alleen vrij op een beveiligde
(https) pagina, en vertrouwen dit certificaat pas als je het één keer installeert.</p>
<p><a class="knop" href="/certificaat/root.crt">Certificaat downloaden</a></p>
<h2>iPhone / iPad</h2><ol><li>Open deze pagina in <b>Safari</b> en download het certificaat; kies <i>Sta toe</i>.</li>
<li>Instellingen → <i>Profiel gedownload</i> → Installeer.</li>
<li>Instellingen → Algemeen → Info → <b>Certificaatvertrouwen</b> → zet het certificaat aan.</li></ol>
<h2>Android</h2><ol><li>Download het certificaat.</li>
<li>Instellingen → Beveiliging (en privacy) → Meer beveiligingsinstellingen → Versleuteling en inloggegevens →
<b>Certificaat installeren</b> → CA-certificaat → kies het bestand. (De namen verschillen per toestel; zoek
in Instellingen op „certificaat”.)</li></ol>
<h2>Windows</h2><ol><li>Download en open het bestand → Certificaat installeren → Huidige gebruiker →
Alle certificaten in het volgende archief plaatsen → <b>Vertrouwde basiscertificeringsinstanties</b>.</li>
<li>Herstart de browser.</li></ol>
<h2>macOS</h2><ol><li>Open het bestand (Sleutelhangertoegang) → dubbelklik op het certificaat →
Vertrouw → <b>Altijd vertrouwen</b>.</li></ol>
<p>Firefox gebruikt een eigen lijst: Instellingen → Privacy en beveiliging → Certificaten bekijken → Autoriteiten →
Importeren.</p><p><a href="/">← naar de trainer</a></p></html>"""


class Handler(BaseHTTPRequestHandler):
    def _stuur(self, code, body, soort="application/json; charset=utf-8", extra=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", soort)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _bestand(self, pad, soort):
        return self._stuur(200, pad.read_bytes(), soort) if pad and pad.exists() else self._stuur(404, {"fout": "niet gevonden"})

    def do_GET(self):
        url = urlparse(self.path)
        pad, q = url.path, parse_qs(url.query)
        if pad in ("/", "/index.html"):
            return self._stuur(200, (HIER / "index.html").read_bytes(), "text/html; charset=utf-8")
        if pad == "/certificaat":
            return self._stuur(200, CERT_PAGINA.encode("utf-8"), "text/html; charset=utf-8")
        if pad == "/certificaat/root.crt":
            if not CADDY_ROOT.exists():
                return self._stuur(404, {"fout": "nog geen certificaat (start Caddy eerst)"})
            return self._stuur(200, CADDY_ROOT.read_bytes(), "application/x-x509-ca-cert",
                               {"Content-Disposition": 'attachment; filename="uitspraak-root.crt"'})
        if pad == "/api/gebruikers":
            return self._stuur(200, [{"id": k, "naam": v} for k, v in GEBRUIKERS.items()])
        if pad == "/api/teksten":
            TEKST.ververs()
            return self._stuur(200, TEKST.data)
        if pad == "/api/status":
            uit = {}
            for naam, adres in API.items():
                try:
                    urllib.request.urlopen(adres, timeout=2).read()
                    uit[naam] = True
                except Exception:  # noqa: BLE001
                    uit[naam] = False
            return self._stuur(200, {"analyses": uit, "voorbeeld": voorbeeld_voortgang(),
                                     "wachtrij": len(WACHTRIJ.lijst)})
        if pad == "/api/wachtrij":       # voor de voorbeeldtaak: die wacht als er geanalyseerd wordt
            return self._stuur(200, {"lengte": len(WACHTRIJ.lijst), "bezig": WACHTRIJ.bezig is not None})
        if m := re.fullmatch(r"/api/voorbeeld/([A-Za-z0-9-]+)", pad):
            stuk = TEKST.stuk(m.group(1))
            return self._bestand(voorbeeld(stuk)[0] if stuk else None, "audio/wav")
        if m := re.fullmatch(r"/api/([a-z0-9-]+)/(.*)", pad):
            gebruiker, rest = m.groups()
            if gebruiker not in GEBRUIKERS:
                return self._stuur(404, {"fout": "onbekende gebruiker"})
            return self.gebruiker_get(gebruiker, rest, q)
        return self._stuur(404, {"fout": "niet gevonden"})

    def gebruiker_get(self, g, rest, q):
        if rest == "voortgang":
            # Per stuk het oordeel van de laatste opname.
            uit = {}
            for naam, v in sorted(lees_index(g).items()):
                if v.get("klaar"):
                    uit[v["stuk"]] = {"kop": v["kop"], "soort": v["soort"], "schaal": v.get("schaal"), "tijd": v["tijd"]}
            return self._stuur(200, uit)
        if rest == "patronen":
            return self._stuur(200, patronen(recente_analyses(g)))
        if m := re.fullmatch(r"geschiedenis/([A-Za-z0-9-]+)", rest):
            idx = lees_index(g)
            return self._stuur(200, [dict(v, naam=n) for n, v in sorted(idx.items(), reverse=True)
                                     if v.get("stuk") == m.group(1)])
        if m := re.fullmatch(r"analyse/(" + NAAM.pattern + ")", rest):
            naam = m.group(1)
            f = map_van(g) / f"{naam}.json"
            if f.exists():
                return self._stuur(200, dict(met_audio(g, json.loads(f.read_text(encoding="utf-8"))), status="klaar"))
            if not (map_van(g) / f"{naam}.meta.json").exists():
                return self._stuur(404, {"fout": "onbekende opname"})
            plek = WACHTRIJ.plek(g, naam)
            if plek is None:
                return self._stuur(200, {"status": "mislukt", "fout": lees_index(g).get(naam, {}).get("fout", "")})
            bezig = WACHTRIJ.bezig or {}
            stap = bezig.get("stap") if bezig.get("naam") == naam and bezig.get("gebruiker") == g else None
            return self._stuur(200, {"status": "bezig" if stap else "wachtrij", "plek": plek, "stap": stap})
        if m := re.fullmatch(r"audio/(" + NAAM.pattern + r"-16k\.wav)", rest):
            return self._bestand(map_van(g) / m.group(1), "audio/wav")
        return self._stuur(404, {"fout": "niet gevonden"})

    def do_POST(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        g = q.get("gebruiker", [""])[0]
        if g not in GEBRUIKERS:
            return self._stuur(400, {"fout": "kies eerst wie je bent"})
        if m := re.fullmatch(r"/api/opnieuw/(" + NAAM.pattern + ")", url.path):
            naam = m.group(1)
            if not (map_van(g) / f"{naam}.meta.json").exists():
                return self._stuur(404, {"fout": "onbekende opname"})
            (map_van(g) / f"{naam}.json").unlink(missing_ok=True)
            WACHTRIJ.zet(g, naam)
            return self._stuur(200, {"naam": naam, "status": "wachtrij", "plek": WACHTRIJ.plek(g, naam)})
        if url.path != "/api/opname":
            return self._stuur(404, {"fout": "niet gevonden"})
        stuk = TEKST.stuk(q.get("stuk", [""])[0])
        if not stuk:
            return self._stuur(400, {"fout": "onbekend oefenstuk"})
        audio = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if len(audio) < 1000:
            return self._stuur(400, {"fout": "opname is leeg"})
        try:
            microfoon = json.loads(unquote(self.headers.get("X-Microfoon", "")) or "{}")
        except ValueError:
            microfoon = {}
        ext = EXT.get(self.headers.get("Content-Type", "").split(";")[0].strip(), "webm")
        naam = f"{stuk['id']}__{time.strftime('%Y%m%d-%H%M%S')}"
        m = map_van(g)
        bron = m / f"{naam}.{ext}"
        bron.write_bytes(audio)
        try:
            geluid = zet_om(bron, m / f"{naam}-16k.wav")   # 16 kHz mono; plof en brom eruit (ook mp4 van Safari)
        except Exception as e:  # noqa: BLE001
            return self._stuur(400, {"fout": f"kon de opname niet omzetten ({ext}): {e}"})
        (m / f"{naam}.meta.json").write_text(json.dumps(
            {"stuk": stuk["id"], "tekst": stuk["tekst"], "microfoon": microfoon, "geluid": geluid},
            ensure_ascii=False), encoding="utf-8")
        zet_in_index(g, naam, {"stuk": stuk["id"], "klaar": False, "tijd": tijd_van(naam)})
        WACHTRIJ.zet(g, naam)
        self._stuur(200, {"naam": naam, "status": "wachtrij", "plek": WACHTRIJ.plek(g, naam)})

    def log_message(self, fmt, *args):
        if not re.search(r"/analyse/|/api/wachtrij|/api/status", str(args[0] if args else "")):   # pollen niet loggen
            print(self.address_string(), fmt % args, flush=True)


if __name__ == "__main__":
    TEKST.ververs()
    threading.Thread(target=WACHTRIJ.werk, daemon=True).start()
    WACHTRIJ.herstel()
    print(f"Uitspraaktrainer op poort 8080 (gebruikers: {', '.join(GEBRUIKERS.values())})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
