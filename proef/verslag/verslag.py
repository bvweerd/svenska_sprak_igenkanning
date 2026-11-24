"""Voegt alle CSV's samen tot resultaten/verslag.md (met de criteria uit PLAN.md)."""
import re
from collections import defaultdict
from statistics import mean

from proef_common import RESULTATEN, lees_csv, zinnen

# Verwachte keuze bij de accentparen; bij overige goede opnames 'goed', bij D 'fout'.
VERWACHT_KEUZE = {"A01": "accent1", "A02": "accent2", "A03": "accent1", "A04": "accent2",
                  "D06": "accent1"}
LENGTEPAREN = [("B01", "B02", "glas – glass"), ("B03", "B04", "tak – tack"),
               ("B05", "B06", "vit – vitt"), ("B01", "D03", "glas goed – glas kort (fout)"),
               ("B04", "D02", "tack goed – tack lang (fout)")]
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
            c = [r for r in rs if r["deel"] == "C"]
            d = [r for r in rs if r["deel"] == "D"]
            rijen.append([m, s, gem(r["wer_verwacht"] for r in c), gem(r["sec"] for r in rs),
                          f"{sum(int(r['afwijking_gevonden']) for r in d)}/{len(d)}" if d else "–"])
            if s == "ik" and c:
                criteria.append((f"WER deel C ≤ 0,10 ({m})", gem(r["wer_verwacht"] for r in c),
                                 "ja" if float(gem(r["wer_verwacht"] for r in c)) <= 0.10 else "nee"))
        out.append(tabel(["model", "spreker", "WER deel C", "sec/opname", "D: afwijking gezien"], rijen))
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

    out.append("\n## Criteria (uit PLAN.md)\n\n")
    out.append(tabel(["criterium", "waarde", "gehaald"], criteria) if criteria else "_Nog niets te beoordelen._\n")
    out.append("\nLengte- en melodiecriteria (≥ 80% juist onderscheiden) beoordeel je uit de tabellen in deel 3.\n")

    pad = RESULTATEN / "verslag.md"
    pad.write_text("".join(out), encoding="utf-8")
    print(f"→ {pad}")


if __name__ == "__main__":
    main()
