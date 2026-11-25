"""Gebruikersvriendelijke feedback voor de testpagina.

Gebaseerd op wat in de proef betrouwbaar bleek (zie README):
- het oordeel komt uit de score op de hele zin, in woorden;
- hoogstens twee tips, op volgorde van betrouwbaarheid: wat Whisper anders verstond (goed in weggelaten
  woorden en woordvolgorde), een fout bij een doelwoord volgens MFA, en pas dan een klanktip;
- klanktips in Nederlandse klanken, zonder IPA, uit een vaste lijst typische fouten van Nederlandstaligen;
- woordtijden (MFA) om je eigen woord en het voorbeeld (Piper) na elkaar te horen;
- patronen over je opnames heen: één klanktip zegt weinig, tien keer dezelfde fout wel.
"""
import json
import re
from collections import Counter, defaultdict

from proef_common import (CORPUS, MFA_UIT, OPNAMES, SCORE_KLANKEN, WERK, bewerkingen, doel_variant, klank,
                          klank_oordeel, lees_klank_varianten, normaliseer)

ARCHIEF = WERK / "web" / "archief"


def _eerste(w, f):
    """Is deze extra klank de eerste van het woord (een 'eh' ervoor)?"""
    herkend, verwacht = w["herkend"].split(), w["verwacht"].split()
    return bool(herkend) and herkend[0] == f["gehoord"] and (not verwacht or verwacht[0] != f["gehoord"])


# Typische fouten van Nederlandstaligen in het Zweeds: id, titel, uitleg, test op één klankfout (f) in woord (w).
FOUTEN = [
    ("v_f", "v klinkt als f",
     "Laat je stem meetrillen, zoals in het Engelse *very*. In het Zweeds is de v altijd stemhebbend, ook aan het "
     "begin van een woord (*vi*, *var*, *vill*).",
     lambda f, w: f["soort"] == "anders" and f["verwacht"] == "v" and f["gehoord"] == "f"),
    ("aa", "å klinkt als a",
     "De Zweedse å klinkt bijna als de oo in *boot* (lang, *på*, *två*) of de o in *pot* (kort, *gått*), niet als een a.",
     lambda f, w: f["soort"] == "anders" and f["verwacht"] in ("o", "ɔ") and f["gehoord"] in ("a", "ɑ")),
    ("sj", "sj-klank",
     "De Zweedse sj (*sj*, *sk*, *skj*, *stj*) is geen Nederlandse sj: lippen iets naar voren, lucht achter in de "
     "mond, bijna een zachte, fluisterende ch.",
     lambda f, w: f.get("verwacht") == "ɧ"),
    ("tj", "tj-klank",
     "De Zweedse tj (*tj*, en k vóór e, i, y, ä, ö: *kök*, *köpa*): tongpunt achter de ondertanden, midden van de "
     "tong tegen het verhemelte. Een zachte sj-achtige klank, geen t-j en geen harde k.",
     lambda f, w: f.get("verwacht") == "ɕ"),
    ("zw_u", "Zweedse u",
     "De Zweedse u (*hus*, *du*, *nu*) ligt tussen de Nederlandse uu en oe: lippen sterk getuit en naar voren, "
     "tong in het midden.",
     lambda f, w: f["soort"] != "extra" and f.get("verwacht") in ("ʉ", "ɵ")),
    ("zw_y", "Zweedse y",
     "De Zweedse y (*ny*, *cykla*, *tycker*): lippen getuit als bij oe, tong vooraan zoals bij ie.",
     lambda f, w: f["soort"] != "extra" and f.get("verwacht") in ("y", "ʏ")),
    ("o_oe", "o klinkt niet als oe",
     "Een Zweedse lange o (*sol*, *bo*, *stor*, *hon*) klinkt bijna als de Nederlandse oe.",
     lambda f, w: f["soort"] == "anders" and f["verwacht"] == "u" and f["gehoord"] in ("o", "ɔ", "ʊ")),
    ("rs", "rs-klank",
     "r en s smelten in het Zweeds samen tot één sj-achtige klank (*först*, *kurs*, *personnummer*): spreek ze "
     "niet apart uit.",
     lambda f, w: f.get("verwacht") == "ʂ"),
    ("extra_e", "een 'eh' vóór het woord",
     "Begin direct met de eerste klank van het woord, zonder kort 'eh' ervoor.",
     lambda f, w: f["soort"] == "extra" and f["gehoord"] in ("ɛ", "e") and _eerste(w, f)),
]
INFO = {i: (t, u) for i, t, u, _ in FOUTEN}


