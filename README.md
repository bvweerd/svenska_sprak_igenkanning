# Uitspraaktrainer Zweeds

Zweedse teksten voorlezen en feedback krijgen op je uitspraak: een oordeel in woorden, een paar gerichte tips
(in Nederlandse klanken, zonder IPA) en „Luister en vergelijk”, waar je per woord jezelf en een Zweedse
voorbeeldstem na elkaar hoort. De teksten komen van de oefensites *Svenska övningar* (A1–A2) en
*Svenska övningar B* (B1–B2). Alles draait lokaal (Docker), zonder externe diensten, op een lichte server thuis.

- **Installeren en gebruiken:** [`app/README.md`](app/README.md)
- **Plan en keuzes:** [`PLAN_PRODUCTIE.md`](PLAN_PRODUCTIE.md)
- **Waarom het zo werkt** (modellen, score, ijking, tips, wat niet werkte): [`ONDERZOEK.md`](ONDERZOEK.md); de code
  van die proef staat onder de git-tag `proef`.

## Hoe het werkt

| stap | model | |
|---|---|---|
| wat zeg je? | KB-Whisper small (KBLab) | woorden die anders verstaan worden |
| hoe zeg je het? | twee wav2vec2-klankherkenners | welke klanken afwijken, vergeleken met wat moedertaalsprekers ook doen |
| waar staat elk woord? | Montreal Forced Aligner | woordgrenzen (luisteren) en de uitspraakvariant bij woorden als *sju*, *kök* |
| voorbeeld | MMS-TTS Zweeds | voorgelezen met pauzes bij leestekens |

De score zet de opname op een schaal van Nederlands accent (0) tot moedertaalspreker (100); die ijking is in de
proef gemaakt en hier bevroren (`app/ijking/`).
