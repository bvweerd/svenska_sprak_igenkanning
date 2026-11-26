"""Gedeelde hulpfuncties voor alle stappen van de proef (in elke container gekopieerd)."""
import csv
import os
import re
import unicodedata
from pathlib import Path

DATA = Path(os.environ.get("PROEF_DATA", "/data"))
TSV = DATA / "testzinnen.tsv"
OPNAMES = DATA / "opnames"          # jouw bestanden: <id>.<ext> of <spreker>/<id>.<ext>
WERK = DATA / "werk"                # tussenbestanden (niet in git)
CORPUS = WERK / "corpus"            # 16 kHz mono wav + .lab per spreker, in MFA-vorm
PIPER_RUW = WERK / "piper_ruw"      # Piper-uitvoer voor de omzetting
ANKER_RUW = WERK / "anker_ruw"      # Zweedse zinnen voorgelezen met Nederlandse uitspraak (espeak-ng nl)
MFA_UIT = WERK / "mfa"              # TextGrids van MFA
RESULTATEN = DATA / "resultaten"    # CSV's en verslag


def zinnen():
    """Alle rijen uit testzinnen.tsv als dicts, op id. Zonder testzinnen.tsv (productieversie, app/): leeg."""
    if not TSV.exists():
        return {}
    with open(TSV, encoding="utf-8", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f, delimiter="\t")}


def rij_voor_verzoek(verzoek, rijen):
    """De zin bij een API-verzoek. De productieversie (app/) stuurt de tekst zelf mee ("tekst"); de proef
    alleen het id uit testzinnen.tsv."""
    if verzoek.get("tekst"):
        return {"id": verzoek.get("id", ""), "deel": "P productie", "zweeds": verzoek["tekst"], "gezegd": "",
                "goed_id": "", "nederlands": "", "wat_meten": "", "opdracht": ""}
    return rijen[verzoek["id"]]


def woordenboek_extra():
    """Uitspraken voor woorden die niet in het MFA-woordenboek staan (gemaakt met MFA's G2P door
    app/woordenboek): [(woord, uitspraak)]. Leeg als het bestand er niet is."""
    pad = Path(os.environ.get("WOORDENBOEK_EXTRA", DATA / "woordenboek_extra.dict"))
    if not pad.exists():
        return []
    uit = []
    for regel in pad.read_text(encoding="utf-8").splitlines():
        delen = regel.split("\t")
        if len(delen) >= 2 and delen[0].strip():
            uit.append((delen[0].strip(), delen[-1].strip()))
    return uit


EXTERN = "extern-"   # sprekermap in het corpus voor opnames van moedertaalsprekers
ANKER = "anker-nl"   # sprekermap voor het accent-ankerpunt (0 op de schaal)


def zin_voor(spreker, zin_id, rijen):
    """De rij voor een opname. Externe fragmenten staan niet in testzinnen.tsv: dan komt de
    tekst uit de .lab die prep schreef, met deel 'E'."""
    if not spreker.startswith(EXTERN) and zin_id in rijen:
        return rijen[zin_id]
    lab = CORPUS / spreker / f"{zin_id}.lab"
    tekst = lab.read_text(encoding="utf-8").strip() if lab.exists() else ""
    return {"id": zin_id, "deel": "E extern", "zweeds": tekst, "gezegd": "", "goed_id": "",
            "nederlands": "", "wat_meten": "", "opdracht": ""}


def opnames():
    """Alle voorbereide opnames: lijst van (spreker, id, wav-pad)."""
    uit = []
    if not CORPUS.exists():
        return uit
    for spreker_dir in sorted(p for p in CORPUS.iterdir() if p.is_dir()):
        for wav in sorted(spreker_dir.glob("*.wav")):
            uit.append((spreker_dir.name, wav.stem, wav))
    return uit


# Schrijfwijzen die hetzelfde zijn (Whisper schrijft getallen soms in cijfers).
GELIJKE_VORMEN = {"idag": "i dag", "2": "två", "3": "tre", "4": "fyra", "5": "fem", "6": "sex", "7": "sju",
                  "8": "åtta", "9": "nio", "10": "tio", "11": "elva", "12": "tolv", "20": "tjugo", "27": "tjugosju",
                  "80": "åttio"}


