"""Voegt alle CSV's samen tot resultaten/verslag.md (met de criteria uit PLAN.md)."""
import re
from collections import defaultdict
from statistics import mean

from proef_common import (ANKER, EXTERN, KLANK_MODELLEN, KLANK_PER_WOORD, NATIVE_PER, RESULTATEN, SCORE_KLANKEN,
                          SCORE_WHISPER, klank_oordeel, leer_varianten, lees_csv, maak_ijking, ruwe_score,
                          schrijf_csv, score_onderdelen, vergelijk, zinnen)

# Verwachte keuze bij de accentparen; bij overige goede opnames 'goed', bij D 'fout'.
VERWACHT_KEUZE = {"A01": "accent1", "A02": "accent2", "A03": "accent1", "A04": "accent2",
                  "D06": "accent1"}
LENGTEPAREN = [("B01", "B02", "glas – glass"), ("B03", "B04", "tak – tack"),
               ("B05", "B06", "vit – vitt"), ("B01", "D03", "glas goed – glas kort (fout)"),
               ("B04", "D02", "tack goed – tack lang (fout)")]
ZINDELEN = ("C", "F", "G", "T", "L")   # C (proef), F (A1), G (A2), T (tekst), L (oefenteksten)
MELODIE = ["A01", "A02", "A03", "A04", "D06", "C09"]


def gem(xs):
    xs = [float(x) for x in xs if x not in ("", None)]
    return f"{mean(xs):.2f}" if xs else "–"


def tabel(koppen, rijen):
    regels = ["| " + " | ".join(koppen) + " |", "|" + "---|" * len(koppen)]
    regels += ["| " + " | ".join(str(c) for c in r) + " |" for r in rijen]
    return "\n".join(regels) + "\n"


def verwacht_label(zin_id):
    return VERWACHT_KEUZE.get(zin_id, "fout" if zin_id.startswith("D") else "goed")


