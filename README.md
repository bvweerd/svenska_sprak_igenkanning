# Svenska språkigenkänning (proef)

Proef met lokale modellen (Docker) voor Zweedse spraakherkenning en uitspraakcontrole, met als doel op termijn
spreekopdrachten in de oefensite. `PLAN.md` beschrijft kandidaten, opzet en criteria; `testzinnen.tsv` wat er
ingesproken wordt.

## Op de pc

Nodig: Docker (Docker Desktop op Windows/macOS), ±15 GB schijf, 8 GB geheugen of meer. Bouwen duurt de eerste
keer lang (MFA via conda, PyTorch, modellen); daarna werkt alles offline.

```bash
git clone https://github.com/bvweerd/svenska_sprak_igenkanning.git
```

```bash
cd svenska_sprak_igenkanning && mkdir -p opnames werk resultaten && chmod a+rwx opnames werk resultaten
```

### Testpagina: opnemen en direct feedback

```bash
docker compose up --build
```

Open http://localhost:8080 (de microfoon werkt alleen via `localhost` of https, dus niet vanaf een telefoon
via het IP-adres). Kies een zin, druk op Opnemen, spreek, druk op Stop. Je krijgt:

- **Verstaan** (KB-Whisper small): wat het model hoorde, en welke woorden afweken.
- **Uitspraak** (MFA keuze-uitspraak): per doelwoord of de goede of een foute uitspraak het best past.
- **Info**: wat de klankherkenner hoorde, aantal toppen in de toonhoogte, klinkerduur.

Elke opname wordt opgeslagen als `opnames/<id>.<ext>` (de laatste per zin), met alle versies en de
analyse in `werk/web/archief/`. De eerste analyse na het starten duurt langer (modellen laden).

### Batch: alle opnames, met verslag

```bash
./proef/alles.sh
```

Of stap voor stap (zie de kop van `docker-compose.yml`), bv. `docker compose run --rm whisper`. Uitkomst:
CSV's en `resultaten/verslag.md`. Opnames kunnen ook als losse bestanden in `opnames/` (WAV, m4a, mp3, webm…,
naam = id, bv. `A01.m4a`); een tweede spreker in `opnames/<naam>/`.

### Moedertaalsprekers: wordt een Zweed onterecht afgekeurd?

Fragmenten van echte Zweden komen in `opnames/extern/<bron>/` (audio + `.txt` met de tekst) en lopen
daarna gewoon mee in de batch; het verslag krijgt een deel „Moedertaalsprekers”. Het script kiest
fragmenten met de doelwoorden uit `proef/mfa/varianten.tsv` (één fragment per spreker, vaste seed) en
schrijft herkomst en licentie in `_bronnen.tsv`. Downloads pak je uit in `bronnen/` (niet in git).

**Common Voice** (CC0, de hoofdbron): maak een gratis account op Mozilla Data Collective, download
„Common Voice Scripted Speech – Swedish” en pak het uit in `bronnen/commonvoice/`.

```bash
docker compose run --rm extern commonvoice /bronnen/commonvoice --per-woord 5
```

Het MFA-model is deels op oudere Common Voice getraind. Heb je ook een oude release (bv. v8), dan sluit
`--uitsluiten /bronnen/cv8/sv-SE/validated.tsv` die fragmenten uit.

**Lingua Libre / Wikimedia Commons** (losse woorden, licentie per bestand, meestal CC BY-SA): weinig
materiaal; bij het voorbereiden gevonden: *sju* en *tack*.

```bash
docker compose run --rm extern lingualibre
```

**Andere sets** (FLEURS `sv_se`, NST, eigen materiaal): alles met een tabel pad/tekst. FLEURS bijvoorbeeld:

```bash
docker compose run --rm extern tsv /bronnen/fleurs/sv_se/test.tsv fleurs --geen-kop --pad-kolom 1 --tekst-kolom 2 --audiomap /bronnen/fleurs/sv_se/audio/test --licentie CC-BY-4.0
```

Woorden die niet in het MFA-woordenboek staan, krijgen een uitspraak van het Zweedse G2P-model.
Daarna `./proef/alles.sh --zonder-piper` (of de stappen vanaf `prep`).

## Mappen

| Map | Inhoud |
|---|---|
| `proef/common/` | gedeelde code (paden, normaliseren, foutpercentage, kleine API) |
| `proef/<stap>/` | Dockerfile en script per stap: `piper`, `prep`, `whisper`, `mfa`, `klanken`, `prosodie`, `verslag`, `web` |
| `proef/mfa/varianten.tsv` | goede en foute uitspraken per doelwoord (aanpassen en opnieuw bouwen) |
| `opnames/` | jouw opnames; `opnames/extern/` fragmenten van moedertaalsprekers |
| `bronnen/` | uitgepakte downloads (Common Voice, FLEURS …), niet in git |
| `werk/` | tussenbestanden (niet in git) |
| `resultaten/` | CSV's en verslag |

## Wat al getest is en wat niet

Zonder Docker getest in een Python-omgeving: `prep`, `piper`, `whisper` (met `kb-whisper-tiny`), de
webpagina met de Whisper-API (opnemen met een nagebootste microfoon, telefoonformaat, licht en donker), en
`prosodie` en `verslag` op nagemaakte TextGrids, en `extern commonvoice` met een nagemaakte
Common Voice-map. `extern lingualibre` vond de bestanden, maar Wikimedia weigerde het downloaden vanuit de
cloudomgeving (te veel verzoeken); op een gewone pc hoort dat te werken. **Niet getest**: de Docker-builds, MFA (`mfa/align.sh`,
`mfa/api.py`, G2P) en de klankherkenners (`klanken/`). Loopt daar iets mis bij het bouwen of draaien, stuur de
foutmelding.
