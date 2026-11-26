"""Gebruikersvriendelijke feedback (productieversie). Overgenomen uit de proef (git-tag 'proef'), met wat daar
betrouwbaar bleek (zie ONDERZOEK.md):
- het oordeel komt uit de score op het hele stuk, in woorden;
- een paar tips, op volgorde van betrouwbaarheid: wat Whisper anders verstond (alleen als een klankherkenner
  het bevestigt), een fout bij een doelwoord volgens MFA, en pas dan een klanktip;
- klanktips in Nederlandse klanken, zonder IPA, uit een vaste lijst typische fouten van Nederlandstaligen;
- woordtijden (MFA) om je eigen woord en het voorbeeld (MMS) na elkaar te horen;
- patronen over je recente opnames: één klanktip zegt weinig, tien keer dezelfde fout wel.
Verschil met de proef: geen testzinnen maar oefenstukken, per gebruiker, en de woordtijden van het voorbeeld
komen uit data/voorbeeld/<stuk>.json (gemaakt door de voorbeeldtaak).
"""
from collections import Counter, defaultdict

from gedeeld import (KLANK_MODELLEN, SCORE_KLANKEN, bewerkingen, doel_variant, klank, klank_oordeel,
                          lees_ijking, lees_klank_varianten, normaliseer, ruwe_score, score_onderdelen, vergelijk)


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
    """Is deze afwijking normaal bij moedertaalsprekers (geleerd in de proef, bevroren in app/ijking)?"""
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
        return f["gehoord"] not in gehoord
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
    if not uit and echt:
        uit.append("klank")
    return uit


def niets_gehoord(wh, geluid):
    """Een (bijna) stille of afgebroken opname: Whisper hoorde geen woord en de opname is erg zacht."""
    return bool((geluid or {}).get("zacht")) and not normaliseer((wh or {}).get("herkend", "")).split()


def eindoordeel(score, wh, tips=(), geluid=None):
    """Eén oordeel in woorden: (kop, zin, soort). Geen 'Uitstekend' zolang er een betrouwbare tip is."""
    niveau = (score or {}).get("niveau")
    wer = (wh or {}).get("wer_verwacht")
    verstaan = wer is not None and float(wer) <= 0.1
    betrouwbare_tip = any(t.get("bron") in ("verstaan", "uitspraak") for t in tips)
    if niets_gehoord(wh, geluid):
        return ("Niets gehoord", "De opname is (bijna) stil of heel kort. Kies bij Microfoon de goede microfoon, "
                                 "druk op Opnemen, lees het hele stuk en druk dan pas op Stop.", "onbekend")
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
    return ("Oefen dit stuk nog eens", "Een Zweed zou je hier lastig verstaan. Luister naar het voorbeeld en "
                                      "probeer het rustig opnieuw.", "zwak")


# ---------- namen: Whisper kent ze slecht; een andere spelling is geen uitspraakfout ----------

ALLE_NAMEN = set()


def namen_in(tekst):
    """Woorden die midden in een zin met een hoofdletter staan (Wilma, Fleur, Västerås)."""
    uit, begin = set(), True
    for w in tekst.split():
        if w[:1].isupper() and not begin:
            uit.update(normaliseer(w).split())
        begin = w[-1:] in ".!?"
    return uit


def zet_namen(teksten):
    """Namen uit alle oefenstukken: zo telt Olle ook aan het begin van een zin als naam."""
    ALLE_NAMEN.clear()
    for tekst in teksten:
        ALLE_NAMEN.update(namen_in(tekst))


def namen(r):
    return ALLE_NAMEN | namen_in(r["zweeds"])


def _bevestigd(k, res, var_alle):
    """Een Whisper-tip gaat alleen door als geen van beide klankherkenners het woord goed vond (Whisper raadt
    bij twijfel een waarschijnlijker woord, ook als de klanken klopten). Zonder klankanalyse: niet tegenhouden."""
    oordelen = []
    for m in KLANK_MODELLEN:
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


