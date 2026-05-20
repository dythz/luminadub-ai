import logging
import re
from pathlib import Path

import gradio as gr

from config import Config
from pipeline import DubbingPipeline

logger = logging.getLogger("dubbing")

PROJECTS_DIR = Config().PROJECTS_DIR


def toggle_subtitles(choice: str, project_id: str):
    """Switch between plain and subtitled video based on radio selection."""
    if not project_id:
        return gr.update(value=None)

    output_dir = PROJECTS_DIR / project_id / "output"
    if choice == "With Subtitles":
        sub_path = output_dir / "dubbed_video_subtitled.mp4"
        if sub_path.exists():
            return str(sub_path)
    plain_path = output_dir / "dubbed_video.mp4"
    if plain_path.exists():
        return str(plain_path)
    return gr.update(value=None)


def on_start_processing(
    video_file, enable_vocal_separation, tts_engine, edge_voice,
    bg_volume, dub_volume, max_speed_ratio, stretch_method,
    words_per_cue, reference_audio, progress=gr.Progress(),
):
    """Main callback: start the full dubbing pipeline."""
    if not video_file:
        return list(_make_output(error_msg="Please upload a video file first.").values())

    logger.info("=== STARTING DUBBING PIPELINE ===")
    logger.info(f"Video: {video_file}")
    logger.info(f"Settings: vocal_sep={enable_vocal_separation}, tts={tts_engine}, voice={edge_voice}")

    config = Config()
    config.enable_vocal_separation = enable_vocal_separation
    config.tts_engine = tts_engine
    config.EDGE_TTS_VOICE = edge_voice
    config.BACKGROUND_VOLUME = bg_volume
    config.DUB_VOLUME = dub_volume
    config.MAX_SPEED_RATIO = max_speed_ratio
    config.STRETCH_METHOD = stretch_method
    config.WORDS_PER_CUE = int(words_per_cue)
    config.MAX_WORDS_PER_CUE = max(config.MAX_WORDS_PER_CUE, config.WORDS_PER_CUE)
    if reference_audio:
        config.reference_audio_path = reference_audio

    try:
        pipeline = DubbingPipeline(config=config)
        project_id = pipeline.setup_project(video_file)
    except Exception as e:
        logger.error(f"Setup error: {e}")
        return list(_make_output(error_msg=f"Setup error: {e}").values())

    try:
        results = pipeline.run_all(progress_callback=lambda frac, desc="": progress(frac, desc=desc))
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        return list(_make_output(error_msg=f"Pipeline error: {e}").values())

    # Build output
    try:
        status = pipeline.get_status()
        work_dir = pipeline.project_dir / "work"
        output_dir = pipeline.project_dir / "output"
    except Exception as e:
        logger.error(f"Error reading status: {e}")
        return list(_make_output(error_msg=f"Error after pipeline: {e}").values())

    out = _make_output()
    out["status_text"] = "Dubbing complete!" if not status.get("error") else f"Error: {status['error']}"
    out["project_state"] = project_id
    out["original_video"] = video_file
    logger.info(f"Pipeline status: error={status.get('error')}, completed={status.get('completed_stages')}")

    # Identify the failed stage from error message
    error_stage = None
    if status.get("error"):
        m = re.match(r"\[(\w+)\]", status["error"])
        if m:
            error_stage = m.group(1)

    # Update stage statuses
    for stage_info in status["stages"]:
        name = stage_info["name"]
        s = stage_info["status"]
        if name == error_stage:
            out[f"{name}_icon"] = "\u2717"
            out[f"{name}_progress"] = 0
            out[f"{name}_status"] = "Error"
        elif s == "completed":
            out[f"{name}_icon"] = "\u2713"
            out[f"{name}_progress"] = 100
            out[f"{name}_status"] = "Done"
        elif s == "running":
            out[f"{name}_icon"] = "\u27F3"
            out[f"{name}_status"] = "Running..."
        else:
            out[f"{name}_icon"] = "\u25CB"
            out[f"{name}_status"] = "Pending"

    # Preview files
    if (work_dir / "vocals.wav").exists():
        out["vocals_audio"] = str(work_dir / "vocals.wav")
    if (work_dir / "background.wav").exists():
        out["bg_audio"] = str(work_dir / "background.wav")
    if (work_dir / "en.srt").exists():
        with open(work_dir / "en.srt", "r", encoding="utf-8") as f:
            out["en_srt_text"] = f.read()
    if (work_dir / "pt.srt").exists():
        with open(work_dir / "pt.srt", "r", encoding="utf-8") as f:
            out["pt_srt_text"] = f.read()
    if (work_dir / "dubbed_vocals.wav").exists():
        out["pt_audio"] = str(work_dir / "dubbed_vocals.wav")

    # Video: prefer subtitled version by default, fall back to plain
    video_path = output_dir / "dubbed_video.mp4"
    video_sub_path = output_dir / "dubbed_video_subtitled.mp4"

    if video_sub_path.exists():
        out["final_video"] = str(video_sub_path)
        logger.info(f"Using subtitled video: {video_sub_path}")
    elif video_path.exists():
        out["final_video"] = str(video_path)
        logger.info(f"Using plain video: {video_path}")
    else:
        logger.warning(f"No output video found at {output_dir}")

    if video_path.exists():
        out["download_video"] = str(video_path)
    if video_sub_path.exists():
        out["download_video_sub"] = str(video_sub_path)
    if (output_dir / "en.srt").exists():
        out["download_en"] = str(output_dir / "en.srt")
    if (output_dir / "pt.srt").exists():
        out["download_pt"] = str(output_dir / "pt.srt")

    return list(out.values())


def _make_output(error_msg=None) -> dict:
    """Create a default output dict with all fields in correct order."""
    config = Config()
    out = {
        "status_text": error_msg or "",
        "project_state": None,
        "original_video": None,
    }
    for s in config.STAGE_ORDER:
        out[f"{s}_icon"] = "\u25CB"
        out[f"{s}_progress"] = 0
        out[f"{s}_status"] = "Pending" if not error_msg else "Error"
    out["final_video"] = None
    out["vocals_audio"] = None
    out["bg_audio"] = None
    out["en_srt_text"] = ""
    out["pt_srt_text"] = ""
    out["pt_audio"] = None
    out["download_video"] = None
    out["download_video_sub"] = None
    out["download_en"] = None
    out["download_pt"] = None
    return out