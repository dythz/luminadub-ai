import os
from pathlib import Path
from dataclasses import dataclass, field

# Auto-detect base directory: use APP_BASE_DIR env var, or the directory of this file
_BASE = Path(os.environ.get("APP_BASE_DIR", str(Path(__file__).parent)))


@dataclass
class Config:
    # Paths
    BASE_DIR: Path = _BASE
    PROJECTS_DIR: Path = _BASE / "data" / "projects"
    MODEL_CACHE_DIR: Path = _BASE / "data" / "models"

    # GPU
    DEVICE: str = "cuda"
    MAX_VRAM_MB: int = 12288

    # Demucs
    DEMUCS_MODEL: str = "htdemucs"
    DEMUCS_TWO_STEM: str = "vocals"
    DEMUCS_SEGMENT: float = 10.0
    DEMUCS_SHIFTS: int = 1
    DEMUCS_OVERLAP: float = 0.25

    # Whisper - valid: tiny, base, small, medium, large-v3, large, distil-large-v3
    WHISPER_MODEL: str = "large-v3"
    WHISPER_COMPUTE_TYPE: str = "int8_float16"
    WHISPER_DEVICE: str = "cuda"
    WHISPER_LANGUAGE: str = "en"
    WHISPER_VAD_FILTER: bool = True
    WORDS_PER_CUE: int = 7
    MAX_WORDS_PER_CUE: int = 10
    MAX_CHARS_PER_CUE: int = 45
    MIN_CUE_DURATION: float = 1.0
    MIN_CUE_GAP: float = 0.08
    MAX_CUE_DURATION: float = 10.0

    # Translation
    TRANSLATION_ENGINE: str = "opus-mt"  # "opus-mt" or "ollama"
    TRANSLATION_MODEL: str = "Helsinki-NLP/opus-mt-tc-big-en-pt"
    TRANSLATION_DEVICE: str = "cuda"
    OLLAMA_MODEL: str = "llama3.2"
    OLLAMA_URL: str = "http://localhost:11434"

    # TTS
    TTS_DEFAULT: str = "xtts"
    XTTS_MODEL: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    XTTS_LANGUAGE: str = "pt"
    XTTS_MIN_REF_SEC: float = 3.0
    XTTS_TEMPERATURE: float = 0.7
    XTTS_REPETITION_PENALTY: float = 2.0
    EDGE_TTS_VOICE: str = "pt-BR-ThalitaMultilingualNeural"
    EDGE_TTS_RATE: str = "+0%"

    # Time sync
    MAX_SPEED_RATIO: float = 1.5
    MIN_SPEED_RATIO: float = 0.60
    STRETCH_METHOD: str = "atempo"
    TOLERANCE_RATIO: float = 0.08

    # Audio assembly
    FADE_MS: float = 30.0       # Fade-in/out duration per segment (ms)
    CROSSFADE_MS: float = 50.0  # Crossfade overlap between adjacent cues (ms)

    # Merge
    BACKGROUND_VOLUME: float = 0.7
    DUB_VOLUME: float = 1.0
    AUDIO_BITRATE: str = "192k"

    # Pipeline
    STAGE_ORDER: list = field(default_factory=lambda: [
        "extract", "separate", "transcribe", "translate",
        "synthesize", "sync", "merge"
    ])
    STAGE_WEIGHTS: dict = field(default_factory=lambda: {
        "extract": 0.02, "separate": 0.25, "transcribe": 0.15,
        "translate": 0.08, "synthesize": 0.30, "sync": 0.10, "merge": 0.10
    })
    STAGE_NAMES: dict = field(default_factory=lambda: {
        "extract": "Extract Audio",
        "separate": "Vocal Separation",
        "transcribe": "Transcribe (Whisper)",
        "translate": "Translate EN→PT",
        "synthesize": "Synthesize (TTS)",
        "sync": "Time Sync",
        "merge": "Merge Video"
    })

    # User toggles
    enable_vocal_separation: bool = True
    tts_engine: str = "xtts"
    reference_audio_path: str = ""

    def ensure_dirs(self):
        self.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        self.MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)