FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng \
    && rm -rf /var/lib/apt/lists/*
# CPU-versie van PyTorch (veel kleiner dan de CUDA-versie).
RUN pip install --no-cache-dir torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir "transformers>=4.46,<5" soundfile numpy huggingface_hub phonemizer
WORKDIR /app
COPY diensten/klanken/download.py ./
RUN python download.py
ADD --chmod=755 https://raw.githubusercontent.com/MontrealCorpusTools/mfa-models/main/dictionary/swedish/mfa/swedish_mfa.dict /modellen/
# Zelfde aanvulling als in het MFA-image (namen e.d.).
COPY common/extra_uitspraak.dict /tmp/
RUN cat /tmp/extra_uitspraak.dict >> /modellen/swedish_mfa.dict
# Dit image draait twee services: klanken-api (klanken_api.py) en de voorbeeldstem (maak.py, achtergrondtaak).
COPY common/gedeeld.py diensten/klanken/klanken_api.py diensten/klanken/voorbeeldstem.py voorbeeld/maak.py ./
ENV HF_HOME=/tmp/hf HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
CMD ["python", "klanken_api.py"]
