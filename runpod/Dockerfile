FROM runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    build-essential \
    python3-pip \
    libsndfile1 \
    libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip

WORKDIR /app

# Grupo 1: ML core
RUN pip install --no-cache-dir \
    "faster-whisper>=1.0.0" \
    "transformers>=4.50.0" \
    "sentencepiece>=0.2.0" \
    "sacremoses>=0.1.0"

# Grupo 2: Audio separation
RUN pip install --no-cache-dir "demucs>=4.0.0"

# Grupo 3: TTS
RUN pip install --no-cache-dir \
    "coqui-tts>=0.27.0" \
    "edge-tts>=6.0.0"

# Patch coqui-tts: corrige isin_mps_friendly removido no transformers>=4.46
RUN python3 -c "
import glob
for f in glob.glob('/usr/local/lib/python*/dist-packages/TTS/tts/layers/tortoise/autoregressive.py'):
    content = open(f).read()
    patched = content.replace(
        'from transformers.pytorch_utils import isin_mps_friendly as isin',
        'import torch; isin = torch.isin'
    )
    open(f, 'w').write(patched)
print('Tortoise patch OK')
"

# Grupo 4: Web UI
RUN pip install --no-cache-dir --ignore-installed \
    "blinker>=1.9.0" \
    "flask>=2.0.0" \
    "flask-cors>=3.0.0" \
    "waitress>=2.1.0" \
    "gunicorn>=21.0.0" \
    "gevent>=23.0.0"

# Grupo 5: Audio/video
RUN pip install --no-cache-dir torchcodec

# Grupo 6: Utilities
RUN pip install --no-cache-dir \
    "soundfile>=0.12.0" \
    "numpy>=1.24.0" \
    "audiostretchy>=1.2.0" \
    "psutil>=5.9.0" \
    "pysubs2>=1.7.0"

# Gradio opcional
RUN pip install --no-cache-dir "gradio==4.44.1" || echo "Gradio nao instalado"

COPY requirements.txt .
COPY . .

ENV COQUI_TOS_AGREED=1
ENV HF_HUB_DISABLE_SYMLINKS=1
ENV PYTHONUNBUFFERED=1

VOLUME ["/app/data"]
EXPOSE 5000
CMD ["python3", "server.py"]
