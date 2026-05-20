import torch

from config import Config
from gpu_manager import GPUManager


class TranslationModelWrapper:
    def __init__(self, config: Config):
        self.config = config
        self._tokenizer = None
        self._model = None

    def load(self) -> None:
        GPUManager.acquire("translate")
        from transformers import MarianMTModel, MarianTokenizer
        self._tokenizer = MarianTokenizer.from_pretrained(self.config.TRANSLATION_MODEL)
        self._model = MarianMTModel.from_pretrained(self.config.TRANSLATION_MODEL)
        if self.config.TRANSLATION_DEVICE == "cuda" and torch.cuda.is_available():
            self._model = self._model.cuda()
        GPUManager.set_model(self._model)

    def translate(self, texts: list[str]) -> list[str]:
        """Translate a list of texts from EN to PT. Returns translated texts."""
        if not texts:
            return []
        inputs = self._tokenizer(
            texts, return_tensors="pt", padding=True,
            truncation=True, max_length=512,
        )
        if next(self._model.parameters()).is_cuda:
            inputs = {k: v.cuda() for k, v in inputs.items()}
        with torch.no_grad():
            translated = self._model.generate(**inputs, max_length=512)
        return [self._tokenizer.decode(t, skip_special_tokens=True) for t in translated]

    def translate_single(self, text: str) -> str:
        return self.translate([text])[0]

    def unload(self) -> None:
        del self._model
        del self._tokenizer
        self._model = None
        self._tokenizer = None
        GPUManager.release("translate")