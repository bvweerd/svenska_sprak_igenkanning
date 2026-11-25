FROM python:3.11-slim
# espeak-ng: de Zweedse zinnen ook met Nederlandse uitspraakregels voorlezen (accent-ankerpunt voor de score).
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir piper-tts==1.8.0
# Stem downloaden bij het bouwen, zodat de proef daarna offline draait.
ADD --chmod=755 https://huggingface.co/rhasspy/piper-voices/resolve/main/sv/sv_SE/nst/medium/sv_SE-nst-medium.onnx /stemmen/
ADD --chmod=755 https://huggingface.co/rhasspy/piper-voices/resolve/main/sv/sv_SE/nst/medium/sv_SE-nst-medium.onnx.json /stemmen/
WORKDIR /app
COPY common/proef_common.py piper/synth.py ./
CMD ["python", "synth.py"]
