FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng \
    && rm -rf /var/lib/apt/lists/*
# CPU-versie van PyTorch (veel kleiner dan de CUDA-versie).
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir "transformers>=4.46,<5" soundfile numpy huggingface_hub phonemizer
WORKDIR /app
COPY klanken/download.py ./
RUN python download.py
ADD https://raw.githubusercontent.com/MontrealCorpusTools/mfa-models/main/dictionary/swedish/mfa/swedish_mfa.dict /modellen/
COPY common/proef_common.py klanken/klanken.py ./
ENV HF_HOME=/tmp/hf HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
CMD ["python", "klanken.py"]
