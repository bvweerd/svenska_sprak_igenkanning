FROM python:3.11-slim
RUN pip install --no-cache-dir praat-parselmouth==0.4.5 praatio==6.2.0 numpy
WORKDIR /app
COPY common/proef_common.py prosodie/analyse.py mfa/varianten.tsv ./
CMD ["python", "analyse.py"]