def _normaal(f, var):
    """Is deze afwijking normaal bij moedertaalsprekers (geleerd in de batch)?"""
    var = var or {}
    if f["soort"] == "anders":
        return [f["verwacht"], f["gehoord"]] in var.get("anders", [])
    if f["soort"] == "weg":
        return f["verwacht"] in var.get("weg", [])
    return f["gehoord"] in var.get("extra", [])


# Korte functiewoorden worden in gewone spraak bijna altijd verkort uitgesproken (och → „ok”, det → „de”,
# jag → „ja”); het woordenboek geeft de volle vorm. Daarop geen klanktips.
KORTE_WOORDEN = {"och", "det", "de", "dem", "jag", "mig", "dig", "sig", "med", "ska", "en", "ett", "att", "är"}


def _gehoord_door_ander(f, w_ander):
    """Hoorde de andere klankherkenner (espeak) in hetzelfde woord wél wat verwacht werd? Dan is de afwijking
    van het Zweedse model twijfelachtig (bv. sjön: Zweeds model [ɛ r n], espeak [ɧ ø n])."""
    if not w_ander:
        return False
    gehoord = w_ander["herkend"].split()
    if f["soort"] == "extra":
        return f["gehoord"] not in gehoord          # de extra klank hoorde espeak niet
    return f["verwacht"] in gehoord


def klank_tips(w, var, w_ander=None):
    """Tipcategorieën voor één woord (per_woord-item van het Zweedse model), alleen als het woord een melding
    krijgt. w_ander: hetzelfde woord volgens de espeak-klankherkenner, ter controle."""
    if w["woord"] in KORTE_WOORDEN or klank_oordeel(w, var)[0] == "goed":
        return []
    uit, echt = [], False
    for f in w["fouten"]:
        if _normaal(f, var) or _gehoord_door_ander(f, w_ander):
            continue
        echt = True
        for i, _, _, test in FOUTEN:
            if test(f, w) and i not in uit:
                uit.append(i)
    if not uit and echt:                 # alleen als er na de controle nog iets overblijft
        uit.append("klank")
    return uit


def niets_gehoord(wh, geluid):
    """Een (bijna) stille of afgebroken opname: Whisper hoorde geen woord en de opname is erg zacht."""
    return bool((geluid or {}).get("zacht")) and not normaliseer((wh or {}).get("herkend", "")).split()


def eindoordeel(score, wh, tips=(), geluid=None):
    """Eén oordeel in woorden: (kop, zin, soort).
    De score middelt over de hele zin: één verkeerde klank in een zin van 25 klanken verschuift hem nauwelijks
    (gemeten: een bewust harde sk in D10 kreeg 97). Daarom geen 'Uitstekend' zolang er een betrouwbare tip is
    (Whisper verstond een woord anders, of MFA keurt een doelwoord af)."""
    niveau = (score or {}).get("niveau")
    wer = (wh or {}).get("wer_verwacht")
    verstaan = wer is not None and float(wer) <= 0.1
    betrouwbare_tip = any(t.get("bron") in ("verstaan", "uitspraak") for t in tips)
    if niets_gehoord(wh, geluid):
        return ("Niets gehoord", "De opname is (bijna) stil of heel kort. Kies bij Microfoon je headset, druk op "
                                 "Opnemen, spreek de hele zin en druk dan pas op Stop.", "onbekend")
    if not niveau:
        return ("Geen oordeel", "De analyse is niet gelukt; probeer het nog eens.", "onbekend")
    if niveau == "als een moedertaalspreker" and betrouwbare_tip:
        return ("Goed", "Bijna als een moedertaalspreker; let op de tip hieronder.", "goed")
    if niveau == "als een moedertaalspreker":
        return ("Uitstekend", "Je klinkt als een moedertaalspreker.", "top")
    if niveau == "met een licht accent":
        return ("Goed", ("Goed verstaanbaar" if verstaan else "Verstaanbaar") + ", met een licht accent.", "goed")
    if niveau == "met een duidelijk accent":
        return ("Redelijk", ("Verstaanbaar" if verstaan else "Deels verstaanbaar") + ", met een duidelijk accent.",
                "redelijk")
    return ("Oefen deze zin nog eens", "Een Zweed zou je hier lastig verstaan. Luister naar het voorbeeld en "
                                       "probeer het rustig opnieuw.", "zwak")


