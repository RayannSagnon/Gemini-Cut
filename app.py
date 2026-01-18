import json
import os
import shutil
import smtplib
import subprocess
import threading
import time
import uuid
from email.message import EmailMessage
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google import genai

from ai.elevenlabs_client import (
    audio_isolation,
    list_voices,
    music_generation,
    sound_effects,
    speech_to_speech,
    speech_to_text,
    text_to_speech,
    voice_generation,
)
from ai.gemini_plan import get_plan
from ai.visual_assets import generate_visual_assets
from editing.captions_ass import build_ass
from editing.ffmpeg_engine import (
    apply_overlays,
    apply_transitions,
    build_video_filter,
    concat_clips,
    render_final,
)
from editing.plan_validation import clamp_duration_to_range, normalize_segments
from media_ingest import (
    IngestError,
    download_url,
    inspect_url,
    sanitize_url_for_logs,
    verify_video,
)
from utils.logging import append_log, init_job_dir, write_json
import traceback


APP_DIR = Path(__file__).parent
UPLOADS_DIR = APP_DIR / "uploads"
RUNS_DIR = APP_DIR / "runs"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
RUNS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
app.mount("/images", StaticFiles(directory=str(APP_DIR / "images")), name="images")
REACT_DIST = APP_DIR / "frontend" / "dist"
if REACT_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(REACT_DIST / "assets")), name="assets")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/start", "/start_from_url", "/analyze_url")):
        print(f"{request.method} {request.url.path} -> {response.status_code}")
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"Validation error on {request.url.path}: {exc}")
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


JOBS = {}
JOB_LOCK = threading.Lock()

MODEL_NAME = "gemini-2.5-flash"
MAX_URL_BYTES = 800 * 1024 * 1024
ALLOW_PLATFORM_DL = os.getenv("ENABLE_PLATFORM_DL", "false").lower() == "true"
ELEVENLABS_DEFAULT_VOICE = os.getenv("ELEVENLABS_VOICE_ID")

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)

ALLOWED_PLATFORMS = {"Shorts", "TikTok", "Reels"}
ALLOWED_STYLES = {"Energique", "Pro", "Storytelling", "Tutorial"}
ALLOWED_CUTS = {"Soft", "Medium", "Hard"}
ALLOWED_LANGS = {"FR", "EN"}
ALLOWED_CAPTIONS = {"ON", "OFF"}
ALLOWED_RES = {"1080x1920", "720x1280"}
ALLOWED_PRESETS = {"auto", "podcast", "facecam", "screen", "vlog"}
ALLOWED_REFRAME = {"center", "smart"}
ALLOWED_FPS = {24, 30, 60}
ALLOWED_FILTERS = {"none", "clean", "cinematic", "vibrant", "bw", "retro", "sharp", "soft"}
ALLOWED_CAPTION_TEMPLATES = {"tiktok_bold", "minimal", "creator", "high_contrast"}
ALLOWED_CAPTION_POSITIONS = {"bottom", "center", "top"}
ALLOWED_CAPTION_SIZES = {"sm", "md", "lg"}
ALLOWED_TRANSITIONS = {"auto", "none", "fade", "crossfade", "dip_black", "swipe"}
ALLOWED_VOICEOVER_MODES = {"replace", "mix", "duck"}


def normalize_transition_type(value: str) -> str:
    if value is None:
        return "auto"
    normalized = str(value).strip().lower()
    aliases = {
        "auto (gemini)": "auto",
        "auto_gemini": "auto",
        "cross-fade": "crossfade",
        "cross fade": "crossfade",
        "dip to black": "dip_black",
        "dip_black": "dip_black",
        "swipe": "swipe",
        "fade": "fade",
        "none": "none",
        "auto": "auto",
    }
    if normalized in aliases:
        return aliases[normalized]
    return normalized


