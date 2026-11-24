#!/usr/bin/env bash
# Hele proef in de goede volgorde. Gebruik: ./proef/alles.sh [--zonder-piper]
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p werk resultaten opnames
# Containers draaien als uid 1000; zo kunnen ze hier schrijven, ook als jouw uid anders is.
chmod a+rwx werk resultaten opnames
dc() { docker compose --profile batch "$@"; }
dc build
[ "${1:-}" = "--zonder-piper" ] || dc run --rm piper
dc run --rm prep
dc run --rm whisper
dc run --rm mfa
dc run --rm klanken
dc run --rm prosodie
dc run --rm verslag
echo "Klaar: resultaten/verslag.md"
