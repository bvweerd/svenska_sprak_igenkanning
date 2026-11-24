FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY common/proef_common.py web/server.py web/index.html mfa/varianten.tsv ./
EXPOSE 8080
CMD ["python", "server.py"]
