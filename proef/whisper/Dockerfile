FROM python:3.11-slim
RUN pip install --no-cache-dir faster-whisper==1.2.1 "av<16" huggingface_hub
# Welke maten in het image komen (medium/large kan ook, maar is groot en traag op de CPU).
ARG WHISPER_MODELLEN="tiny base small"
ENV WHISPER_MODELLEN=${WHISPER_MODELLEN}
WORKDIR /app
COPY whisper/download.py ./
RUN python download.py ${WHISPER_MODELLEN}
# Getallen die Whisper in cijfers schrijft, in woorden vergelijken (productieversie: teksten met getallen).
RUN pip install --no-cache-dir num2words==0.5.14
COPY common/proef_common.py whisper/transcribe.py ./
ENV HF_HOME=/tmp/hf HF_HUB_OFFLINE=1
CMD ["python", "transcribe.py"]