def _namen_in(tekst):
    uit, begin = set(), True
    for w in tekst.split():
        if w[:1].isupper() and not begin:
            uit.update(normaliseer(w).split())
        begin = w[-1:] in ".!?"
    return uit


def namen(r):
    """Namen: woorden die ergens in de zinnen midden in een zin met een hoofdletter staan (Wilma, Fleur, Olle,
    Västerås); zo telt Olle ook aan het begin van een zin als naam. Whisper kent zulke namen slecht en schrijft
    er iets anders van (Vilma, flue, Alla); dat is geen uitspraakfout."""
    from proef_common import zinnen
    alle = set()
    for rij in zinnen().values():
        alle |= _namen_in(rij["zweeds"])
    return alle | _namen_in(r["zweeds"])


def _bevestigd(k, res, var_alle):
    """Bevestigt een klankherkenner dat er met woord k iets mis is? Whisper is een taalmodel en raadt bij twijfel
    een ander, waarschijnlijker woord (sjön → „kön”) — ook als de klanken klopten. Een Whisper-tip gaat alleen
    door als geen van beide klankherkenners het woord goed vond. Zonder klankanalyse: niet tegenhouden."""
    oordelen = []
    for m in ("xlsr300m-sv", "xlsr53-espeak"):
        pw = res.get("klanken", {}).get(m, {}).get("per_woord") or []
        if k < len(pw):
            oordelen.append(klank_oordeel(pw[k], var_alle.get(m))[0])
    return not oordelen or all(o != "goed" for o in oordelen)


def _weergave(r):
    """Getoonde woorden (met leestekens) en per genormaliseerd woord het nummer van het getoonde woord."""
    weergave = r["zweeds"].split()
    naar = []
    for i, w in enumerate(weergave):
        naar += [i] * len(normaliseer(w).split())
    return weergave, naar


def textgrid_woorden(pad):
    """Woorden met tijden uit een (lange) TextGrid van MFA: [(start, eind, woord)]."""
    if not pad.exists():
        return []
    for tier in re.split(r"item \[\d+\]:", pad.read_text(encoding="utf-8"))[1:]:
        m = re.search(r'name = "([^"]*)"', tier)
        if m and m.group(1).endswith("words"):
            return [(float(a), float(b), c) for a, b, c in
                    re.findall(r'xmin = ([\d.]+)\s+xmax = ([\d.]+)\s+text = "([^"]*)"', tier) if c.strip()]
    return []


def _tijden(verwacht, uitgelijnd):
    """Per genormaliseerd woord (start, eind) uit een lijst (start, eind, woord) van MFA."""
    uit = [None] * len(verwacht)
    _, ops = bewerkingen(verwacht, [w for _, _, w in uitgelijnd])
    i = j = 0
    for soort, _, _ in ops:
        if soort in ("=", "S"):
            uit[i] = uitgelijnd[j][:2]
        i += soort != "I"
        j += soort != "D"
    return uit


def woordtijden(zin_id, r, res):
    """Per getoond woord: tijden in je eigen opname en in het voorbeeld (Piper), voor 'luister en vergelijk'."""
    weergave, naar = _weergave(r)
    verwacht = normaliseer(r["zweeds"]).split()
    eigen = [(w["start"], w["start"] + w["duur_ms"] / 1000, w["woord"])
             for w in res.get("mfa", {}).get("woorden", []) if w.get("woord")]
    voorbeeld = textgrid_woorden(MFA_UIT / "standaard" / "piper" / f"{zin_id}.TextGrid")
    uit = [{"eigen": None, "voorbeeld": None} for _ in weergave]
    for soort, lijst in (("eigen", eigen), ("voorbeeld", voorbeeld)):
        for k, t in enumerate(_tijden(verwacht, lijst) if lijst else []):
            if t and k < len(naar):
                oud = uit[naar[k]][soort]
                uit[naar[k]][soort] = [min(oud[0], t[0]), max(oud[1], t[1])] if oud else [round(t[0], 3), round(t[1], 3)]
    return uit


