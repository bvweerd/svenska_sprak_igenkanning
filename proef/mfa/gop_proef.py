"""GOP, eigen berekening op MFA's features en model (verbeterde versie van MFA's phone_goodness).

Verschillen met MFA:
- per klank de BESTE modeltoestand (max over pdf's) i.p.v. een gewogen gemiddelde over alle contextafhankelijke
  toestanden;
- toon- en positievarianten (uː˧˩, uː_B …) tellen als dezelfde klank.
GOP per frame = log-likelihood beste klank − die van de verwachte klank (≥ 0); per klank het gemiddelde.

  python gop_proef.py <corpus> <woordenboek> <uit.csv>   (in het mfa-image, met "mfa server start"; zie README)
"""
import collections
import csv
import re
import sys
from pathlib import Path

import numpy as np
from _kalpy.gmm import gmm_compute_likes
from kalpy.gmm.utils import read_gmm_model
from montreal_forced_aligner.alignment.pretrained import PretrainedAligner
from montreal_forced_aligner.db import File, Job, Phone, PhoneInterval, Speaker, Utterance, Word, WordInterval
from sqlalchemy.orm import joinedload, selectinload

corpus, woordenboek, uit = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])


def basis(foneem):
    """Klank zonder positie (_B/_I/_E/_S) en zonder toon."""
    return re.sub(r"[˥˦˧˨˩]", "", re.sub(r"_[BIES]$", "", foneem))


aligner = PretrainedAligner(corpus_directory=corpus, dictionary_path=woordenboek,
                            acoustic_model_path=Path("/mfa/pretrained_models/acoustic/swedish_mfa.zip"),
                            beam=100, retry_beam=400)
aligner.align()

transitie, akoestisch = read_gmm_model(aligner.model_path)
fonemen = {int(nr): naam for naam, nr in (r.split() for r in
           (Path(aligner.phones_dir) / "phones.txt").read_text(encoding="utf-8").splitlines())}
pdfs_per_basis = collections.defaultdict(set)
for tid in range(1, transitie.NumTransitionIds() + 1):
    pdfs_per_basis[basis(fonemen[transitie.TransitionIdToPhone(tid)])].add(transitie.TransitionIdToPdf(tid))
pdfs_per_basis.pop("sil", None)
for k in [k for k in pdfs_per_basis if k.startswith("<") or k in ("spn",)]:
    pdfs_per_basis.pop(k)
basissen = sorted(pdfs_per_basis)
index = {b: i for i, b in enumerate(basissen)}
pdf_lijsten = [sorted(pdfs_per_basis[b]) for b in basissen]
print(f"{len(basissen)} basisklanken")

rijen = []
with aligner.session() as s:
    bestanden = {f.id: f.name for f in s.query(File)}
    utts = {u.id: u for u in s.query(Utterance).options(
        selectinload(Utterance.phone_intervals).joinedload(PhoneInterval.phone),
        selectinload(Utterance.phone_intervals).joinedload(PhoneInterval.word_interval).joinedload(WordInterval.word),
        joinedload(Utterance.speaker))}
    for job in s.query(Job).options(joinedload(Job.dictionaries), joinedload(Job.corpus)):
        for d in job.dictionaries:
            try:
                archief = job.construct_feature_archive(aligner.working_directory, d.name)
            except OSError:
                continue
            for utt_naam, feats in archief:
                u = utts[int(utt_naam.split("-")[-1])]
                likes = gmm_compute_likes(akoestisch, feats).numpy()          # frames × pdf's
                per_basis = np.stack([likes[:, p].max(axis=1) for p in pdf_lijsten], axis=1)   # frames × klanken
                beste = per_basis.max(axis=1)
                top = per_basis.argmax(axis=1)
                for pi in u.phone_intervals:
                    b = basis(pi.phone.phone)
                    if b not in index:
                        continue
                    f0 = int(round((pi.begin - u.begin) * 100))
                    f1 = max(f0 + 1, min(int(round((pi.end - u.begin) * 100)), len(beste)))
                    gop = float(np.mean(beste[f0:f1] - per_basis[f0:f1, index[b]]))
                    vaakst = collections.Counter(basissen[t] for t in top[f0:f1]).most_common(1)[0][0]
                    rijen.append({"spreker": u.speaker.name, "id": bestanden.get(u.file_id, u.file_id),
                                  "woord": pi.word_interval.word.word if pi.word_interval and pi.word_interval.word else "",
                                  "klank": b, "begin": round(pi.begin, 3), "eind": round(pi.end, 3),
                                  "gop": round(gop, 3), "gehoord": vaakst})
with open(uit, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, list(rijen[0]))
    w.writeheader()
    w.writerows(rijen)
print(f"{len(rijen)} klanken → {uit}")