# ---------- audio omzetten en schoonmaken (ffmpeg; gebruikt door prep en de webpagina) ----------

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
    """Opname → 16 kHz mono wav, schoongemaakt. Begint de opname met een plof (veel meer laag dan
    spraak in de eerste 0,25 s, typisch voor een headset die net aangaat), dan gaat de eerste 0,6 s
    eraf; brom onder 80 Hz gaat altijd weg. Geeft info terug (voor een waarschuwing op de pagina)."""
    import subprocess
    plof_laag = _rms(bron, LAAG, 0, 0.25)
    spraak = _rms(bron, SPRAAK, 0.25)
    # Alleen een echte plof: luid (gemeten bij een headset: −11 tot −14 dB) én veel luider dan de spraak.
    # Zo blijft een stille aanloop (Piper: −60 dB) gewoon staan.
    # Een plof houdt daarna op (gemeten: −11 dB, na 0,7 s −35 dB); een stem die meteen begint niet.
    laag_daarna = _rms(bron, LAAG, 0.7)
    # En een plof is alleen laag: in hetzelfde begin is de spraakband veel zachter (een stem niet).
    spraak_begin = _rms(bron, SPRAAK, 0, 0.25)
    plof = plof_laag > -30 and plof_laag > spraak_begin + 6 and plof_laag > laag_daarna + 12
    start = PLOF_SEC if plof else 0
    brom = _rms(bron, LAAG, max(start, 0.25))          # wat er na de plof aan laag overblijft
    spraak = _rms(bron, SPRAAK, start)
    af = (f"atrim=start={start},asetpts=PTS-STARTPTS," if plof else "") + SPRAAK
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(bron), "-af", af, "-ac", "1",
                    "-ar", "16000", "-sample_fmt", "s16", str(doel)], check=True)
    return {"plof_weggehaald": plof, "brom_db": round(brom, 1), "spraak_db": round(spraak, 1),
            # Onder 80 Hz zit ook de grondtoon van een lage stem; pas als het laag luider is dan de spraak,
            # is het echt brom (ventilator, luchtstroom).
            "veel_brom": brom > spraak + 3 and brom > -40, "zacht": spraak < -45}


def _getal(w):
    """Een getal dat Whisper in cijfers schreef, in woorden (zoals de import van de productieversie doet);
    zonder num2words (de proefimages) blijft het staan."""
    if w in GELIJKE_VORMEN or not w.isdigit():
        return GELIJKE_VORMEN.get(w, w)
    try:
        from num2words import num2words
        return num2words(int(w), lang="sv")
    except (ImportError, NotImplementedError, ValueError, OverflowError):
        return w


def normaliseer(tekst):
    """Kleine letters, zonder leestekens; voor het vergelijken van zinnen."""
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


def schrijf_csv(pad, rijen, velden):
    pad.parent.mkdir(parents=True, exist_ok=True)
    with open(pad, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, velden, extrasaction="ignore")
        w.writeheader()
        w.writerows(rijen)
    print(f"→ {pad} ({len(rijen)} rijen)")


