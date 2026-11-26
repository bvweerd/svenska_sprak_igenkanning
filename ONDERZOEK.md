# Onderzoek: de proef achter de uitspraaktrainer

Dit is het verslag van de proef (november 2026) waaruit de uitspraaktrainer in [`app/`](app/README.md) is ontstaan:
welke modellen, hoe de score is opgebouwd en geijkt, waarom de tips zo werken, en wat niet werkte. De code van de
proef (batch, verslag, testpagina, testzinnen) is uit de repo gehaald en staat onder de git-tag **`proef`**:

```bash
git checkout proef        # of: git show proef:README.md
```

Paden en commando's hieronder verwijzen naar die versie.

---

Proef met lokale modellen (Docker) voor Zweedse spraakherkenning en uitspraakcontrole, met als doel op termijn
spreekopdrachten in de oefensite. `PLAN.md` beschrijft kandidaten, opzet en criteria; `testzinnen.tsv` wat er
ingesproken wordt: proefzinnen (C), zinnen op niveau A1 (F) en A2 (G), een korte leestekst (T: per zin en in
zijn geheel), 16 oefenteksten (L) en bewuste fouten (D). Losse woorden zijn er weer uit: zonder zin eromheen
zijn Whisper en de klankherkenner onbetrouwbaar (*sju* werd „Ja”, *sol* „Så”), dus geen goede training. Namen
die niet in het uitspraakwoordenboek staan (zoals Fleur, Bram, Wilma) gaan in `proef/common/extra_uitspraak.dict`.

