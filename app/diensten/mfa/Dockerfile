# Montreal Forced Aligner 3.x met het Zweedse model en woordenboek (swedish_mfa, CC BY 4.0).
# MFA 3 gebruikt een PostgreSQL-server die niet als root mag draaien: daarom een eigen gebruiker.
FROM condaforge/miniforge3:latest
RUN conda create -y -p /env -c conda-forge montreal-forced-aligner=3.4.4 python=3.11 postgresql \
    && conda clean -afy \
    && /env/bin/pip install --no-cache-dir praatio==6.2.0
ENV PATH=/env/bin:$PATH \
    MFA_ROOT_DIR=/mfa
# Het basisimage heeft al een gebruiker met uid 1000 (ubuntu): die eerst weghalen.
RUN (userdel -r "$(getent passwd 1000 | cut -d: -f1)" 2>/dev/null || true) \
    && useradd -m -u 1000 mfa && mkdir -p /mfa /app && chown mfa:mfa /mfa /app
USER mfa
# Modellen bij het bouwen ophalen: daarna werkt alles offline. Rechtstreeks uit de GitHub-releases
# (niet via 'mfa model download': die gebruikt de GitHub-API, die anoniem maar 60 verzoeken per uur toestaat).
ARG MFA_MODELS=https://github.com/MontrealCorpusTools/mfa-models/releases/download
ADD --chown=mfa:mfa ${MFA_MODELS}/acoustic-swedish_mfa-v2.0.0a/swedish_mfa.zip /mfa/pretrained_models/acoustic/
ADD --chown=mfa:mfa ${MFA_MODELS}/dictionary-swedish_mfa-v2.0.0a/swedish_mfa.dict /mfa/pretrained_models/dictionary/
ADD --chown=mfa:mfa ${MFA_MODELS}/g2p-swedish_mfa-v2.0.0a/swedish_mfa.zip /mfa/pretrained_models/g2p/
# Woorden die niet in het woordenboek staan (bv. namen uit de teksten): aanvullen.
COPY common/extra_uitspraak.dict /tmp/
RUN cat /tmp/extra_uitspraak.dict >> /mfa/pretrained_models/dictionary/swedish_mfa.dict \
    && mfa model inspect acoustic swedish_mfa > /dev/null && mfa server init
WORKDIR /app
# mfa_api.py: uitlijning per opname (interne API); woordenboek.py: uitspraak van namen e.d. (bij bijwerken).
COPY --chown=mfa:mfa diensten/mfa/varianten.tsv diensten/mfa/mfa_api.py diensten/mfa/uitlijning.py common/gedeeld.py ./
COPY --chown=mfa:mfa woordenboek/maak.py ./woordenboek.py
CMD ["python", "mfa_api.py"]
