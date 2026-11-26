FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
# num2words: getallen die Whisper in cijfers schrijft, vergelijken met de getallen in woorden in de teksten.
RUN pip install --no-cache-dir num2words==0.5.14
WORKDIR /app
COPY common/gedeeld.py diensten/mfa/varianten.tsv web/server.py web/coach.py web/index.html ./
EXPOSE 8080
CMD ["python", "server.py"]