def main():
    z = zinnen()
    out = ["# Verslag proef Zweedse spraakherkenning\n\n",
           "Gemaakt door `proef/verslag/verslag.py`. Kleine aantallen: lees het als indicatie.\n"]
    criteria = []

    # 1. Whisper
    wh = lees_csv(RESULTATEN / "whisper.csv")
    out.append("\n## 1. Wát zeg je? — KB-Whisper\n\n")
    if wh:
        groep = defaultdict(list)
        for r in wh:
            groep[(r["model"], r["spreker"])].append(r)
        rijen = []
        for (m, s), rs in sorted(groep.items()):
            c = [r for r in rs if r["deel"] in ZINDELEN]
            d = [r for r in rs if r["deel"] == "D"]
            rijen.append([m, s, gem(r["wer_verwacht"] for r in c), gem(r["sec"] for r in rs),
                          f"{sum(int(r['afwijking_gevonden']) for r in d)}/{len(d)}" if d else "–"])
            if s == "ik" and c:
                criteria.append((f"WER zinnen (C, A1, A2, tekst) ≤ 0,10 ({m})", gem(r["wer_verwacht"] for r in c),
                                 "ja" if float(gem(r["wer_verwacht"] for r in c)) <= 0.10 else "nee"))
        out.append(tabel(["model", "spreker", "WER zinnen (C/A1/A2/T)", "sec/opname", "D: afwijking gezien"], rijen))
        out.append("\nFoutvarianten (D) en wat Whisper ervan maakte:\n\n")
        out.append(tabel(["id", "model", "bedoeld (goed)", "werkelijk gezegd", "herkend", "gezien"],
                         [[r["id"], r["model"], r["verwacht"], r["gezegd"] or "(zie opdracht)", r["herkend"],
                           "ja" if r["afwijking_gevonden"] == "1" else "nee"]
                          for r in wh if r["deel"] == "D" and r["spreker"] == "ik"]))
    else:
        out.append("_Geen resultaten (whisper.csv ontbreekt)._\n")

    # 2. MFA keuze-uitspraak
    kz = lees_csv(RESULTATEN / "mfa_keuze.csv")
    out.append("\n## 2. Hóé zeg je het? — MFA keuze-uitspraak\n\n")
    if kz:
        rijen, goed_fout, d_gevonden = [], [0, 0], [0, 0]
        for r in kz:
            if r["spreker"].startswith("extern-"):
                continue  # zie deel 4
            vl = verwacht_label(r["id"])
            klopt = r["gekozen"] == vl
            rijen.append([r["spreker"], r["id"], r["woord"], vl, r["gekozen"], r["klanken"],
                          "✓" if klopt else "✗"])
            if r["spreker"] == "ik":
                if r["id"].startswith("D"):
                    d_gevonden[0] += klopt; d_gevonden[1] += 1
                else:
                    goed_fout[0] += (not klopt); goed_fout[1] += 1
        out.append(tabel(["spreker", "id", "woord", "verwacht", "gekozen", "klanken", ""], rijen))
        criteria.append(("MFA: fouten gevonden (D) ≥ 80%", f"{d_gevonden[0]}/{d_gevonden[1]}",
                         "ja" if d_gevonden[1] and d_gevonden[0] / d_gevonden[1] >= 0.8 else "nee"))
        criteria.append(("MFA: onterecht afgekeurd (A–C) ≤ 10%", f"{goed_fout[0]}/{goed_fout[1]}",
                         "ja" if goed_fout[1] and goed_fout[0] / goed_fout[1] <= 0.1 else "nee"))
    else:
        out.append("_Geen resultaten (mfa_keuze.csv ontbreekt)._\n")

    # MFA-score per uiting
    for run in ("standaard",):
        an = lees_csv(RESULTATEN / f"mfa_{run}.csv")
        if an:
            per_id = {}
            for r in an:
                m = re.search(r"([A-D]\d\d)", " ".join(r.values()))
                spreker = r.get("speaker", "")
                if m:
                    per_id[(spreker, m.group(1))] = r
            rijen = []
            for zin_id, r in z.items():
                if r["goed_id"] and ("ik", zin_id) in per_id and ("ik", r["goed_id"]) in per_id:
                    a, b = per_id[("ik", r["goed_id"])], per_id[("ik", zin_id)]
                    rijen.append([zin_id, r["goed_id"], a.get("speech_log_likelihood", "?"),
                                  b.get("speech_log_likelihood", "?"),
                                  a.get("phone_duration_deviation", "?"), b.get("phone_duration_deviation", "?")])
            out.append("\nMFA-score per uiting (fout vs. goed, spreker ik; lager = slechter passend):\n\n")
            out.append(tabel(["fout", "goed", "loglik goed", "loglik fout", "duurafwijking goed",
                              "duurafwijking fout"], rijen) if rijen else "_Geen paren._\n")

    # 2b. Klankherkenner
    kl = lees_csv(RESULTATEN / "klanken.csv")
    out.append("\n## 2b. Klankherkenner (wav2vec2)\n\n")
    if kl:
        groep = defaultdict(list)
        for r in kl:
            groep[(r["model"], r["spreker"])].append(r)
        out.append(tabel(["model", "spreker", "PER A–C", "sec/opname"],
                         [[m, s, gem(r["per"] for r in rs if r["deel"] != "D"), gem(r["sec"] for r in rs)]
                          for (m, s), rs in sorted(groep.items())]))
        idx = {(r["model"], r["spreker"], r["id"]): r for r in kl}
        rijen = []
        for zin_id, r in z.items():
            for m in sorted({k[0] for k in idx}):
                f, g = idx.get((m, "ik", zin_id)), idx.get((m, "ik", r["goed_id"]))
                if r["goed_id"] and f and g:
                    rijen.append([zin_id, m, g["per"], f["per"], g["herkend"], f["herkend"]])
        out.append("\nFout vs. goed (spreker ik):\n\n")
        out.append(tabel(["id", "model", "PER goed", "PER fout", "herkend goed", "herkend fout"], rijen)
                   if rijen else "_Geen paren._\n")
    else:
        out.append("_Geen resultaten (klanken.csv ontbreekt)._\n")

    # 3. Lengte en melodie
    kv = lees_csv(RESULTATEN / "prosodie_klinkers.csv")
    pw = lees_csv(RESULTATEN / "prosodie_woorden.csv")
    out.append("\n## 3. Lengte en melodie\n\n")
    if kv:
        eerste = {}
        for r in kv:
            eerste.setdefault((r["spreker"], r["id"]), r)
        rijen = []
        for a, b, naam in LENGTEPAREN:
            for s in sorted({k[0] for k in eerste}):
                ra, rb = eerste.get((s, a)), eerste.get((s, b))
                if ra and rb:
                    rijen.append([naam, s, f"{ra['duur_ms']} ms ({ra['aandeel_woord']})",
                                  f"{rb['duur_ms']} ms ({rb['aandeel_woord']})"])
        out.append("Klinkerduur (aandeel van het woord), eerste klinker:\n\n")
        out.append(tabel(["paar", "spreker", "eerste", "tweede"], rijen) if rijen else "_Geen paren._\n")
    if pw:
        rijen = [[r["spreker"], r["id"], r["woord"], r["f0_toppen"], r["f0_top_positie"], r["f0_kontoer_ht"]]
                 for r in pw if r["id"] in MELODIE and r["woord"] in ("anden", "tanken", "barnen", "parken")]
        out.append("\nToonhoogte (halve tonen t.o.v. mediaan spreker; accent 2 verwacht 2 toppen):\n\n")
        out.append(tabel(["spreker", "id", "woord", "toppen", "positie hoogste", "kontoer (10 punten)"], rijen)
                   if rijen else "_Geen gegevens._\n")
    if not kv and not pw:
        out.append("_Geen resultaten (prosodie_*.csv ontbreken)._\n")

    # 4. Moedertaalsprekers (opnames/extern/)
    out.append("\n## 4. Moedertaalsprekers — onterecht afgekeurd?\n\n")
    ext_bronnen = sorted({r["spreker"] for r in wh + kz + kl if r.get("spreker", "").startswith("extern-")})
    if ext_bronnen:
        rijen = []
        for bron in ext_bronnen:
            w = [r for r in wh if r["spreker"] == bron]
            k = [r for r in kz if r["spreker"] == bron and r["woord"] not in ("anden", "tanken")]
            fout = [r for r in k if r["gekozen"] != "goed"]
            p_ = [r for r in kl if r["spreker"] == bron and r["model"] == "xlsr300m-sv"]
            modellen = sorted({r["model"] for r in w})
            rijen.append([bron.removeprefix("extern-"), len({r["id"] for r in w + k + p_}),
                          "; ".join(f"{m}: {gem(r['wer_verwacht'] for r in w if r['model'] == m)}"
                                    for m in modellen) or "–",
                          f"{len(fout)}/{len(k)}" if k else "–",
                          gem(r["per"] for r in p_)])
            if k:
                criteria.append((f"Moedertaal ({bron.removeprefix('extern-')}): onterecht afgekeurd ≤ 10%",
                                 f"{len(fout)}/{len(k)}", "ja" if len(fout) / len(k) <= 0.1 else "nee"))
        out.append(tabel(["bron", "fragmenten", "WER per model", "MFA: doelwoord afgekeurd", "PER xlsr300m-sv"],
                         rijen))
        afgekeurd = [r for r in kz if r["spreker"].startswith("extern-") and r["gekozen"] != "goed"
                     and r["woord"] not in ("anden", "tanken")]
        if afgekeurd:
            out.append("\nOnterecht afgekeurde doelwoorden (luister deze na: klopt de opname, of het model niet?):\n\n")
            out.append(tabel(["bron", "fragment", "woord", "gekozen", "klanken"],
                             [[r["spreker"].removeprefix("extern-"), r["id"], r["woord"], r["gekozen"], r["klanken"]]
                              for r in afgekeurd]))
        out.append("\nWER is bij losse woorden (Lingua Libre) streng: één fout woord = 100%.\n")
    else:
        out.append("_Geen externe opnames (opnames/extern/)._\n")

    criteria += score_deel(out, z, wh, kz, kl)
    criteria += woord_oordeel_deel(out)

    out.append("\n## Criteria (uit PLAN.md)\n\n")
    out.append(tabel(["criterium", "waarde", "gehaald"], criteria) if criteria else "_Nog niets te beoordelen._\n")
    out.append("\nLengte- en melodiecriteria (≥ 80% juist onderscheiden) beoordeel je uit de tabellen in deel 3.\n")

    pad = RESULTATEN / "verslag.md"
    pad.write_text("".join(out), encoding="utf-8")
    print(f"→ {pad}")


