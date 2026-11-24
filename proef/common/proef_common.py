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
MFA_UIT = WERK / "mfa"              # TextGrids van MFA
RESULTATEN = DATA / "resultaten"    # CSV's en verslag


def zinnen():
    """Alle rijen uit testzinnen.tsv als dicts, op id."""
    with open(TSV, encoding="utf-8", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f, delimiter="\t")}


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
GELIJKE_VORMEN = {"idag": "i dag", "7": "sju", "20": "tjugo", "27": "tjugosju"}


def normaliseer(tekst):
    """Kleine letters, zonder leestekens; voor het vergelijken van zinnen."""
    tekst = unicodedata.normalize("NFC", tekst.lower())
    tekst = re.sub(r"[^\w\s]", " ", tekst)
    return " ".join(GELIJKE_VORMEN.get(w, w) for w in tekst.split())


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
