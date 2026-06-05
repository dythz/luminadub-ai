import os
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
from pathlib import Path
from config import Config
from gpu_manager import GPUManager

class WhisperModelWrapper:
    def __init__(self, config: Config):
        self.config = config
        self.model = None

    def load(self) -> None:
        GPUManager.acquire("transcribe")
        from faster_whisper import WhisperModel
        self.model = WhisperModel(
            self.config.WHISPER_MODEL,
            device=self.config.WHISPER_DEVICE,
            compute_type=self.config.WHISPER_COMPUTE_TYPE,
            download_root=str(self.config.MODEL_CACHE_DIR / "whisper"),
            num_workers=4,
        )
        GPUManager.set_model(self.model)

    def transcribe(self, audio_path: Path) -> list[dict]:
        segments, info = self.model.transcribe(
            str(audio_path),
            language=self.config.WHISPER_LANGUAGE,
            word_timestamps=True,
            vad_filter=self.config.WHISPER_VAD_FILTER,
            vad_parameters=dict(min_silence_duration_ms=500),
            beam_size=5,
            best_of=5,
            batch_size=16,
        )
        words = []
        for seg in segments:
            for w in seg.words:
                words.append({
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "probability": w.probability,
                })
        return words

    def unload(self) -> None:
        del self.model
        self.model = None
        GPUManager.release("transcribe")
