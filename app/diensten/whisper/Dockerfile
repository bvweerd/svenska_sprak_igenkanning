FROM python:3.11-slim
RUN pip install --no-cache-dir faster-whisper==1.2.1 "av<16" huggingface_hub
WORKDIR /app
COPY diensten/whisper/download.py ./
RUN python download.py small
# Getallen die Whisper in cijfers schrijft, in woorden vergelijken (de teksten schrijven getallen in woorden).
RUN pip install --no-cache-dir num2words==0.5.14
COPY common/gedeeld.py diensten/whisper/whisper_api.py ./
ENV HF_HOME=/tmp/hf HF_HUB_OFFLINE=1
CMD ["python", "whisper_api.py"]