def max_tips_voor(n_woorden):
    """Een zin: twee tips. Een langere tekst heeft meer ruimte voor fouten, dus meer tips (hoogstens vier)."""
    return 2 if n_woorden <= 15 else 3 if n_woorden <= 40 else 4


def kies_tips(zin_id, r, res, toelichting, patronen=(), max_tips=None):
    """Tips op volgorde van betrouwbaarheid (twee bij een zin, meer bij een tekst). Elke tip: titel, uitleg,
    woord (nummer van het getoonde woord, of None) en eventueel woorden (alle betrokken woorden).
    toelichting: {(woord, variant): uitleg} uit varianten.tsv."""
    weergave, naar = _weergave(r)
    verwacht = normaliseer(r["zweeds"]).split()
    max_tips = max_tips or max_tips_voor(len(verwacht))
    tips = []

    # 1. Whisper verstond iets anders (betrouwbaar voor weggelaten woorden en woordvolgorde).
    wh = res.get("whisper", {})
    if "herkend" in wh:
        _, ops = bewerkingen(verwacht, normaliseer(wh["herkend"]).split())
        eigennamen, var_alle = namen(r), lees_klank_varianten()
        i = 0
        for soort, a, b in ops:
            if a in eigennamen:          # andere spelling van een naam: geen tip
                pass
            elif soort in ("S", "D") and not _bevestigd(i, res, var_alle):
                pass                     # de klanken waren in orde: Whisper raadde een ander woord
            elif soort == "S":
                tips.append({"titel": f"„{a}” werd „{b}” verstaan",
                             "uitleg": f"Een Zweed hoort hier „{b}” in plaats van „{a}”. Luister naar het voorbeeld "
                                       "en zeg het woord nog eens.", "woord": naar[i] if i < len(naar) else None,
                             "bron": "verstaan"})
            elif soort == "D":
                tips.append({"titel": f"„{a}” was niet te horen",
                             "uitleg": "Dit woord ontbrak of was te zacht. Spreek het duidelijk uit.",
                             "woord": naar[i] if i < len(naar) else None, "bron": "verstaan"})
            i += soort != "I"
        # Meer dan twee woorden anders verstaan (vaak bij een tekst): samen in één tip, met alle woorden
        # gemarkeerd om na te luisteren; zo blijft er ruimte voor klanktips.
        anders = [t for t in tips if t["bron"] == "verstaan"]
        if len(anders) > 2:
            lijst = ", ".join(t["titel"].replace(" werd ", " als ").replace(" verstaan", "")
                              .replace(" was niet te horen", " (niet gehoord)") for t in anders[:6])
            tips = [{"titel": f"{len(anders)} woorden anders verstaan",
                     "uitleg": f"Een Zweed verstond: {lijst}{' …' if len(anders) > 6 else ''}. Luister ze na bij "
                               "„Luister en vergelijk” (blauw onderstreept) en zeg ze nog eens.",
                     "woord": anders[0]["woord"], "woorden": [t["woord"] for t in anders], "bron": "verstaan"}]

    # 2. MFA: bij een doelwoord de verkeerde uitspraakvariant (bv. harde sk, lange a).
    for k in res.get("mfa", {}).get("keuze", []):
        doel = doel_variant(zin_id, k["woord"])
        if k["gekozen"] != doel and k["woord"] in verwacht:
            tips.append({"titel": f"Uitspraak van „{k['woord']}”",
                         "uitleg": f"Klonk als {toelichting.get((k['woord'], k['gekozen']), k['gekozen'])}; "
                                   f"bedoeld: {toelichting.get((k['woord'], doel), doel)}.",
                         "woord": naar[verwacht.index(k["woord"])], "bron": "uitspraak"})

    # 3. Klanktips: de categorie die in deze opname het vaakst voorkomt; terugkerende patronen gaan voor.
    var = lees_klank_varianten().get(SCORE_KLANKEN)
    pw = res.get("klanken", {}).get(SCORE_KLANKEN, {}).get("per_woord") or []
    pw_es = res.get("klanken", {}).get("xlsr53-espeak", {}).get("per_woord") or []
    if len(pw) == len(verwacht):
        per_cat = defaultdict(list)
        for k, w in enumerate(pw):
            for cat in klank_tips(w, var, pw_es[k] if len(pw_es) == len(pw) else None):
                per_cat[cat].append(k)
        terugkerend = {p["id"] for p in patronen}
        volgorde = sorted(per_cat, key=lambda c: (c == "klank", c not in terugkerend, -len(per_cat[c])))
        for cat in volgorde:
            k = per_cat[cat][0]
            if cat == "klank":
                w = pw[k]
                w_es = pw_es[k] if len(pw_es) == len(pw) else None
                f = next((f for f in w["fouten"] if not _normaal(f, var) and not _gehoord_door_ander(f, w_es)), None)
                uitleg = (f"{klank(f['verwacht'])} klonk als {klank(f['gehoord'])}." if f and f["soort"] == "anders"
                          else "Een klank in dit woord klonk anders.") + " Luister naar het voorbeeld en vergelijk."
                tips.append({"titel": f"Klank in „{w['woord']}”", "uitleg": uitleg, "woord": naar[k], "bron": "klanken"})
            else:
                titel, uitleg = INFO[cat]
                woorden = ", ".join(f"„{pw[x]['woord']}”" for x in per_cat[cat][:3])
                tips.append({"titel": titel, "uitleg": f"{uitleg} (in {woorden})", "woord": naar[k],
                             "bron": "klanken", "categorie": cat, "terugkerend": cat in terugkerend})
    # Hoogstens max_tips, en niet twee keer hetzelfde woord.
    gekozen, woorden = [], set()
    for t in tips:
        if t["woord"] in woorden and t["woord"] is not None:
            continue
        gekozen.append(t)
        woorden.add(t["woord"])
        if len(gekozen) == max_tips:
            break
    return gekozen


