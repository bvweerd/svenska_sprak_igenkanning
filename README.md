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

## Mappen

| Map | Inhoud |
|---|---|
| `proef/common/` | gedeelde code (paden, normaliseren, foutpercentage, kleine API) |
| `proef/<stap>/` | Dockerfile en script per stap: `piper`, `prep`, `whisper`, `mfa`, `klanken`, `prosodie`, `verslag`, `web` |
| `proef/mfa/varianten.tsv` | goede en foute uitspraken per doelwoord (aanpassen en opnieuw bouwen) |
| `opnames/` | jouw opnames |
| `werk/` | tussenbestanden (niet in git) |
| `resultaten/` | CSV's en verslag |

## Wat al getest is en wat niet

Zonder Docker getest in een Python-omgeving: `prep`, `piper`, `whisper` (met `kb-whisper-tiny`), de
webpagina met de Whisper-API (opnemen met een nagebootste microfoon, telefoonformaat, licht en donker), en
`prosodie` en `verslag` op nagemaakte TextGrids. **Niet getest**: de Docker-builds, MFA (`mfa/align.sh`,
`mfa/api.py`) en de klankherkenners (`klanken/`). Loopt daar iets mis bij het bouwen of draaien, stuur de
foutmelding.
