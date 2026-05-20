import logging
import shutil
import subprocess
from pathlib import Path

from config import Config
from utils import StageResult, mix_audio, mux_video_audio, mux_video_with_mix, srt_to_vtt

logger = logging.getLogger("dubbing")


def merge(project_dir: Path, config: Config, progress=None) -> StageResult:
    """Stage 7: Merge dubbed vocals + background audio + original video.
    Uses single-pass FFmpeg when possible to avoid intermediate files.
    Subtitles are served as VTT tracks — no video re-encode needed."""
    try:
        work_dir = project_dir / "work"
        output_dir = project_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        dubbed_vocals_path = work_dir / "dubbed_vocals.wav"
        if not dubbed_vocals_path.exists():
            return StageResult(success=False, error="dubbed_vocals.wav not found. Run sync first.")

        video_path = _find_video(project_dir)
        if not video_path:
            return StageResult(success=False, error="No video file found in input/")
        video_path = Path(video_path) if isinstance(video_path, str) else video_path
        if not video_path.exists():
            return StageResult(success=False, error=f"Video file not found: {video_path}")

        # Output name: original_name_dublado_pt.mp4
        stem = video_path.stem
        output_name = f"{stem}_dublado_pt.mp4"
        output_video = output_dir / output_name

        background_path = work_dir / "background.wav"
        logger.info(f"[MERGE] Video: {video_path.name}, Vocals: {dubbed_vocals_path.name}, Output: {output_name}")

        if progress:
            progress(0.2, desc="Merging audio and video...")

        # Single-pass: mix audio + mux video in one FFmpeg command
        if background_path.exists() and config.enable_vocal_separation:
            logger.info(f"[MERGE] Single-pass mix+mux (background + vocals + video)")
            mux_video_with_mix(
                video_path, background_path, dubbed_vocals_path, output_video,
                bg_volume=config.BACKGROUND_VOLUME,
                dub_volume=config.DUB_VOLUME,
                bitrate=config.AUDIO_BITRATE,
            )
        else:
            # No vocal separation — just mux video with dubbed vocals
            final_audio_path = work_dir / "final_audio.wav"
            logger.info(f"[MERGE] No vocal separation, muxing video + vocals")
            shutil.copy(dubbed_vocals_path, final_audio_path)
            mux_video_audio(video_path, final_audio_path, output_video, bitrate=config.AUDIO_BITRATE)

        if not output_video.exists():
            return StageResult(success=False, error=f"Mux output not created: {output_video}")
        size = output_video.stat().st_size
        if size < 50_000:
            return StageResult(success=False, error=f"Output video is corrupt or empty ({size} bytes): {output_video}")
        logger.info(f"[MERGE] Output video created: {output_video} ({size // 1024 // 1024} MB)")

        if progress:
            progress(0.75, desc="Preparing subtitles...")

        # Generate WebVTT for the player's <track> element
        output_paths = [output_video]
        en_srt = work_dir / "en.srt"
        pt_srt = work_dir / "pt.srt"
        if en_srt.exists():
            shutil.copy(en_srt, output_dir / "en.srt")
            output_paths.append(output_dir / "en.srt")
            try:
                srt_to_vtt(output_dir / "en.srt", output_dir / "en.vtt")
                output_paths.append(output_dir / "en.vtt")
            except Exception as e:
                logger.warning(f"[MERGE] EN VTT generation failed: {e}")
        if pt_srt.exists():
            shutil.copy(pt_srt, output_dir / "pt.srt")
            output_paths.append(output_dir / "pt.srt")
            try:
                srt_to_vtt(output_dir / "pt.srt", output_dir / "pt.vtt")
                output_paths.append(output_dir / "pt.vtt")
            except Exception as e:
                logger.warning(f"[MERGE] PT VTT generation failed: {e}")

        if progress:
            progress(1.0, desc="Merge complete!")

        return StageResult(
            success=True,
            output_paths=output_paths,
            metadata={"output_video": str(output_video)},
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode(errors='replace') if e.stderr else "")
        logger.error(f"[MERGE] FFmpeg FAILED | returncode={e.returncode}")
        logger.error(f"[MERGE] stderr: {stderr[:2000]}")
        error_msg = stderr[-500:] if stderr else f"FFmpeg exit code {e.returncode}"
        return StageResult(success=False, error=f"FFmpeg error: {error_msg}")
    except Exception as e:
        logger.exception("[MERGE] Unexpected error")
        return StageResult(success=False, error=str(e))


def _find_video(project_dir: Path) -> Path | None:
    input_dir = project_dir / "input"
    for ext in [".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"]:
        for f in input_dir.glob(f"*{ext}"):
            return f
    return None