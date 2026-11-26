"""Gedeelde code van de uitspraaktrainer (in elk image gekopieerd): teksten vergelijken, audio omzetten, de score
en het oordeel per woord. De keuzes (gewichten, drempels, ijking) komen uit de proef; zie ONDERZOEK.md en de
git-tag 'proef'.
"""
import os
import re
import unicodedata
from pathlib import Path

DATA = Path(os.environ.get("DATA", "/data"))


def rij_voor_verzoek(verzoek):
    """De zin bij een API-verzoek {"wav": pad, "id": stuk-id, "tekst": tekst}."""
    return {"id": verzoek.get("id", ""), "zweeds": verzoek["tekst"]}


def woordenboek_extra():
    """Uitspraken voor woorden die niet in het MFA-woordenboek staan (vooral namen; gemaakt met MFA's G2P door
    app/woordenboek): [(woord, uitspraak)]. Leeg als het bestand er niet is."""
    pad = Path(os.environ.get("WOORDENBOEK_EXTRA", "/teksten/woordenboek_extra.dict"))
    if not pad.exists():
        return []
    uit = []
    for regel in pad.read_text(encoding="utf-8").splitlines():
        delen = regel.split("\t")
        if len(delen) >= 2 and delen[0].strip():
            uit.append((delen[0].strip(), delen[-1].strip()))
    return uit


# ---------- teksten vergelijken ----------

GELIJKE_VORMEN = {"idag": "i dag"}     # schrijfwijzen die hetzelfde zijn


def _getal(w):
    """Een getal dat Whisper in cijfers schreef, in woorden (zoals de import de teksten schrijft)."""
    if w in GELIJKE_VORMEN or not w.isdigit():
        return GELIJKE_VORMEN.get(w, w)
    try:
        from num2words import num2words
        return num2words(int(w), lang="sv")
    except (ImportError, NotImplementedError, ValueError, OverflowError):
        return w


def normaliseer(tekst):
    """Kleine letters, zonder leestekens, getallen in woorden; voor het vergelijken van zinnen."""
    tekst = unicodedata.normalize("NFC", tekst.lower())
    tekst = re.sub(r"[^\w\s]", " ", tekst)
    return " ".join(_getal(w) for w in tekst.split())


