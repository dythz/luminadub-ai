import logging
import time
from pathlib import Path

from config import Config
from models.tts_xtts_parallel import XTTSParallelWrapper
from models.tts_edge import EdgeTTSWrapper
from utils import StageResult, read_srt, get_audio_duration

logger = logging.getLogger("dubbing")

MAX_XTTS_CHARS = 250


def _clean_text(text: str) -> str:
    text = text.strip()
    words = text.split()
    if len(words) > 5:
        unique = set(words)
        if len(unique) < len(words) * 0.3:
            text = " ".join(list(dict.fromkeys(words))[:20])
    return text[:MAX_XTTS_CHARS]


def synthesize(project_dir: Path, config: Config, progress=None) -> StageResult:
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


def _synthesize_xtts(project_dir, config, cues, segments_dir, progress):
    vocals_path = project_dir / "work" / "vocals.wav"
    reference_audio = config.reference_audio_path or str(vocals_path) if vocals_path.exists() else None
    if not reference_audio or not Path(reference_audio).exists():
        return StageResult(success=False, error="No reference audio for XTTS voice cloning.")
    if progress:
        progress(0.05, desc="Loading XTTSv2 instances...")
    t_load_start = time.time()
    wrapper = XTTSParallelWrapper(config)
    wrapper.load(reference_audio=reference_audio)
    t_load = time.time() - t_load_start
    logger.info(f"[SYNTHESIZE] XTTSv2 loaded in {t_load:.1f}s")
    total = len(cues)
    warnings = []
    t_start = time.time()
    if progress:
        progress(0.10, desc=f"Synthesizing {total} cues...")
    try:
        output_paths = wrapper.synthesize_batch(cues, segments_dir)
    except Exception as e:
        wrapper.unload()
        return StageResult(success=False, error=str(e))
    wrapper.unload()
    t_total = time.time() - t_start
    avg = t_total / total if total else 0
    logger.info(f"[SYNTHESIZE] XTTS done: {total} cues em {t_total:.1f}s ({avg:.2f}s/cue)")
    if progress:
        progress(1.0, desc=f"TTS done: {total} cues em {t_total:.1f}s ({avg:.2f}s/cue)")
    return StageResult(
        success=True,
        output_paths=[Path(p) for p in output_paths if p],
        metadata={"warnings": warnings, "time_s": round(t_total, 1), "avg_per_cue_s": round(avg, 3), "model_load_s": round(t_load, 1)},
    )


def _estimate_edge_rate(text: str, target_duration: float) -> str:
    char_count = len(text.replace(" ", ""))
    if char_count == 0 or target_duration <= 0:
        return "+0%"
    natural_duration = char_count / 7.0
    ratio = natural_duration / target_duration
    rate_pct = round((ratio - 1.0) * 100)
    rate_pct = max(-50, min(100, rate_pct))
    return f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"


def _synthesize_edge(config, cues, segments_dir, progress):
    total = len(cues)
    if progress:
        progress(0.05, desc=f"Synthesizing {total} cues with Edge-TTS...")
    wrapper = EdgeTTSWrapper(config)
    output_paths = []
    warnings = []
    t_start = time.time()
    for i, cue in enumerate(cues):
        out_path = str(segments_dir / f"{cue.index:03d}.wav")
        try:
            rate = _estimate_edge_rate(cue.text, cue.duration())
            wrapper.set_rate(rate)
            wrapper.synthesize(cue.text, out_path)
            dur = get_audio_duration(Path(out_path))
            if dur < 0.1:
                warnings.append(f"Cue {cue.index}: generated audio is silent")
        except Exception as e:
            warnings.append(f"Cue {cue.index}: synthesis failed - {e}")
        output_paths.append(Path(out_path))
        done = i + 1
        elapsed = time.time() - t_start
        avg = elapsed / done
        if progress:
            progress(0.05 + 0.9*(done/total), desc=f"Edge {done}/{total} | ETA {avg*(total-done):.0f}s")
    t_total = time.time() - t_start
    avg = t_total / total if total else 0
    logger.info(f"[SYNTHESIZE] Edge done: {total} cues em {t_total:.1f}s ({avg:.2f}s/cue)")
    if progress:
        progress(1.0, desc=f"TTS done: {total} cues em {t_total:.1f}s")
    return StageResult(success=True, output_paths=output_paths,
        metadata={"warnings": warnings, "time_s": round(t_total,1), "avg_per_cue_s": round(avg,3)})
