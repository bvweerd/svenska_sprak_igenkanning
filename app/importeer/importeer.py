"""Teksten van de A-site (svenska_ovningar, A1–A2) en de B-site (svenska_ovningar_b, B1–B2) → app/teksten/teksten.json (in git).

De sites zelf worden alleen gelezen (content/chapters/*.yaml en content/index.yaml). Per hoofdstuk:
  - de leestekst, de makkelijke leesteksten en de luistertekst (oefeningen met 'text');
  - de dialogen (items van het type 'dialogue'), in hun geheel;
  - de voorbeeldzinnen bij de woordenschat (vocab[].ex, met Nederlandse vertaling), elk een eigen oefenstuk.
Hoofdstuk 0 (losse woorden) doet niet mee: losse woorden zijn geen goede training.

Elke tekst wordt opgedeeld in oefenstukken van een paar zinnen: hoe langer een opname, hoe trager de analyse en
hoe vager de feedback. Getallen worden woorden (de voorbeeldstem kan geen cijfers lezen, en zo vergelijkt de
analyse woorden met woorden).

  python importeer.py      (in de container; bronnen in /bron/a en /bron/b)
"""
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import yaml
from num2words import num2words

BRONNEN = {"A": Path(os.environ.get("BRON_A", "/bron/a")), "B": Path(os.environ.get("BRON_B", "/bron/b"))}
UIT = Path(os.environ.get("TEKSTEN", "/teksten/teksten.json"))
STUK_MAX = 320        # tekens per oefenstuk (±2–4 zinnen)
ALINEA_MAX = 420      # een alinea tot zo lang blijft heel
KLEIN = 70            # een kleiner laatste stuk gaat bij het vorige

SOORT_NAAM = {"lezen": "Leestekst", "makkelijk": "Makkelijk lezen", "luisteren": "Luistertekst",
              "dialoog": "Dialoog", "woordenschat": "Woordenschat (voorbeeldzinnen)"}


# ---------- tekst schoonmaken ----------

def slug(t):
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "x"


def getal(n, soort="cardinal"):
    try:
        return num2words(n, lang="sv", to=soort)
    except (NotImplementedError, OverflowError):
        return num2words(n, lang="sv")


def getallen_in_woorden(t):
    t = re.sub(r"(\d+)\s?%", lambda m: f"{getal(int(m.group(1)))} procent", t)
    t = re.sub(r"(\d+),(\d+)", lambda m: f"{getal(int(m.group(1)))} komma {' '.join(getal(int(c)) for c in m.group(2))}", t)
    t = re.sub(r"\b(\d+):([ae])\b", lambda m: getal(int(m.group(1)), "ordinal"), t)    # 1:a, 3:e
    t = re.sub(r"\b(\d{1,2})[.:](\d{2})\b", lambda m: f"{getal(int(m.group(1)))} {getal(int(m.group(2)))}", t)  # 14.30
    t = re.sub(r"(\d)\s(\d{3})\b", r"\1\2", t)                                           # 12 000
    return re.sub(r"\d+", lambda m: getal(int(m.group(0))), t)


def schoon(t):
    """Opmaak van de sites weg: **vet**, *cursief*, {a|b} (eerste keuze), [optioneel] (houden)."""
    t = re.sub(r"\{([^{}|]*)\|[^{}]*\}", r"\1", t)
    t = t.replace("**", "").replace("*", "").replace("[", "").replace("]", "")
    t = getallen_in_woorden(t)
    return re.sub(r"[ \t]+", " ", t).strip()


SPREKER = re.compile(r"^\s*(?:[A-ZÅÄÖ][\wåäöéü-]*(?: [A-ZÅÄÖ][\wåäöéü-]*)?):\s+")


def regel_zonder_spreker(r):
    """'Olle: Hej!' → 'Hej!'; '– Hej!' → 'Hej!' (de dialoog wordt in zijn geheel voorgelezen)."""
    return re.sub(r"^\s*[–—-]\s+", "", SPREKER.sub("", r))


def zinnen_van(alinea):
    return [z for z in re.split(r"(?<=[.!?…])\s+(?=[\"”„'–—A-ZÅÄÖÉ0-9])", alinea) if z.strip()]


def in_stukken(alineas):
    """Alinea's → oefenstukken van hoogstens ±STUK_MAX tekens. Korte alinea's (dialoogregels) samen."""
    # Eenheden: een alinea tot ALINEA_MAX blijft heel; een langere wordt in zinnen gesplitst.
    eenheden = [z for a in alineas for z in ([a] if len(a) <= ALINEA_MAX else zinnen_van(a))]
    stukken, huidig = [], ""
    for z in eenheden:
        if huidig and len(huidig) + 1 + len(z) > STUK_MAX:
            stukken.append(huidig)
            huidig = ""
        huidig = f"{huidig} {z}".strip()
    if huidig:
        stukken.append(huidig)
    if len(stukken) > 1 and len(stukken[-1]) < KLEIN:
        stukken[-2:] = [stukken[-2] + " " + stukken[-1]]
    return stukken


