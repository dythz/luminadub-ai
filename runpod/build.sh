#!/bin/bash
# Build and push the LuminaDub AI Docker image for RunPod

IMAGE_NAME="luminadub-ai"
TAG="latest"

echo "========================================="
echo "  LuminaDub AI - Build para RunPod"
echo "========================================="
echo ""

# Build from project root (parent directory)
cd "$(dirname "$0")/.."

echo "[1/3] Building Docker image..."
docker build -f runpod/Dockerfile -t ${IMAGE_NAME}:${TAG} .

if [ $? -ne 0 ]; then
    echo "ERRO: Build falhou!"
    exit 1
fi

echo ""
echo "[2/3] Image built successfully!"
echo ""

# Option: push to Docker Hub or GitHub Container Registry
read -p "Push to registry? (y/n): " PUSH
if [ "$PUSH" = "y" ]; then
    read -p "Registry (e.g. username/luminadub-ai): " REGISTRY
    docker tag ${IMAGE_NAME}:${TAG} ${REGISTRY}:${TAG}
    docker push ${REGISTRY}:${TAG}
    echo ""
    echo "[3/3] Pushed to ${REGISTRY}:${TAG}"
    echo ""
    echo "No RunPod, use a imagem: ${REGISTRY}:${TAG}"
else
    echo ""
    echo "[3/3] Skipped push."
    echo ""
    echo "Para push manual:"
    echo "  docker tag ${IMAGE_NAME}:${TAG} <registry>/<nome>:${TAG}"
    echo "  docker push <registry>/<nome>:${TAG}"
fi

echo ""
echo "========================================="
echo "  Pronto! Configure no RunPod:"
echo "  - Imagem Docker: ${REGISTRY:-${IMAGE_NAME}}:${TAG}"
echo "  - GPU: RTX 5090"
echo "  - Porta: 5000"
echo "  - Volume: /app/data"
echo "========================================="