# Svenska språkigenkänning (proef)

Proef met lokale modellen (Docker) voor Zweedse spraakherkenning en uitspraakcontrole, met als doel op termijn
spreekopdrachten in de oefensite. `PLAN.md` beschrijft kandidaten, opzet en criteria; `testzinnen.tsv` wat er
ingesproken wordt: losse woorden en proefzinnen (A–C), zinnen op niveau A1 (F) en A2 (G), een korte
leestekst (T: per zin en in zijn geheel), en bewuste fouten (D). Namen die niet in het uitspraakwoordenboek
staan (zoals Fleur) gaan in `proef/common/extra_uitspraak.dict`.

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
via het IP-adres). **Kies eerst bovenaan je microfoon** (druk op Test voor toestemming en een niveaumeter):
zonder keuze pakt de browser de standaard van Windows, vaak de laptopmicrofoon, en dan zijn de scores
onbruikbaar (zie „Opnamekwaliteit”). Kies een zin, druk op Opnemen, spreek, druk op Stop; daarna **Volgende zin ›**. Met het
toetsenbord: spatie = opnemen/stoppen, → en ← = volgende/vorige zin. Vink „sla opgenomen zinnen over” aan om
alleen langs de zinnen te gaan die je nog niet hebt ingesproken. Je krijgt:

- **Score**: waar je zit op de schaal Nederlands accent (0) → moedertaalspreker (100), met een niveau (zie hieronder).
- **Per woord**: de zin met elk woord groen (goed), oranje (let op) of rood (fout), en daaronder wat er
  mis was: welke klank anders klonk (bv. „sj-klank [ɧ] klonk als k”), welk woord Whisper anders verstond of
  waar het twijfelde, en of de uitspraakvariant van een doelwoord klopte. Afwijkingen van de woordenboek-
  uitspraak die moedertaalsprekers óók maken, tellen niet: de stap `klanken` leert die uit de FLEURS-
  fragmenten (`werk/klank_varianten.json`). Klinkers die alleen in lengte of openheid verschillen (e/ä, i/ɪ,
  o/å …) zijn hooguit oranje. Rood pas als het woord grotendeels anders klinkt (minstens twee echte
  afwijkingen), of als Whisper of MFA het afkeurt. Het verslag (deel 6) meet hoe vaak moedertaalsprekers
  onterecht oranje/rood krijgen.
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

### Score: hoe dicht zit je bij een moedertaalspreker?

Per opname een ruwe score van 0 tot 100: 50% klanken, 30% verstaan (Whisper: 1 − WER, met woordzekerheid)
en 20% juiste uitspraakvariant (MFA, alleen bij de doelwoorden). Klanken = per klankherkenner 1 − PER, gedeeld
door wat een moedertaalspreker bij dat model haalt; het Zweedse model weegt 75%, het espeak-model 25%.

Die ruwe score komt op een **schaal met twee ijkpunten**:

- **0** = dezelfde zinnen voorgelezen met Nederlandse uitspraakregels (espeak-ng `nl`, gemaakt in de stap
  `piper`): een duidelijk Nederlands accent;
- **100** = de mediaan van de **moedertaalsprekers** (FLEURS, zie hieronder).

Het **niveau**: „als een moedertaalspreker” vanaf het 25e percentiel van de moedertaalsprekers; daaronder
„licht accent” (schaal ≥ 50), „duidelijk accent” (> 0) of „sterk Nederlands accent”. Het verslag heeft een
vaste **accenttest**: het Nederlandse accent moet duidelijk lager scoren dan moedertaalsprekers (AUC ≥ 0,9) en
vrijwel nooit „als een moedertaalspreker” krijgen.

Waarom zo streng: een eerdere, mildere versie (beste van de twee klankherkenners) gaf een stem met duidelijk
Nederlands accent bij 1 op de 5 zinnen „binnen het bereik van moedertaalsprekers”. Het espeak-model hoort
nauwelijks accent (AUC 0,64), het Zweedse wel (0,96); en Whisper verstaat geaccentueerde spraak goed, dus
verstaanbaar ≠ Zweeds klinkend.

De moedertaalsprekers komen uit **FLEURS** (Google, CC BY 4.0): `alles.sh` haalt eenmalig 40 korte zinnen van
Hugging Face op (geen account nodig, ±190 MB downloaden, alleen de fragmenten blijven bewaard in
`opnames/extern/fleurs/`). De ijking staat daarna in `werk/score_ijking.json`; de testpagina gebruikt die
vanzelf. Zonder internet valt het terug op een voorlopige ijking met de computerstem. Let op: losse woorden
geven een grovere score dan zinnen, en de Zweden lezen andere zinnen dan jij; het is een indicatie.

