# Uitspraaktrainer Zweeds — productieversie

Thuis, voor twee gebruikers, op een lichte server (getest ontwerp voor een mini-pc met een Intel N6005: 4 kernen,
geen AVX2, geen GPU). Je leest teksten van de A-site (A1–A2) en de B-site (B1–B2) voor, neemt op in de browser
(laptop, tablet of telefoon) en krijgt een oordeel, tips en „Luister en vergelijk” met een Zweedse voorbeeldstem.
Het plan en de keuzes staan in [`../PLAN_PRODUCTIE.md`](../PLAN_PRODUCTIE.md); hoe de analyse werkt en waarom,
in [`../ONDERZOEK.md`](../ONDERZOEK.md).

## Onderdelen

| service | wat | grenzen |
|---|---|---|
| `caddy` | HTTPS met een eigen certificaat (nodig voor de microfoon) | 128 MB |
| `web` | pagina, opslag per gebruiker, **wachtrij: één analyse tegelijk** | 1 kern, 512 MB |
| `whisper-api` | wat zeg je? (KB-Whisper small) | `ANALYSE_KERNEN`, 1,5 GB |
| `klanken-api` | welke klanken? (twee wav2vec2-klankherkenners) | `ANALYSE_KERNEN`, 3 GB |
| `mfa-api` | woordgrenzen en uitspraakvariant (Montreal Forced Aligner) | `ANALYSE_KERNEN`, 2 GB |
| `voorbeeld` | voorbeeldstem (MMS-TTS) voor alle stukken, op de achtergrond | 1 kern, nice 19, 1,5 GB |
| `importeer` | teksten van de sites → `teksten/teksten.json` (alleen bij bijwerken) | |
| `woordenboek` | uitspraak van namen e.d. met MFA's G2P → `teksten/woordenboek_extra.dict` (alleen bij bijwerken) | |

De drie analyses lopen **na elkaar** (niet tegelijk), met hoogstens `ANALYSE_KERNEN` threads; zo blijft er een kern
vrij voor de rest van de server. De voorbeeldtaak wacht zolang er een opname in de wachtrij staat. De ijking van de
score (moedertaalsprekers = 100, Nederlands accent = 0) is uit de proef overgenomen en bevroren in `ijking/`.

De code: `web/` (pagina en server), `common/gedeeld.py` (score, oordeel per woord, audio), `diensten/` (de drie
modelservices), `voorbeeld/` (voorbeeldstem), `importeer/` en `woordenboek/` (bijwerken), `teksten/` (de
oefenteksten), `ijking/`, `caddy/`.

## Installeren

De oefenteksten staan al in git (`teksten/`), dus op de server (Linux met Docker en de compose-plugin) is alleen
deze repo nodig:

```bash
git clone -b dev <deze repo> svenska_sprak_igenkanning
cd svenska_sprak_igenkanning/app
cp .env.voorbeeld .env        # gebruikers, adres van de server, poort
mkdir -p data/caddy data/caddy-config && sudo chown -R 1000:1000 data   # alles draait als uid 1000
docker compose build          # eenmalig ±20–40 min; downloadt de modellen (±10 GB aan images)
docker compose up -d
```

Geef de server een **vast IP-adres** in de router (of gebruik een naam als `server.local`) en zet precies die
adressen in `SITE_ADRESSEN`: het certificaat geldt alleen daarvoor. Alleen via het thuisnetwerk; zet geen poort open
in de router.

Daarna op elk apparaat:
1. Open `https://<server>:8443/certificaat` (de browser waarschuwt eenmalig: doorgaan), download het certificaat en
   volg de stappen voor dat apparaat (iPhone/iPad: profiel installeren én aanzetten bij Certificaatvertrouwen).
2. Open `https://<server>:8443` en kies bovenaan wie je bent.

## Bijwerken

Nieuwe of gewijzigde teksten op de sites: draai de import waar de A- en B-site naast deze repo staan (bv. op je
laptop; paden in `.env`: `BRON_A`, `BRON_B`), en commit het resultaat:

```bash
docker compose --profile bijwerken run --rm importeer      # → teksten/teksten.json
docker compose --profile bijwerken run --rm woordenboek    # → teksten/woordenboek_extra.dict
git add teksten && git commit -m "Update practice texts" && git push
```

Op de server daarna alleen `git pull`. De pagina en de voorbeeldtaak lezen de nieuwe teksten vanzelf; de voorbeeldstem maakt alleen nieuwe of gewijzigde
stukken opnieuw en ruimt voorbeelden van verdwenen stukken op. Oude opnames houden de tekst waarop ze gemaakt zijn.

Nieuwe code: `git pull && docker compose build && docker compose up -d`.

## Hoe lang duurt het?

- **Voorbeeldstem**: lokaal (laptop, 1 kern) ±12–18 s per stuk incl. woordtijden; op de N6005 naar schatting
  ±1 minuut. De ±2300 stukken zijn dan in **ongeveer twee dagen** klaar, A-site eerst, woordenschat als laatste. Tot
  een stuk klaar is, speelt Voorbeeld de stem van de browser. De voortgang staat bovenaan de pagina.
- **Analyse** van een opname: lokaal ±18 s; op de N6005 naar schatting 1–2 minuten (niet gemeten). Je hoeft niet te
  wachten: neem gerust het volgende stuk op; de uitslag verschijnt bij „Eerdere opnames”.
- Valt de analyse te traag uit: `ANALYSE_KERNEN=4` (dan deelt hij met de rest van de server), of kortere oefenstukken
  (`STUK_MAX` in `importeer/importeer.py`).

## Gegevens

De oefenteksten en de uitspraak van namen staan in `teksten/` (in git). Wat de trainer maakt, staat in `data/` (niet in git):

| | |
|---|---|
| `voorbeeld/<stuk>.wav` / `.json` | voorbeeldstem en de woordtijden daarvan |
| `opnames/<gebruiker>/` | per opname: origineel, `-16k.wav`, `.meta.json` (tekst, microfoon), `.json` (analyse); `index.json` |
| `caddy/` | certificaten (het rootcertificaat: `caddy/pki/authorities/local/root.crt`) |

Er is geen back-up ingesteld. Een opname die nog niet geanalyseerd was (bv. na een herstart) gaat bij het starten
vanzelf weer in de wachtrij.

## Bekende beperkingen

- De voorbeeldstem (MMS) zegt sommige leenwoorden, afkortingen en namen verkeerd (*chef*, *tv*, *sms*) en een vraag
  klinkt als een mededeling; zie ONDERZOEK.md. Getallen staan in de teksten als woorden.
- Een opname van Safari (iPhone/iPad) is mp4; die wordt met ffmpeg omgezet. Nog niet op een echt toestel getest.
- Licenties: MMS-TTS (CC BY-NC 4.0) en de teksten (CC BY-NC-SA 4.0) alleen niet-commercieel — thuisgebruik.
