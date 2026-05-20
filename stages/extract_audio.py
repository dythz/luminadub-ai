import logging
import subprocess
from pathlib import Path

from config import Config
from gpu_manager import GPUManager
from utils import StageResult, get_video_duration

logger = logging.getLogger("dubbing")


def extract_audio(project_dir: Path, config: Config, progress=None) -> StageResult:
    """Stage 1: Extract audio from video using FFmpeg."""
    try:
        video_path = _find_video(project_dir)
        if not video_path:
            logger.error("[EXTRACT] No video file found in input/")
            return StageResult(success=False, error="No video file found in input/")

        work_dir = project_dir / "work"
        whisper_audio = work_dir / "audio_whisper.wav"
        full_audio = work_dir / "audio_full.wav"
        logger.info(f"[EXTRACT] Video: {video_path.name}")

        if progress:
            progress(0.3, desc="Extracting audio for Whisper (16kHz mono)...")

        r = subprocess.run([
            "ffmpeg", "-y", "-i", str(video_path),
            "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
            str(whisper_audio),
        ], capture_output=True, text=True, errors='replace', timeout=600)
        if r.returncode != 0:
            raise RuntimeError(f"FFmpeg whisper extract failed: {r.stderr[-500:]}")
        logger.info(f"[EXTRACT] Whisper audio: {whisper_audio}")

        if progress:
            progress(0.6, desc="Extracting audio for Demucs (44.1kHz stereo)...")

        r = subprocess.run([
            "ffmpeg", "-y", "-i", str(video_path),
            "-ar", "44100", "-ac", "2", "-acodec", "pcm_s16le",
            str(full_audio),
        ], capture_output=True, text=True, errors='replace', timeout=600)
        if r.returncode != 0:
            raise RuntimeError(f"FFmpeg full extract failed: {r.stderr[-500:]}")
        logger.info(f"[EXTRACT] Full audio: {full_audio}")

        duration = get_video_duration(video_path)
        logger.info(f"[EXTRACT] Duration: {duration:.1f}s")

        if progress:
            progress(1.0, desc="Audio extraction complete")

        return StageResult(
            success=True,
            output_paths=[whisper_audio, full_audio],
            metadata={"duration": duration},
        )
    except Exception as e:
        return StageResult(success=False, error=str(e))


def _find_video(project_dir: Path) -> Path | None:
    input_dir = project_dir / "input"
    for ext in [".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"]:
        for f in input_dir.glob(f"*{ext}"):
            return f
    return None