def woord_oordeel_deel(out):
    """Deel 6: hoe vaak krijgt een woord oranje/rood van de klankherkenner? Bij moedertaalsprekers hoort dat
    zelden te gebeuren (valse alarmen), bij het accent-anker vaak. De moedertaalsprekers worden beoordeeld met
    varianten die uit de ándere helft van de moedertaalsprekers geleerd zijn (anders te gunstig)."""
    import json
    out.append("\n## 6. Oordeel per woord — klopt het?\n\nPer woord oranje (let op) of rood (fout) volgens de "
               "klankherkenner, na het wegfilteren van afwijkingen die moedertaalsprekers ook maken. Bij "
               "moedertaalsprekers is elk oranje of rood woord een vals alarm.\n\n")
    if not KLANK_PER_WOORD.exists():
        out.append("_Geen klanken_per_woord.json (draai eerst de stap klanken)._\n")
        return []
    pw = json.loads(KLANK_PER_WOORD.read_text(encoding="utf-8"))
    items = [(k.split("|")[0], k.split("|")[1], k.split("|")[2], v) for k, v in pw.items()]
    groepen = [("moedertaalsprekers (FLEURS)", lambda s_, i: s_.startswith(EXTERN)),
               ("Voorbeeldstem (MMS)", lambda s_, i: s_ == "piper"),
               ("Nederlands accent (anker)", lambda s_, i: s_ == ANKER),
               ("eigen opnames (ik)", lambda s_, i: s_ == "ik")]
    tab, criteria = [], []
    m = SCORE_KLANKEN
    for naam, f in groepen:
        rs = [(s_, i, w) for s_, i, mm, w in items if mm == m and f(s_, i) and not i.startswith("D")]
        if not rs:
            continue
        tel = {"goed": 0, "let_op": 0, "fout": 0}
        voor, na = 0, 0
        native = sorted({s_ + i for s_, i, _ in rs}) if naam.startswith("moedertaal") else None
        for s_, i, w in rs:
            if native is not None:      # 2-voudige kruisvalidatie: leren op de andere helft
                helft = native.index(s_ + i) % 2
                andere = [(a, mm, ww) for a, b, mm, ww in items if mm == m and a.startswith(EXTERN)
                          and (a + b) in native and native.index(a + b) % 2 != helft]
                var = leer_varianten(andere).get(m)
            else:
                var = leer_varianten((a, mm, ww) for a, b, mm, ww in items if mm == m).get(m)
            for woord in w:
                if woord.get("score") is None:
                    continue
                voor += bool(woord["fouten"])
                tel[klank_oordeel(woord, var)[0]] += 1
        n = sum(tel.values())
        pct = lambda x: f"{round(100 * x / max(n, 1))}%"
        tab.append([naam, n, pct(voor), pct(tel["let_op"]), pct(tel["fout"]), pct(tel["let_op"] + tel["fout"])])
        if naam.startswith("moedertaal"):
            criteria.append((f"Per woord: valse alarmen bij {naam} ≤ 20%", pct(tel["let_op"] + tel["fout"]),
                             "ja" if (tel["let_op"] + tel["fout"]) / max(n, 1) <= 0.25 else "nee"))
        if naam.startswith("Nederlands accent"):
            criteria.append((f"Per woord: accent opgemerkt bij {naam} ≥ 40%", pct(tel["let_op"] + tel["fout"]),
                             "ja" if (tel["let_op"] + tel["fout"]) / max(n, 1) >= 0.4 else "nee"))
    out.append(tabel(["groep", "woorden", "afwijking (oud: elke afwijking)", "oranje", "rood", "oranje + rood"], tab))
    out.append("\nNiet meegeteld: Whisper (verstaan) en MFA (uitspraakvariant); die geven hun eigen meldingen.\n")
    return criteria


