import logging
import time
import shutil
from pathlib import Path

from config import Config
from models.tts_xtts import XTTSModelWrapper
from models.tts_edge import EdgeTTSWrapper
from utils import StageResult, read_srt, get_audio_duration

logger = logging.getLogger("dubbing")


def synthesize(project_dir: Path, config: Config, progress=None) -> StageResult:
    """Stage 5: Generate Portuguese speech for each SRT cue."""
    try:
        pt_srt_path = project_dir / "work" / "pt.srt"
        if not pt_srt_path.exists():
            return StageResult(success=False, error="pt.srt not found. Run translate first.")

        work_dir = project_dir / "work"
        segments_dir = work_dir / "pt_segments"
        segments_dir.mkdir(parents=True, exist_ok=True)

        cues = read_srt(pt_srt_path)
        tts_engine = config.tts_engine
        logger.info(f"[SYNTHESIZE] Engine: {tts_engine}, Cues: {len(cues)}")

        if tts_engine == "xtts":
            return _synthesize_xtts(project_dir, config, cues, segments_dir, progress)
        else:
            return _synthesize_edge(config, cues, segments_dir, progress)
    except Exception as e:
        logger.error(f"[SYNTHESIZE] Error: {e}")
        return StageResult(success=False, error=str(e))


def _synthesize_xtts(
    project_dir: Path, config: Config, cues: list, segments_dir: Path, progress
) -> StageResult:
    """Synthesize using Coqui XTTSv2 with voice cloning."""
    vocals_path = project_dir / "work" / "vocals.wav"
    reference_audio = config.reference_audio_path or str(vocals_path) if vocals_path.exists() else None

    if not reference_audio or not Path(reference_audio).exists():
        return StageResult(
            success=False,
            error="No reference audio for XTTS voice cloning. Upload reference or enable vocal separation.",
        )

    if progress:
        progress(0.05, desc="Loading XTTSv2 model...")

    t_load_start = time.time()
    wrapper = XTTSModelWrapper(config)
    wrapper.load(reference_audio=reference_audio)
    t_load = time.time() - t_load_start
    logger.info(f"[SYNTHESIZE] XTTSv2 loaded in {t_load:.1f}s")

    total = len(cues)
    if progress:
        progress(0.10, desc=f"Synthesizing {total} cues with XTTSv2...")

    output_paths = []
    warnings = []
    t_start = time.time()

    for i, cue in enumerate(cues):
        out_path = str(segments_dir / f"{cue.index:03d}.wav")
        t_cue = time.time()
        try:
            wrapper.synthesize_with_latents(cue.text, out_path)
            dur = get_audio_duration(Path(out_path))
            if dur < 0.1:
                warnings.append(f"Cue {cue.index}: generated audio is silent")
        except Exception as e:
            warnings.append(f"Cue {cue.index}: synthesis failed - {e}")
            dur = 0.0
        cue_time = time.time() - t_cue

        output_paths.append(Path(out_path))

        done = i + 1
        pct = done / total * 100
        elapsed = time.time() - t_start
        avg = elapsed / done
        remaining = avg * (total - done)
        logger.info(
            f"[SYNTHESIZE] XTTS {done}/{total} ({pct:.0f}%) | "
            f"cue {cue.index} ({cue.duration():.1f}s SRT -> {dur:.1f}s audio) in {cue_time:.2f}s | "
            f"elapsed {elapsed:.1f}s | avg {avg:.2f}s/cue | ETA {remaining:.1f}s"
        )

        if progress:
            frac = 0.10 + 0.85 * (done / total)
            progress(frac, desc=f"XTTS {done}/{total} ({pct:.0f}%) | {elapsed:.1f}s | ETA {remaining:.0f}s")

    wrapper.unload()
    t_total = time.time() - t_start
    avg_per_cue = t_total / total if total else 0
    logger.info(
        f"[SYNTHESIZE] XTTS done: {total} cues in {t_total:.1f}s "
        f"({avg_per_cue:.2f}s/cue avg) | {len(warnings)} warnings"
    )

    if progress:
        progress(1.0, desc=f"TTS done: {total} cues in {t_total:.1f}s ({avg_per_cue:.2f}s/cue)")

    return StageResult(
        success=True,
        output_paths=output_paths,
        metadata={
            "warnings": warnings,
            "time_s": round(t_total, 1),
            "avg_per_cue_s": round(avg_per_cue, 3),
            "model_load_s": round(t_load, 1),
        },
    )


