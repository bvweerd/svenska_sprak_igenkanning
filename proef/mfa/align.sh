#!/usr/bin/env bash
# Vraag 2 en 3 — MFA legt de verwachte zin over de opname (woord- en klankgrenzen).
# Draait twee keer:
#   standaard/  met het gewone swedish_mfa-woordenboek
#   varianten/  met daarbij de goede en foute uitspraken uit varianten.tsv (keuze-uitspraak)
set -euo pipefail
CORPUS=/data/werk/corpus
UIT=/data/werk/mfa
WB=$MFA_ROOT_DIR/pretrained_models/dictionary/swedish_mfa.dict
mkdir -p "$UIT"

[ -d "$CORPUS" ] || { echo "Geen corpus: draai eerst 'prep'."; exit 1; }

# Woorden in de .lab-bestanden die niet in het woordenboek staan (zouden <unk> worden).
python - "$CORPUS" "$WB" "$UIT/oov.txt" <<'PY'
import re, sys
from pathlib import Path
corpus, wb, uit = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
bekend = {r.split("\t", 1)[0] for r in open(wb, encoding="utf-8")}
woorden = {w for lab in corpus.glob("*/*.lab")
           for w in re.findall(r"\w+", lab.read_text(encoding="utf-8").lower())}
Path(uit).write_text("".join(f"{w}\n" for w in sorted(woorden - bekend)), encoding="utf-8")
PY
mfa server start 2>/dev/null || true
trap 'mfa server stop 2>/dev/null || true' EXIT

# Onbekende woorden (vooral in externe zinnen): uitspraak laten voorspellen met het Zweedse
# G2P-model. Lukt dat niet, dan worden ze <unk> en lijnt MFA de rest gewoon uit.
cp "$WB" "$UIT/woordenboek_standaard.dict"
if [ -s "$UIT/oov.txt" ]; then
  echo "$(wc -l < "$UIT/oov.txt") woorden niet in het woordenboek; G2P maakt een uitspraak."
  if mfa g2p "$UIT/oov.txt" swedish_mfa "$UIT/oov.dict" --clean; then
    cat "$UIT/oov.dict" >> "$UIT/woordenboek_standaard.dict"
  else
    echo "G2P mislukt; deze woorden worden <unk>:"; cat "$UIT/oov.txt"
  fi
fi

# Woordenboek met varianten: het standaardwoordenboek plus alle regels uit varianten.tsv.
cp "$UIT/woordenboek_standaard.dict" "$UIT/woordenboek_varianten.dict"
grep -v '^#' /app/varianten.tsv | awk -F'\t' 'NF>=3 {print $1 "\t" $3}' >> "$UIT/woordenboek_varianten.dict"

for run in standaard varianten; do
  dict=$UIT/woordenboek_$run.dict
  echo "== MFA align ($run)"
  # Ruime beam: een foute uitspraak moet nog steeds uitgelijnd worden, niet overgeslagen.
  mfa align "$CORPUS" "$dict" swedish_mfa "$UIT/$run" \
    --clean --overwrite --output_format long_textgrid \
    --beam 100 --retry_beam 400 --num_jobs "${MFA_JOBS:-2}"
done

# Score per uiting (log-likelihood, afwijking klankduur) schrijft MFA naast de TextGrids.
mkdir -p /data/resultaten
for run in standaard varianten; do
  if [ -f "$UIT/$run/alignment_analysis.csv" ]; then
    cp "$UIT/$run/alignment_analysis.csv" "/data/resultaten/mfa_$run.csv"
  fi
done
echo "Klaar: TextGrids in $UIT/{standaard,varianten}/<spreker>/<id>.TextGrid"
