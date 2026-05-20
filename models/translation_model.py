import torch

from config import Config
from gpu_manager import GPUManager


class TranslationModelWrapper:
    def __init__(self, config: Config):
        self.config = config
        self.translator = None

    def load(self) -> None:
        GPUManager.acquire("translate")
        from transformers import pipeline
        device = 0 if self.config.TRANSLATION_DEVICE == "cuda" and torch.cuda.is_available() else -1
        self.translator = pipeline(
            "translation",
            model=self.config.TRANSLATION_MODEL,
            device=device,
        )
        GPUManager.set_model(self.translator)

    def translate(self, texts: list[str]) -> list[str]:
        """Translate a list of texts from EN to PT. Returns translated texts."""
        if not texts:
            return []
        results = self.translator(texts, max_length=512)
        if isinstance(results[0], list):
            return [r[0]["translation_text"] for r in results]
        return [r["translation_text"] for r in results]

    def translate_single(self, text: str) -> str:
        result = self.translator(text, max_length=512)
        return result[0]["translation_text"]

    def unload(self) -> None:
        del self.translator
        self.translator = None
        GPUManager.release("translate")