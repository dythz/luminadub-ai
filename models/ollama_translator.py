"""Translation via Ollama local LLM for natural, contextual EN→PT translation."""

import json
import logging
import urllib.request
import urllib.error

from config import Config

logger = logging.getLogger("dubbing")

SYSTEM_PROMPT = """You are a professional translator specializing in English to Brazilian Portuguese (pt-BR) translation for film and video dubbing.

Rules:
- Translate naturally, as spoken in Brazilian Portuguese
- Keep the same tone and emotion as the original
- Do NOT add explanations, notes, or quotation marks
- Do NOT add periods at the end unless the original has one
- Keep the translation concise - it will be spoken aloud and must fit in a short time slot
- If the original has slang or informal language, translate to equivalent Brazilian Portuguese slang
- Output ONLY the translated text, nothing else"""

BATCH_SYSTEM_PROMPT = """You are a professional translator specializing in English to Brazilian Portuguese (pt-BR) translation for film and video dubbing.

You will receive a JSON array of strings to translate. Return a JSON array of translated strings in the SAME ORDER.
Rules:
- Translate naturally, as spoken in Brazilian Portuguese
- Keep the same tone and emotion as the original
- Do NOT add periods at the end unless the original has one
- Keep translations concise - they will be spoken aloud in short time slots
- Output ONLY the JSON array, nothing else"""


class OllamaTranslator:
    """Translate text using a local Ollama LLM model."""

    def __init__(self, config: Config):
        self.config = config
        self.model = config.OLLAMA_MODEL
        self.url = config.OLLAMA_URL
        self.available = False

    def check_available(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            req = urllib.request.Request(f"{self.url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
                self.available = self.model.split(":")[0] in models
                if not self.available:
                    logger.warning(f"[OLLAMA] Model '{self.model}' not found. Available: {models}")
                return self.available
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            logger.warning(f"[OLLAMA] Connection failed: {e}")
            self.available = False
            return False

    def translate_single(self, text: str) -> str:
        """Translate a single text string from EN to PT-BR."""
        prompt = f"Translate to Brazilian Portuguese:\n{text}"
        response = self._generate(prompt, system=SYSTEM_PROMPT)
        return response.strip().strip('"').strip()

    def translate_batch(self, texts: list[str]) -> list[str]:
        """Translate a batch of texts. Uses JSON mode for reliability."""
        if not texts:
            return []

        if len(texts) == 1:
            return [self.translate_single(texts[0])]

        # For small batches, use single requests for reliability
        if len(texts) <= 4:
            return [self.translate_single(t) for t in texts]

        # For larger batches, try JSON batch mode
        try:
            return self._translate_batch_json(texts)
        except Exception as e:
            logger.warning(f"[OLLAMA] Batch JSON failed, falling back to single: {e}")
            return [self.translate_single(t) for t in texts]

    def _translate_batch_json(self, texts: list[str]) -> list[str]:
        """Translate using JSON batch mode for efficiency."""
        prompt = json.dumps(texts, ensure_ascii=False)
        response = self._generate(prompt, system=BATCH_SYSTEM_PROMPT)

        # Parse JSON response
        response = response.strip()
        # Remove markdown code fences if present
        if response.startswith("```"):
            response = response.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            results = json.loads(response)
            if isinstance(results, list) and len(results) == len(texts):
                return results
        except json.JSONDecodeError:
            pass

        logger.warning("[OLLAMA] Batch parse failed, falling back to single requests")
        return [self.translate_single(t) for t in texts]

    def _generate(self, prompt: str, system: str = "") -> str:
        """Send a generate request to Ollama API."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 256,
            },
        }
        if system:
            payload["system"] = system

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            return result.get("response", "")

    def unload(self):
        """No-op for API-based translator."""
        pass