def validate_opts(opts):
    if opts["duration_s"] < 30 or opts["duration_s"] > 60:
        raise HTTPException(status_code=400, detail="Duration must be 30-60 seconds.")
    if opts["platform"] not in ALLOWED_PLATFORMS:
        raise HTTPException(status_code=400, detail="Invalid platform.")
    if opts["style"] not in ALLOWED_STYLES:
        raise HTTPException(status_code=400, detail="Invalid style.")
    if opts["cut_intensity"] not in ALLOWED_CUTS:
        raise HTTPException(status_code=400, detail="Invalid cut intensity.")
    if opts["language"] not in ALLOWED_LANGS:
        raise HTTPException(status_code=400, detail="Invalid language.")
    if opts["captions"] not in ALLOWED_CAPTIONS:
        raise HTTPException(status_code=400, detail="Invalid captions option.")
    if opts["resolution"] not in ALLOWED_RES:
        raise HTTPException(status_code=400, detail="Invalid resolution.")
    if opts["content_preset"] not in ALLOWED_PRESETS:
        raise HTTPException(status_code=400, detail="Invalid content preset.")
    if opts["output_resolution"] not in ALLOWED_RES:
        raise HTTPException(status_code=400, detail="Invalid output resolution.")
    if opts["reframe_mode"] not in ALLOWED_REFRAME:
        raise HTTPException(status_code=400, detail="Invalid reframe mode.")
    if int(opts["fps"]) not in ALLOWED_FPS:
        raise HTTPException(status_code=400, detail="Invalid fps.")
    if opts["filter_preset"] not in ALLOWED_FILTERS:
        raise HTTPException(status_code=400, detail="Invalid filter preset.")
    if opts["caption_template"] not in ALLOWED_CAPTION_TEMPLATES:
        raise HTTPException(status_code=400, detail="Invalid caption template.")
    if opts["caption_position"] not in ALLOWED_CAPTION_POSITIONS:
        raise HTTPException(status_code=400, detail="Invalid caption position.")
    if opts["caption_size"] not in ALLOWED_CAPTION_SIZES:
        raise HTTPException(status_code=400, detail="Invalid caption size.")
    opts["transition_type"] = normalize_transition_type(opts.get("transition_type"))
    if opts["transition_type"] not in ALLOWED_TRANSITIONS:
        opts["transition_type"] = "auto"
    if opts.get("voiceover_mode") not in ALLOWED_VOICEOVER_MODES:
        raise HTTPException(status_code=400, detail="Invalid voiceover mode.")


def update_job(job_id, **fields):
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.update(fields)


def send_ready_email(to_email: str, job_id: str):
    if not (SMTP_HOST and SMTP_FROM):
        raise RuntimeError("SMTP is not configured.")
    message = EmailMessage()
    message["Subject"] = "Your Gemini Cut video is ready"
    message["From"] = SMTP_FROM
    message["To"] = to_email
    message.set_content(
        "Your video is ready.\n"
        f"Download: http://localhost:8000/download/{job_id}\n"
    )
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
        server.ehlo()
        if SMTP_USER and SMTP_PASS:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
        server.send_message(message)


def elevenlabs_enabled():
    return bool(os.getenv("ELEVENLABS_API_KEY"))


def build_srt_from_stt(stt_result):
    segments = stt_result.get("segments") or stt_result.get("data") or []
    if not segments and stt_result.get("words"):
        words = stt_result.get("words", [])
        segments = []
        chunk = []
        for word in words:
            chunk.append(word)
            if len(chunk) >= 6:
                segments.append(chunk)
                chunk = []
        if chunk:
            segments.append(chunk)
        srt_lines = []
        for idx, group in enumerate(segments, start=1):
            start = float(group[0].get("start", 0))
            end = float(group[-1].get("end", start + 0.5))
            text = " ".join(w.get("word", "") for w in group).strip()
            if not text:
                continue
            srt_lines.append(
                f"{idx}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}\n"
            )
        return "\n".join(srt_lines).strip()
    if segments:
        srt_lines = []
        idx = 1
        for seg in segments:
            start = float(seg.get("start", 0))
            end = float(seg.get("end", start + 0.5))
            text = seg.get("text") or seg.get("transcript") or ""
            text = str(text).strip()
            if not text:
                continue
            srt_lines.append(
                f"{idx}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}\n"
            )
            idx += 1
        return "\n".join(srt_lines).strip()
    return ""


def format_srt_time(seconds: float) -> str:
    millis = int(seconds * 1000)
    hours = millis // 3600000
    millis %= 3600000
    minutes = millis // 60000
    millis %= 60000
    secs = millis // 1000
    ms = millis % 1000
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def get_file_by_name(client, file_name):
    try:
        return client.files.get(name=file_name)
    except TypeError:
        pass
    try:
        return client.files.get(file_name=file_name)
    except TypeError:
        pass
    return client.files.get(id=file_name)


def wait_for_file_active(client, file_name, timeout_s=120):
    start = time.time()
    while True:
        file_obj = get_file_by_name(client, file_name)
        state = getattr(file_obj.state, "name", file_obj.state)
        if str(state).upper() == "ACTIVE":
            return file_obj
        if time.time() - start > timeout_s:
            raise RuntimeError("Gemini file processing timeout.")
        time.sleep(1.5)


def upload_file(client, source_path):
    try:
        return client.files.upload(path=str(source_path))
    except TypeError:
        pass
    try:
        return client.files.upload(file=str(source_path))
    except TypeError:
        pass
    with open(source_path, "rb") as handle:
        return client.files.upload(file=handle)


def ensure_ffmpeg_available():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "FFmpeg not found. Please install FFmpeg and ensure it is in PATH."
        )


