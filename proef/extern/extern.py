"""Fragmenten van moedertaalsprekers klaarzetten in opnames/extern/<bron>/ (audio + .txt).

Doel: meten hoe vaak de app een Zweed ONTERECHT afkeurt. Gekozen worden fragmenten met de
doelwoorden uit varianten.tsv (sju, tack, glas, hus, kök, skiner, stjärnor), omdat de
keuze-uitspraak daar een oordeel geeft. Accentwoorden (anden, tanken) vallen af: zonder
betekenis weet je niet welk accent goed is.

  python extern.py commonvoice /bronnen/commonvoice [--per-woord 5] [--uitsluiten oud.tsv]
      Uitgepakte Common Voice-download (Mozilla Data Collective, CC0). Zoekt validated.tsv.
  python extern.py lingualibre [--per-woord 5]
      Losse woorden van Wikimedia Commons (Lingua Libre en Sv-<woord>.ogg); licentie per bestand.
  python extern.py tsv <bestand.tsv> <bron> --pad-kolom X --tekst-kolom Y [--geen-kop] [--audiomap M]
      Elke andere set met een tabel pad/tekst (FLEURS, NST, eigen materiaal). Kolom = naam of nummer.

Per bron komt er een _bronnen.tsv met herkomst en licentie. Alles is herhaalbaar (vaste seed).
"""
import argparse
import csv
import json
import random
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from proef_common import OPNAMES, normaliseer

UIT = OPNAMES / "extern"
VARIANTEN = Path(__import__("os").environ.get("VARIANTEN", "/app/varianten.tsv"))
ACCENTWOORDEN = {"anden", "tanken"}
UA = "svenska-uitspraakproef/0.1 (lokale test, geen bulk)"


def doelwoorden(extra):
    woorden = set(extra or [])
    if VARIANTEN.exists():
        for regel in VARIANTEN.read_text(encoding="utf-8").splitlines():
            if regel.strip() and not regel.startswith("#"):
                woorden.add(regel.split("\t")[0])
    return sorted(woorden - ACCENTWOORDEN)


def veilige_naam(tekst):
    return re.sub(r"[^A-Za-z0-9_-]", "_", tekst)[:80]


def schrijf(bron, naam, audio_bron, tekst, meta, rijen):
    doelmap = UIT / bron
    doelmap.mkdir(parents=True, exist_ok=True)
    doel = doelmap / f"{naam}{Path(audio_bron).suffix.lower()}"
    if isinstance(audio_bron, Path):
        shutil.copy(audio_bron, doel)
    else:
        try:
            doel.write_bytes(audio_bron_bytes(audio_bron))
        except (RuntimeError, OSError) as e:
            print(f"    overgeslagen: {e}")
            return False
    (doelmap / f"{naam}.txt").write_text(tekst.strip() + "\n", encoding="utf-8")
    rijen.append(dict(naam=naam, tekst=tekst.strip(), **meta))
    return True


def audio_bron_bytes(url):
    """Downloaden met wachten bij 429/5xx (Retry-After respecteren)."""
    for poging in range(5):
        time.sleep(2)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                raise
            wacht = int(e.headers.get("Retry-After") or 0) or 10 * 2 ** poging
            print(f"    {e.code} bij downloaden; opnieuw over {wacht} s")
            time.sleep(min(wacht, 120))
    raise RuntimeError(f"download blijft mislukken: {url}")


def schrijf_meta(bron, rijen):
    if not rijen:
        print("Niets gevonden.")
        return
    pad = UIT / bron / "_bronnen.tsv"
    velden = list(dict.fromkeys(k for r in rijen for k in r))
    with open(pad, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, velden, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rijen)
    print(f"{len(rijen)} fragmenten in {UIT / bron}; herkomst en licentie in {pad.name}")


# ---------- Common Voice ----------

def commonvoice(args):
    tsvs = sorted(Path(args.map).rglob("validated.tsv"))
    if not tsvs:
        sys.exit(f"Geen validated.tsv onder {args.map}. Pak de Common Voice-download daar uit.")
    tsv = tsvs[-1]
    clips = tsv.parent / "clips"
    uitsluiten = set()
    for pad in args.uitsluiten or []:
        with open(pad, encoding="utf-8", newline="") as f:
            uitsluiten |= {r["path"] for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}
    with open(tsv, encoding="utf-8", newline="") as f:
        alle = [r for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
                if r["path"] not in uitsluiten
                and int(r.get("up_votes") or 0) >= 2 and int(r.get("down_votes") or 0) == 0]
    print(f"{tsv}: {len(alle)} goedgekeurde fragmenten (na uitsluiten: {len(uitsluiten)} weg)")
    random.Random(args.seed).shuffle(alle)
    sprekers, rijen = set(), []
    for woord in doelwoorden(args.woorden):
        n = 0
        for r in alle:
            if n >= args.per_woord:
                break
            # Eén fragment per spreker over de hele selectie: zoveel mogelijk verschillende stemmen.
            if r["client_id"] in sprekers or woord not in normaliseer(r["sentence"]).split():
                continue
            bron = clips / r["path"]
            if not bron.exists():
                continue
            sprekers.add(r["client_id"])
            schrijf("commonvoice", veilige_naam(Path(r["path"]).stem), bron, r["sentence"],
                    {"doelwoord": woord, "spreker": r["client_id"][:12], "accent": r.get("accents", ""),
                     "geslacht": r.get("gender", ""), "leeftijd": r.get("age", ""),
                     "licentie": "CC0-1.0", "bron": f"Common Voice ({tsv.parent.parent.name})"}, rijen)
            n += 1
        print(f"  {woord}: {n}")
    schrijf_meta("commonvoice", rijen)


