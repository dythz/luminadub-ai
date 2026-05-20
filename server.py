"""Flask server with SSE for real-time pipeline progress."""

import asyncio
import json
import logging
import multiprocessing as mp
import os
import time
import uuid
from pathlib import Path
from queue import Queue
from threading import Thread, Lock

from flask import Flask, request, jsonify, Response, send_file, send_from_directory
from flask_cors import CORS

os.environ["COQUI_TOS_AGREED"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"

# Ensure spawned worker subprocesses can import project modules from this directory.
# mp.get_context("spawn") starts a fresh Python interpreter that does NOT inherit
# sys.path from the parent — it only sees site-packages unless PYTHONPATH is set.
_APP_DIR = str(Path(__file__).parent.resolve())
if _APP_DIR not in os.environ.get("PYTHONPATH", "").split(os.pathsep):
    os.environ["PYTHONPATH"] = _APP_DIR + os.pathsep + os.environ.get("PYTHONPATH", "")

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

# Clean up any stale chunk directories left by interrupted uploads
def _cleanup_stale_chunks():
    import shutil
    try:
        for chunks_dir in CONFIG.PROJECTS_DIR.glob("*/chunks"):
            shutil.rmtree(str(chunks_dir), ignore_errors=True)
            logger.info(f"[STARTUP] Removed stale chunks: {chunks_dir}")
    except Exception:
        pass
_cleanup_stale_chunks()

# Active SSE queues keyed by session_id
sse_queues: dict[str, Queue] = {}


# ── Job Queue ─────────────────────────────────────────────────────────

class JobQueue:
    """FIFO queue that runs each video pipeline in an isolated subprocess.
    If the GPU crashes in one job, only that subprocess dies — the server keeps running."""

    MAX_JOB_SECONDS = 7200  # 2 hour hard limit per job

    def __init__(self):
        self._lock = Lock()
        self._queue: list[dict] = []
        self._active: dict | None = None
        self._done: list[dict] = []
        self._counter = 0

    def enqueue(self, session_id: str, project_id: str, filename: str, config_overrides: dict) -> int:
        with self._lock:
            self._counter += 1
            job = {
                "id": self._counter,
                "session_id": session_id,
                "project_id": project_id,
                "filename": filename,
                "config_overrides": config_overrides,
                "status": "queued",
                "progress": 0.0,
                "stage": "",
                "started_at": None,
            }
            if self._active is None:
                self._active = job
                job["status"] = "running"
                job["started_at"] = time.time()
                Thread(target=self._execute, args=(job,), daemon=True).start()
                return 0
            else:
                self._queue.append(job)
                return len(self._queue)

    def update_job(self, session_id: str, progress: float, stage: str):
        with self._lock:
            if self._active and self._active["session_id"] == session_id:
                self._active["progress"] = progress
                self._active["stage"] = stage

    def _execute(self, job: dict):
        p = None
        event_queue = None
        try:
            import worker as _worker_module
            ctx = mp.get_context("spawn")
            event_queue = ctx.Queue()
            p = ctx.Process(
                target=_worker_module.run,
                args=(job["project_id"], job["session_id"], job["config_overrides"], event_queue),
                daemon=False,
            )
            p.start()
            logger.info(f"[WORKER] PID {p.pid} started for job {job['id']} ({job['filename']})")
            job_start = time.time()

            while True:
                # Hard timeout
                if time.time() - job_start > self.MAX_JOB_SECONDS:
                    logger.error(f"[WORKER] Job {job['id']} timed out, killing PID {p.pid}")
                    p.terminate()
                    p.join(timeout=10)
                    if p.is_alive():
                        p.kill()
                    sse_send(job["session_id"], "error", {"message": "Job atingiu limite de 2 horas e foi cancelado."})
                    break

                p.join(timeout=0)
                if not p.is_alive():
                    # Drain remaining events
                    while not event_queue.empty():
                        try:
                            sid, event, data = event_queue.get_nowait()
                            self.update_job(sid, data.get("frac", 0), data.get("desc", ""))
                            sse_send(sid, event, data)
                        except Exception:
                            pass
                    if p.exitcode not in (0, None):
                        logger.error(f"[WORKER] PID {p.pid} crashed with exit code {p.exitcode}")
                        sse_send(job["session_id"], "error", {
                            "message": f"GPU travou (exit {p.exitcode}). Tente reenviar o video."
                        })
                    break

                # Forward progress events
                try:
                    sid, event, data = event_queue.get(timeout=0.5)
                    self.update_job(sid, data.get("frac", 0), data.get("desc", ""))
                    sse_send(sid, event, data)
                except Exception:
                    pass

        except Exception as e:
            logger.exception(f"[WORKER] Job {job['id']} failed: {e}")
            sse_send(job["session_id"], "error", {"message": f"Erro ao processar video: {e}"})
        finally:
            try:
                if p is not None and p.is_alive():
                    p.kill()
                    p.join(timeout=5)
            except Exception:
                pass

            with self._lock:
                job["status"] = "done"
                self._done.append(job)
                if len(self._done) > 20:
                    self._done = self._done[-20:]
                self._active = None
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
    """Push an event to all listeners for a session (non-blocking — drops if client disconnected)."""
    q = sse_queues.get(session_id)
    if q:
        try:
            q.put_nowait((event, data))
        except Exception:
            pass  # client disconnected or queue full — never block the job thread


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


@app.route("/api/upload/chunk", methods=["POST"])
def upload_chunk():
    """Receive one 48 MB chunk of a large file upload and reassemble when complete."""
    import shutil
    project_id = request.form.get("project_id", "")
    chunk_index = int(request.form.get("chunk_index", 0))
    total_chunks = int(request.form.get("total_chunks", 1))
    filename = request.form.get("filename", "video.mp4")
    chunk = request.files.get("chunk")

    if not chunk:
        return jsonify({"error": "No chunk data"}), 400

    ext = Path(filename).suffix.lower()
    if ext not in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        return jsonify({"error": f"Unsupported format: {ext}"}), 400

    if not project_id:
        project_id = uuid.uuid4().hex[:12]

    project_dir = CONFIG.PROJECTS_DIR / project_id
    chunks_dir = project_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "input").mkdir(exist_ok=True)
    (project_dir / "output").mkdir(exist_ok=True)

    chunk_path = chunks_dir / f"chunk_{chunk_index:05d}"
    chunk.save(str(chunk_path))
    logger.info(f"[UPLOAD] Chunk {chunk_index+1}/{total_chunks} for {filename} (project {project_id})")

    received = len(list(chunks_dir.glob("chunk_*")))
    if received >= total_chunks:
        dest = project_dir / "input" / filename
        with open(str(dest), "wb") as out:
            for i in range(total_chunks):
                cp = chunks_dir / f"chunk_{i:05d}"
                with open(str(cp), "rb") as cf:
                    out.write(cf.read())
        shutil.rmtree(str(chunks_dir))
        logger.info(f"[UPLOAD] Assembled {filename} ({dest.stat().st_size // 1024 // 1024} MB)")
        return jsonify({"project_id": project_id, "filename": filename, "complete": True})

    return jsonify({"project_id": project_id, "chunk_index": chunk_index, "received": received, "complete": False})


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

    words_per_cue = int(data.get("words_per_cue", 7))
    config_overrides = {
        "enable_vocal_separation": data.get("vocal_separation", True),
        "tts_engine": data.get("tts_engine", "xtts"),
        "TRANSLATION_ENGINE": data.get("translation_engine", "opus-mt"),
        "OLLAMA_MODEL": data.get("ollama_model", "llama3.2"),
        "EDGE_TTS_VOICE": data.get("edge_voice", "pt-BR-ThalitaMultilingualNeural"),
        "BACKGROUND_VOLUME": float(data.get("bg_volume", 0.7)),
        "DUB_VOLUME": float(data.get("dub_volume", 1.0)),
        "MAX_SPEED_RATIO": float(data.get("max_speed", 1.5)),
        "STRETCH_METHOD": data.get("stretch_method", "atempo"),
        "WORDS_PER_CUE": words_per_cue,
        "MAX_WORDS_PER_CUE": max(int(data.get("max_words_per_cue", 10)), words_per_cue),
        "MAX_CHARS_PER_CUE": int(data.get("max_chars_per_cue", 45)),
        "MIN_CUE_DURATION": float(data.get("min_cue_duration", 1.0)),
        "MIN_CUE_GAP": float(data.get("min_cue_gap", 0.08)),
        "MAX_CUE_DURATION": float(data.get("max_cue_duration", 10.0)),
    }
    if data.get("reference_audio"):
        config_overrides["reference_audio_path"] = data["reference_audio"]

    # Set up SSE queue
    q = Queue(maxsize=500)
    sse_queues[session_id] = q

    position = job_queue.enqueue(session_id, project_id, filename, config_overrides)

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
        sse_queues[session_id] = Queue(maxsize=500)

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