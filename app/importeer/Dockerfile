FROM python:3.12-slim
RUN pip install --no-cache-dir pyyaml==6.0.2 num2words==0.5.14
WORKDIR /app
COPY importeer/importeer.py ./
CMD ["python", "importeer.py"]