def patronen(min_aantal=3, max_aantal=3):
    """Terugkerende klankfouten over je laatste opname per zin (niet de bewuste fouten D)."""
    ids = {p.stem.upper() for p in OPNAMES.glob("*.*") if not p.stem.upper().startswith("D")}
    laatste = {}
    for p in sorted(ARCHIEF.glob("*.json")):
        z = p.name.split("-")[0]
        if z in ids:
            laatste[z] = p
    var = lees_klank_varianten().get(SCORE_KLANKEN)
    tel, voorbeelden = Counter(), defaultdict(list)
    for p in laatste.values():
        try:
            kl = json.loads(p.read_text(encoding="utf-8"))["resultaten"]["klanken"]
            pw = kl[SCORE_KLANKEN]["per_woord"]
            pw_es = (kl.get("xlsr53-espeak") or {}).get("per_woord") or []
        except (KeyError, TypeError, ValueError):
            continue
        for k, w in enumerate(pw):
            for cat in klank_tips(w, var, pw_es[k] if len(pw_es) == len(pw) else None):
                if cat != "klank":
                    tel[cat] += 1
                    if w["woord"] not in voorbeelden[cat]:
                        voorbeelden[cat].append(w["woord"])
    return [{"id": c, "titel": INFO[c][0], "uitleg": INFO[c][1], "aantal": n, "voorbeelden": voorbeelden[c][:4],
             "opnames": len(laatste)}
            for c, n in tel.most_common() if n >= min_aantal][:max_aantal]


def _tijd(stempel):
    """'20261125-143820' → '25-11 14:38'."""
    return f"{stempel[6:8]}-{stempel[4:6]} {stempel[9:11]}:{stempel[11:13]}"


def eigen_wav(naam):
    """De schoongemaakte 16 kHz-opname bij een analyse (naam = '<ID>-<stempel>'). Oudere opnames hebben geen
    '-16k' in de naam (toen was de upload nooit zelf een .wav)."""
    nieuw = ARCHIEF / f"{naam}-16k.wav"
    if nieuw.exists():
        return nieuw
    oud = ARCHIEF / f"{naam}.wav"   # oud formaat: alleen de omgezette versie als de upload webm was
    return oud if oud.exists() and (ARCHIEF / f"{naam}.webm").exists() else None