def lees_csv(pad):
    if not pad.exists():
        return []
    with open(pad, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def serveer(analyseer, poort):
    """Kleine interne JSON-API voor de webpagina: POST {"wav": pad, "id": zin-id} → analyse.
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
                verzoek = json.loads(self.rfile.read(n) or b"{}")
                self._stuur(200, analyseer(verzoek))
            except Exception as e:  # noqa: BLE001 — fout terug naar de webpagina
                traceback.print_exc()
                self._stuur(500, {"fout": repr(e)})

        def log_message(self, *a):
            pass

    print(f"API luistert op poort {poort}", flush=True)
    HTTPServer(("0.0.0.0", poort), Handler).serve_forever()


# ---------- score: hoe dicht zit een opname bij een moedertaalspreker? ----------
# Eén ruwe score (0–100) uit drie onderdelen, daarna vergeleken met de scores van moedertaalsprekers
# (FLEURS, automatisch opgehaald). De batch (verslag) en de webpagina rekenen met dezelfde code.

# Juiste uitspraakvariant bij de woorden met woordaccent; overige variantwoorden: 'goed'.
DOEL_ACCENT = {"A01": "accent1", "A02": "accent2", "A03": "accent1", "A04": "accent2", "D06": "accent2"}
ACCENTWOORDEN = {"anden", "tanken"}
SCORE_GEWICHT = {"klanken": 0.5, "verstaan": 0.3, "uitspraak": 0.2}
SCORE_WHISPER = "kb-whisper-small"     # zelfde maat als de webpagina
SCORE_KLANKEN = "xlsr300m-sv"          # voor de klankuitleg per woord
KLANK_MODELLEN = ("xlsr300m-sv", "xlsr53-espeak")
# Mediaan foutpercentage (PER) van moedertaalsprekers per model; wordt bij de ijking opnieuw gemeten.
NATIVE_PER = {"xlsr300m-sv": 0.25, "xlsr53-espeak": 0.40}
KLANK_GEWICHT = {"xlsr300m-sv": 0.75, "xlsr53-espeak": 0.25}
IJKING = Path(os.environ.get("IJKING", WERK / "score_ijking.json"))   # productie: bevroren kopie
ACCENT_NAAM = "Nederlands accent"   # het 0-punt van de schaal


def doel_variant(zin_id, woord):
    return DOEL_ACCENT.get(zin_id, "goed") if woord in ACCENTWOORDEN else "goed"


def score_onderdelen(whisper=None, klanken=None, keuze=None, zin_id="", extern=False, native_per=None):
    """Onderdelen (0–1) uit de ruwe uitkomsten; ontbrekende onderdelen blijven weg.
    whisper: dict met wer_verwacht en woorden ('w:0.93 ...'); klanken: {model: dict met per};
    keuze: lijst dicts met woord en gekozen (MFA keuze-uitspraak)."""
    uit = {}
    # klanken: {model: rij met 'per'}. Per model 1 − PER, gedeeld door wat een moedertaalspreker bij dat
    # model haalt (afgetopt op 1). Het Zweedse model weegt 75%: alleen dat model hoort accent echt
    # (gemeten: AUC 0,96 tegen 0,64 voor espeak); het andere (25%) dempt een model dat de weg kwijtraakt.
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
    # Bij moedertaalsprekers weet je niet welk woordaccent bedoeld is: accentwoorden tellen niet mee.
    k = [r for r in (keuze or []) if not (extern and r["woord"] in ACCENTWOORDEN)]
    if k:
        uit["uitspraak"] = sum(r["gekozen"] == doel_variant(zin_id, r["woord"]) for r in k) / len(k)
    return uit


def ruwe_score(onderdelen):
    som = sum(SCORE_GEWICHT[n] for n in onderdelen)
    return round(100 * sum(SCORE_GEWICHT[n] * v for n, v in onderdelen.items()) / som, 1) if som else None


def maak_ijking(scores, bron, native_per=None, anker=None):
    """Verdeling van ruwe scores van de referentiesprekers (100) en van het accent-anker (0)
    → werk/score_ijking.json."""
    import json
    s = sorted(scores)
    if not s:
        return None
    a = sorted(anker or [])
    ijking = {"bron": bron, "n": len(s), "mediaan": s[len(s) // 2], "p10": s[len(s) // 10],
              "p25": s[len(s) // 4], "native_per": native_per or NATIVE_PER, "scores": s,
              "anker": {"bron": "Zweedse zinnen met Nederlandse uitspraak (espeak-ng nl)", "n": len(a),
                        "accent": ACCENT_NAAM, "mediaan": a[len(a) // 2]} if a else None}
    IJKING.parent.mkdir(parents=True, exist_ok=True)
    IJKING.write_text(json.dumps(ijking, ensure_ascii=False, indent=1), encoding="utf-8")
    return ijking


def lees_ijking():
    import json
    try:
        return json.loads(IJKING.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def vergelijk(ruw, ijking):
    """Ruwe score op een schaal met twee ijkpunten: 0 = mediaan van het Nederlandse accent-anker,
    100 = mediaan van de moedertaalsprekers. Plus percentiel t.o.v. de moedertaalsprekers en een niveau.
    'Als een moedertaalspreker' pas vanaf het 25e percentiel van de moedertaalsprekers: streng genoeg dat
    het accent-anker het (bijna) nooit haalt."""
    if ruw is None or not ijking:
        return {"ruw": ruw}
    s = ijking["scores"]
    percentiel = round(100 * sum(x <= ruw for x in s) / len(s))
    nul = (ijking.get("anker") or {}).get("mediaan")
    accent = (ijking.get("anker") or {}).get("accent", "Nederlands accent")
    if nul is not None and ijking["mediaan"] > nul:
        schaal = round(100 * (ruw - nul) / (ijking["mediaan"] - nul))
    else:                                   # geen anker: oude verhouding t.o.v. de mediaan
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
    return {"ruw": ruw, "percentiel": percentiel, "gelijkenis": gelijkenis, "niveau": niveau, "nul": accent,
            "referentie": f"{ijking['bron']} (n={ijking['n']})"
                          + (f"; 0 = {accent} (n={ijking['anker']['n']})" if ijking.get("anker") else "")}


# ---------- oordeel per woord (klanken): alleen afwijkingen die moedertaalsprekers NIET maken ----------
# De verwachte klanken komen uit één 'woordenboek-uitspraak' (MFA-woordenboek of espeak-ng). Echte sprekers
# wijken daar voortdurend van af (zo bleek ook in een Nederlandse controle: g als [x], r als [ɾ], v als [f]). Daarom leert de
# batch uit de moedertaalsprekers (FLEURS) welke afwijkingen normaal zijn; die tellen per woord niet als fout.

KLANK_VARIANTEN = Path(os.environ.get("KLANK_VARIANTEN", WERK / "klank_varianten.json"))
KLANK_PER_WOORD = WERK / "klanken_per_woord.json"
VARIANT_MIN_N = 3          # minstens zo vaak bij moedertaalsprekers gezien …
VARIANT_MIN_AANDEEL = 0.10  # … en bij minstens dit aandeel van die verwachte klank (of van de woorden, bij 'extra')

KLANK_NAAM = {
    "ɧ": "sj-klank (sj, sk, stj)", "ɕ": "tj-klank (tj, k vóór e/i/y/ä/ö)", "ʉ": "Zweedse u (hus)",
    "ɵ": "korte Zweedse u (buss)", "u": "o-klank (sol, als oe)", "ʊ": "korte o (ost)", "o": "å (lang)",
    "ɔ": "korte å/o", "y": "y (ny)", "ʏ": "korte y", "ø": "ö (lang)", "œ": "korte ö", "ɛ": "ä/e (kort)",
    "e": "e (lang)", "ɪ": "korte i", "i": "i", "ɑ": "lange a", "a": "korte a", "ŋ": "ng-klank",
    "ʂ": "rs-klank", "r": "r", "j": "j (ook g/gj/hj)", "v": "v (ook w)",
}

# Klinkerparen die alleen in lengte/openheid verschillen (de klankherkenner hoort geen lengte):
# een verwisseling is hooguit 'let op'. Lengte zelf beoordeelt MFA bij de doelwoorden.
NABIJ = {frozenset(p) for p in [("e", "ɛ"), ("i", "ɪ"), ("u", "ʊ"), ("o", "ɔ"), ("a", "ɑ"), ("y", "ʏ"),
                                 ("ø", "œ"), ("ʉ", "ɵ")]}


def klank(k):
    return f"{KLANK_NAAM[k]} [{k}]" if k in KLANK_NAAM else f"[{k}]"


def leer_varianten(rijen):
    """rijen: (spreker, model, per_woord). Uit de moedertaalsprekers (spreker extern-…) per model tellen
    welke afwijkingen van de woordenboek-uitspraak normaal zijn. → {model: {"anders": [[v, g]], "weg": [v],
    "extra": [g], "n_woorden": …}}"""
    from collections import Counter
    per_model = {}
    for spreker, model, pw in rijen:
        if not spreker.startswith(EXTERN):
            continue
        t = per_model.setdefault(model, {"klank": Counter(), "anders": Counter(), "weg": Counter(),
                                         "extra": Counter(), "woorden": 0})
        for w in pw:
            if w.get("score") is None:
                continue
            t["woorden"] += 1
            t["klank"].update(w["verwacht"].split())
            for f in w["fouten"]:
                if f["soort"] == "anders":
                    t["anders"][(f["verwacht"], f["gehoord"])] += 1
                elif f["soort"] == "weg":
                    t["weg"][f["verwacht"]] += 1
                else:
                    t["extra"][f["gehoord"]] += 1
    uit = {}
    for model, t in per_model.items():
        ok = lambda n, totaal: n >= VARIANT_MIN_N and n / max(totaal, 1) >= VARIANT_MIN_AANDEEL
        uit[model] = {
            "anders": sorted([v, g] for (v, g), n in t["anders"].items() if ok(n, t["klank"][v])),
            "weg": sorted(v for v, n in t["weg"].items() if ok(n, t["klank"][v])),
            "extra": sorted(g for g, n in t["extra"].items() if ok(n, t["woorden"])),
            "n_woorden": t["woorden"],
        }
    return uit


def lees_klank_varianten():
    import json
    try:
        return json.loads(KLANK_VARIANTEN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def klank_oordeel(w, var=None):
    """Oordeel over één woord uit de klankherkenner (per_woord-item): ('goed'|'let_op'|'fout', uitleg|None).
    var: de geleerde moedertaalvarianten van dit model (leer_varianten)."""
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
            normaal += f["soort"] != "extra"      # normale variant: telt als goed (extra: telt niet mee)
        elif f["soort"] == "anders" and frozenset((f["verwacht"], f["gehoord"])) in NABIJ:
            klein.append(f)
        else:
            echt.append(f)
    n = n_verwacht + sum(f["soort"] == "extra" for f in echt + klein)
    score = (goed + normaal + 0.5 * len(klein)) / max(n, 1)
    # Eén afwijkende klank zegt weinig: de klankherkenner zit ook bij moedertaalsprekers vaak naast (±1 op 4
    # klanken). Gemeten op FLEURS + accent-anker: met 'score < 0,6' krijgt 18% van de woorden van Zweden een
    # melding (eerst 55%) en 35% van de woorden met Nederlands accent. Strenger dan dit maakt de tips onbetrouwbaar.
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
    status = "fout" if score < 0.34 and len(echt) >= 2 else "let_op"
    return status, tekst


# ---------- cache: alleen nieuwe of gewijzigde opnames opnieuw analyseren ----------
# Per stap een JSON in werk/cache/ met {sleutel: uitkomst}. De sleutel is een hash van de inhoud (wav, tekst,
# model …); de versie is een hash van de broncode van de stap plus ANALYSE_VERSIE. Verandert de code, dan
# vervalt de cache vanzelf. Opnames die er niet meer zijn, vallen er bij het bewaren uit.

CACHE_MAP = WERK / "cache"
ANALYSE_VERSIE = "2"   # ophogen als gedeelde analyse-logica verandert die niet in het script van de stap staat


def inhoud_hash(*delen):
    """sha1 over bestanden (Path: de bytes) en teksten."""
    import hashlib
    h = hashlib.sha1()
    for d in delen:
        h.update(d.read_bytes() if isinstance(d, Path) else str(d).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


class Cache:
    def __init__(self, naam, script):
        import json
        self.naam, self.pad = naam, CACHE_MAP / f"{naam}.json"
        self.versie = inhoud_hash(Path(script), ANALYSE_VERSIE)
        try:
            d = json.loads(self.pad.read_text(encoding="utf-8"))
            self.oud = d["items"] if d.get("versie") == self.versie else {}
        except (OSError, ValueError, KeyError):
            self.oud = {}
        self.nieuw, self.hits, self.missers = {}, 0, 0

    def get(self, sleutel):
        if sleutel in self.oud:
            self.nieuw[sleutel] = self.oud[sleutel]
            self.hits += 1
            return self.oud[sleutel]
        return None

    def put(self, sleutel, waarde):
        self.nieuw[sleutel] = waarde
        self.missers += 1

    def bewaar(self):
        import json
        self.pad.parent.mkdir(parents=True, exist_ok=True)
        self.pad.write_text(json.dumps({"versie": self.versie, "items": self.nieuw}, ensure_ascii=False),
                            encoding="utf-8")
        print(f"[cache {self.naam}] {self.hits} uit de cache, {self.missers} (opnieuw) geanalyseerd", flush=True)