def _estimate_edge_rate(text: str, target_duration: float) -> str:
    """Estimate Edge-TTS rate parameter so speech fits within target duration.
    Portuguese speech averages ~7 chars/sec at normal speed (+0%).
    Returns rate string like '+20%' or '-10%'."""
    char_count = len(text.replace(" ", ""))
    if char_count == 0 or target_duration <= 0:
        return "+0%"
    natural_duration = char_count / 7.0
    ratio = natural_duration / target_duration
    rate_pct = round((ratio - 1.0) * 100)
    rate_pct = max(-50, min(100, rate_pct))
    if rate_pct >= 0:
        return f"+{rate_pct}%"
    return f"{rate_pct}%"


def _synthesize_edge(config: Config, cues: list, segments_dir: Path, progress) -> StageResult:
    """Synthesize using Edge TTS (free, cloud-based, no GPU).
    Calculates per-cue speaking rate so audio naturally fits SRT timing."""
    total = len(cues)
    if progress:
        progress(0.05, desc=f"Synthesizing {total} cues with Edge-TTS...")

    wrapper = EdgeTTSWrapper(config)
    output_paths = []
    warnings = []
    t_start = time.time()

    for i, cue in enumerate(cues):
        out_path = str(segments_dir / f"{cue.index:03d}.wav")
        t_cue = time.time()
        try:
            rate = _estimate_edge_rate(cue.text, cue.duration())
            wrapper.set_rate(rate)
            wrapper.synthesize(cue.text, out_path)
            dur = get_audio_duration(Path(out_path))
            if dur < 0.1:
                warnings.append(f"Cue {cue.index}: generated audio is silent")
        except Exception as e:
            warnings.append(f"Cue {cue.index}: synthesis failed - {e}")
            dur = 0.0
        cue_time = time.time() - t_cue

        output_paths.append(Path(out_path))

        done = i + 1
        pct = done / total * 100
        elapsed = time.time() - t_start
        avg = elapsed / done
        remaining = avg * (total - done)
        logger.info(
            f"[SYNTHESIZE] Edge {done}/{total} ({pct:.0f}%) | "
            f"cue {cue.index} ({cue.duration():.1f}s SRT -> {dur:.1f}s audio) in {cue_time:.2f}s | "
            f"elapsed {elapsed:.1f}s | avg {avg:.2f}s/cue | ETA {remaining:.1f}s"
        )

        if progress:
            frac = 0.05 + 0.9 * (done / total)
            progress(frac, desc=f"Edge {done}/{total} ({pct:.0f}%) | {elapsed:.1f}s | ETA {remaining:.0f}s")

    t_total = time.time() - t_start
    avg_per_cue = t_total / total if total else 0
    logger.info(
        f"[SYNTHESIZE] Edge-TTS done: {total} cues in {t_total:.1f}s "
        f"({avg_per_cue:.2f}s/cue avg) | {len(warnings)} warnings"
    )

    if progress:
        progress(1.0, desc=f"TTS done: {total} cues in {t_total:.1f}s ({avg_per_cue:.2f}s/cue)")

    return StageResult(
        success=True,
        output_paths=output_paths,
        metadata={
            "warnings": warnings,
            "time_s": round(t_total, 1),
            "avg_per_cue_s": round(avg_per_cue, 3),
        },
    )