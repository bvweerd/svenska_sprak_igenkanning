# Plan: productieversie uitspraaktrainer

Tool voor 2 gebruikers op een mini-pc thuis (Intel N6005, 4 kernen, zonder AVX2 en zonder GPU). Beveiliging is niet nodig. Spraak maken mag
lang duren, maar mag de processor niet overbelasten. De teksten komen van de A-site (`svenska_ovningar`,
A1–A2) en de B-site (`svenska_ovningar_b`, B1–B2).

**Stand (26-11-2026):** gebouwd op branch `dev` in `app/` (installatie: `app/README.md`). Fase 0 (meten op de
mini-pc) is op verzoek overgeslagen. Afwijkingen van dit plan: geen SQLite maar een `index.json` per gebruiker; de
woordtijden van het voorbeeld komen via de MFA-API (geen aparte MFA-batch); namen e.d. krijgen hun uitspraak van
MFA's G2P-model (`app/woordenboek`). Lokaal getest: import (232 teksten, 2334 stukken), analyse via de wachtrij
(±16–18 s op de laptop), mp4-opname via Caddy, twee gebruikers, herstel na een herstart. Niet getest: op de mini-pc
zelf en met een echte telefoon.

Daarna opgeruimd: de proef is uit de repo (git-tag `proef`); alles wat de trainer gebruikt staat in `app/`
(`common/`, `diensten/`), de oefenteksten in `app/teksten/` (in git), het verslag van de proef in `ONDERZOEK.md`.

## 1. Wat blijft en wat eruit gaat

**Blijft** (bewezen in de proef):
- Analyseketen: KB-Whisper small, de twee klankherkenners (xlsr300m-sv en xlsr53-espeak) en MFA.
- Coachlaag (`coach.py`): oordeel in woorden, tips, „Luister en vergelijk” met rood/oranje, eerdere opnames
  en patronen.
- Voorbeeldstem MMS met pauzes bij leestekens.
- De ijking wordt **bevroren** als vaste bestanden in de repo:
  - `score_ijking.json` (moedertaalsprekers en accent-anker). Die is algemeen, niet per zin, en geldt dus ook
    voor nieuwe teksten.
  - `klank_varianten.json`.

**Gaat eruit:**
- De batch en het verslag.
- FLEURS ophalen.
- Het espeak-accent-anker (alleen nodig om de ijking te maken).
- Prosodie, GOP, de testzinnen (C/F/G/T/D) en de Nederlandse controle.

**Opzet in de repo:** de productiecode komt in een nieuwe map `app/`. `proef/` blijft ongewijzigd als
onderzoeksarchief.

## 2. Teksten van de A- en B-site

**Bron:** `content/chapters/*.yaml` in beide repos, alleen gelezen. Het importscript
`app/import_teksten.py` maakt daaruit `data/teksten.json`.

**Wat we meenemen** (gemeten):

| soort | A | B |
|---|---|---|
| leestekst (hoofdtekst per hoofdstuk) | 12 | 18 |
| makkelijk lezen | 48 | 72 |
| luistertekst | 10 | 18 |
| **totaal** | **70 teksten, ±23k tekens** | **108 teksten, ±69k tekens** |

Samen zijn dat ongeveer 1650 zinnen.

- Hoofdstuk 0 (losse woorden) doet niet mee: losse woorden zijn geen goede training (zie de README).
- Ook: de voorbeeldzinnen bij de woordenschat (±1960 korte zinnen, met Nederlandse vertaling); elke zin een eigen oefenstuk.

**Sleutel en niveau:**
- Elke tekst krijgt een vaste sleutel van de vorm site–hoofdstuk–oefening-id, bijvoorbeeld
  `A-H01-makkelijk-2`. De sites veranderen hun id's nooit.
- Niveau op de B-site: uit `index.yaml`.
- Niveau op de A-site: H1–H6 is A1 en H7–H12 is A2 (volgens het PLAN.md van de A-site).

**Opschonen bij de import:**
- `**` en `*` weg.
- Bij dialogen: sprekersnamen („Olle: ”) en streepjes uit de te lezen tekst. De sprekersnamen blijven
  wel zichtbaar.
- **Cijfers worden woorden** (`num2words`, Zweeds), zowel voor de voorbeeldstem als voor wat Whisper
  verwacht. MMS kan geen cijfers lezen. Het gaat om 6 A-teksten en 22 B-teksten (jaartallen, leeftijden,
  prijzen).
- Woorden die niet in het MFA-woordenboek staan (vooral namen) krijgt de import als lijst. Hun uitspraak
  komt van het G2P-model van MFA (standaard). Wat fout gaat, komt in `extra_uitspraak.dict`.

**Opdelen in oefenstukken:**
- B-teksten zijn lang: een hoofdtekst is gemiddeld ±1700 tekens. Hoe langer de opname, hoe trager de
  analyse en hoe vager de feedback.