def huidige_score(zin_id, res):
    """De score van een (oude) analyse opnieuw berekenen op de huidige schaal en ijking, zodat oude en nieuwe
    opnames vergelijkbaar zijn (de schaal is in de proef een paar keer veranderd)."""
    from proef_common import KLANK_MODELLEN, lees_ijking, ruwe_score, score_onderdelen, vergelijk
    wh, kl, mfa = res.get("whisper", {}), res.get("klanken", {}), res.get("mfa", {})
    ijking = lees_ijking()
    ond = score_onderdelen(wh if "fout" not in wh else None,
                           {m: kl.get(m) for m in KLANK_MODELLEN if isinstance(kl.get(m), dict)},
                           mfa.get("keuze"), zin_id, native_per=(ijking or {}).get("native_per"))
    return {**vergelijk(ruwe_score(ond), ijking), "onderdelen": {n: round(100 * v) for n, v in ond.items()}}


def geschiedenis(zin_id, rij=None, toelichting=None):
    """Alle eerdere analyses van een zin, nieuwste eerst: naam, tijd, oordeel, schaal, microfoon. Oordeel en
    score met de huidige regels, net als bij terugkijken (oude_analyse)."""
    uit, pat = [], patronen() if rij is not None else []
    for p in sorted(ARCHIEF.glob(f"{zin_id}-*.json"), reverse=True):
        m = re.fullmatch(r"([A-Z]\d\d)-(\d{8}-\d{6})\.json", p.name)
        if not m:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        res = d.get("resultaten", {})
        score = huidige_score(zin_id, res)
        tips = ([] if rij is None or niets_gehoord(res.get("whisper"), d.get("geluid"))
                else kies_tips(zin_id, rij, res, toelichting or {}, pat))
        kop = eindoordeel(score, res.get("whisper"), tips, d.get("geluid"))[0]
        # Geen browseropname (geen .webm, wel een geüploade .wav): een testbestand, bv. de computerstem.
        test = not (ARCHIEF / f"{p.stem}.webm").exists() and (ARCHIEF / f"{p.stem}.wav").exists()
        uit.append({"naam": p.stem, "tijd": _tijd(m.group(2)), "kop": kop, "schaal": score.get("gelijkenis"),
                    "microfoon": (d.get("microfoon") or {}).get("naam"), "test": test})
    return uit


def oude_analyse(naam, rij, toelichting):
    """Een opgeslagen analyse, aangevuld met wat oudere versies nog niet bewaarden (oordeel in woorden, tips,
    woordtijden, audio). Het archiefbestand zelf blijft ongewijzigd."""
    d = json.loads((ARCHIEF / f"{naam}.json").read_text(encoding="utf-8"))
    zin_id, res = naam.split("-")[0], d.get("resultaten", {})
    d["tijd"] = _tijd(naam.split("-", 1)[1])
    if rij is not None:
        # Tips altijd opnieuw met de huidige regels (de bewaarde kunnen van een oudere versie zijn).
        d["tips"] = ([] if niets_gehoord(res.get("whisper"), d.get("geluid"))
                     else kies_tips(zin_id, rij, res, toelichting, patronen()))
        # Woordtijden altijd opnieuw: de voorbeeldstem kan sinds de opname veranderd zijn (Piper → MMS).
        woorden = d.get("woorden") or []
        tijden = woordtijden(zin_id, rij, res)
        if woorden and len(tijden) == len(woorden):
            d["woorden"] = [dict(w, **t) for w, t in zip(woorden, tijden)]
    d["score"] = huidige_score(zin_id, res)
    kop, zin, soort = eindoordeel(d["score"], res.get("whisper"), d.get("tips", []), d.get("geluid"))
    d["eindoordeel"] = {"kop": kop, "zin": zin, "soort": soort}
    wav = eigen_wav(naam)
    d["audio"] = {"eigen": f"/api/audio/{wav.name}" if wav else None,
                  "voorbeeld": f"/api/voorbeeld/{zin_id}" if voorbeeld_wav(zin_id) else None}
    d.pop("patronen", None)   # patronen gaan over nu, niet over toen
    return d


def voorbeeld_wav(zin_id):
    """Het voorbeeld (Piper, schoongemaakt en uitgelijnd in de batch), als dat er is."""
    p = CORPUS / "piper" / f"{zin_id}.wav"
    return p if p.exists() else None