**Opnamekwaliteit.** De klankherkenners zijn erg gevoelig voor de verhouding stem/ruis. De eerste opnames in
deze proef waren (onbedoeld) met de laptopmicrofoon gemaakt: ruis even luid als de stem, en dan scoort ook een
moedertaalspreker „sterk Nederlands accent” (getest: Zweedse fragmenten met die ruis erbij gaan van 27% naar
71% klankfouten; ruisfilters achteraf helpen niet). Dezelfde zin met de headset: score 0 → 100. Daarom:

- de testpagina laat je de microfoon kiezen, toont het niveau en bewaart per opname welke microfoon het was
  (`microfoon` in `werk/web/archief/*.json`);
- de pagina wacht 0,7 s voordat hij opneemt (een microfoon kan bij het aanzetten ploffen), en bij het omzetten
  (`zet_om` in `proef_common`) gaat een plof aan het begin eraf en brom onder 80 Hz altijd;
- blijft er veel brom over of is de opname erg zacht, dan meldt de pagina dat.

### Geleerd van een controle in het Nederlands (niet meer in de code)

Om te zien of microfoon en methode deugen, is dezelfde score tijdelijk ook in het Nederlands gebouwd (meertalig
Whisper small, het espeak-model met Nederlandse verwachte klanken, FLEURS `nl_nl` als moedertaalsprekers) en
door een Nederlandse moedertaalspreker ingesproken. Uitkomst en lessen:

- **Met de juiste microfoon klopt de score**: 10 van de 10 zinnen „als een moedertaalspreker” (gemiddeld 99 op
  de schaal; Nederlandse moedertaalsprekers uit FLEURS gemiddeld 87).
- **Het oordeel per woord was te streng**: 55% van de woorden kreeg oranje/rood, bij een moedertaalspreker.
  Bijna allemaal normale variatie t.o.v. de woordenboek-uitspraak (g als [x], r als [ɾ], v als [f], ij als
  [aɪ]). Daarom leert de stap `klanken` nu uit moedertaalsprekers welke afwijkingen normaal zijn.

Omdat Zweeds het doel is, is de Nederlandse tak er daarna weer uitgehaald (scheelde een tweede Whisper-model,
een extra download en veel taalafhankelijke code). De opnames staan nog in `werk/nl_controle/`.

### Snelheid

Alles draait op de CPU. De batch analyseert **alleen nieuwe of gewijzigde opnames**: elke stap (prep, whisper,
mfa, klanken) houdt in `werk/cache/<stap>.json` per opname bij wat eruit kwam, op basis van de inhoud (wav,
tekst, model; bij MFA ook de woordenboekregels van de woorden). Gemeten met ±230 opnames: een volledige run
duurt ±24 minuten, een run zonder wijzigingen ±40 seconden.

- Verandert de code van een stap, dan vervalt diens cache vanzelf (de versie is een hash van het script). Wie
  gedeelde logica in `proef_common` verandert (bv. `zet_om`), verhoogt `ANALYSE_VERSIE`.
- Alles opnieuw: `rm -r werk/cache`. Alleen MFA opnieuw: `rm werk/cache/mfa.json`.
- MFA past het akoestisch model per spreker aan op de opnames in de run; bij een gedeeltelijke run gebeurt dat
  op minder opnames, dus een uitlijning kan iets anders uitvallen dan bij een volledige run.

Verder: Whisper alleen in maat `small` (die gebruikt de score; zet `WHISPER_MODELLEN` in `docker-compose.yml`
op `"tiny base small"` om maten te vergelijken), Piper en het accent-anker alleen voor nieuwe of gewijzigde
zinnen (`_teksten.json` in `werk/piper_ruw` en `werk/anker_ruw`), en FLEURS maar één keer ophalen.

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

Getest met Docker Desktop op Windows (november 2026): alle images bouwen; de testpagina met alle drie de
analyses (Whisper, klankherkenner, MFA) en de score; de hele batch (`alles.sh`) inclusief het automatisch
ophalen van FLEURS, met Piper-opnames en echte opnames via de pagina (headset), plus de Nederlandse controle
hierboven. **Nog niet gedaan**: een volledige set eigen Zweedse opnames met de headset (alle zinnen, ook de
foutvarianten D); de opnames van vóór de microfoonkeuze zijn met de laptopmicrofoon gemaakt en tellen niet.
`extern commonvoice` en `extern lingualibre` zijn niet opnieuw getest (de score heeft ze niet nodig).
