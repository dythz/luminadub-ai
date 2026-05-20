"""Pipeline worker — runs in an isolated subprocess per video.
GPU crashes here do NOT kill the main server."""
import logging
import os
import sys
import time

os.environ["COQUI_TOS_AGREED"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

if "/app" not in sys.path:
    sys.path.insert(0, "/app")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("worker")

_STAGE_NAMES = {
    "extract":    "Extrair Audio",
    "separate":   "Separar Vocais",
    "transcribe": "Transcrever",
    "translate":  "Traduzir",
    "synthesize": "Sintetizar Voz",
    "sync":       "Sincronizar",
    "merge":      "Mesclar Video",
}


def run(project_id: str, session_id: str, config_overrides: dict, event_queue) -> None:
    """Execute the dubbing pipeline. Called in a subprocess by JobQueue."""

    def emit(event: str, data: dict) -> None:
        try:
            event_queue.put_nowait((session_id, event, data))
        except Exception:
            pass

    try:
        from config import Config
        from pipeline import STAGE_FUNCTIONS, PipelineState, DubbingPipeline

        config = Config()
        config.ensure_dirs()
        for key, val in config_overrides.items():
            if hasattr(config, key):
                setattr(config, key, val)

        project_dir = config.PROJECTS_DIR / project_id
        if not project_dir.exists():
            emit("error", {"message": f"Projeto nao encontrado: {project_id}"})
            return

        video_files = list((project_dir / "input").glob("*"))
        if not video_files:
            emit("error", {"message": "Nenhum video encontrado em input/"})
            return

        pipeline = DubbingPipeline(project_id=project_id, config=config)
        pipeline.setup_project(str(video_files[0]))

        state = pipeline.state
        completed = state.completed_stages
        stages_to_run = [s for s in config.STAGE_ORDER if s not in completed]
        if not config.enable_vocal_separation and "separate" in stages_to_run:
            stages_to_run.remove("separate")

        total_stages = len(stages_to_run)
        start_time = time.time()

        for stage_name in stages_to_run:
            display = _STAGE_NAMES.get(stage_name, stage_name)
            emit("stage_start", {
                "stage": stage_name,
                "display": display,
                "stages_done": len(state.completed_stages),
                "stages_total": total_stages,
            })
            state.mark_running(stage_name)

            def _progress(frac, desc="", _stage=stage_name, _display=display):
                done = len(state.completed_stages)
                overall = (done + frac) / max(total_stages, 1)
                elapsed = time.time() - start_time
                eta = (elapsed / max(overall, 0.01)) * (1.0 - overall) if overall > 0.05 else 0
                emit("progress", {
                    "frac": round(overall, 4),
                    "stage_frac": round(frac, 4),
                    "desc": f"{_display}: {desc}" if desc else _display,
                    "elapsed": round(elapsed, 1),
                    "eta": round(max(eta, 0.0), 1),
                    "stage": _stage,
                })

            stage_fn = STAGE_FUNCTIONS[stage_name]
            result = stage_fn(project_dir, config, progress=_progress)

            if result.success:
                state.mark_completed(stage_name, metadata=result.metadata or {})
                emit("stage_done", {
                    "stage": stage_name,
                    "display": display,
                    "warnings": (result.metadata or {}).get("warnings", []),
                    "elapsed_total": round(time.time() - start_time, 1),
                })
            else:
                state.mark_error(stage_name, result.error or "Erro desconhecido")
                emit("stage_error", {
                    "stage": stage_name,
                    "display": display,
                    "error": result.error or "Erro desconhecido",
                })
                return

        total_time = time.time() - start_time
        output_dir = config.PROJECTS_DIR / project_id / "output"
        result_files = {}
        if output_dir.exists():
            for f in output_dir.iterdir():
                if f.is_file():
                    result_files[f.name] = f"/api/file/{project_id}/{f.name}"

        emit("done", {
            "total_time": round(total_time, 1),
            "project_id": project_id,
            "files": result_files,
        })

    except Exception as exc:
        logger.exception("Worker pipeline error")
        emit("error", {"message": str(exc)})
