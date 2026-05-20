"""Flask server with SSE for real-time pipeline progress."""

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from queue import Queue
from threading import Thread, Lock, Condition

from flask import Flask, request, jsonify, Response, send_file, send_from_directory
from flask_cors import CORS

os.environ["COQUI_TOS_AGREED"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from config import Config
from pipeline import DubbingPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("server")

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024 * 1024  # 10GB upload limit

CONFIG = Config()
CONFIG.ensure_dirs()

# Active SSE queues keyed by session_id
sse_queues: dict[str, Queue] = {}


# ── Job Queue ─────────────────────────────────────────────────────────

class JobQueue:
    """In-memory FIFO queue that serializes GPU pipeline execution."""

    def __init__(self):
        self._lock = Lock()
        self._queue: list[dict] = []
        self._active: dict | None = None
        self._done: list[dict] = []
        self._counter = 0

    def enqueue(self, session_id: str, project_id: str, filename: str, run_fn) -> int:
        with self._lock:
            self._counter += 1
            job = {
                "id": self._counter,
                "session_id": session_id,
                "project_id": project_id,
                "filename": filename,
                "run_fn": run_fn,
                "status": "queued",
                "progress": 0.0,
                "stage": "",
                "started_at": None,
            }
            if self._active is None:
                self._active = job
                job["status"] = "running"
                job["started_at"] = time.time()
                position = 0
                Thread(target=self._execute, args=(job,), daemon=True).start()
            else:
                self._queue.append(job)
                position = len(self._queue)
            return position

    def update_job(self, session_id: str, progress: float, stage: str):
        with self._lock:
            if self._active and self._active["session_id"] == session_id:
                self._active["progress"] = progress
                self._active["stage"] = stage

    def _execute(self, job: dict):
        try:
            job["run_fn"]()
        finally:
            # Force garbage collection between jobs to free GPU/CPU memory
            import gc
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
            except Exception:
                pass
            with self._lock:
                job["status"] = "done"
                self._done.append(job)
                if len(self._done) > 20:
                    self._done = self._done[-20:]
                self._active = None
                # Clean up SSE queue for completed job to avoid memory leak
                sse_queues.pop(job["session_id"], None)
                if self._queue:
                    next_job = self._queue.pop(0)
                    self._active = next_job
                    next_job["status"] = "running"
                    next_job["started_at"] = time.time()
                    sse_send(next_job["session_id"], "queue_start", {
                        "position": 0,
                        "message": "Seu video esta sendo processado",
                    })
                    Thread(target=self._execute, args=(next_job,), daemon=True).start()

    def get_position(self, session_id: str) -> dict:
        with self._lock:
            if self._active and self._active["session_id"] == session_id:
                return {"status": "running", "position": 0}
            for i, job in enumerate(self._queue):
                if job["session_id"] == session_id:
                    return {"status": "queued", "position": i + 1}
            return {"status": "unknown", "position": -1}

    def get_all_jobs(self) -> list[dict]:
        with self._lock:
            jobs = []
            if self._active:
                a = dict(self._active)
                a.pop("run_fn", None)
                jobs.append(a)
            for j in self._queue:
                s = dict(j)
                s.pop("run_fn", None)
                jobs.append(s)
            for j in self._done[-10:]:
                s = dict(j)
                s.pop("run_fn", None)
                jobs.append(s)
            return jobs

    @property
    def queue_length(self) -> int:
        with self._lock:
            return len(self._queue)


job_queue = JobQueue()


# ── SSE helpers ──────────────────────────────────────────────────────

def sse_send(session_id: str, event: str, data: dict):
    """Push an event to all listeners for a session."""
    q = sse_queues.get(session_id)
    if q:
        q.put((event, data))


def progress_callback_factory(session_id: str):
    """Return a progress callback that pushes SSE events."""
    def cb(frac: float, desc: str = ""):
        sse_send(session_id, "progress", {"frac": round(frac, 4), "desc": desc})
    return cb


# ── Routes ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/test")
def test_page():
    return send_from_directory("static", "test.html")


@app.route("/api/upload", methods=["POST"])
def upload():
    """Upload a video file and return a project_id."""
    logger.info(f"[UPLOAD] Request files: {list(request.files.keys())}")
    logger.info(f"[UPLOAD] Content-Length: {request.content_length}")
    if "video" not in request.files:
        logger.error(f"[UPLOAD] No 'video' in request. Keys: {list(request.files.keys())}")
        return jsonify({"error": "No video file provided"}), 400
    f = request.files["video"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    ext = Path(f.filename).suffix.lower()
    if ext not in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        return jsonify({"error": f"Unsupported format: {ext}"}), 400

    project_id = uuid.uuid4().hex[:12]
    project_dir = CONFIG.PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "input").mkdir(exist_ok=True)
    (project_dir / "output").mkdir(exist_ok=True)

    dest = project_dir / "input" / f.filename
    f.save(str(dest))

    return jsonify({"project_id": project_id, "filename": f.filename})


@app.route("/api/jobs")
def list_jobs():
    """List all queue jobs (active, queued, recent done)."""
    return jsonify({"jobs": job_queue.get_all_jobs()})


@app.route("/api/start", methods=["POST"])
def start_pipeline():
    """Start the dubbing pipeline for a project (queued)."""
    data = request.json or {}
    project_id = data.get("project_id")
    if not project_id:
        return jsonify({"error": "project_id required"}), 400

    session_id = data.get("session_id", project_id)
    filename = data.get("filename", "video")
    config = Config()
    config.ensure_dirs()

    # Apply settings from request
    config.enable_vocal_separation = data.get("vocal_separation", True)
    config.tts_engine = data.get("tts_engine", "xtts")
    config.TRANSLATION_ENGINE = data.get("translation_engine", "opus-mt")
    config.OLLAMA_MODEL = data.get("ollama_model", "llama3.2")
    config.EDGE_TTS_VOICE = data.get("edge_voice", "pt-BR-ThalitaMultilingualNeural")
    config.BACKGROUND_VOLUME = float(data.get("bg_volume", 0.7))
    config.DUB_VOLUME = float(data.get("dub_volume", 1.0))
    config.MAX_SPEED_RATIO = float(data.get("max_speed", 1.5))
    config.STRETCH_METHOD = data.get("stretch_method", "atempo")
    config.WORDS_PER_CUE = int(data.get("words_per_cue", 7))
    config.MAX_WORDS_PER_CUE = max(config.MAX_WORDS_PER_CUE, config.WORDS_PER_CUE)
    config.MAX_CHARS_PER_CUE = int(data.get("max_chars_per_cue", 45))
    config.MIN_CUE_DURATION = float(data.get("min_cue_duration", 1.0))
    config.MIN_CUE_GAP = float(data.get("min_cue_gap", 0.08))
    config.MAX_CUE_DURATION = float(data.get("max_cue_duration", 10.0))

    reference_audio = data.get("reference_audio")
    if reference_audio:
        config.reference_audio_path = reference_audio

    # Set up SSE queue
    q = Queue(maxsize=200)
    sse_queues[session_id] = q

    def run_pipeline():
        try:
            pipeline = DubbingPipeline(project_id=project_id, config=config)
            project_dir = CONFIG.PROJECTS_DIR / project_id
            video_files = list((project_dir / "input").glob("*"))
            if not video_files:
                sse_send(session_id, "error", {"message": "No video found in input/"})
                return

            video_path = str(video_files[0])
            pipeline.setup_project(video_path)

            stage_names = {
                "extract": "Extrair Audio", "separate": "Separar Vocais",
                "transcribe": "Transcrever", "translate": "Traduzir",
                "synthesize": "Sintetizar Voz", "sync": "Sincronizar", "merge": "Mesclar Video",
            }

            # Custom run with per-stage SSE events
            completed = pipeline.state.completed_stages
            stages_to_run = [s for s in config.STAGE_ORDER if s not in completed]
            if not config.enable_vocal_separation and "separate" in stages_to_run:
                stages_to_run.remove("separate")

            start_time = time.time()

            for stage_name in stages_to_run:
                display = stage_names.get(stage_name, stage_name)
                sse_send(session_id, "stage_start", {
                    "stage": stage_name, "display": display,
                    "stages_done": len(pipeline.state.completed_stages),
                    "stages_total": len(stages_to_run),
                })

                pipeline.state.mark_running(stage_name)
                from pipeline import STAGE_FUNCTIONS

                def stage_progress(frac, desc=""):
                    total_stages = len(stages_to_run)
                    done = len(pipeline.state.completed_stages)
                    overall = (done + frac) / total_stages
                    elapsed = time.time() - start_time
                    eta = (elapsed / max(overall, 0.01)) * (1 - overall) if overall > 0.05 else 0
                    job_queue.update_job(session_id, overall, display)
                    sse_send(session_id, "progress", {
                        "frac": round(overall, 4),
                        "stage_frac": round(frac, 4),
                        "desc": f"{display}: {desc}" if desc else display,
                        "elapsed": round(elapsed, 1),
                        "eta": round(max(eta, 0), 1),
                        "stage": stage_name,
                    })

                stage_fn = STAGE_FUNCTIONS[stage_name]
                result = stage_fn(pipeline.project_dir, config, progress=stage_progress)

                if result.success:
                    pipeline.state.mark_completed(stage_name, metadata=result.metadata or {})
                    stage_time = time.time() - start_time
                    sse_send(session_id, "stage_done", {
                        "stage": stage_name, "display": display,
                        "warnings": result.metadata.get("warnings", []) if result.metadata else [],
                        "elapsed_total": round(stage_time, 1),
                    })
                else:
                    pipeline.state.mark_error(stage_name, result.error or "Unknown error")
                    sse_send(session_id, "stage_error", {
                        "stage": stage_name, "display": display,
                        "error": result.error or "Unknown error",
                    })
                    return

            total_time = time.time() - start_time

            # Include output files in done event
            output_dir = CONFIG.PROJECTS_DIR / project_id / "output"
            result_files = {}
            if output_dir.exists():
                for f in output_dir.iterdir():
                    if f.is_file():
                        result_files[f.name] = f"/api/file/{project_id}/{f.name}"

            sse_send(session_id, "done", {
                "total_time": round(total_time, 1),
                "project_id": project_id,
                "files": result_files,
            })

        except Exception as e:
            logger.exception("Pipeline error")
            sse_send(session_id, "error", {"message": str(e)})

    # Enqueue instead of spawning directly
    position = job_queue.enqueue(session_id, project_id, filename, run_pipeline)

    result = {"status": "started", "project_id": project_id}
    if position > 0:
        result["queue_position"] = position
        sse_send(session_id, "queue", {"position": position, "message": f"Aguardando na fila - posicao {position}"})

    return jsonify(result)


@app.route("/api/queue/<session_id>")
def queue_status(session_id):
    return jsonify(job_queue.get_position(session_id))


@app.route("/api/events/<session_id>")
def sse_stream(session_id):
    """SSE endpoint for real-time progress."""
    # Don't overwrite the queue if start_pipeline already created one
    if session_id not in sse_queues:
        sse_queues[session_id] = Queue(maxsize=200)

    def generate():
        while True:
            try:
                event, data = sse_queues[session_id].get(timeout=300)
                yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
                if event in ("done", "error"):
                    break
            except Exception:
                yield f"event: ping\ndata: {{}}\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


@app.route("/api/result/<project_id>")
def get_result(project_id):
    """Get pipeline results and file paths."""
    project_dir = CONFIG.PROJECTS_DIR / project_id
    if not project_dir.exists():
        return jsonify({"error": "Project not found"}), 404

    work_dir = project_dir / "work"
    output_dir = project_dir / "output"

    result = {"project_id": project_id}

    # Check which files exist — return URLs instead of absolute paths
    # Find the output video (name varies: *_dublado_pt.mp4)
    video_file = None
    if output_dir.exists():
        for f in output_dir.iterdir():
            if f.is_file() and f.suffix.lower() == ".mp4" and "_dublado_pt" in f.name:
                video_file = f
                break
        if not video_file:
            # Fallback to old naming
            fallback = output_dir / "dubbed_video.mp4"
            if fallback.exists():
                video_file = fallback

    file_map = {
        "vocals": work_dir / "vocals.wav",
        "background": work_dir / "background.wav",
        "dubbed_vocals": work_dir / "dubbed_vocals.wav",
        "final_audio": work_dir / "final_audio.wav",
        "en_srt": work_dir / "en.srt",
        "pt_srt": work_dir / "pt.srt",
        "video": video_file,
        "pt_vtt": output_dir / "pt.vtt",
        "en_vtt": output_dir / "en.vtt",
    }

    result["files"] = {}
    for name, path in file_map.items():
        if path and path.exists():
            # Use relative URL instead of absolute filesystem path
            # Determine subdir (work/ or output/)
            if path.parent.name == "output":
                result["files"][name] = f"/api/file/{project_id}/output/{path.name}"
            elif path.parent.name == "work":
                result["files"][name] = f"/api/file/{project_id}/work/{path.name}"
            else:
                result["files"][name] = None
        else:
            result["files"][name] = None

    # Read SRT content
    for srt_name in ("en_srt", "pt_srt"):
        path = file_map[srt_name]
        if path and path.exists():
            with open(path, "r", encoding="utf-8") as f:
                result[srt_name + "_content"] = f.read()
        else:
            result[srt_name + "_content"] = ""

    # Pipeline state
    state_file = project_dir / "state.json"
    if state_file.exists():
        with open(state_file, "r", encoding="utf-8") as f:
            result["state"] = json.load(f)
    else:
        result["state"] = None

    return jsonify(result)


@app.route("/api/file/<project_id>/<path:filepath>")
def serve_file(project_id, filepath):
    """Serve a file from a project directory (output/ or work/)."""
    if ".." in filepath or filepath.startswith("/"):
        return jsonify({"error": "Invalid path"}), 400

    project_dir = CONFIG.PROJECTS_DIR / project_id
    full_path = project_dir / filepath
    if not full_path.exists() or not full_path.is_file():
        return jsonify({"error": "File not found"}), 404

    # Set correct MIME type for VTT subtitles
    mime_map = {
        ".vtt": "text/vtt",
        ".srt": "text/plain",
        ".mp4": "video/mp4",
        ".wav": "audio/wav",
        ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
    }
    ext = Path(filepath).suffix.lower()
    mimetype = mime_map.get(ext)
    return send_file(str(full_path), mimetype=mimetype)


@app.route("/api/config", methods=["GET"])
def get_config():
    """Return current configuration defaults."""
    return jsonify({
        "words_per_cue": CONFIG.WORDS_PER_CUE,
        "max_words_per_cue": CONFIG.MAX_WORDS_PER_CUE,
        "max_chars_per_cue": CONFIG.MAX_CHARS_PER_CUE,
        "min_cue_duration": CONFIG.MIN_CUE_DURATION,
        "max_cue_duration": CONFIG.MAX_CUE_DURATION,
        "max_speed_ratio": CONFIG.MAX_SPEED_RATIO,
        "min_speed_ratio": CONFIG.MIN_SPEED_RATIO,
        "stretch_method": CONFIG.STRETCH_METHOD,
        "background_volume": CONFIG.BACKGROUND_VOLUME,
        "dub_volume": CONFIG.DUB_VOLUME,
        "tts_engine": CONFIG.tts_engine,
        "edge_voice": CONFIG.EDGE_TTS_VOICE,
        "vocal_separation": CONFIG.enable_vocal_separation,
    })


if __name__ == "__main__":
    print("\n  +======================================+")
    print("  |     LuminaDub AI - Server v2.1       |")
    print("  |     http://localhost:5000            |")
    print("  +======================================+\n")
    try:
        from waitress import serve as waitress_serve
        print("  Using waitress (production WSGI server)")
        waitress_serve(app, host="0.0.0.0", port=5000, threads=4, max_request_body_size=10*1024*1024*1024)
    except ImportError:
        print("  Using Flask dev server (install waitress for stability)")
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)