# LuminaDub AI - Deploy no RunPod

## Passo a Passo

### 1. Build da imagem Docker

No seu PC (com Docker instalado):

```bash
cd "D:\AI DUBBING"
docker build -f runpod/Dockerfile -t luminadub-ai:latest .
```

### 2. Push para um registry

Escolha UM:

**Docker Hub:**
```bash
docker login
docker tag luminadub-ai:latest seunome/luminadub-ai:latest
docker push seunome/luminadub-ai:latest
```

**GitHub Container Registry:**
```bash
docker login ghcr.io
docker tag luminadub-ai:latest ghcr.io/seunome/luminadub-ai:latest
docker push ghcr.io/seunome/luminadub-ai:latest
```

### 3. Criar Pod no RunPod

1. Acesse https://runpod.io
2. Clique **"Deploy"** > **"Custom Container"**
3. Configure:
   - **Image:** `seunome/luminadub-ai:latest`
   - **GPU:** RTX 5090 ($0.99/h)
   - **Volume:** `/app/data` (Network Storage - 50GB+)
   - **Port:** `5000`
   - **Start Command:** `bash /app/runpod/setup-pod.sh`
4. Clique **"Deploy"**

### 4. Acessar

- No RunPod, vá em **"Connect"** > **"Expose Port"** (porta 5000)
- Abra a URL fornecida no navegador
- A interface do LuminaDub AI vai aparecer

### 5. Custos

| Cenário | Tempo | Custo |
|---------|-------|-------|
| 1 video de 15min | ~5-7 min | ~$0.10 |
| 10 videos | ~1 hora | ~$0.99 |
| 50 videos | ~6 horas | ~$5.94 |

**Dica:** Pare o pod quando nao estiver usando. So paga enquanto o pod esta rodando.

## Volumes (importante!)

Monte `/app/data` como Network Storage para:
- Nao perder uploads quando o pod reiniciar
- Manter modelos em cache (nao baixar de novo)
- Compartilhar entre pods