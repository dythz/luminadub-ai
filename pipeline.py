import json
import logging
import time
from pathlib import Path
from typing import Callable, Optional

from config import Config
from stages.extract_audio import extract_audio
from stages.vocal_separate import separate_vocals
from stages.transcribe import transcribe
from stages.translate import translate
from stages.synthesize import synthesize
from stages.time_sync import time_sync
from stages.merge import merge
from utils import generate_project_id, ensure_project_dirs

logger = logging.getLogger("dubbing")


STAGE_FUNCTIONS = {
    "extract": extract_audio,
    "separate": separate_vocals,
    "transcribe": transcribe,
    "translate": translate,
    "synthesize": synthesize,
    "sync": time_sync,
    "merge": merge,
}


class PipelineState:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.state_file = project_dir / "state.json"
        self.completed_stages: list[str] = []
        self.current_stage: str | None = None
        self.error: str | None = None
        self.stage_details: dict = {}
        self.load()

    def load(self):
        if self.state_file.exists():
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.completed_stages = data.get("completed_stages", [])
            self.current_stage = data.get("current_stage")
            self.error = data.get("error")
            self.stage_details = data.get("stage_details", {})

    def save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump({
                "completed_stages": self.completed_stages,
                "current_stage": self.current_stage,
                "error": self.error,
                "stage_details": self.stage_details,
            }, f, indent=2, ensure_ascii=False)

    def mark_running(self, stage: str):
        self.current_stage = stage
        self.error = None
        self.save()

    def mark_completed(self, stage: str, metadata: dict = None):
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)
        self.current_stage = None
        if metadata:
            self.stage_details[stage] = metadata
        self.save()

    def mark_error(self, stage: str, error: str):
        self.current_stage = None
        self.error = f"[{stage}] {error}"
        self.save()

    def reset_from(self, stage: str):
        idx = self.completed_stages.index(stage) if stage in self.completed_stages else len(self.completed_stages)
        self.completed_stages = self.completed_stages[:idx]
        self.current_stage = None
        self.error = None
        self.save()


class DubbingPipeline:
    def __init__(self, project_id: str | None = None, config: Config = None):
        self.config = config or Config()
        self.config.ensure_dirs()

        if project_id is None:
            project_id = generate_project_id()
        self.project_id = project_id
        self.project_dir = self.config.PROJECTS_DIR / project_id
        self.state = PipelineState(self.project_dir)

    def setup_project(self, video_path: str) -> str:
        """Create project directory and copy video to input/."""
        ensure_project_dirs(self.project_dir)
        video_src = Path(video_path)
        video_dst = self.project_dir / "input" / video_src.name
        if not video_dst.exists():
            import shutil
            logger.info(f"[SETUP] Copying video: {video_src} -> {video_dst}")
            shutil.copy(video_src, video_dst)
        logger.info(f"[SETUP] Project ID: {self.project_id} | Dir: {self.project_dir}")
        return self.project_id

    def run_all(
        self,
        progress_callback: Callable = None,
        skip_stages: list[str] = None,
    ) -> dict:
        """Run full pipeline from start or from last completed stage."""
        skip_stages = skip_stages or []
        stage_order = self.config.STAGE_ORDER
        weights = self.config.STAGE_WEIGHTS

        # Calculate progress offsets
        completed = self.state.completed_stages
        offset = sum(weights.get(s, 0) for s in completed)

        stages_to_run = [
            s for s in stage_order
            if s not in completed and s not in skip_stages
        ]

        # Skip separation if disabled
        if not self.config.enable_vocal_separation and "separate" in stages_to_run:
            stages_to_run.remove("separate")
            self.state.mark_completed("separate", metadata={"skipped": True})

        results = {}
        cumulative_weight = offset
        total_stages = len(stages_to_run)
        pipeline_start = time.time()

        for idx, stage_name in enumerate(stages_to_run):
            stage_weight = weights.get(stage_name, 0.1)
            display = self.config.STAGE_NAMES.get(stage_name, stage_name)

            def stage_progress(frac, desc=""):
                if progress_callback:
                    total_frac = cumulative_weight + frac * stage_weight
                    progress_callback(total_frac, desc)

            self.state.mark_running(stage_name)
            stage_fn = STAGE_FUNCTIONS[stage_name]
            logger.info(f"[{stage_name.upper()}] Starting stage: {display} ({idx + 1}/{total_stages})")

            stage_start = time.time()
            try:
                result = stage_fn(self.project_dir, self.config, progress=stage_progress)
                stage_time = time.time() - stage_start
                if result.success:
                    self.state.mark_completed(stage_name, metadata={
                        "paths": [str(p) for p in result.output_paths],
                        **result.metadata,
                    })
                    results[stage_name] = result
                    pipeline_elapsed = time.time() - pipeline_start
                    logger.info(
                        f"[{stage_name.upper()}] Completed in {stage_time:.1f}s | "
                        f"pipeline total {pipeline_elapsed:.1f}s | "
                        f"stages done {idx + 1}/{total_stages}"
                    )
                else:
                    self.state.mark_error(stage_name, result.error)
                    results[stage_name] = result
                    logger.error(f"[{stage_name.upper()}] FAILED after {stage_time:.1f}s: {result.error}")
                    if progress_callback:
                        progress_callback(1.0, f"Error in {stage_name}: {result.error}")
                    return results
            except Exception as e:
                stage_time = time.time() - stage_start
                self.state.mark_error(stage_name, str(e))
                from utils import StageResult
                results[stage_name] = StageResult(success=False, error=str(e))
                logger.error(f"[{stage_name.upper()}] EXCEPTION after {stage_time:.1f}s: {e}")
                if progress_callback:
                    progress_callback(1.0, f"Error in {stage_name}: {str(e)}")
                return results

            cumulative_weight += stage_weight

        total_time = time.time() - pipeline_start
        logger.info(f"[PIPELINE] All stages complete in {total_time:.1f}s!")
        if progress_callback:
            progress_callback(1.0, desc=f"Dubbing complete in {total_time:.1f}s!")

        return results

    def run_stage(self, stage_name: str, progress_callback: Callable = None) -> object:
        """Run a single stage."""
        self.state.reset_from(stage_name)
        stage_fn = STAGE_FUNCTIONS.get(stage_name)
        if not stage_fn:
            return type('StageResult', (), {'success': False, 'error': f'Unknown stage: {stage_name}'})()

        self.state.mark_running(stage_name)
        try:
            result = stage_fn(self.project_dir, self.config, progress=progress_callback)
            if result.success:
                self.state.mark_completed(stage_name)
            else:
                self.state.mark_error(stage_name, result.error)
            return result
        except Exception as e:
            self.state.mark_error(stage_name, str(e))
            from utils import StageResult
            return StageResult(success=False, error=str(e))

    def get_status(self) -> dict:
        """Get current pipeline status for the diagnostic dashboard."""
        return {
            "project_id": self.project_id,
            "completed_stages": self.state.completed_stages,
            "current_stage": self.state.current_stage,
            "error": self.state.error,
            "stage_details": self.state.stage_details,
            "stages": [
                {
                    "name": s,
                    "display": self.config.STAGE_NAMES.get(s, s),
                    "status": "completed" if s in self.state.completed_stages
                    else "running" if s == self.state.current_stage
                    else "pending",
                }
                for s in self.config.STAGE_ORDER
            ],
        }