De oefenteksten (L01–L16) zijn de eerste „makkelijk lezen”-tekst zonder cijfers uit hoofdstuk 1–16 van
[Svenska övningar](https://github.com/bvweerd/svenska_ovningar) (A1–A2) en
[Svenska övningar B](https://github.com/bvweerd/svenska_ovningar_b) (B1), onveranderd overgenomen;
licentie CC BY-NC-SA 4.0.

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
alleen langs de zinnen te gaan die je nog niet hebt ingesproken. Je krijgt (`proef/web/coach.py`):

- **Eén oordeel in woorden**: „Uitstekend”, „Goed — goed verstaanbaar, met een licht accent”, „Redelijk” of
  „Oefen deze zin nog eens”, met een rustige balk (de score op de schaal hieronder).
- **Tips** (twee bij een zin, drie of vier bij een langere tekst; meerdere anders verstane woorden samen in
  één tip, allemaal blauw onderstreept om na te luisteren), op volgorde van betrouwbaarheid: eerst wat Whisper anders verstond (betrouwbaar
  voor weggelaten woorden en woordvolgorde), dan een fout bij een doelwoord volgens MFA, dan pas een
  klanktip. Klanktips komen uit een vaste lijst typische fouten van Nederlandstaligen (v klinkt als f, å
  klinkt als a, sj- en tj-klank, Zweedse u en y, o als oe, rs-klank, een „eh” vóór het woord) met een
  concrete instructie in Nederlandse klanken, zonder IPA. Een fout die in je opnames vaker terugkomt, gaat voor.
- **Luister en vergelijk**: klik op een woord en je hoort eerst jezelf, dan de voorbeeldstem (MMS, zie
  „Voorbeeldstem”), geknipt op de woordtijden van MFA. Omdat die grenzen een paar honderdsten onzeker zijn
  („på” klonk als „enpoi”), schuift de pagina elke grens tot 30 ms naar buiten naar het stilste moment, met
  een korte fade. Alleen naar buiten: binnen een woord is de stilte vóór een p/t/k net zo stil. Losse woorden
  laten inspreken door MMS werkt niet: korte woorden (på, ut, och) komen er bijna stil uit, langere als gebrom.
  Rood = daar gaat een tip over (bevestigd door meerdere modellen), oranje = één bron hoorde een fout; klik
  voor de uitleg per woord. Ook de knop Voorbeeld speelt die stem.
- **Waar je aan kunt werken**: de klankfouten die over je laatste opname per zin het vaakst terugkomen (min.
  3 keer), want één klanktip zegt weinig en tien keer dezelfde fout wel.
- **Eerdere opnames** onder elke zin (datum, oordeel, score; „?” = gemaakt vóór de microfoonkeuze, „test” =
  testbestand). Klik erop om die analyse terug te kijken, met tips en luisteren per woord. Score, oordeel en
  tips van oude opnames worden met de huidige schaal en regels herberekend, zodat oud en nieuw vergelijkbaar
  zijn. Een analyse die destijds mislukte (bv. opgenomen terwijl de analyses opnieuw opstartten), wordt bij
  het openen alsnog gedaan. Een (bijna) stille opname krijgt „Niets gehoord” in plaats van een oordeel.
- Whisper-tips slaan namen over (Wilma → „Vilma” is spelling, geen uitspraak; een naam is elk woord dat
  ergens in de zinnen midden in een zin met een hoofdletter staat) en tellen cijfers als het getalwoord
  (8 = *åtta*).
- **Kruiscontrole**: Whisper is een taalmodel en raadt bij twijfel een waarschijnlijker woord (*sjön* →
  „kön”), ook als de klanken klopten. Een Whisper-tip gaat daarom alleen door als geen van beide
  klankherkenners het woord goed vond, en een klanktip vervalt als de espeak-herkenner de verwachte klank wél
  hoorde. Korte functiewoorden (*och*, *det*, *jag*, *är* …) krijgen geen klanktip: die worden in gewone spraak
  verkort. Gevolg: minder onterechte tips, maar ook een gemiste (de bewust harde sk in D10 krijgt geen tip).
- Onder **Meer details** (ingeklapt) de rest:
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

### Onderzocht: GOP met MFA (nog niet in gebruik)

GOP (*goodness of pronunciation*): per klank hoe goed de opname past bij de verwachte klank, vergeleken met de
best passende klank (per frame van 10 ms het verschil in log-likelihood, gemiddeld). MFA 3.4 heeft dit
ingebouwd (`get_phone_confidences`), maar het Zweedse model mist het bestand dat modeltoestanden aan klanken
koppelt, en MFA middelt over alle contextafhankelijke toestanden en telt toonvarianten (uː˧˩ / uː) als andere
klanken. `proef/mfa/gop_proef.py` rekent het zelf uit met MFA's features en model: per klank de beste toestand,
toon- en positievarianten samen. Gemeten op 42 opnames:

- **Als totaalscore onbruikbaar**: moedertaal vs Nederlands accent per opname AUC 0,66 (de huidige score: 0,98).
  GOP reageert sterk op microfoon en ruimte (de FLEURS-opnames scoren slechter dan de schone Piper-stem).
- **Per klank veelbelovend**, omdat GOP ook zegt wát er gehoord werd: de bewust harde sk in D10 gaf bij de
  sj-klank GOP 4,9 met „k” gehoord (bij de goede *skiner* in C08 niet opvallend), en de letterlijk
  uitgesproken *stjärnor* (D09) „t” in plaats van sj.

Daarna ingebouwd geprobeerd als snelle controle per opname (`proef/mfa/gop.py`, via kalpy zoals `mfa align_one`):
zonder sprekeradaptatie is het te onbetrouwbaar (bij moedertaalsprekers werd de sj-klank in 83% van de gevallen
niet als sj-achtig gehoord; je goede *skiner* in C08 klonk „k”). **Niet in gebruik**; het module blijft als
onderzoeksgereedschap.

### Voorbeeldstem

De voorbeelden (knop Voorbeeld en „Luister en vergelijk”) komen van **Meta MMS-TTS Zweeds**
(`facebook/mms-tts-swe`, CC BY-NC 4.0; stap `voorbeeld`, `proef/klanken/voorbeeldstem.py`). Eerst was dat Piper,
maar alle Piper-stemmen leerden Zweeds via espeak-klanksymbolen (die schrijven de sj-klank als „s”+„x”) en
zeggen juist de sj-klank vaak verkeerd. MMS kent geen leestekens (de tokenizer laat alleen letters en spaties
over) en las elke zin in één adem; daarom spreekt de stap elk zinsdeel apart in, knipt de stilte die MMS er zelf
omheen zet weg en zet de delen aan elkaar met 0,25 s pauze na een komma en 0,5 s na een punt. Stukjes van minder
dan 3 woorden gaan bij het stuk ernaast (MMS maakt van heel korte invoer bijna stilte). Een vraag klinkt nog
steeds als een mededeling. Losse woorden laten inspreken werkt om dezelfde reden niet.
MMS zegt ook sommige leenwoorden en afkortingen verkeerd (*chef*, *tv*, *sms*, *cv*, *Sverige*); een lijst met
aangepaste spellingen alleen voor de stem is bewust niet gemaakt (geen standaardconfiguratie meer).
Betere Zweedse stemmen (november 2026) zijn te zwaar zonder GPU: **Sten-TTS-1.7B** (Qwen3-TTS, Apache-2.0) deed
zo'n 45 s rekenen per seconde spraak (60 zinnen ≈ 11 uur), **Chatterbox Multilingual** (0,5B, MIT, met
watermerk) minuten per korte zin. Sten verstond Whisper wel foutloos op de drie zinnen die klaar kwamen. Met een
GPU de moeite van opnieuw proberen waard.
Gemeten met Whisper op 14 zinnen met 23 sj/tj-woorden:

| stem | sj/tj-woorden goed verstaan | WER |
|---|---|---|
| **MMS** | **20/23** | 0,10 |
| Piper sv_SE-lisa | 12/23 | 0,11 |
| Piper sv_SE-nst (eerst gebruikt) | 10/23 | 0,14 |
| Piper sv_SE-alma | 8/23 | 0,16 |

Ook MMS is een computerstem: hij is een betere, niet een volmaakte voorbeeldspreker. De opnames heten om
historische redenen nog `werk/piper_ruw` en spreker `piper`.

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
op `"tiny base small"` om maten te vergelijken), de voorbeeldstem en het accent-anker alleen voor nieuwe of gewijzigde
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
