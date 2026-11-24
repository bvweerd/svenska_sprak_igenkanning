FROM python:3.11-slim
WORKDIR /app
COPY common/proef_common.py extern/extern.py mfa/varianten.tsv ./
ENTRYPOINT ["python", "extern.py"]
