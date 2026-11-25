"""GOP (goodness of pronunciation) per klank, met MFA's Zweedse model via kalpy.

GOP per frame = log-likelihood van de best passende klank − die van de verwachte klank (≥ 0; 0 = de verwachte
klank past het best), gemiddeld over de klank. Per klank de beste modeltoestand; toon- en positievarianten
(uː˧˩, uː_B …) tellen als dezelfde klank. Daarnaast: welke klank er het vaakst het best paste ('gehoord').
Onderzoek en metingen: README, „Onderzocht: GOP met MFA”.

Eén Gop-object bouwt de uitlijner één keer (woordenboek → FST's duurt even); daarna is analyseren per opname
snel. Gebruik:
  from gop import Gop;  g = Gop(woordenboekpad);  g.analyseer(wav, "de tekst")
  python gop.py <corpusmap> <woordenboek> <uit.json>      (alle wav+lab in de corpusmap; met cache)
"""
import collections
import re
import sys
from pathlib import Path

import numpy as np

MODEL = Path("/mfa/pretrained_models/acoustic/swedish_mfa.zip")


def basis(foneem):
    """Klank zonder positie (_B/_I/_E/_S) en zonder toon."""
    return re.sub(r"[˥˦˧˨˩]", "", re.sub(r"_[BIES]$", "", foneem))


class Gop:
    def __init__(self, woordenboek):
        from kalpy.aligner import KalpyAligner
        from kalpy.fstext.lexicon import LexiconCompiler
        from montreal_forced_aligner.models import AcousticModel

        self.am = AcousticModel(MODEL)
        p = self.am.parameters
        self.lc = LexiconCompiler(
            disambiguation=False, silence_probability=p["silence_probability"],
            initial_silence_probability=p["initial_silence_probability"],
            final_silence_correction=p["final_silence_correction"],
            final_non_silence_correction=p["final_non_silence_correction"],
            silence_phone=p["optional_silence_phone"], oov_phone=p["oov_phone"],
            position_dependent_phones=p["position_dependent_phones"], phones=p["non_silence_phones"],
            ignore_case=True)
        self.lc.load_pronunciations(Path(woordenboek))
        self.lc.create_fsts()
        self.lc.clear()
        self.uitlijner = KalpyAligner(self.am, self.lc, beam=100, retry_beam=400)
        # Bij één opname zonder sprekeradaptatie lijnt kalpy uit met het sprekeronafhankelijke model (alimdl);
        # GOP rekent met datzelfde model, op dezelfde features.
        self.gmm = self.uitlijner.ali_aligner or self.uitlijner.aligner
        tm = self.gmm.transition_model
        pdfs = collections.defaultdict(set)
        for tid in range(1, tm.NumTransitionIds() + 1):
            naam = self.lc.phone_table.find(tm.TransitionIdToPhone(tid))
            b = basis(naam)
            if b and b != "sil" and not b.startswith("<") and b != "spn":
                pdfs[b].add(tm.TransitionIdToPdf(tid))
        self.basissen = sorted(pdfs)
        self.index = {b: i for i, b in enumerate(self.basissen)}
        self.pdf_lijsten = [sorted(pdfs[b]) for b in self.basissen]

    def analyseer(self, wav, tekst):
        """[{woord, klank, begin, eind, gop, gehoord}] voor één opname (16 kHz mono wav) met de verwachte tekst."""
        import soundfile as sf
        from _kalpy.gmm import gmm_compute_likes
        from kalpy.feat.cmvn import CmvnComputer
        from kalpy.utterance import Segment, Utterance

        duur = sf.info(str(wav)).duration
        woorden = re.sub(r"[^\w\s]", " ", tekst.lower()).split()
        utt = Utterance(Segment(str(wav), 0, duur, 0), " ".join(woorden))
        utt.generate_mfccs(self.am.mfcc_computer)
        cmvn = CmvnComputer().compute_cmvn_from_features([utt.mfccs])
        utt.apply_cmvn(cmvn)
        alignment = self.uitlijner._align_utterance(utt, cmvn)
        feats = utt.generate_features(self.am, cmvn=cmvn)
        likes = gmm_compute_likes(self.gmm.acoustic_model, feats).numpy()          # frames × pdf's
        per_klank = np.stack([likes[:, p].max(axis=1) for p in self.pdf_lijsten], axis=1)
        beste, top = per_klank.max(axis=1), per_klank.argmax(axis=1)
        stap = self.am.mfcc_computer.frame_shift
        stap = stap / 1000 if stap > 1 else stap                                      # ms of s
        intervallen = alignment.generate_ctm(self.gmm.transition_model, self.lc.phone_table, stap)
        ctm = self.lc.phones_to_pronunciations(alignment.words, intervallen, transcription=False, text=utt.transcript)
        uit = []
        for w in ctm.word_intervals:
            for ph in w.phones:
                b = basis(ph.label)
                if b not in self.index:
                    continue
                f0 = int(round(ph.begin / stap))
                f1 = max(f0 + 1, min(int(round(ph.end / stap)), len(beste)))
                gehoord = collections.Counter(self.basissen[t] for t in top[f0:f1]).most_common(1)[0][0]
                uit.append({"woord": w.label, "klank": b, "begin": round(ph.begin, 3), "eind": round(ph.end, 3),
                            "gop": round(float(np.mean(beste[f0:f1] - per_klank[f0:f1, self.index[b]])), 3),
                            "gehoord": gehoord})
        return uit


if __name__ == "__main__":
    import json
    corpus, woordenboek, uitpad = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    g = Gop(woordenboek)
    resultaat = {}
    for lab in sorted(corpus.glob("*/*.lab")):
        wav = lab.with_suffix(".wav")
        try:
            resultaat[f"{lab.parent.name}|{lab.stem}"] = g.analyseer(wav, lab.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            print("GOP mislukt:", lab.parent.name, lab.stem, repr(e)[:120], flush=True)
    uitpad.write_text(json.dumps(resultaat, ensure_ascii=False), encoding="utf-8")
    print(f"GOP voor {len(resultaat)} opnames → {uitpad}")
