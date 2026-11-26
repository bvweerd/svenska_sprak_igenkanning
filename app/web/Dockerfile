FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
# num2words: getallen die Whisper in cijfers schrijft, vergelijken met de getallen in woorden in de teksten.
RUN pip install --no-cache-dir num2words==0.5.14
WORKDIR /app
COPY proef/common/proef_common.py proef/mfa/varianten.tsv app/web/server.py app/web/coach.py app/web/index.html ./
EXPOSE 8080
CMD ["python", "server.py"]