# ---------- Lingua Libre / Wikimedia Commons ----------

def commons(params):
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        dict(params, format="json", formatversion=2))
    for wacht in (0, 5, 15, 45):
        time.sleep(wacht + 1.5)  # beleefd: Commons beperkt snelle verzoeken
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except (json.JSONDecodeError, OSError) as e:
            print(f"    Commons weigerde ({e.__class__.__name__}); opnieuw over {wacht + 5} s")
    raise RuntimeError("Commons blijft weigeren; probeer later opnieuw")


def lingualibre(args):
    rijen = []
    for woord in doelwoorden(args.woorden):
        patroon = re.compile(rf"^File:(LL-Q9027 \(swe\)-[^-]+-{re.escape(woord)}\.wav|Sv-{re.escape(woord)}\.ogg)$",
                             re.IGNORECASE)
        zoek = commons({"action": "query", "list": "search", "srnamespace": 6, "srlimit": 50,
                        "srsearch": f'intitle:"{woord}" intitle:swe'})
        titels = [s["title"] for s in zoek["query"]["search"] if patroon.match(s["title"])]
        titels.append(f"File:Sv-{woord}.ogg")  # oudere Wiktionary-opname, als die bestaat
        info = commons({"action": "query", "prop": "imageinfo", "iiprop": "url|extmetadata",
                        "titles": "|".join(dict.fromkeys(titels))[:2000]})
        n = 0
        for pagina in info["query"]["pages"]:
            if n >= args.per_woord or pagina.get("missing") or "imageinfo" not in pagina:
                continue
            ii = pagina["imageinfo"][0]
            meta = ii.get("extmetadata", {})
            lic = meta.get("LicenseShortName", {}).get("value", "?")
            maker = re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", "?")).strip()
            naam = veilige_naam(pagina["title"].removeprefix("File:").rsplit(".", 1)[0])
            n += schrijf("lingualibre", naam, ii["url"], woord,
                         {"doelwoord": woord, "spreker": maker, "licentie": lic,
                          "bron": ii.get("descriptionurl", pagina["title"])}, rijen)
        print(f"  {woord}: {n}")
    schrijf_meta("lingualibre", rijen)


# ---------- willekeurige tabel ----------

def kolom(rij, kop, naam_of_nr):
    return rij[int(naam_of_nr)] if naam_of_nr.isdigit() else rij[kop.index(naam_of_nr)]


def tabel(args):
    tsv = Path(args.bestand)
    audiomap = Path(args.audiomap) if args.audiomap else tsv.parent
    with open(tsv, encoding="utf-8", newline="") as f:
        lezer = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    kop = [] if args.geen_kop else lezer.pop(0)
    woorden = set(doelwoorden(args.woorden))
    random.Random(args.seed).shuffle(lezer)
    rijen, per = [], {}
    for r in lezer:
        tekst = kolom(r, kop, args.tekst_kolom)
        geraakt = [w for w in normaliseer(tekst).split() if w in woorden]
        if args.alleen_doelwoorden and not geraakt:
            continue
        w = geraakt[0] if geraakt else ""
        if per.get(w, 0) >= args.per_woord or len(rijen) >= args.max:
            continue
        bron = audiomap / kolom(r, kop, args.pad_kolom)
        if not bron.exists():
            continue
        per[w] = per.get(w, 0) + 1
        schrijf(args.bron, veilige_naam(bron.stem), bron, tekst,
                {"doelwoord": w, "licentie": args.licentie, "bron": str(tsv)}, rijen)
    schrijf_meta(args.bron, rijen)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for naam in ("commonvoice", "lingualibre", "tsv"):
        s = sub.add_parser(naam)
        s.add_argument("--per-woord", type=int, default=5)
        s.add_argument("--woorden", nargs="*", help="extra doelwoorden naast varianten.tsv")
        s.add_argument("--seed", type=int, default=1)
        if naam == "commonvoice":
            s.add_argument("map")
            s.add_argument("--uitsluiten", nargs="*",
                           help="validated.tsv van een oudere release: die fragmenten overslaan "
                                "(het MFA-model is deels op oudere Common Voice getraind)")
        if naam == "tsv":
            s.add_argument("bestand")
            s.add_argument("bron", help="naam van de map onder opnames/extern/")
            s.add_argument("--pad-kolom", required=True)
            s.add_argument("--tekst-kolom", required=True)
            s.add_argument("--geen-kop", action="store_true")
            s.add_argument("--audiomap")
            s.add_argument("--licentie", default="?")
            s.add_argument("--alleen-doelwoorden", action="store_true",
                           help="alleen zinnen met een doelwoord (anders ook willekeurige zinnen)")
            s.add_argument("--max", type=int, default=50)
    args = p.parse_args()
    {"commonvoice": commonvoice, "lingualibre": lingualibre, "tsv": tabel}[args.cmd](args)


if __name__ == "__main__":
    main()
