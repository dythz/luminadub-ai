#!/bin/bash
# Run this INSIDE the RunPod container after it starts
# Pre-downloads all ML models so first dubbing is fast

echo "========================================="
echo "  LuminaDub AI - Download de Modelos"
echo "========================================="
echo ""

cd /app

# Set environment variables before loading ML libs
export COQUI_TOS_AGREED=1
export HF_HUB_DISABLE_SYMLINKS=1

python3 -c "
import os
os.environ['COQUI_TOS_AGREED'] = '1'
os.environ['HF_HUB_DISABLE_SYMLINKS'] = '1'

print('[1/4] Baixando Whisper large-v3...')
from faster_whisper import WhisperModel
WhisperModel('large-v3', device='cuda', compute_type='int8_float16')
print('  OK')

print('[2/4] Baixando Demucs htdemucs...')
from demucs.pretrained import get_model
get_model('htdemucs')
print('  OK')

print('[3/4] Baixando Opus-MT EN->PT...')
from transformers import MarianMTModel, MarianTokenizer
MarianTokenizer.from_pretrained('Helsinki-NLP/opus-mt-tc-big-en-pt')
MarianMTModel.from_pretrained('Helsinki-NLP/opus-mt-tc-big-en-pt')
print('  OK')

print('[4/4] Baixando XTTSv2...')
from TTS.api import TTS
TTS('tts_models/multilingual/multi-dataset/xtts_v2')
print('  OK')
"

echo ""
echo "========================================="
echo "  Todos os modelos baixados com sucesso"
echo "========================================="
