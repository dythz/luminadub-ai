import os
os.environ["COQUI_TOS_AGREED"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

print("[PRELOAD] Baixando modelos...")

print("[PRELOAD] 1/3 Whisper large-v3...")
from faster_whisper import WhisperModel
WhisperModel("large-v3", device="cuda", compute_type="float16", download_root="/app/data/models/whisper")
print("[PRELOAD] Whisper ok")

print("[PRELOAD] 2/3 opus-mt...")
from transformers import MarianMTModel, MarianTokenizer
MarianTokenizer.from_pretrained("Helsinki-NLP/opus-mt-tc-big-en-pt", cache_dir="/app/data/models/opus")
MarianMTModel.from_pretrained("Helsinki-NLP/opus-mt-tc-big-en-pt", cache_dir="/app/data/models/opus")
print("[PRELOAD] opus-mt ok")

print("[PRELOAD] 3/3 XTTS v2...")
from TTS.api import TTS
TTS("tts_models/multilingual/multi-dataset/xtts_v2")
print("[PRELOAD] XTTS ok")

print("[PRELOAD] Todos os modelos prontos!")
