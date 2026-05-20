import logging
import shutil
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from config import Config
from utils import (
    StageResult, SRTCue, read_srt, get_audio_duration,
    stretch_audio, pad_silence, fade_out, assemble_dubbed_vocals,
)

logger = logging.getLogger("dubbing")


def time_sync(project_dir: Path, config: Config, progress=None) -> StageResult:
    """Stage 6: Time-stretch/pad synthesized audio to match SRT timing.
    Prefers speed adjustment and padding over cutting audio."""
    try:
        pt_srt_path = project_dir / "work" / "pt.srt"
        if not pt_srt_path.exists():
            return StageResult(success=False, error="pt.srt not found. Run translate first.")

        work_dir = project_dir / "work"
        segments_dir = work_dir / "pt_segments"
        synced_dir = work_dir / "pt_synced"
        synced_dir.mkdir(parents=True, exist_ok=True)

        cues = read_srt(pt_srt_path)
        if not cues:
            return StageResult(success=False, error="No cues found in pt.srt")

        total = len(cues)
        logger.info(f"[SYNC] Syncing {total} cues")

        if progress:
            progress(0.05, desc=f"Syncing {total} cues to SRT timing...")

        warnings = []
        method_counts = {}
        t_start = time.time()

        for i, cue in enumerate(cues):
            synth_path = segments_dir / f"{cue.index:03d}.wav"
            synced_path = synced_dir / f"{cue.index:03d}.wav"

            if not synth_path.exists():
                _write_silence(synced_path, cue.duration())
                warnings.append(f"Cue {cue.index}: segment file not found")
                method = "missing"
            else:
                next_cue = cues[i + 1] if i + 1 < len(cues) else None
                t_cue = time.time()
                result = _sync_cue_audio(cue, synth_path, synced_path, config, next_cue=next_cue)
                cue_time = time.time() - t_cue
                method = result["method"]
                ratio = result["ratio"]
                srt_dur = cue.duration()
                if result.get("warnings"):
                    warnings.extend(result["warnings"])

                logger.info(
                    f"[SYNC] {i + 1}/{total} ({(i + 1) / total * 100:.0f}%) | "
                    f"cue {cue.index} | SRT {srt_dur:.2f}s | ratio {ratio:.2f} | "
                    f"method: {method} | {cue_time:.2f}s"
                )

            method_counts[method] = method_counts.get(method, 0) + 1

            done = i + 1
            elapsed = time.time() - t_start
            avg = elapsed / done
            remaining = avg * (total - done)

            if progress:
                frac = 0.05 + 0.6 * (done / total)
                progress(frac, desc=f"Sync {done}/{total} ({done / total * 100:.0f}%) | {elapsed:.1f}s | ETA {remaining:.0f}s")

        if progress:
            progress(0.70, desc="Assembling dubbed vocals track...")

        t_assemble = time.time()
        total_duration = cues[-1].end + 1.0
        audio_full = work_dir / "audio_full.wav"
        if audio_full.exists():
            total_duration = get_audio_duration(audio_full)

        fade_ms = getattr(config, 'FADE_MS', 30.0)
        crossfade_ms = getattr(config, 'CROSSFADE_MS', 50.0)
        dubbed_vocals_path = assemble_dubbed_vocals(
            synced_dir, cues, total_duration,
            fade_ms=fade_ms, crossfade_ms=crossfade_ms,
        )
        assemble_time = time.time() - t_assemble

        t_total = time.time() - t_start
        avg_per_cue = t_total / total if total else 0
        logger.info(
            f"[SYNC] Done: {total} cues synced in {t_total:.1f}s "
            f"({avg_per_cue:.2f}s/cue) | assembly {assemble_time:.1f}s | "
            f"methods: {method_counts} | output: {dubbed_vocals_path} ({total_duration:.1f}s)"
        )

        if progress:
            progress(1.0, desc=f"Sync done: {total} cues in {t_total:.1f}s")

        return StageResult(
            success=True,
            output_paths=[synced_dir, dubbed_vocals_path],
            metadata={
                "warnings": warnings,
                "cue_count": total,
                "time_s": round(t_total, 1),
                "avg_per_cue_s": round(avg_per_cue, 3),
                "assemble_s": round(assemble_time, 1),
                "method_counts": method_counts,
            },
        )
    except Exception as e:
        return StageResult(success=False, error=str(e))


def _write_silence(output_path: Path, duration: float, sample_rate: int = 44100) -> None:
    """Write a silent WAV file of the given duration."""
    samples = int(max(duration, 0.1) * sample_rate)
    silence = np.zeros(samples, dtype=np.float32)
    sf.write(str(output_path), silence, sample_rate)


def _sync_cue_audio(
    cue: SRTCue, synth_path: Path, output_path: Path, config: Config,
    next_cue: SRTCue | None = None,
) -> dict:
    """Adjust synthesized audio to fit within SRT cue timing.
    Prefers speed adjustment over cutting. Allows slight overflow if space permits."""
    srt_duration = cue.duration()
    synth_duration = get_audio_duration(synth_path)

    if synth_duration <= 0:
        _write_silence(output_path, srt_duration)
        return {"ratio": 0, "method": "silence", "warnings": ["Empty audio replaced with silence"]}

    ratio = synth_duration / srt_duration
    tolerance = config.TOLERANCE_RATIO
    max_speed = config.MAX_SPEED_RATIO
    min_speed = config.MIN_SPEED_RATIO

    # Within tolerance - copy as-is
    if (1 - tolerance) <= ratio <= (1 + tolerance):
        shutil.copy2(synth_path, output_path)
        return {"ratio": ratio, "method": "none", "warnings": []}

    # Audio slightly longer - compress (speed up)
    if 1 + tolerance < ratio <= max_speed:
        stretch_audio(synth_path, output_path, ratio, method=config.STRETCH_METHOD)
        return {"ratio": ratio, "method": "compress", "warnings": []}

    # Audio slightly shorter - stretch (slow down)
    if min_speed <= ratio < 1 - tolerance:
        stretch_audio(synth_path, output_path, ratio, method=config.STRETCH_METHOD)
        return {"ratio": ratio, "method": "stretch", "warnings": []}

    # Audio MUCH shorter - stretch to max + pad silence
    if ratio < min_speed:
        stretch_audio(synth_path, output_path, min_speed, method=config.STRETCH_METHOD)
        pad_silence(output_path, srt_duration, position="end")
        return {
            "ratio": ratio, "method": "stretch+pad",
            "warnings": [f"Short audio padded with silence"],
        }

    # Audio MUCH longer - compress to max speed
    if ratio > max_speed:
        stretch_audio(synth_path, output_path, max_speed, method=config.STRETCH_METHOD)
        actual = get_audio_duration(output_path)

        if actual > srt_duration and next_cue is not None:
            available_until_next = next_cue.start - cue.start
            if actual <= available_until_next:
                return {
                    "ratio": ratio, "method": "compress+overflow",
                    "warnings": [f"Compressed {ratio:.2f}x, extends into gap ({actual:.1f}s / {available_until_next:.1f}s)"],
                }

        if actual > srt_duration:
            fade_out(output_path, srt_duration)
            return {
                "ratio": ratio, "method": "aggressive_compress+fade",
                "warnings": [f"Compressed {ratio:.2f}x, faded at {srt_duration:.1f}s"],
            }
        return {"ratio": ratio, "method": "aggressive_compress", "warnings": []}

    shutil.copy2(synth_path, output_path)
    return {"ratio": ratio, "method": "copy", "warnings": []}