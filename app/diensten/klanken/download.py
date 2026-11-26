"""Bij het bouwen: de twee klankherkenners en de voorbeeldstem (MMS-TTS Zweeds) ophalen."""
from huggingface_hub import snapshot_download

for repo in ["facebook/wav2vec2-xlsr-53-espeak-cv-ft",
             "patrickvonplaten/wav2vec2-xls-r-phoneme-300m-sv"]:
    snapshot_download(repo, local_dir=f"/modellen/{repo.split('/')[1]}",
                      allow_patterns=["*.json", "pytorch_model.bin", "*.safetensors"])
    print("gedownload:", repo)

snapshot_download("facebook/mms-tts-swe", local_dir="/modellen/mms-tts-swe",
                  allow_patterns=["*.json", "*.safetensors", "vocab.json"])
print("gedownload: facebook/mms-tts-swe")
