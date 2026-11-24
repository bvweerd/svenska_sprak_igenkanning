# Proef: Zweedse spraakherkenning en uitspraakcontrole

Doel op termijn: **spreekopdrachten in de oefensite** (`svenska_ovningar`, `svenska_ovningar_b`) die de app
zelf nakijkt. Deze proef beantwoordt eerst of dat goed genoeg kan, met lokale modellen in Docker.

## Verhouding tot de spelregels

De site sluit spreken nu uit (`../svenska_ovningar/PLAN.md`, „Geen spreken en uitspraak nakijken”): herkenning
was niet goed genoeg, werkte alleen via een externe dienst en terugluisteren vraagt zelfbeoordeling. Deze
proef toetst precies die drie bezwaren:

| Bezwaar | Wat de proef meet |
|---|---|
| Niet goed genoeg | Herkent het systeem goede uitspraak als goed en een bewuste fout als fout? |
| Externe dienst | Welke modellen kunnen ook **in de browser** draaien (offline, geen server)? |
| Zelfbeoordeling | Kan de app een oordeel geven per klank, woord of zin, zonder de leerling te laten kiezen? |

Pas als de proef slaagt, beslist de eigenaar of de spelregels en de onderwijskundige lijn (punt 8, „Geen
spreken nakijken”) veranderen. Tot dan komt er niets van dit werk in de sites.

## Kandidaten

Drie vragen, elk met een eigen soort model:

1. **Wát zeg je?** (woorden herkennen, spraakherkenning)
2. **Hóé zeg je het?** (klanken: sj/tj, lang/kort, u/y/o)
3. **Melodie** (woordaccent 1/2, klinkerlengte)

| Kandidaat | Vraag | Wat het is | Docker | In de browser? |
|---|---|---|---|---|
| **KB-Whisper** (KBLab, Kungliga biblioteket) | 1 | Whisper getraind op 50.000+ uur Zweeds; `small` is beter dan OpenAI's `whisper-large-v3` op Zweeds. Maten tiny/base/small/medium/large | `python:3.11-slim` + `faster-whisper` of `transformers` | **Ja**: tiny/base via transformers.js (ONNX), ~40–150 MB |
| **Montreal Forced Aligner** met `swedish_mfa` (akoestisch model + uitspraakwoordenboek, v3.0.0, CC BY 4.0) | 2, 3 | Legt de **bekende** zin over de opname: begin/eind van elk woord en elke klank, plus een score per uiting | geen officieel onderhouden image; zelf bouwen op `condaforge/miniforge3` + `conda install -c conda-forge montreal-forced-aligner` | Nee (Kaldi); alleen op een server |
| **wav2vec2 klankherkenner** (`facebook/wav2vec2-xlsr-53-espeak-cv-ft`, of het Zweedse `patrickvonplaten/wav2vec2-xls-r-phoneme-300m-sv`) | 2 | Schrijft op welke klanken (IPA) je zei, zonder taalmodel dat „verbetert”; vergelijken met de verwachte uitspraak uit `espeak-ng -v sv --ipa` | `python:3.11-slim` + `transformers`, `espeak-ng` | Mogelijk: ~300M parameters, gekwantiseerd ~300 MB; zwaar voor een telefoon |
| **Praat / parselmouth** | 3 | Toonhoogte (F0) en duur meten in de stukken die MFA aanwijst; woordaccent 2 heeft in Centraal-Zweeds twee toppen | `python:3.11-slim` + `praat-parselmouth` | Ja, toonhoogte meten kan in JS (Web Audio) |
| **Piper TTS** stem `sv_SE-nst-medium` | controle | Computerstem als „goede” referentie naast jouw opnames | `rhasspy/wyoming-piper` of `piper` in Python | (de site gebruikt al de browserstem) |

Bewust **niet** gekozen: Vosk (kleiner en zwakker dan KB-Whisper), clouddiensten (Azure Pronunciation
Assessment ondersteunt Zweeds, maar is een externe dienst en past niet bij de spelregels).

Verwachte zwakte van Whisper: het taalmodel **verbetert** wat je zegt („Klockan sju vi äter” wordt misschien
„Klockan sju äter vi”). Dan is het goed voor vraag 1, maar slecht voor foutdetectie. De proef meet dat met
de foutvarianten (deel D van de testzinnen).

## Opzet

Alles staat klaar in `docker-compose.yml` en `proef/` (bouwen op de pc; zie README). Twee manieren:

