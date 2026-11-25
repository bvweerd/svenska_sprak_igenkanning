FROM python:3.11-slim
# Uitspraakwoordenboek: FLEURS-zinnen alleen kiezen als alle woorden erin staan (anders telt de
# klankherkenner bij een Zweed onterecht fouten, omdat de verwachte klanken van dat woord ontbreken).
ADD --chmod=755 https://raw.githubusercontent.com/MontrealCorpusTools/mfa-models/main/dictionary/swedish/mfa/swedish_mfa.dict /modellen/
COPY common/extra_uitspraak.dict /tmp/
RUN cat /tmp/extra_uitspraak.dict >> /modellen/swedish_mfa.dict
WORKDIR /app
COPY common/proef_common.py extern/extern.py mfa/varianten.tsv ./
ENTRYPOINT ["python", "extern.py"]
