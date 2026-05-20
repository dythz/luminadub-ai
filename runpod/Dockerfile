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
RUN grep -vE "^(torch|torchaudio|#)" requirements.txt > /tmp/requirements-filtered.txt && \
    pip install --no-cache-dir -r /tmp/requirements-filtered.txt

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