def extract_audio(source_path: Path, output_path: Path):
    ensure_ffmpeg_available()
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "44100",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def mux_audio(source_video: Path, audio_path: Path, output_path: Path):
    ensure_ffmpeg_available()
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_video),
        "-i",
        str(audio_path),
        "-c:v",
        "copy",
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def apply_audio_speed(source_audio: Path, output_audio: Path, speed: float):
    ensure_ffmpeg_available()
    speed = max(0.5, min(2.0, speed))
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_audio),
        "-filter:a",
        f"atempo={speed}",
        str(output_audio),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def inspect_video(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams") or []
    if not streams:
        return {"width": 0, "height": 0, "r_frame_rate": "0/0"}
    return streams[0]


def render_video_pipeline(source_path, segments, opts, plan, run_dir):
    ensure_ffmpeg_available()
    cmd_log = run_dir / "ffmpeg_commands.txt"
    stderr_log = run_dir / "ffmpeg_stderr.log"
    clip_paths = []
    source_info = inspect_video(source_path)
    target_width = max(
        source_info["width"],
        int(opts.get("output_resolution", "1080x1920").split("x")[0]),
    )
    target_height = int(target_width * 16 / 9)
    opts["target_width"] = target_width
    opts["target_height"] = target_height
    filter_chain = build_video_filter(opts)
    fps = str(opts.get("fps", 30))
    for idx, seg in enumerate(segments):
        clip_path = run_dir / f"clip_{idx}.mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(seg["start"]),
            "-to",
            str(seg["end"]),
            "-i",
            str(source_path),
            "-vf",
            filter_chain,
            "-r",
            fps,
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(clip_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        clip_paths.append(clip_path)

    transition_type = opts.get("transition_type", "none")
    transition_duration = opts.get("transition_duration", 0.3)
    concat_output = run_dir / "concat.mp4"
    try:
        apply_transitions(
            clip_paths,
            transition_type,
            transition_duration,
            concat_output,
            cmd_log,
            stderr_log,
        )
    except Exception:
        concat_clips(clip_paths, concat_output, cmd_log, stderr_log)

    overlays = []
    if opts.get("ai_visuals_enabled"):
        overlays = generate_visual_assets(
            plan.get("ai_visual_suggestions", []),
            run_dir / "assets",
            opts.get("ai_visuals_max_overlays", 2),
            opts.get("ai_visuals_transparent_png", True),
        )

    overlay_output = run_dir / "overlay.mp4"
    try:
        apply_overlays(concat_output, overlays, overlay_output, cmd_log, stderr_log)
    except Exception:
        overlay_output = concat_output

    captions_ass = None
    if opts.get("captions_enabled") and plan.get("captions_srt"):
        ass_text = build_ass(
            plan.get("captions_srt", ""),
            opts.get("output_resolution"),
            opts.get("caption_template"),
            opts.get("caption_position"),
            opts.get("caption_size"),
            opts.get("caption_safe_margin"),
        )
        captions_ass = run_dir / "captions.ass"
        captions_ass.write_text(ass_text, encoding="utf-8")

    output_path = run_dir / "final.mp4"
    render_final(overlay_output, captions_ass, opts, output_path, cmd_log, stderr_log)
    return output_path


FALLBACK_MODELS = ["gemini-2.5-pro", "gemini-2.0-flash"]


def process_job(job_id, source_path, opts, set_queue=True):
    try:
        if set_queue:
            update_job(job_id, status="queued", progress=10)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")

        client = genai.Client(api_key=api_key)

        update_job(job_id, status="analyzing", progress=45)
        uploaded = upload_file(client, source_path)
        file_obj = wait_for_file_active(client, uploaded.name)

        run_dir = init_job_dir(RUNS_DIR, job_id)

        update_job(job_id, status="planning", progress=60)
        plan, prompt = get_plan(client, file_obj, opts, MODEL_NAME, FALLBACK_MODELS)
        append_log(run_dir / "server.log", "Gemini plan generated.")
        write_json(run_dir / "plan_raw.json", plan)
        write_json(run_dir / "opts.json", opts)

        if (
            opts.get("voiceover_enabled")
            and opts.get("voiceover_text")
            and not opts.get("voiceover_path")
        ):
            if not elevenlabs_enabled():
                raise RuntimeError("ELEVENLABS_API_KEY is not set.")
            voice_id = opts.get("voiceover_voice_id") or ELEVENLABS_DEFAULT_VOICE
            if not voice_id:
                raise RuntimeError("ElevenLabs voice_id is missing.")
            speed = float(opts.get("voiceover_speed", 1.0))
            audio_bytes = text_to_speech(
                text=str(opts.get("voiceover_text")).strip(),
                voice_id=voice_id,
                model_id="eleven_multilingual_v2",
                output_format="mp3_44100_128",
            )
            voiceover_path = run_dir / "voiceover.mp3"
            voiceover_path.write_bytes(audio_bytes)
            if abs(speed - 1.0) > 0.01:
                sped_path = run_dir / "voiceover_sped.mp3"
                apply_audio_speed(voiceover_path, sped_path, speed)
                voiceover_path = sped_path
            opts["voiceover_path"] = str(voiceover_path)

        if opts.get("transition_type") in {"auto", "none"}:
            suggested = plan.get("transition")
            if suggested in ALLOWED_TRANSITIONS and suggested != "none":
                opts["transition_type"] = suggested
            else:
                opts["transition_type"] = "fade"

        segments = normalize_segments(plan.get("segments") or [])
        if len(segments) < 2:
            raise RuntimeError("Plan returned insufficient segments.")
        segments, total = clamp_duration_to_range(segments, opts.get("duration_s", 45))
        plan["segments"] = segments
        write_json(run_dir / "plan_normalized.json", plan)

        render_source = source_path

        if opts.get("audio_isolation_enabled"):
            if not elevenlabs_enabled():
                raise RuntimeError("ELEVENLABS_API_KEY is not set.")
            audio_wav = run_dir / "source_audio.wav"
            extract_audio(source_path, audio_wav)
            isolated_bytes = audio_isolation(audio_wav)
            isolated_path = run_dir / "isolated.mp3"
            isolated_path.write_bytes(isolated_bytes)
            isolated_video = run_dir / "isolated_source.mp4"
            mux_audio(source_path, isolated_path, isolated_video)
            render_source = isolated_video
            opts["isolated_audio_path"] = str(isolated_path)

        if opts.get("stt_captions"):
            if not elevenlabs_enabled():
                raise RuntimeError("ELEVENLABS_API_KEY is not set.")
            audio_for_stt = (
                Path(opts.get("isolated_audio_path"))
                if opts.get("isolated_audio_path")
                else None
            )
            if not audio_for_stt:
                audio_for_stt = run_dir / "source_audio.wav"
                extract_audio(source_path, audio_for_stt)
            stt_result = speech_to_text(audio_for_stt)
            captions_srt = build_srt_from_stt(stt_result)
            if captions_srt:
                plan["captions_srt"] = captions_srt
                opts["captions_enabled"] = True

        if opts.get("sfx_enabled"):
            sfx_items = []
            for idx, item in enumerate(plan.get("sound_effects", [])[:5]):
                prompt = str(item.get("text", "")).strip()
                if not prompt:
                    continue
                audio_bytes = sound_effects(prompt, duration_s=2.5)
                sfx_path = run_dir / f"sfx_{idx}.mp3"
                sfx_path.write_bytes(audio_bytes)
                sfx_items.append(
                    {
                        "path": str(sfx_path),
                        "start": float(item.get("start", 0)),
                        "volume": 0.8,
                    }
                )
            if sfx_items:
                opts["sfx_items"] = sfx_items

        update_job(job_id, status="rendering", progress=80)
        try:
            output_path = render_video_pipeline(
                render_source, segments, opts, plan, run_dir
            )
        except Exception:
            fallback_opts = {**opts, "ai_visuals_enabled": False, "transition_type": "none"}
            try:
                output_path = render_video_pipeline(
                    render_source, segments, fallback_opts, plan, run_dir
                )
            except Exception:
                fallback_opts["captions_enabled"] = False
                output_path = render_video_pipeline(
                    render_source, segments, fallback_opts, plan, run_dir
                )

        output_info = inspect_video(Path(output_path))
        source_info = inspect_video(Path(render_source))
        if (
            output_info.get("width", 0) < source_info.get("width", 0)
            or output_info.get("height", 0) < source_info.get("height", 0)
        ):
            raise RuntimeError("Output resolution lower than source.")

        update_job(job_id, status="done", progress=100, output=str(output_path))
        notify_email = opts.get("notify_email")
        if notify_email:
            try:
                send_ready_email(notify_email, job_id)
            except Exception as exc:
                append_log(run_dir / "server.log", f"EMAIL ERROR: {exc}")
    except Exception as exc:
        run_dir = init_job_dir(RUNS_DIR, job_id)
        append_log(run_dir / "server.log", f"ERROR: {exc}")
        append_log(run_dir / "server.log", traceback.format_exc())
        update_job(job_id, status="error", progress=100, error=str(exc))


def process_job_from_url(job_id, url, opts):
    try:
        update_job(job_id, status="queued", progress=10)
        update_job(job_id, status="fetching_url", progress=20)
        safe_url = sanitize_url_for_logs(url)
        opts["source_url"] = safe_url
        update_job(job_id, status="downloading", progress=30)
        input_path = UPLOADS_DIR / f"{job_id}_url.mp4"
        run_dir = init_job_dir(RUNS_DIR, job_id)
        append_log(run_dir / "server.log", f"Downloading URL: {safe_url}")
        download_url(url, input_path, ALLOW_PLATFORM_DL, MAX_URL_BYTES)
        verify_video(input_path)
        process_job(job_id, input_path, opts, set_queue=False)
    except IngestError as exc:
        run_dir = init_job_dir(RUNS_DIR, job_id)
        append_log(run_dir / "server.log", f"ERROR: {exc.code} {exc}")
        update_job(job_id, status="error", progress=100, error=str(exc))
    except Exception as exc:
        run_dir = init_job_dir(RUNS_DIR, job_id)
        append_log(run_dir / "server.log", f"ERROR: {exc}")
        append_log(run_dir / "server.log", traceback.format_exc())
        update_job(job_id, status="error", progress=100, error=str(exc))


@app.get("/", response_class=HTMLResponse)
def index():
    react_index = REACT_DIST / "index.html"
    if react_index.exists():
        return react_index.read_text(encoding="utf-8")
    index_path = APP_DIR / "static" / "index.html"
    return index_path.read_text(encoding="utf-8")


@app.get("/app", response_class=HTMLResponse)
def app_page():
    app_path = APP_DIR / "static" / "app.html"
    return app_path.read_text(encoding="utf-8")


@app.get("/elevenlabs/status")
def elevenlabs_status():
    enabled = elevenlabs_enabled()
    capabilities = {
        "text_to_speech": enabled,
        "speech_to_speech": enabled,
        "speech_to_text": enabled,
        "sound_effects": enabled,
        "audio_isolation": enabled,
        "music_generation": enabled,
        "voice_generation": enabled,
    }
    return {"enabled": enabled, "capabilities": capabilities}


@app.get("/elevenlabs/voices")
def elevenlabs_voices():
    if not elevenlabs_enabled():
        raise HTTPException(status_code=400, detail="ElevenLabs API key not set.")
    try:
        return list_voices()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/elevenlabs/tts")
async def elevenlabs_tts(request: Request):
    if not elevenlabs_enabled():
        raise HTTPException(status_code=400, detail="ElevenLabs API key not set.")
    try:
        payload = await request.json()
        text = payload.get("text", "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="Missing text.")
        voice_id = payload.get("voice_id") or ELEVENLABS_DEFAULT_VOICE
        if not voice_id:
            raise HTTPException(status_code=400, detail="Missing voice_id.")
        model_id = payload.get("model_id", "eleven_multilingual_v2")
        output_format = payload.get("output_format", "mp3_44100_128")
        voice_settings = payload.get("voice_settings")
        speed = float(payload.get("speed", 1.0))
        audio_bytes = text_to_speech(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            output_format=output_format,
            voice_settings=voice_settings,
        )
        job_id = str(uuid.uuid4())
        run_dir = init_job_dir(RUNS_DIR, f"elevenlabs_{job_id}")
        output_path = run_dir / "tts.mp3"
        output_path.write_bytes(audio_bytes)
        if abs(speed - 1.0) > 0.01:
            sped_path = run_dir / "tts_sped.mp3"
            apply_audio_speed(output_path, sped_path, speed)
            output_path = sped_path
        return FileResponse(output_path, media_type="audio/mpeg", filename="tts.mp3")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/elevenlabs/sts")
def elevenlabs_sts(
    audio: UploadFile = File(...),
    voice_id: str | None = Form(None),
    model_id: str = Form("eleven_multilingual_v2"),
):
    if not elevenlabs_enabled():
        raise HTTPException(status_code=400, detail="ElevenLabs API key not set.")
    try:
        voice = voice_id or ELEVENLABS_DEFAULT_VOICE
        if not voice:
            raise HTTPException(status_code=400, detail="Missing voice_id.")
        job_id = str(uuid.uuid4())
        run_dir = init_job_dir(RUNS_DIR, f"elevenlabs_{job_id}")
        input_path = run_dir / f"sts_{audio.filename}"
        with input_path.open("wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)
        audio_bytes = speech_to_speech(input_path, voice, model_id=model_id)
        output_path = run_dir / "sts.mp3"
        output_path.write_bytes(audio_bytes)
        return FileResponse(output_path, media_type="audio/mpeg", filename="sts.mp3")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/elevenlabs/stt")
def elevenlabs_stt(
    audio: UploadFile = File(...),
    language: str | None = Form(None),
):
    if not elevenlabs_enabled():
        raise HTTPException(status_code=400, detail="ElevenLabs API key not set.")
    try:
        job_id = str(uuid.uuid4())
        run_dir = init_job_dir(RUNS_DIR, f"elevenlabs_{job_id}")
        input_path = run_dir / f"stt_{audio.filename}"
        with input_path.open("wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)
        result = speech_to_text(input_path, language=language)
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/elevenlabs/sfx")
async def elevenlabs_sfx(request: Request):
    if not elevenlabs_enabled():
        raise HTTPException(status_code=400, detail="ElevenLabs API key not set.")
    try:
        payload = await request.json()
        prompt = payload.get("prompt", "").strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="Missing prompt.")
        duration_s = float(payload.get("duration_s", 2.5))
        audio_bytes = sound_effects(prompt, duration_s=duration_s)
        job_id = str(uuid.uuid4())
        run_dir = init_job_dir(RUNS_DIR, f"elevenlabs_{job_id}")
        output_path = run_dir / "sfx.mp3"
        output_path.write_bytes(audio_bytes)
        return FileResponse(output_path, media_type="audio/mpeg", filename="sfx.mp3")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/elevenlabs/isolate")
def elevenlabs_isolate(audio: UploadFile = File(...)):
    if not elevenlabs_enabled():
        raise HTTPException(status_code=400, detail="ElevenLabs API key not set.")
    try:
        job_id = str(uuid.uuid4())
        run_dir = init_job_dir(RUNS_DIR, f"elevenlabs_{job_id}")
        input_path = run_dir / f"source_{audio.filename}"
        with input_path.open("wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)
        audio_bytes = audio_isolation(input_path)
        output_path = run_dir / "isolated.mp3"
        output_path.write_bytes(audio_bytes)
        return FileResponse(output_path, media_type="audio/mpeg", filename="isolated.mp3")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/elevenlabs/music")
async def elevenlabs_music(request: Request):
    if not elevenlabs_enabled():
        raise HTTPException(status_code=400, detail="ElevenLabs API key not set.")
    try:
        payload = await request.json()
        prompt = payload.get("prompt", "").strip()
        if not prompt:
            raise HTTPException(status_code=400, detail="Missing prompt.")
        duration_s = float(payload.get("duration_s", 10.0))
        audio_bytes = music_generation(prompt, duration_s=duration_s)
        job_id = str(uuid.uuid4())
        run_dir = init_job_dir(RUNS_DIR, f"elevenlabs_{job_id}")
        output_path = run_dir / "music.mp3"
        output_path.write_bytes(audio_bytes)
        return FileResponse(output_path, media_type="audio/mpeg", filename="music.mp3")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/elevenlabs/voice")
async def elevenlabs_voice(request: Request):
    if not elevenlabs_enabled():
        raise HTTPException(status_code=400, detail="ElevenLabs API key not set.")
    try:
        payload = await request.json()
        name = payload.get("name", "").strip()
        description = payload.get("description", "").strip()
        if not name or not description:
            raise HTTPException(status_code=400, detail="Missing name or description.")
        return voice_generation(name=name, description=description)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/start")
def start_job(
    file: UploadFile = File(...),
    platform: str = Form(...),
    duration: int = Form(45),
    style: str = Form(...),
    cut_intensity: str = Form(...),
    language: str = Form(...),
    captions: str = Form(...),
    resolution: str = Form(...),
    content_preset: str = Form("auto"),
    output_resolution: str = Form("1080x1920"),
    reframe_mode: str = Form("center"),
    fps: int = Form(30),
    filters_enabled: bool = Form(False),
    filter_preset: str = Form("none"),
    brightness: float = Form(0.0),
    contrast: float = Form(1.0),
    saturation: float = Form(1.0),
    gamma: float = Form(1.0),
    sharpness: float = Form(0.0),
    denoise: bool = Form(False),
    vignette: bool = Form(False),
    grain: bool = Form(False),
    captions_enabled: bool = Form(True),
    caption_template: str = Form("tiktok_bold"),
    caption_position: str = Form("bottom"),
    caption_size: str = Form("md"),
    caption_safe_margin: int = Form(40),
    caption_highlight_keywords: bool = Form(False),
    caption_max_chars_per_line: int = Form(32),
    transition_type: str = Form("none"),
    transition_duration: float = Form(0.3),
    audio_enhance: bool = Form(False),
    audio_loudnorm: bool = Form(False),
    audio_compressor: bool = Form(False),
    audio_denoise: bool = Form(False),
    audio_isolation_enabled: bool = Form(False),
    sfx_enabled: bool = Form(False),
    stt_captions: bool = Form(False),
    voiceover_enabled: bool = Form(False),
    voiceover_text: str = Form(""),
    voiceover_voice_id: str = Form(""),
    voiceover_speed: float = Form(1.0),
    voiceover_mode: str = Form("replace"),
    voiceover_pre_sped: bool = Form(False),
    voiceover_file: UploadFile | None = File(None),
    music_enabled: bool = Form(False),
    music_volume: float = Form(0.15),
    music_ducking: bool = Form(False),
    music_file: UploadFile | None = File(None),
    ai_visuals_enabled: bool = Form(False),
    ai_visuals_style: str = Form("minimal_abstract"),
    ai_visuals_intensity: str = Form("low"),
    ai_visuals_max_overlays: int = Form(2),
    ai_visuals_transparent_png: bool = Form(True),
    ai_broll_enabled: bool = Form(False),
    ai_broll_mode: str = Form("off"),
    ai_video_model: str = Form("auto"),
    notify_email: str = Form(""),
):
    job_id = str(uuid.uuid4())
    upload_path = UPLOADS_DIR / f"{job_id}_{file.filename}"
    with upload_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    run_dir = init_job_dir(RUNS_DIR, job_id)
    append_log(run_dir / "server.log", "Job created from file upload.")
    append_log(run_dir / "server.log", f"Uploaded file: {file.filename}")
    append_log(run_dir / "server.log", f"Stored at: {upload_path}")
    with JOB_LOCK:
        JOBS[job_id] = {
            "status": "queued",
            "progress": 0,
            "error": None,
            "output": None,
        }

    opts = {
        "platform": platform,
        "duration_s": duration,
        "style": style,
        "cut_intensity": cut_intensity,
        "language": language,
        "captions": captions,
        "resolution": resolution,
        "content_preset": content_preset,
        "output_resolution": output_resolution,
        "reframe_mode": reframe_mode,
        "fps": fps,
        "filters_enabled": filters_enabled,
        "filter_preset": filter_preset,
        "brightness": max(-0.2, min(0.2, brightness)),
        "contrast": max(0.8, min(1.3, contrast)),
        "saturation": max(0.8, min(1.4, saturation)),
        "gamma": max(0.8, min(1.2, gamma)),
        "sharpness": max(0.0, min(1.0, sharpness)),
        "denoise": denoise,
        "vignette": vignette,
        "grain": grain,
        "captions_enabled": captions_enabled,
        "caption_template": caption_template,
        "caption_position": caption_position,
        "caption_size": caption_size,
        "caption_safe_margin": max(0, caption_safe_margin),
        "caption_highlight_keywords": caption_highlight_keywords,
        "caption_max_chars_per_line": max(10, caption_max_chars_per_line),
        "transition_type": transition_type,
        "transition_duration": max(0.1, min(0.6, transition_duration)),
        "audio_enhance": audio_enhance,
        "audio_loudnorm": audio_loudnorm,
        "audio_compressor": audio_compressor,
        "audio_denoise": audio_denoise,
        "audio_isolation_enabled": audio_isolation_enabled,
        "sfx_enabled": sfx_enabled,
        "stt_captions": stt_captions,
        "voiceover_enabled": voiceover_enabled,
        "voiceover_text": voiceover_text,
        "voiceover_voice_id": voiceover_voice_id,
        "voiceover_speed": voiceover_speed,
        "voiceover_mode": voiceover_mode,
        "voiceover_pre_sped": voiceover_pre_sped,
        "music_enabled": music_enabled,
        "music_volume": max(0.0, min(0.25, music_volume)),
        "music_ducking": music_ducking,
        "ai_visuals_enabled": ai_visuals_enabled,
        "ai_visuals_style": ai_visuals_style,
        "ai_visuals_intensity": ai_visuals_intensity,
        "ai_visuals_max_overlays": max(0, min(4, ai_visuals_max_overlays)),
        "ai_visuals_transparent_png": ai_visuals_transparent_png,
        "ai_broll_enabled": ai_broll_enabled,
        "ai_broll_mode": ai_broll_mode,
        "ai_video_model": ai_video_model,
        "notify_email": notify_email.strip(),
    }
    validate_opts(opts)
    write_json(run_dir / "request.json", opts)
    if music_file:
        music_path = UPLOADS_DIR / f"{job_id}_music_{music_file.filename}"
        with music_path.open("wb") as buffer:
            shutil.copyfileobj(music_file.file, buffer)
        opts["music_file"] = str(music_path)
    if voiceover_file:
        voice_path = RUNS_DIR / job_id / f"voiceover_{voiceover_file.filename}"
        with voice_path.open("wb") as buffer:
            shutil.copyfileobj(voiceover_file.file, buffer)
        opts["voiceover_path"] = str(voice_path)
    thread = threading.Thread(
        target=process_job,
        args=(job_id, upload_path, opts),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.post("/analyze_url")
def analyze_url(payload: dict):
    url = payload.get("url", "")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required.")
    try:
        metadata = inspect_url(url, ALLOW_PLATFORM_DL)
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=exc.code)
    return {
        "url": sanitize_url_for_logs(metadata.url),
        "content_type": metadata.content_type,
        "content_length": metadata.content_length,
    }


@app.post("/start_from_url")
def start_from_url(payload: dict):
    url = payload.get("url", "")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required.")
    job_id = str(uuid.uuid4())
    run_dir = init_job_dir(RUNS_DIR, job_id)
    append_log(run_dir / "server.log", "Job created from URL.")
    with JOB_LOCK:
        JOBS[job_id] = {
            "status": "queued",
            "progress": 0,
            "error": None,
            "output": None,
        }
    opts = {**payload}
    opts.pop("url", None)
    opts["source_type"] = "url"
    opts.setdefault("platform", "Shorts")
    opts.setdefault("duration_s", int(payload.get("duration", 45)))
    opts.setdefault("style", payload.get("style", "Storytelling"))
    opts.setdefault("cut_intensity", payload.get("cut_intensity", "Medium"))
    opts.setdefault("language", payload.get("language", "EN"))
    opts.setdefault("captions", payload.get("captions", "ON"))
    opts.setdefault("resolution", payload.get("resolution", "1080x1920"))
    opts.setdefault("content_preset", payload.get("content_preset", "auto"))
    opts.setdefault("output_resolution", payload.get("output_resolution", "1080x1920"))
    opts.setdefault("reframe_mode", payload.get("reframe_mode", "center"))
    opts.setdefault("fps", int(payload.get("fps", 30)))
    opts.setdefault("filters_enabled", bool(payload.get("filters_enabled", False)))
    opts.setdefault("filter_preset", payload.get("filter_preset", "none"))
    opts.setdefault("brightness", float(payload.get("brightness", 0.0)))
    opts.setdefault("contrast", float(payload.get("contrast", 1.0)))
    opts.setdefault("saturation", float(payload.get("saturation", 1.0)))
    opts.setdefault("gamma", float(payload.get("gamma", 1.0)))
    opts.setdefault("sharpness", float(payload.get("sharpness", 0.0)))
    opts.setdefault("denoise", bool(payload.get("denoise", False)))
    opts.setdefault("vignette", bool(payload.get("vignette", False)))
    opts.setdefault("grain", bool(payload.get("grain", False)))
    opts.setdefault("captions_enabled", bool(payload.get("captions_enabled", True)))
    opts.setdefault("caption_template", payload.get("caption_template", "tiktok_bold"))
    opts.setdefault("caption_position", payload.get("caption_position", "bottom"))
    opts.setdefault("caption_size", payload.get("caption_size", "md"))
    opts.setdefault("caption_safe_margin", int(payload.get("caption_safe_margin", 40)))
    opts.setdefault(
        "caption_highlight_keywords",
        bool(payload.get("caption_highlight_keywords", False)),
    )
    opts.setdefault(
        "caption_max_chars_per_line",
        int(payload.get("caption_max_chars_per_line", 32)),
    )
    opts.setdefault("transition_type", payload.get("transition_type", "none"))
    opts.setdefault("transition_duration", float(payload.get("transition_duration", 0.3)))
    opts.setdefault("audio_enhance", bool(payload.get("audio_enhance", False)))
    opts.setdefault("audio_loudnorm", bool(payload.get("audio_loudnorm", False)))
    opts.setdefault("audio_compressor", bool(payload.get("audio_compressor", False)))
    opts.setdefault("audio_denoise", bool(payload.get("audio_denoise", False)))
    opts.setdefault(
        "audio_isolation_enabled", bool(payload.get("audio_isolation_enabled", False))
    )
    opts.setdefault("sfx_enabled", bool(payload.get("sfx_enabled", False)))
    opts.setdefault("stt_captions", bool(payload.get("stt_captions", False)))
    opts.setdefault("voiceover_enabled", bool(payload.get("voiceover_enabled", False)))
    opts.setdefault("voiceover_text", payload.get("voiceover_text", ""))
    opts.setdefault("voiceover_voice_id", payload.get("voiceover_voice_id", ""))
    opts.setdefault("voiceover_speed", float(payload.get("voiceover_speed", 1.0)))
    opts.setdefault("voiceover_mode", payload.get("voiceover_mode", "replace"))
    opts.setdefault(
        "voiceover_pre_sped", bool(payload.get("voiceover_pre_sped", False))
    )
    opts.setdefault("notify_email", payload.get("notify_email", "").strip())
    opts.setdefault("music_enabled", bool(payload.get("music_enabled", False)))
    opts.setdefault("music_volume", float(payload.get("music_volume", 0.15)))
    opts.setdefault("music_ducking", bool(payload.get("music_ducking", False)))
    opts.setdefault("ai_visuals_enabled", bool(payload.get("ai_visuals_enabled", False)))
    opts.setdefault(
        "ai_visuals_style", payload.get("ai_visuals_style", "minimal_abstract")
    )
    opts.setdefault("ai_visuals_intensity", payload.get("ai_visuals_intensity", "low"))
    opts.setdefault("ai_visuals_max_overlays", int(payload.get("ai_visuals_max_overlays", 2)))
    opts.setdefault(
        "ai_visuals_transparent_png",
        bool(payload.get("ai_visuals_transparent_png", True)),
    )
    opts.setdefault("ai_broll_enabled", bool(payload.get("ai_broll_enabled", False)))
    opts.setdefault("ai_broll_mode", payload.get("ai_broll_mode", "off"))
    opts.setdefault("ai_video_model", payload.get("ai_video_model", "auto"))
    validate_opts(opts)
    write_json(run_dir / "request.json", opts)
    thread = threading.Thread(
        target=process_job_from_url,
        args=(job_id, url, opts),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/status/{job_id}")
def get_status(job_id: str):
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        response = dict(job)
        if job.get("status") == "done":
            response["output_url"] = f"/download/{job_id}"
        return response


@app.get("/download/{job_id}")
def download(job_id: str):
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        if job["status"] != "done":
            raise HTTPException(status_code=400, detail="Job not completed.")
        output_path = job["output"]

    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"{job_id}.mp4",
    )
