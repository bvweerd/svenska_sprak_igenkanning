FROM python:3.11-slim
RUN pip install --no-cache-dir piper-tts==1.8.0
# Stem downloaden bij het bouwen, zodat de proef daarna offline draait.
ADD https://huggingface.co/rhasspy/piper-voices/resolve/main/sv/sv_SE/nst/medium/sv_SE-nst-medium.onnx /stemmen/
ADD https://huggingface.co/rhasspy/piper-voices/resolve/main/sv/sv_SE/nst/medium/sv_SE-nst-medium.onnx.json /stemmen/
WORKDIR /app
COPY common/proef_common.py piper/synth.py ./
CMD ["python", "synth.py"]