- **Testpagina** (`docker compose up --build`, http://localhost:8080): zin kiezen, opnemen, en binnen
  enkele seconden feedback van de drie analyses. Elke opname komt in `opnames/<id>`.
- **Batch** (`./proef/alles.sh`): alle opnames door alle modellen, met `resultaten/verslag.md`.

| Stap | Map | Wat | Uitkomst |
|---|---|---|---|
| 0 | `web/` | Jij neemt op (testpagina, of losse bestanden in `opnames/`) | `opnames/<id>.*` |
| 1 | `piper/` | Referentie: zinnen A–C met de Piper-stem | `werk/piper_ruw/` |
| 2 | `prep/` | Omzetten naar 16 kHz mono + `.lab` met de verwachte zin | `werk/corpus/<spreker>/` |
| 3 | `whisper/` | KB-Whisper tiny, base, small | `resultaten/whisper.csv` |
| 4 | `mfa/` | MFA align met `swedish_mfa`, gewoon en met `varianten.tsv` | TextGrids, `mfa_standaard.csv` |
| 5 | `klanken/` | Twee klankherkenners, vergeleken met de woordenboekuitspraak | `resultaten/klanken.csv` |
| 6 | `prosodie/` | Keuze-uitspraak, klinkerduur, toonhoogte (toppen) | `mfa_keuze.csv`, `prosodie_*.csv` |
| 7 | `verslag/` | Alles samen, met de criteria hieronder | `resultaten/verslag.md` |

**Keuze-uitspraak** (`proef/mfa/varianten.tsv`): het Zweedse MFA-woordenboek gebruikt hetzelfde
klankenstelsel als het model en markeert woordaccent 2 (`tanken` → `t̪ʰ a˧˩ ŋ k ɛ˥˩ n̪`). Per doelwoord
staan er een goede en een of meer foute uitspraken in (sj als *ɕ*, korte/lange *a*, harde *k*, accent 1/2).
MFA kiest de best passende. Zo wordt uitlijnen een oordeel per klank dat de app zelf kan geven. Of het
akoestische model het accentverschil hoort, is een van de vragen.

Al gezien bij het voorbereiden: `kb-whisper-tiny` verstaat de Piper-stem slecht (WER ±35% op deel C,
„sju” → „huvud”). Daarom gebruikt de testpagina standaard `small`. Het espeak-klankmodel kent geen *ɧ*
(sj-klank), het Zweedse klankmodel wel (als `sx`).

## Wanneer is de proef geslaagd?

Klein aantal opnames, dus indicatief. Per vraag:

- **Vraag 1 (wat)**: WER ≤ 10% op de goede opnames van deel C met een model dat in de browser past (tiny/base).
- **Vraag 2 (hoe)**: ≥ 8 van de 10 bewuste klankfouten (D01–D10) gevonden, en ≤ 1 op 10 goede opnames
  onterecht afgekeurd. Onterecht afkeuren is het ergste: dat frustreert en ondermijnt „de app kijkt na”.
- **Vraag 3 (melodie)**: lang/kort-paren (B) en accentparen (A) in ≥ 80% juist onderscheiden.

Daarnaast: tijd per opname < 3 s, en welk deel offline in de browser kan.

## Wat er in de app zou kunnen (pas na de proef)

Afhankelijk van de uitkomst, van licht naar zwaar:

1. **Zeg de zin**: KB-Whisper tiny/base in de browser; de app vergelijkt de herkende tekst met de goede
   antwoorden (zoals nu bij typen). Kijkt *wat* na, niet *hoe*. Offline, geen server.
2. **Klankcontrole**: per woord een klankherkenner in de browser, vergelijken met de verwachte IPA; feedback
   in lagen („de *sj* in *sju* klonk als een Nederlandse sj”).
3. **Uitspraak op klankniveau met MFA**: alleen via een eigen server (de Cloudflare Worker kan geen MFA
   draaien). Dat is een nieuwe externe dienst en vraagt een besluit van de eigenaar.

## Opnemen

- **Bestand**: WAV (of m4a/mp3, ik zet het om), mono, liefst 16 kHz of hoger. Telefoon is goed.
- **Naam**: de id uit `testzinnen.tsv`, bv. `A01.wav`, `D03.wav`. Per opname één woord of zin.
- **Ruimte**: stil, geen echo; mond op ±20 cm van de microfoon; ±1 s stilte voor en na.
- **Tempo**: rustig en natuurlijk, zoals je het in de app zou zeggen.
- **Deel A–C**: zo goed als je kunt. **Deel D**: maak precies de beschreven fout, en alleen die.
- Is een „goede” opname volgens jezelf niet gelukt, noteer het (`opnames/notities.txt`): je bent geen
  moedertaalspreker, dus de Piper-opnames dienen als tweede ijkpunt.
- Zet de bestanden in `opnames/` in deze repo (of stuur ze, dan zet ik ze erin).