def accenttest(out, rijen, ijking):
    """Vaste controle: scheidt de score moedertaalsprekers van een Nederlands accent?"""
    out.append("\n### Accenttest\n\nDezelfde zinnen met Nederlandse uitspraakregels voorgelezen (espeak-ng `nl`, "
               "het 0-punt van de schaal) moeten duidelijk lager scoren dan moedertaalsprekers (100), en vrijwel "
               "nooit „als een moedertaalspreker” krijgen.\n\n")
    groepen = {"moedertaalsprekers": lambda r: r["deel"] == "E", "Voorbeeldstem (MMS)": lambda r: r["spreker"] == "piper",
               "Nederlands accent (anker)": lambda r: r["spreker"] == ANKER, "eigen opnames (ik)": lambda r: r["spreker"] == "ik"}
    tab, per_groep = [], {}
    for naam, f in groepen.items():
        rs = [r for r in rijen if f(r) and r["ruw"] is not None
              and r["deel"] not in ("A", "B", "D")]
        per_groep[naam] = rs
        if rs:
            als = sum(r.get("niveau") == "als een moedertaalspreker" for r in rs)
            tab.append([naam, len(rs), gem(r["ruw"] for r in rs), gem(r.get("gelijkenis") for r in rs),
                        f"{als}/{len(rs)}"])
    out.append(tabel(["groep (zinnen, geen losse woorden)", "n", "gem. ruwe score", "gem. schaal (0–100)",
                      "„als een moedertaalspreker”"], tab))
    criteria = []
    m, a = per_groep["moedertaalsprekers"], per_groep["Nederlands accent (anker)"]
    if m and a:
        auc = sum((x["ruw"] > y["ruw"]) + 0.5 * (x["ruw"] == y["ruw"]) for x in m for y in a) / (len(m) * len(a))
        fout_native = sum(r.get("niveau") == "als een moedertaalspreker" for r in a)
        out.append(f"\nAUC moedertaal > Nederlands accent: **{auc:.2f}** (1 = altijd hoger, 0,5 = gokken).\n")
        criteria.append(("Accent: AUC moedertaal > Nederlands accent ≥ 0,9", f"{auc:.2f}", "ja" if auc >= 0.9 else "nee"))
        criteria.append(("Accent: anker krijgt „als een moedertaalspreker” ≤ 5%", f"{fout_native}/{len(a)}",
                         "ja" if fout_native / len(a) <= 0.05 else "nee"))
    return criteria


