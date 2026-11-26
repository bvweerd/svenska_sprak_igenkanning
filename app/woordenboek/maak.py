"""Uitspraak voor woorden uit de teksten die niet in het MFA-woordenboek staan (vooral namen), met het G2P-model
van MFA zelf (swedish_mfa) → app/teksten/woordenboek_extra.dict (in git, naast de teksten). De MFA- en klanken-API lezen dat bestand bij elke
analyse; zonder dit worden zulke woorden niet uitgelijnd en niet beoordeeld.

  python /app/woordenboek.py      (in het MFA-image; na de import)
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from gedeeld import normaliseer

WB = Path(os.environ["MFA_ROOT_DIR"]) / "pretrained_models" / "dictionary" / "swedish_mfa.dict"
TEKSTEN = Path(os.environ.get("TEKSTEN", "/teksten/teksten.json"))
UIT = Path(os.environ.get("WOORDENBOEK_EXTRA", "/teksten/woordenboek_extra.dict"))


def main():
    teksten = json.loads(TEKSTEN.read_text(encoding="utf-8"))["teksten"]
    woorden = {w for t in teksten for s in t["stukken"] for w in normaliseer(s["tekst"]).split()}
    bekend = {r.split("\t", 1)[0] for r in WB.read_text(encoding="utf-8").splitlines() if r.strip()}
    nieuw = sorted(w for w in woorden - bekend if w.isalpha())
    print(f"{len(woorden)} verschillende woorden, {len(nieuw)} niet in het woordenboek")
    if not nieuw:
        UIT.write_text("", encoding="utf-8")
        return
    with tempfile.TemporaryDirectory() as tmp:
        lijst, uit = Path(tmp) / "woorden.txt", Path(tmp) / "uitspraak.txt"
        lijst.write_text("\n".join(nieuw) + "\n", encoding="utf-8")
        subprocess.run(["mfa", "g2p", str(lijst), "swedish_mfa", str(uit), "--clean"], check=True)
        # Gesorteerd: MFA schrijft in wisselende volgorde, en het bestand staat in git.
        regels = sorted({r for r in uit.read_text(encoding="utf-8").splitlines() if "\t" in r})
    UIT.write_text("\n".join(regels) + "\n", encoding="utf-8")
    print(f"→ {UIT} ({len(regels)} woorden), bv.: " + "; ".join(regels[:5]))


if __name__ == "__main__":
    main()
