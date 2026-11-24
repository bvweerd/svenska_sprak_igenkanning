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
cat "$CORPUS"/*/*.lab | tr '[:upper:]' '[:lower:]' | tr -c '[:alnum:]åäöéü\n' ' ' | tr ' ' '\n' \
  | sed '/^$/d' | sort -u > "$UIT/woorden.txt"
cut -f1 "$WB" | sort -u > "$UIT/woordenboek_woorden.txt"
comm -23 "$UIT/woorden.txt" "$UIT/woordenboek_woorden.txt" > "$UIT/oov.txt" || true
if [ -s "$UIT/oov.txt" ]; then
  echo "Let op, niet in het woordenboek (voeg toe aan varianten.tsv als 'goed'):"; cat "$UIT/oov.txt"
fi

# Woordenboek met varianten: het gewone plus alle regels uit varianten.tsv.
cp "$WB" "$UIT/woordenboek_varianten.dict"
grep -v '^#' /app/varianten.tsv | awk -F'\t' 'NF>=3 {print $1 "\t" $3}' >> "$UIT/woordenboek_varianten.dict"

mfa server start 2>/dev/null || true
trap 'mfa server stop 2>/dev/null || true' EXIT

for run in standaard varianten; do
  dict=$WB; [ $run = varianten ] && dict=$UIT/woordenboek_varianten.dict
  echo "== MFA align ($run)"
  # Ruime beam: een foute uitspraak moet nog steeds uitgelijnd worden, niet overgeslagen.
  mfa align "$CORPUS" "$dict" swedish_mfa "$UIT/$run" \
    --clean --overwrite --output_format long_textgrid \
    --beam 100 --retry_beam 400 --num_jobs "${MFA_JOBS:-2}"
done

# Score per uiting (log-likelihood, afwijking klankduur) schrijft MFA naast de TextGrids.
mkdir -p /data/resultaten
for run in standaard varianten; do
  [ -f "$UIT/$run/alignment_analysis.csv" ] && cp "$UIT/$run/alignment_analysis.csv" "/data/resultaten/mfa_$run.csv"
done
echo "Klaar: TextGrids in $UIT/{standaard,varianten}/<spreker>/<id>.TextGrid"