def alineas_van(tekst, dialoog=False):
    regels = [r for r in re.split(r"\n\s*\n" if not dialoog else r"\n", tekst) if r.strip()]
    uit = []
    for r in regels:
        r = " ".join(regel_zonder_spreker(x) for x in r.splitlines() if x.strip())
        r = schoon(r)
        if r:
            uit.append(r)
    return uit


# ---------- de sites lezen ----------

def niveaus(site, bron):
    index = yaml.safe_load((bron / "content" / "index.yaml").read_text(encoding="utf-8")) or {}
    uit = {}
    for h in index.get("chapters", []):
        n = int(h["chapter"])
        niveau = h.get("level") or ("A1" if n <= 6 else "A2")     # A-site: H1–H6 A1, H7–H12 A2 (PLAN.md van de site)
        uit[n] = {"niveau": niveau, "thema": h.get("theme", "")}
    return uit


def items_recursief(items):
    for it in items or []:
        yield it
        yield from items_recursief(it.get("steps"))


def lees_site(site, bron):
    info = niveaus(site, bron)
    teksten = []
    for pad in sorted((bron / "content" / "chapters").glob("*.yaml")):
        h = yaml.safe_load(pad.read_text(encoding="utf-8")) or {}
        n = int(h.get("chapter", -1))
        if n <= 0:
            continue
        basis = {"site": site, "hoofdstuk": n, "niveau": info.get(n, {}).get("niveau", ""),
                 "thema": info.get(n, {}).get("thema", "")}
        pre = f"{site}-H{n:02d}"
        for sectie in h.get("sections", []):
            for oef in sectie.get("exercises", []):
                if oef.get("text"):
                    soort = "luisteren" if oef.get("listen") else "makkelijk" if oef.get("kind") == "makkelijk" else "lezen"
                    dialoog = bool(re.search(r"^\s*[A-ZÅÄÖ][\wåäö]+:\s", oef["text"], re.M))
                    teksten.append(dict(basis, id=f"{pre}-{slug(oef['id'])}", soort=soort,
                                        titel=schoon(oef.get("textTitle") or oef.get("title", "")),
                                        titel_nl=oef.get("title", ""),
                                        alineas=alineas_van(oef["text"], dialoog)))
                for it in items_recursief(oef.get("items")):
                    if it.get("type") == "dialogue" and it.get("lines"):
                        teksten.append(dict(basis, id=f"{pre}-{slug(oef['id'])}-{slug(it.get('id', 'd'))}",
                                            soort="dialoog", titel=oef.get("title", "Dialoog"),
                                            titel_nl=oef.get("instruction", ""),
                                            alineas=[schoon(regel_zonder_spreker(r)) for r in it["lines"]]))
        voorbeelden = [(v["sv"], schoon(v["ex"]), v.get("exNl", "")) for v in h.get("vocab", []) if v.get("ex")]
        if voorbeelden:
            gezien, stukken = set(), []
            for sv, ex, nl in voorbeelden:
                sid = f"{pre}-woordenschat-{slug(sv)}"
                while sid in gezien:
                    sid += "-2"
                gezien.add(sid)
                stukken.append({"id": sid, "tekst": ex, "nl": nl, "woord": sv})
            teksten.append(dict(basis, id=f"{pre}-woordenschat", soort="woordenschat", titel="Woordenschat",
                                titel_nl="Voorbeeldzinnen bij de woorden van dit hoofdstuk", stukken=stukken))
    for t in teksten:
        if "stukken" not in t:
            t["stukken"] = [{"id": f"{t['id']}-{i + 1}", "tekst": s} for i, s in enumerate(in_stukken(t.pop("alineas")))]
        t["soort_naam"] = SOORT_NAAM[t["soort"]]
    return [t for t in teksten if t["stukken"]]


def main():
    teksten = []
    for site, bron in BRONNEN.items():
        if not (bron / "content" / "chapters").exists():
            print(f"Site {site}: niet gevonden in {bron} (overgeslagen)", file=sys.stderr)
            continue
        deel = lees_site(site, bron)
        print(f"Site {site}: {len(deel)} teksten, {sum(len(t['stukken']) for t in deel)} oefenstukken, "
              f"{sum(len(s['tekst']) for t in deel for s in t['stukken'])} tekens")
        teksten += deel
    if not teksten:
        sys.exit("Geen teksten gevonden: staan de sites in BRON_A/BRON_B (zie app/README.md)?")
    ids = [s["id"] for t in teksten for s in t["stukken"]] + [t["id"] for t in teksten]
    dubbel = {i for i in ids if ids.count(i) > 1}
    assert not dubbel, f"dubbele id's: {sorted(dubbel)[:5]}"
    UIT.parent.mkdir(parents=True, exist_ok=True)
    tmp = UIT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"gemaakt": time.strftime("%Y-%m-%d %H:%M"), "teksten": teksten},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(UIT)
    print(f"→ {UIT}")


if __name__ == "__main__":
    main()
