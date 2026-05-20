FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (torch/torchaudio ja estao na imagem base)
COPY requirements.txt .

# Grupo 1: ML core
RUN pip install --no-cache-dir \
    "faster-whisper>=1.0.0" \
    "transformers>=4.50.0" \
    "sentencepiece>=0.2.0" \
    "sacremoses>=0.1.0"

# Grupo 2: Audio separation
RUN pip install --no-cache-dir \
    "demucs>=4.0.0"

# Grupo 3: TTS
RUN pip install --no-cache-dir \
    "coqui-tts>=0.27.0" \
    "edge-tts>=6.0.0"

# Grupo 4: Web UI
RUN pip install --no-cache-dir \
    "gradio>=5.0.0" \
    "flask>=2.0.0" \
    "flask-cors>=3.0.0" \
    "waitress>=2.1.0"

# Grupo 5: Utilities
RUN pip install --no-cache-dir \
    "soundfile>=0.12.0" \
    "numpy>=1.24.0" \
    "audiostretchy>=1.2.0" \
    "psutil>=5.9.0" \
    "pysubs2>=1.7.0"

# Copy project
COPY . .

# Environment
ENV COQUI_TOS_AGREED=1
ENV HF_HUB_DISABLE_SYMLINKS=1
ENV PYTHONUNBUFFERED=1

# Persistent volumes
VOLUME ["/app/data"]

EXPOSE 5000

# Pre-download models on build, then start server
CMD ["python", "server.py"]