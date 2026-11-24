"""Bij het bouwen: KB-Whisper-modellen (CTranslate2-formaat, model.bin) ophalen."""
import os
import sys

from huggingface_hub import snapshot_download

for maat in sys.argv[1:]:
    snapshot_download(f"KBLab/kb-whisper-{maat}", local_dir=f"/modellen/kb-whisper-{maat}",
                      allow_patterns=["model.bin", "config.json", "tokenizer.json",
                                      "vocabulary.json", "vocabulary.txt", "preprocessor_config.json",
                                      "added_tokens.json", "merges.txt", "vocab.json",
                                      "normalizer.json", "special_tokens_map.json",
                                      "tokenizer_config.json", "generation_config.json"])
    print("gedownload:", maat, os.listdir(f"/modellen/kb-whisper-{maat}"))