def woordtijden(r, res, voorbeeld):
    """Per getoond woord: tijden in je eigen opname en in het voorbeeld, voor 'luister en vergelijk'.
    voorbeeld: [(start, eind, woord)] van de voorbeeldstem, of leeg."""
    weergave, naar = _weergave(r)
    verwacht = normaliseer(r["zweeds"]).split()
    eigen = [(w["start"], w["start"] + w["duur_ms"] / 1000, w["woord"])
             for w in res.get("mfa", {}).get("woorden", []) if w.get("woord") not in (None, "", "<eps>", "<unk>")]
    uit = [{"eigen": None, "voorbeeld": None} for _ in weergave]
    for soort, lijst in (("eigen", eigen), ("voorbeeld", voorbeeld or [])):
        for k, t in enumerate(_tijden(verwacht, lijst) if lijst else []):
            if t and k < len(naar):
                oud = uit[naar[k]][soort]
                uit[naar[k]][soort] = [min(oud[0], t[0]), max(oud[1], t[1])] if oud else [round(t[0], 3), round(t[1], 3)]
    return uit


def max_tips_voor(n_woorden):
    """Een zin: twee tips. Een langer stuk heeft meer ruimte voor fouten, dus meer tips (hoogstens vier)."""
    return 2 if n_woorden <= 15 else 3 if n_woorden <= 40 else 4


def kies_tips(stuk_id, r, res, toelichting, patronen=(), max_tips=None):
    """Tips op volgorde van betrouwbaarheid. Elke tip: titel, uitleg, woord (nummer van het getoonde woord, of
    None) en eventueel woorden (alle betrokken woorden). toelichting: {(woord, variant): uitleg} uit varianten.tsv."""
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
            if a in eigennamen:
                pass
            elif soort in ("S", "D") and not _bevestigd(i, res, var_alle):
                pass
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
        anders = [t for t in tips if t["bron"] == "verstaan"]
        if len(anders) > 2:
            lijst = ", ".join(t["titel"].replace(" werd ", " als ").replace(" verstaan", "")
                              .replace(" was niet te horen", " (niet gehoord)") for t in anders[:6])
            tips = [{"titel": f"{len(anders)} woorden anders verstaan",
                     "uitleg": f"Een Zweed verstond: {lijst}{' …' if len(anders) > 6 else ''}. Luister ze na bij "
                               "„Luister en vergelijk” (rood) en zeg ze nog eens.",
                     "woord": anders[0]["woord"], "woorden": [t["woord"] for t in anders], "bron": "verstaan"}]

    # 2. MFA: bij een doelwoord de verkeerde uitspraakvariant (bv. harde sk, lange a).
    for k in res.get("mfa", {}).get("keuze", []):
        doel = doel_variant(k["woord"])
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
    gekozen, woorden = [], set()
    for t in tips:
        if t["woord"] in woorden and t["woord"] is not None:
            continue
        gekozen.append(t)
        woorden.add(t["woord"])
        if len(gekozen) == max_tips:
            break
    return gekozen


def patronen(analyses, min_aantal=3, max_aantal=3):
    """Terugkerende klankfouten over je laatste opname per stuk. analyses: [res] (de 'resultaten' van recente
    opnames, één per stuk)."""
    var = lees_klank_varianten().get(SCORE_KLANKEN)
    tel, voorbeelden = Counter(), defaultdict(list)
    n = 0
    for res in analyses:
        try:
            kl = res["klanken"]
            pw = kl[SCORE_KLANKEN]["per_woord"]
            pw_es = (kl.get("xlsr53-espeak") or {}).get("per_woord") or []
        except (KeyError, TypeError):
            continue
        n += 1
        for k, w in enumerate(pw):
            for cat in klank_tips(w, var, pw_es[k] if len(pw_es) == len(pw) else None):
                if cat != "klank":
                    tel[cat] += 1
                    if w["woord"] not in voorbeelden[cat]:
                        voorbeelden[cat].append(w["woord"])
    return [{"id": c, "titel": INFO[c][0], "uitleg": INFO[c][1], "aantal": a, "voorbeelden": voorbeelden[c][:4],
             "opnames": n}
            for c, a in tel.most_common() if a >= min_aantal][:max_aantal]


def score_van(stuk_id, res):
    """Score op de bevroren ijking (moedertaalsprekers = 100, Nederlands accent = 0)."""
    wh, kl, mfa = res.get("whisper", {}), res.get("klanken", {}), res.get("mfa", {})
    ijking = lees_ijking()
    ond = score_onderdelen(wh if "fout" not in wh else None,
                           {m: kl.get(m) for m in KLANK_MODELLEN if isinstance(kl.get(m), dict)},
                           mfa.get("keuze"), native_per=(ijking or {}).get("native_per"))
    return {**vergelijk(ruwe_score(ond), ijking), "onderdelen": {n: round(100 * v) for n, v in ond.items()}}