- Daarom wordt elke tekst opgedeeld per alinea. Alinea's langer dan ±400 tekens worden gesplitst in
  stukken van 2–4 zinnen.
- De gebruiker kiest een tekst en oefent die stuk voor stuk.

**Bijwerken:**
- De import opnieuw draaien maakt alleen gewijzigde stukken opnieuw (herkend aan een hash van de tekst).
- Een opname bewaart de tekst waarop hij gemaakt is. Zo blijven oude analyses kloppen.

**Licentie:** de teksten zijn CC BY-NC-SA 4.0. Thuisgebruik is niet-commercieel, dus dat mag.

## 3. Voorbeeldstem maken (achtergrondtaak, licht)

**Gemeten op 1 processorkern:** MMS doet ±25 tekens per seconde (0,55× realtime).

| stap | tijd voor alle A+B-teksten |
|---|---|
| inspreken (92k tekens) | ±1 uur |
| MFA-woordtijden voor „Luister en vergelijk” (±500 stukken, ±5–7 s per stuk) | ±1 uur |
| **totaal, eenmalig** | **±2 uur** |

Daarna worden alleen nieuwe of gewijzigde stukken gemaakt.

**Zo blijft de processor vrij:**
- De taak draait in een eigen container met `cpus: 1`, 1 thread en `nice 19`.
- Hij gaat altijd voor op de analyses (zie 4): staat er een opname in de wachtrij, dan pauzeert de taak
  na het huidige stuk.

**Resultaat:** per stuk een wav en een JSON met woordtijden in `data/voorbeeld/`. Ontbreekt het voorbeeld
nog, dan toont de pagina „voorbeeld wordt nog gemaakt” en werkt de rest gewoon.

**Bekende beperkingen:**
- MMS zegt sommige leenwoorden, afkortingen en namen verkeerd (*chef*, *tv*, *sms*, *Sverige*).
- Een vraag klinkt als een mededeling.
- Betere stemmen (Sten-TTS, Chatterbox) zijn zonder GPU te traag (zie de README).

## 4. Analyse op een lichte server

**Gemeten:**
- Op 16 kernen duurt een analyse 8 s (mediaan, max 34 s bij lange teksten).
- Op 2 kernen kost een opname van een L-tekst: Whisper 3,5 s, MFA 6 s, klankherkenners 62 s.
- Die 62 s komt deels doordat de klankherkenners nog `os.cpu_count()` threads starten, dus 16 threads op 2
  kernen.

**Maatregelen:**
- **Eén wachtrij, één analyse tegelijk.** Met 2 gebruikers is dat genoeg. De pagina toont
  „in de wachtrij” of „bezig” en haalt de uitslag op zodra die klaar is. Een opname gaat nooit verloren,
  ook niet als het lang duurt.
- **Threads gelijk aan de toegewezen kernen** (instelling `THREADS`), niet `os.cpu_count()`.
- **Whisper, MFA en de klankherkenners na elkaar**, niet tegelijk. Dan blijft de piek binnen de kernen.
- **Korte oefenstukken** (punt 2) houden de analysetijd beperkt.

**Verwachting op de mini-pc (N6005, zonder AVX2):** ±1–2 minuten per stuk. Dit is een schatting; fase 0
meet het. Valt het tegen, dan zijn er lichtere opties (zie „Fase 0”).

**Server:**
- De mini-pc: 4 kernen (N6005). De modellen gebruiken ±1,5 GB RAM in rust en ±3–4 GB tijdens een analyse.
- ±20 GB schijf: de images samen ±12 GB, plus opnames (±0,5 MB per stuk).
- Geen GPU.

## 5. Gebruikers en gegevens

- **Geen login.** Bovenaan kies je je naam (2 namen). De browser onthoudt die keuze.
- **Per gebruiker:** opnames, eerdere opnames, „Waar je aan kunt werken” en de voortgang per tekst
  (welke stukken gedaan, laatste oordeel).
- **Opslag:** bestanden zoals nu (`archief/`), plus een SQLite-bestand als index (gebruiker, stuk, tijd,
  oordeel, score).
- **Back-up:** de map `data/` kopiëren.

## 6. Pagina

- **Kiezen:** site (A/B), dan hoofdstuk, dan tekst, dan stuk, met het niveau erbij. Bij elke tekst zie je
  welke stukken al gedaan zijn.
- **Oefenen:** zoals de demo, met microfoonkeuze, oordeel, tips, „Luister en vergelijk”, eerdere opnames
  en patronen.
- **Vervalt:** de testzinnen, de status van de drie analyses en „Meer details” (de uitleg per woord staat
  nu bij „Luister en vergelijk”).

## 7. Uitrol

