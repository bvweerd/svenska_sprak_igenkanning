# Montreal Forced Aligner 3.x met het Zweedse model en woordenboek (swedish_mfa, CC BY 4.0).
# MFA 3 gebruikt een PostgreSQL-server die niet als root mag draaien: daarom een eigen gebruiker.
FROM condaforge/miniforge3:latest
RUN conda create -y -p /env -c conda-forge montreal-forced-aligner=3.4.4 postgresql \
    && conda clean -afy \
    && /env/bin/pip install --no-cache-dir praat-parselmouth==0.4.5 praatio==6.2.0
ENV PATH=/env/bin:$PATH \
    MFA_ROOT_DIR=/mfa
RUN useradd -m -u 1000 mfa && mkdir -p /mfa /app && chown mfa:mfa /mfa /app
USER mfa
# Modellen bij het bouwen ophalen: daarna werkt de proef offline.
RUN mfa model download acoustic swedish_mfa \
    && mfa model download dictionary swedish_mfa \
    && mfa server init
WORKDIR /app
# api.py (webpagina) gebruikt dezelfde analyse als de batchstap 'prosodie'.
COPY --chown=mfa:mfa mfa/align.sh mfa/varianten.tsv mfa/api.py common/proef_common.py prosodie/analyse.py ./
CMD ["bash", "align.sh"]
