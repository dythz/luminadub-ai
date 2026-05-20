import json
import logging
from pathlib import Path

from config import Config
from models.whisper_model import WhisperModelWrapper
from utils import StageResult, group_words_to_cues, write_srt

logger = logging.getLogger("dubbing")


def transcribe(project_dir: Path, config: Config, progress=None) -> StageResult:
    """Stage 3: Transcribe audio with word-level timestamps and generate SRT."""
    try:
        # Use vocals if separated, otherwise use whisper audio
        vocals_path = project_dir / "work" / "vocals.wav"
        whisper_path = project_dir / "work" / "audio_whisper.wav"
        audio_path = vocals_path if vocals_path.exists() else whisper_path

        if not audio_path.exists():
            return StageResult(success=False, error="No audio found. Run extract first.")

        work_dir = project_dir / "work"
        srt_path = work_dir / "en.srt"
        words_path = work_dir / "en_words.json"
        logger.info(f"[TRANSCRIBE] Audio: {audio_path.name}")

        if progress:
            progress(0.1, desc="Loading Whisper model...")

        wrapper = WhisperModelWrapper(config)
        wrapper.load()

        if progress:
            progress(0.3, desc="Transcribing audio...")

        words = wrapper.transcribe(audio_path)
        logger.info(f"[TRANSCRIBE] Words detected: {len(words)}")

        if progress:
            progress(0.7, desc="Grouping words into SRT cues...")

        cues = group_words_to_cues(
            words,
            words_per_cue=config.WORDS_PER_CUE,
            max_words_per_cue=config.MAX_WORDS_PER_CUE,
            max_chars_per_cue=config.MAX_CHARS_PER_CUE,
            min_duration=config.MIN_CUE_DURATION,
            min_gap=config.MIN_CUE_GAP,
            max_duration=config.MAX_CUE_DURATION,
        )

        write_srt(cues, srt_path)
        logger.info(f"[TRANSCRIBE] SRT cues: {len(cues)} -> {srt_path}")

        with open(words_path, "w", encoding="utf-8") as f:
            json.dump(words, f, ensure_ascii=False, indent=2)

        wrapper.unload()

        if progress:
            progress(1.0, desc=f"Transcription complete: {len(cues)} cues")

        return StageResult(
            success=True,
            output_paths=[srt_path, words_path],
            metadata={"cue_count": len(cues), "word_count": len(words)},
        )
    except Exception as e:
        return StageResult(success=False, error=str(e))