- **docker compose** met 5 services (plus Caddy):
  - `web` (pagina en wachtrij)
  - `worker` (analyses)
  - `whisper`
  - `klanken` (ook MMS)
  - `mfa`
- De modellen zitten in de images, dus er wordt niets gedownload bij het starten.
- Alle services krijgen `restart: unless-stopped` en een vaste `cpus`-grens.
- **HTTPS is nodig, ook thuis.** Browsers geven de microfoon alleen vrij op `https://` of `localhost`.
  Caddy met `tls internal` als zesde service; elk apparaat vertrouwt één keer het rootcertificaat van Caddy.

## 8. Fasen

| fase | wat | schatting |
|---|---|---|
| 0 | Meten op de mini-pc (zie „Fase 0”) | ½ dag |
| 1 | `app/` opzetten, ijking bevriezen, wachtrij en worker, threads instelbaar | 1–2 dagen |
| 2 | Import A+B, opdelen, cijfers naar woorden, woordenlijst namen, voorbeeldtaak | 1–2 dagen |
| 3 | Pagina: tekstkeuze, gebruikers, voortgang | 1–2 dagen |
| 4 | Uitrol op de server, HTTPS, testen met beide gebruikers | ½–1 dag |

## Besloten

- **Server:** een mini-pc thuis met een Intel Pentium Silver N6005: 4 kernen, max 3,3 GHz, zonder AVX/AVX2
  en zonder GPU.
  - Zonder AVX2 zijn PyTorch, CTranslate2 (faster-whisper, int8) en de rekenbibliotheek van MFA flink
    trager. Schatting: analyse ±1–2 minuten per stuk, voorbeeldstem 5–10× trager dan op de laptop (alle
    teksten: uren tot een dag, eenmalig).
  - Daarom komt er eerst **fase 0** (zie onder).
- **Licentie:** thuisgebruik is niet-commercieel, dus MMS (CC BY-NC 4.0) en de teksten (CC BY-NC-SA 4.0)
  mogen.
- **HTTPS:** Caddy met een eigen certificaat (`tls internal`).

## Fase 0: meten op de mini-pc (vóór fase 1, ±½ dag)

1. Kopieer de bestaande images naar de mini-pc (`docker save` / `docker load`; x86-64 past).
2. Check dat alles draait zonder AVX, vooral faster-whisper met int8.
3. Meet de tijd van één analyse (een L-tekst en een kort stuk) en van één voorbeeldzin.
4. Valt de analyse te traag uit, dan zijn dit de lichtere opties, in deze volgorde:
   - kortere oefenstukken;
   - Whisper base in plaats van small;
   - het tweede klankmodel eruit (dan opnieuw ijken).

## Ook besloten

- **Geheugen:** 15 GB, waarvan ±8,6 GB beschikbaar. De swap (4 GB) is al helemaal vol: de mini-pc draait
  ook andere dingen (Home Assistant).
  - Daarom krijgt elke container een vaste geheugengrens (`mem_limit`), samen ±5 GB. Zo duwt een analyse
    de rest niet de swap in.
  - Modellen blijven geladen (geen opstarttijd per analyse), maar niet meer dan die grens.
- **Schijf:** 228 GB vrij, ruim genoeg.
- **Alleen het thuisnetwerk.** Niet van buitenaf bereikbaar; geen port forwarding.
- **Geen back-up.**
- **Apparaten:** laptop, tablet en telefoon.
  - Elk apparaat vertrouwt één keer het rootcertificaat van Caddy. De pagina `/certificaat` geeft het bestand
    met korte uitleg per systeem (iOS/iPadOS: profiel installeren én aanzetten bij Instellingen → Algemeen →
    Info → Certificaatvertrouwen; Android: Instellingen → Beveiliging → Certificaat installeren).
  - De mini-pc heeft een vast adres nodig (vast IP-adres in de router) of een naam (`server.local`). Het
    certificaat geldt voor die naam en dat adres.
  - De pagina moet op een telefoonscherm werken (smalle kolom, grote knoppen).
  - Safari op iPhone/iPad neemt op als mp4/aac, niet als webm. De omzetting (`zet_om`, ffmpeg) moet dat aan;
    testen in fase 3.
- **Voorbeeldzinnen bij de woordenschat** gaan mee: ±1960 korte zinnen (±74k tekens), met Nederlandse
  vertaling. Elke zin is een eigen oefenstuk, gegroepeerd per hoofdstuk. Samen met de teksten is dat
  ±166k tekens voor de voorbeeldstem: op de mini-pc naar schatting één tot twee dagen op 1 kern, eenmalig.
- **Dialogen** worden in hun geheel voorgelezen; de sprekersnamen staan erbij maar worden niet uitgesproken
  of verwacht.

## Nog open

Niets meer. Fase 0 (meten op de mini-pc) bepaalt of de analyse snel genoeg is of lichter moet.
