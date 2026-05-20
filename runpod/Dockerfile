FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    build-essential \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Garantir pip atualizado e sem restricoes Ubuntu 24.04
RUN python3 -m pip install --upgrade pip --break-system-packages 2>/dev/null || \
    pip install --upgrade pip

WORKDIR /app

# Definir pip helper que funciona em qualquer ambiente
ENV PIP="python3 -m pip install --no-cache-dir --break-system-packages"

# Grupo 1: ML core
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    "faster-whisper>=1.0.0" \
    "transformers>=4.50.0" \
    "sentencepiece>=0.2.0" \
    "sacremoses>=0.1.0"

# Grupo 2: Audio separation
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    "demucs>=4.0.0"

# Grupo 3: TTS
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    "coqui-tts>=0.27.0" \
    "edge-tts>=6.0.0"

# Patch coqui-tts: corrige incompatibilidade com transformers>=4.46 (isin_mps_friendly removido)
# Usa leitura antes da escrita para evitar esvaziar o arquivo acidentalmente
RUN python3 -c "import glob; [open(f,'w').write(c) for f in glob.glob('/usr/local/lib/python*/dist-packages/TTS/tts/layers/tortoise/autoregressive.py') for c in [open(f).read().replace('from transformers.pytorch_utils import isin_mps_friendly as isin','import torch; isin = torch.isin')]]; print('Tortoise patch OK')"

# Grupo 4: Web UI (--ignore-installed por causa do blinker instalado pelo apt)
RUN pip install --no-cache-dir --ignore-installed \
    "blinker>=1.9.0" \
    "flask>=2.0.0" \
    "flask-cors>=3.0.0" \
    "waitress>=2.1.0" \
    "gunicorn>=21.0.0" \
    "gevent>=23.0.0"

# Gradio opcional
RUN python3 -m pip install --no-cache-dir --break-system-packages "gradio==4.44.1" || \
    echo "Gradio nao instalado, usando Flask UI"

# Grupo 5: Utilities
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    "soundfile>=0.12.0" \
    "numpy>=1.24.0" \
    "audiostretchy>=1.2.0" \
    "psutil>=5.9.0" \
    "pysubs2>=1.7.0"

# Copy project
COPY requirements.txt .
COPY . .

# Environment
ENV COQUI_TOS_AGREED=1
ENV HF_HUB_DISABLE_SYMLINKS=1
ENV PYTHONUNBUFFERED=1

# Persistent volumes
VOLUME ["/app/data"]

EXPOSE 5000

CMD ["python3", "server.py"]