def score_deel(out, z, wh, kz, kl):
    """Deel 5: score per opname (0–100) en vergelijking met moedertaalsprekers."""
    out.append("\n## 5. Score — hoe dicht bij een moedertaalspreker?\n\n")
    w_idx = {(r["spreker"], r["id"]): r for r in wh if r["model"] == SCORE_WHISPER}
    k_idx = defaultdict(dict)   # (spreker, id) → {model: rij}
    for r in kl:
        if r["model"] in KLANK_MODELLEN:
            k_idx[(r["spreker"], r["id"])][r["model"]] = r
    keuze = defaultdict(list)
    for r in kz:
        keuze[(r["spreker"], r["id"])].append(r)
    # Wat haalt een moedertaalspreker per klankherkenner? (mediaan PER; zonder hen de standaardwaarden)
    native_per = dict(NATIVE_PER)
    for m in KLANK_MODELLEN:
        pers = sorted(min(1.0, float(r["per"])) for r in kl if r["model"] == m and r["spreker"].startswith(EXTERN))
        if len(pers) >= 10:
            native_per[m] = round(pers[len(pers) // 2], 3)
    rijen = []
    for sleutel in sorted(set(w_idx) | set(k_idx) | set(keuze)):
        spreker, zin_id = sleutel
        extern = spreker.startswith(EXTERN)
        ond = score_onderdelen(w_idx.get(sleutel), k_idx.get(sleutel), keuze.get(sleutel), zin_id, extern,
                               native_per)
        deel = z[zin_id]["deel"][0] if not extern and zin_id in z else "E"
        rijen.append({"spreker": spreker, "id": zin_id, "deel": deel,
                      **{n: round(v, 3) for n, v in ond.items()}, "ruw": ruwe_score(ond)})
    if not rijen:
        out.append("_Geen resultaten om een score van te maken._\n")
        return []

    # IJking: moedertaalsprekers (FLEURS e.d.); zonder die opnames voorlopig de computerstem.
    # 0-punt: dezelfde zinnen met Nederlandse uitspraak (espeak-ng nl, gemaakt in de stap piper).
    # IJking: moedertaalsprekers (FLEURS) = 100; dezelfde zinnen met Nederlandse uitspraak (espeak-ng nl) = 0.
    # Zonder moedertaalsprekers voorlopig de computerstem.
    native = [r["ruw"] for r in rijen if r["deel"] == "E" and r["ruw"] is not None]
    anker = [r["ruw"] for r in rijen if r["spreker"] == ANKER and r["ruw"] is not None]
    if len(native) >= 10:
        bronnen = sorted({r["spreker"].removeprefix(EXTERN) for r in rijen if r["deel"] == "E"})
        ijking = maak_ijking(native, "moedertaalsprekers (" + ", ".join(bronnen) + ")", native_per, anker)
    else:
        piper = [r["ruw"] for r in rijen if r["spreker"] == "piper" and r["deel"] != "D" and r["ruw"] is not None]
        ijking = maak_ijking(piper, "voorbeeldstem MMS (voorlopig: geen moedertaalsprekers)", native_per, anker)
    for r in rijen:
        r.update(vergelijk(r["ruw"], ijking))
    schrijf_csv(RESULTATEN / "score.csv", rijen, ["spreker", "id", "deel", "klanken", "verstaan", "uitspraak",
                                                   "ruw", "percentiel", "gelijkenis", "niveau"])

    out.append("Ruwe score = 50% klanken (per klankherkenner 1 − PER, gedeeld door wat een moedertaalspreker "
               f"bij dat model haalt — mediaan PER {native_per} — en dan het beste van de twee) + 30% verstaan (Whisper small: 1 − WER, "
               "met woordzekerheid) + 20% juiste uitspraakvariant (MFA), alleen over de onderdelen die er zijn. "
               "**Schaal (0–100)**: 0 = mediaan van dezelfde zinnen met Nederlandse uitspraak (accent-anker), "
               "100 = mediaan van de moedertaalsprekers. **Niveau**: „als een moedertaalspreker” vanaf het 25e "
               "percentiel van de moedertaalsprekers; daaronder licht accent (schaal ≥ 50), duidelijk accent "
               "(> 0) of sterk Nederlands accent. **Percentiel**: aandeel moedertaal-opnames met dezelfde of "
               "een lagere score.\n\n")
    if ijking:
        out.append(f"Referentie: {ijking['bron']}, n = {ijking['n']}, mediaan {ijking['mediaan']}, "
                   f"10e percentiel {ijking['p10']}.\n\n")
        if "voorlopig" in ijking["bron"]:
            out.append("> Geen moedertaalsprekers gevonden: `docker compose run --rm extern fleurs` "
                       "(doet `alles.sh` vanzelf) haalt ze op.\n\n")
    out.append("Losse woorden geven een grovere score dan zinnen: één afwijkende klank weegt dan zwaar.\n\n")

    criteria = accenttest(out, rijen, ijking)
    eigen = [r for r in rijen if r["deel"] != "E"]
    groep = defaultdict(list)
    for r in rijen:
        if r["ruw"] is not None:
            groep[(r["spreker"], r["deel"])].append(r)
    out.append(tabel(["spreker", "deel", "opnames", "gem. ruwe score", "gem. schaal (0–100)"],
                     [[s, d, len(rs), gem(r["ruw"] for r in rs), gem(r.get("gelijkenis") for r in rs)]
                      for (s, d), rs in sorted(groep.items())]))

    idx = {(r["spreker"], r["id"]): r for r in eigen}
    paren = []
    for zin_id, r in z.items():
        if not r["goed_id"]:
            continue
        for s in sorted({k[0] for k in idx}):
            f, g = idx.get((s, zin_id)), idx.get((s, r["goed_id"]))
            if f and g and f["ruw"] is not None and g["ruw"] is not None:
                paren.append([s, zin_id, r["goed_id"], g["ruw"], f["ruw"], "✓" if f["ruw"] < g["ruw"] else "✗"])
    if paren:
        out.append("\nFoutvariant (D) tegenover de goede opname: hoort lager te scoren.\n\n")
        out.append(tabel(["spreker", "fout", "goed", "score goed", "score fout", "lager"], paren))
        ik = [p for p in paren if p[0] == "ik"]
        if ik:
            n = sum(p[5] == "✓" for p in ik)
            criteria.append(("Score: foutvariant lager dan goed (ik) ≥ 80%", f"{n}/{len(ik)}",
                             "ja" if n / len(ik) >= 0.8 else "nee"))
    eigen = [r for r in eigen if r["spreker"] not in ("piper", ANKER)]   # alleen echte sprekers
    out.append("\nAlle eigen opnames:\n\n")
    out.append(tabel(["spreker", "id", "klanken", "verstaan", "uitspraak", "ruw", "schaal", "percentiel", "niveau"],
                     [[r["spreker"], r["id"], r.get("klanken", "–"), r.get("verstaan", "–"),
                       r.get("uitspraak", "–"), r["ruw"], r.get('gelijkenis', '–'),
                       r.get("percentiel", "–"), r.get("niveau", "–")] for r in eigen]))
    return criteria


if __name__ == "__main__":
    main()
