import logging
import time
from pathlib import Path

from config import Config
from models.translation_model import TranslationModelWrapper
from utils import StageResult, SRTCue, read_srt, write_srt

logger = logging.getLogger("dubbing")


def translate(project_dir: Path, config: Config, progress=None) -> StageResult:
    """Stage 4: Translate EN SRT cues to Portuguese.
    Supports Opus-MT (local GPU) and Ollama (local LLM)."""
    try:
        en_srt_path = project_dir / "work" / "en.srt"
        if not en_srt_path.exists():
            return StageResult(success=False, error="en.srt not found. Run transcribe first.")

        work_dir = project_dir / "work"
        pt_srt_path = work_dir / "pt.srt"

        en_cues = read_srt(en_srt_path)
        logger.info(f"[TRANSLATE] EN cues: {len(en_cues)}, engine: {config.TRANSLATION_ENGINE}")

        engine = config.TRANSLATION_ENGINE

        if engine == "ollama":
            return _translate_ollama(config, en_cues, pt_srt_path, progress)
        else:
            return _translate_opus(config, en_cues, pt_srt_path, progress)

    except Exception as e:
        return StageResult(success=False, error=str(e))


def _translate_opus(config, en_cues, pt_srt_path, progress):
    """Translate using Helsinki-NLP Opus-MT (local GPU model)."""
    if progress:
        progress(0.05, desc="Loading Opus-MT model...")

    t_load_start = time.time()
    wrapper = TranslationModelWrapper(config)
    wrapper.load()
    t_load = time.time() - t_load_start
    logger.info(f"[TRANSLATE] Opus-MT loaded in {t_load:.1f}s")

    total = len(en_cues)
    if progress:
        progress(0.10, desc=f"Translating {total} cues (batch 8)...")

    pt_cues = []
    batch_size = 8
    t_translate_start = time.time()

    for i in range(0, total, batch_size):
        batch = en_cues[i: i + batch_size]
        texts = [c.text for c in batch]
        t_batch = time.time()
        translations = wrapper.translate(texts)
        batch_time = time.time() - t_batch

        for en_cue, pt_text in zip(batch, translations):
            pt_text = pt_text.strip().rstrip(".,;:")
            pt_cues.append(SRTCue(
                index=en_cue.index,
                start=en_cue.start,
                end=en_cue.end,
                text=pt_text,
            ))

        done = min(i + batch_size, total)
        pct = done / total * 100
        elapsed = time.time() - t_translate_start
        avg = elapsed / done
        remaining = avg * (total - done)
        logger.info(
            f"[TRANSLATE] Opus-MT {done}/{total} ({pct:.0f}%) | "
            f"batch {len(batch)} cues in {batch_time:.2f}s | "
            f"elapsed {elapsed:.1f}s | ETA {remaining:.1f}s"
        )

        if progress:
            frac = 0.10 + 0.85 * (done / total)
            progress(frac, desc=f"Opus-MT {done}/{total} ({pct:.0f}%) | {elapsed:.1f}s | ETA {remaining:.0f}s")

    write_srt(pt_cues, pt_srt_path)
    t_total = time.time() - t_translate_start
    avg_per_cue = t_total / total if total else 0
    logger.info(
        f"[TRANSLATE] Opus-MT done: {total} cues in {t_total:.1f}s "
        f"({avg_per_cue:.2f}s/cue avg) -> {pt_srt_path}"
    )
    wrapper.unload()

    if progress:
        progress(1.0, desc=f"Translation done: {total} cues in {t_total:.1f}s ({avg_per_cue:.2f}s/cue)")

    return StageResult(
        success=True,
        output_paths=[pt_srt_path],
        metadata={
            "cue_count": total,
            "engine": "opus-mt",
            "time_s": round(t_total, 1),
            "avg_per_cue_s": round(avg_per_cue, 3),
        },
    )


def _translate_ollama(config, en_cues, pt_srt_path, progress):
    """Translate using Ollama local LLM for natural contextual translation."""
    from models.ollama_translator import OllamaTranslator

    if progress:
        progress(0.05, desc="Connecting to Ollama...")

    t_connect = time.time()
    translator = OllamaTranslator(config)
    if not translator.check_available():
        return StageResult(
            success=False,
            error=f"Ollama not available or model '{config.OLLAMA_MODEL}' not found. "
                  f"Make sure Ollama is running and the model is installed.",
        )
    logger.info(f"[TRANSLATE] Ollama connected ({config.OLLAMA_MODEL}) in {time.time() - t_connect:.1f}s")

    total = len(en_cues)
    if progress:
        progress(0.10, desc=f"Translating {total} cues with {config.OLLAMA_MODEL}...")

    pt_cues = []
    t_start = time.time()

    for i, en_cue in enumerate(en_cues):
        t_cue = time.time()
        try:
            pt_text = translator.translate_single(en_cue.text)
            pt_text = pt_text.strip().rstrip(".,;:")
            if not pt_text:
                pt_text = en_cue.text
        except Exception as e:
            logger.warning(f"[TRANSLATE] Ollama error on cue {en_cue.index}: {e}")
            pt_text = en_cue.text
        cue_time = time.time() - t_cue

        pt_cues.append(SRTCue(
            index=en_cue.index,
            start=en_cue.start,
            end=en_cue.end,
            text=pt_text,
        ))

        done = i + 1
        pct = done / total * 100
        elapsed = time.time() - t_start
        avg = elapsed / done
        remaining = avg * (total - done)
        logger.info(
            f"[TRANSLATE] Ollama {done}/{total} ({pct:.0f}%) | "
            f"cue {en_cue.index} in {cue_time:.2f}s | "
            f"elapsed {elapsed:.1f}s | avg {avg:.2f}s/cue | ETA {remaining:.1f}s"
        )

        if progress:
            frac = 0.10 + 0.85 * (done / total)
            progress(frac, desc=f"Ollama {done}/{total} ({pct:.0f}%) | {elapsed:.1f}s | ETA {remaining:.0f}s")

    write_srt(pt_cues, pt_srt_path)
    t_total = time.time() - t_start
    avg_per_cue = t_total / total if total else 0
    logger.info(
        f"[TRANSLATE] Ollama done: {total} cues in {t_total:.1f}s "
        f"({avg_per_cue:.2f}s/cue avg) -> {pt_srt_path}"
    )

    if progress:
        progress(1.0, desc=f"Translation done: {total} cues in {t_total:.1f}s ({avg_per_cue:.2f}s/cue)")

    return StageResult(
        success=True,
        output_paths=[pt_srt_path],
        metadata={
            "cue_count": total,
            "engine": f"ollama/{config.OLLAMA_MODEL}",
            "time_s": round(t_total, 1),
            "avg_per_cue_s": round(avg_per_cue, 3),
        },
    )