def bewerkingen(a, b):
    """Levenshtein-uitlijning van twee lijsten. Geeft (afstand, ops) met ops als
    (soort, a_item, b_item), soort in {'=', 'S', 'D', 'I'}."""
    n, m = len(a), len(b)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
    ops, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (a[i - 1] != b[j - 1]):
            ops.append(("=" if a[i - 1] == b[j - 1] else "S", a[i - 1], b[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            ops.append(("D", a[i - 1], ""))
            i -= 1
        else:
            ops.append(("I", "", b[j - 1]))
            j -= 1
    return d[n][m], ops[::-1]


def foutpercentage(verwacht, herkend):
    """Fractie bewerkingen t.o.v. de lengte van 'verwacht' (WER of PER)."""
    afstand, _ = bewerkingen(verwacht, herkend)
    return afstand / max(len(verwacht), 1)


def ops_tekst(ops):
    """Alleen de verschillen, leesbaar: 'a→b', '-a', '+b'."""
    delen = []
    for soort, x, y in ops:
        if soort == "S":
            delen.append(f"{x}→{y}")
        elif soort == "D":
            delen.append(f"-{x}")
        elif soort == "I":
            delen.append(f"+{y}")
    return " ".join(delen)


# ---------- audio omzetten en schoonmaken (ffmpeg) ----------

LAAG = "lowpass=f=80,lowpass=f=80"         # bromgeluid, plof bij het aanzetten van de microfoon
SPRAAK = "highpass=f=80,highpass=f=80"     # alles waar spraak in zit
PLOF_SEC = 0.6                             # zo lang duurt de plof bij het aanzetten (gemeten: ±0,6 s)


def _rms(bron, filter_, start=None, eind=None):
    """RMS (dB) van een stuk audio na een filter, via ffmpeg astats."""
    import subprocess
    trim = f"atrim={start or 0}" + (f":{eind}" if eind else "") + "," if start or eind else ""
    uit = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(bron), "-af",
                          f"{trim}{filter_},astats=metadata=0:measure_overall=RMS_level:measure_perchannel=none",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.findall(r"RMS level dB: (-?[\d.]+|-inf)", uit)
    return float(m[-1]) if m and m[-1] != "-inf" else -120.0


def zet_om(bron, doel):
    """Opname → 16 kHz mono wav, schoongemaakt. Begint de opname met een plof (veel meer laag dan spraak in de
    eerste 0,25 s, typisch voor een headset die net aangaat), dan gaat de eerste 0,6 s eraf; brom onder 80 Hz gaat
    altijd weg. Geeft info terug (voor een waarschuwing op de pagina)."""
    import subprocess
    plof_laag = _rms(bron, LAAG, 0, 0.25)
    # Een echte plof is luid, houdt daarna op en zit alleen in het laag (een stem die meteen begint niet).
    laag_daarna = _rms(bron, LAAG, 0.7)
    spraak_begin = _rms(bron, SPRAAK, 0, 0.25)
    plof = plof_laag > -30 and plof_laag > spraak_begin + 6 and plof_laag > laag_daarna + 12
    start = PLOF_SEC if plof else 0
    brom = _rms(bron, LAAG, max(start, 0.25))
    spraak = _rms(bron, SPRAAK, start)
    af = (f"atrim=start={start},asetpts=PTS-STARTPTS," if plof else "") + SPRAAK
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(bron), "-af", af, "-ac", "1",
                    "-ar", "16000", "-sample_fmt", "s16", str(doel)], check=True)
    return {"plof_weggehaald": plof, "brom_db": round(brom, 1), "spraak_db": round(spraak, 1),
            # Onder 80 Hz zit ook de grondtoon van een lage stem: pas als het laag luider is dan de spraak, is het
            # echt brom (ventilator, luchtstroom).
            "veel_brom": brom > spraak + 3 and brom > -40, "zacht": spraak < -45}


def serveer(analyseer, poort):
    """Kleine interne JSON-API: POST {"wav": pad, "id": stuk-id, "tekst": tekst} → analyse.
    Eén verzoek tegelijk (modellen zijn niet thread-safe); GET / = gezondheidscheck."""
    import json
    import traceback
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def _stuur(self, code, data):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._stuur(200, {"ok": True})

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
                self._stuur(200, analyseer(json.loads(self.rfile.read(n) or b"{}")))
            except Exception as e:  # noqa: BLE001 — fout terug naar de webserver
                traceback.print_exc()
                self._stuur(500, {"fout": repr(e)})

        def log_message(self, *a):
            pass

    print(f"API luistert op poort {poort}", flush=True)
    HTTPServer(("0.0.0.0", poort), Handler).serve_forever()


# ---------- score: hoe dicht zit een opname bij een moedertaalspreker? ----------
# Eén ruwe score (0–100) uit drie onderdelen, vergeleken met de bevroren ijking uit de proef: 0 = Nederlands
# accent (Zweedse tekst voorgelezen door espeak-ng nl), 100 = mediaan van moedertaalsprekers (FLEURS).

SCORE_GEWICHT = {"klanken": 0.5, "verstaan": 0.3, "uitspraak": 0.2}
SCORE_KLANKEN = "xlsr300m-sv"          # voor de klankuitleg per woord
KLANK_MODELLEN = ("xlsr300m-sv", "xlsr53-espeak")
NATIVE_PER = {"xlsr300m-sv": 0.25, "xlsr53-espeak": 0.40}   # overschreven door de ijking
KLANK_GEWICHT = {"xlsr300m-sv": 0.75, "xlsr53-espeak": 0.25}
IJKING = Path(os.environ.get("IJKING", "/ijking/score_ijking.json"))
KLANK_VARIANTEN = Path(os.environ.get("KLANK_VARIANTEN", "/ijking/klank_varianten.json"))
ACCENT_NAAM = "Nederlands accent"


def doel_variant(woord):
    """De bedoelde uitspraakvariant bij de woorden in varianten.tsv: altijd 'goed' (de woordaccent-woorden van de
    proef, anden/tanken, komen in de teksten niet voor)."""
    return "goed"


def score_onderdelen(whisper=None, klanken=None, keuze=None, native_per=None):
    """Onderdelen (0–1) uit de ruwe uitkomsten; ontbrekende onderdelen blijven weg.
    whisper: dict met wer_verwacht en woorden ('w:0.93 ...'); klanken: {model: dict met per};
    keuze: lijst dicts met woord en gekozen (MFA keuze-uitspraak)."""
    uit = {}
    # Per klankmodel 1 − PER, gedeeld door wat een moedertaalspreker bij dat model haalt (afgetopt op 1). Het
    # Zweedse model weegt 75%: alleen dat model hoort accent echt (proef: AUC 0,96 tegen 0,64 voor espeak).
    native = native_per or NATIVE_PER
    rel = {m: min(1.0, max(0.0, 1 - float(r["per"])) / (1 - native.get(m, 0.3)))
           for m, r in (klanken or {}).items() if r and r.get("per") not in (None, "")}
    if rel:
        gewicht = {m: KLANK_GEWICHT.get(m, 0.5) for m in rel}
        uit["klanken"] = sum(gewicht[m] * v for m, v in rel.items()) / sum(gewicht.values())
    if whisper and whisper.get("wer_verwacht") not in (None, ""):
        zeker = [float(w.rsplit(":", 1)[1]) for w in str(whisper.get("woorden", "")).split() if ":" in w]
        goed = max(0.0, 1 - float(whisper["wer_verwacht"]))
        uit["verstaan"] = 0.75 * goed + 0.25 * (sum(zeker) / len(zeker) if zeker else goed)
    if keuze:
        uit["uitspraak"] = sum(r["gekozen"] == doel_variant(r["woord"]) for r in keuze) / len(keuze)
    return uit


def ruwe_score(onderdelen):
    som = sum(SCORE_GEWICHT[n] for n in onderdelen)
    return round(100 * sum(SCORE_GEWICHT[n] * v for n, v in onderdelen.items()) / som, 1) if som else None


def _lees_json(pad):
    import json
    try:
        return json.loads(pad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def lees_ijking():
    return _lees_json(IJKING)


def vergelijk(ruw, ijking):
    """Ruwe score op een schaal met twee ijkpunten: 0 = mediaan van het Nederlandse accent-anker, 100 = mediaan van
    de moedertaalsprekers. Plus percentiel en een niveau. 'Als een moedertaalspreker' pas vanaf het 25e percentiel
    van de moedertaalsprekers: streng genoeg dat het accent-anker het (bijna) nooit haalt."""
    if ruw is None or not ijking:
        return {"ruw": ruw}
    s = ijking["scores"]
    percentiel = round(100 * sum(x <= ruw for x in s) / len(s))
    nul = (ijking.get("anker") or {}).get("mediaan")
    accent = (ijking.get("anker") or {}).get("accent", ACCENT_NAAM)
    if nul is not None and ijking["mediaan"] > nul:
        schaal = round(100 * (ruw - nul) / (ijking["mediaan"] - nul))
    else:
        schaal = round(100 * ruw / ijking["mediaan"]) if ijking["mediaan"] else None
    gelijkenis = None if schaal is None else max(0, min(100, schaal))
    if ruw >= ijking.get("p25", ijking["p10"]):
        niveau = "als een moedertaalspreker"
    elif gelijkenis is not None and gelijkenis >= 50:
        niveau = "met een licht accent"
    elif gelijkenis is not None and gelijkenis > 0:
        niveau = "met een duidelijk accent"
    else:
        niveau = f"met een sterk {accent}"
    return {"ruw": ruw, "percentiel": percentiel, "gelijkenis": gelijkenis, "niveau": niveau, "nul": accent}


# ---------- oordeel per woord (klanken): alleen afwijkingen die moedertaalsprekers NIET maken ----------
# De verwachte klanken komen uit het MFA-woordenboek. Echte sprekers wijken daar voortdurend van af; welke afwijkingen
# normaal zijn, is in de proef geleerd uit moedertaalsprekers (bevroren in klank_varianten.json).

KLANK_NAAM = {
    "ɧ": "sj-klank (sj, sk, stj)", "ɕ": "tj-klank (tj, k vóór e/i/y/ä/ö)", "ʉ": "Zweedse u (hus)",
    "ɵ": "korte Zweedse u (buss)", "u": "o-klank (sol, als oe)", "ʊ": "korte o (ost)", "o": "å (lang)",
    "ɔ": "korte å/o", "y": "y (ny)", "ʏ": "korte y", "ø": "ö (lang)", "œ": "korte ö", "ɛ": "ä/e (kort)",
    "e": "e (lang)", "ɪ": "korte i", "i": "i", "ɑ": "lange a", "a": "korte a", "ŋ": "ng-klank",
    "ʂ": "rs-klank", "r": "r", "j": "j (ook g/gj/hj)", "v": "v (ook w)",
}

# Klinkerparen die alleen in lengte/openheid verschillen (de klankherkenner hoort geen lengte): hooguit 'let op'.
NABIJ = {frozenset(p) for p in [("e", "ɛ"), ("i", "ɪ"), ("u", "ʊ"), ("o", "ɔ"), ("a", "ɑ"), ("y", "ʏ"),
                                 ("ø", "œ"), ("ʉ", "ɵ")]}


def klank(k):
    return f"{KLANK_NAAM[k]} [{k}]" if k in KLANK_NAAM else f"[{k}]"


def lees_klank_varianten():
    return _lees_json(KLANK_VARIANTEN) or {}


def klank_oordeel(w, var=None):
    """Oordeel over één woord uit de klankherkenner (per_woord-item): ('goed'|'let_op'|'fout', uitleg|None).
    var: de geleerde moedertaalvarianten van dit model."""
    if w.get("score") is None or not w.get("fouten"):
        return "goed", None
    var = var or {}
    anders_ok = {tuple(x) for x in var.get("anders", [])}
    weg_ok, extra_ok = set(var.get("weg", [])), set(var.get("extra", []))
    n_verwacht = len(w["verwacht"].split())
    goed = round(w["score"] * (n_verwacht + sum(f["soort"] == "extra" for f in w["fouten"])))
    normaal, klein, echt = 0, [], []
    for f in w["fouten"]:
        if ((f["soort"] == "anders" and (f["verwacht"], f["gehoord"]) in anders_ok)
                or (f["soort"] == "weg" and f["verwacht"] in weg_ok)
                or (f["soort"] == "extra" and f["gehoord"] in extra_ok)):
            normaal += f["soort"] != "extra"
        elif f["soort"] == "anders" and frozenset((f["verwacht"], f["gehoord"])) in NABIJ:
            klein.append(f)
        else:
            echt.append(f)
    n = n_verwacht + sum(f["soort"] == "extra" for f in echt + klein)
    score = (goed + normaal + 0.5 * len(klein)) / max(n, 1)
    # Eén afwijkende klank zegt weinig: de klankherkenner zit ook bij moedertaalsprekers vaak naast. Met
    # 'score < 0,6' krijgt 18% van de woorden van Zweden een melding en 35% met Nederlands accent (proef).
    if not echt or score >= 0.6:
        return "goed", None
    delen = []
    for f in echt + klein:
        if f["soort"] == "anders":
            delen.append(f"{klank(f['verwacht'])} klonk als {klank(f['gehoord'])}"
                         + (" (bijna goed: lengte/openheid)" if f in klein else ""))
        elif f["soort"] == "weg":
            delen.append(f"{klank(f['verwacht'])} niet gehoord")
        else:
            delen.append(f"extra {klank(f['gehoord'])}")
    gehoord = f"verwacht [{w['verwacht']}], gehoord [{w['herkend'] or '–'}]"
    tekst = (f"klanken: de meeste klanken wijken af ({gehoord})" if len(delen) > 3
             else "klanken: " + "; ".join(delen) + f" ({gehoord})")
    # 'fout' pas als het woord grotendeels anders klinkt én er minstens twee echte afwijkingen zijn.
    return ("fout" if score < 0.34 and len(echt) >= 2 else "let_op"), tekst
