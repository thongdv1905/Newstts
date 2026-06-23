#!/usr/bin/env python3
"""Local web UI for creating videos from images, audio, and prompt text."""

from __future__ import annotations

import html
import shutil
import subprocess
import sys
import tempfile
import uuid
import warnings
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

warnings.simplefilter("ignore", DeprecationWarning)
import cgi
warnings.simplefilter("default", DeprecationWarning)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.create_video import (  # noqa: E402
    collect_images,
    create_video,
    mix_audio_files,
    positive_float,
    resolve_prompt_text,
    synthesize_speech,
)

HOST = "0.0.0.0"
PORT = 2000
OUTPUT_DIR = ROOT / "generated_videos"
MAX_UPLOAD_SIZE = 250 * 1024 * 1024

PAGE_TEMPLATE = """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Newstts Video Tool</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; background: #f5f7fb; color: #172033; }}
    main {{ max-width: 920px; margin: 32px auto; padding: 0 20px; }}
    .card {{ background: #fff; border-radius: 18px; padding: 24px; box-shadow: 0 12px 35px rgba(31, 45, 61, .12); }}
    h1 {{ margin-top: 0; }}
    label {{ display: block; font-weight: 700; margin-top: 16px; }}
    input, textarea, select {{ width: 100%; box-sizing: border-box; padding: 10px 12px; border: 1px solid #cad3df; border-radius: 10px; margin-top: 6px; }}
    textarea {{ min-height: 120px; resize: vertical; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .hint {{ color: #526071; font-size: 14px; margin: 6px 0 0; }}
    button {{ margin-top: 20px; padding: 12px 18px; border: 0; border-radius: 999px; background: #2563eb; color: #fff; font-weight: 700; cursor: pointer; }}
    .message {{ padding: 14px 16px; border-radius: 12px; margin-bottom: 16px; }}
    .success {{ background: #e9f9ef; color: #166534; }}
    .error {{ background: #feecec; color: #991b1b; white-space: pre-wrap; }}
    video {{ width: 100%; margin-top: 12px; border-radius: 12px; background: #000; }}
    @media (max-width: 720px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main>
    <div class="card">
      <h1>Tạo video từ hình ảnh, âm thanh và giọng đọc</h1>
      <p class="hint">Web chạy local tại <strong>localhost:2000</strong>. Chọn một hoặc nhiều ảnh, thêm audio nền hoặc nhập prompt để tạo giọng đọc.</p>
      {message}
      <form method="post" enctype="multipart/form-data">
        <label>Ảnh / nhiều ảnh</label>
        <input type="file" name="images" accept="image/*" multiple required>
        <p class="hint">Nếu chọn nhiều ảnh, web sẽ tạo slideshow theo thứ tự tên file.</p>

        <label>Audio nền (tuỳ chọn)</label>
        <input type="file" name="audio" accept="audio/*">

        <label>Text/prompt tạo giọng đọc (tuỳ chọn nếu đã có audio)</label>
        <textarea name="text" placeholder="Nhập nội dung cần đọc..."></textarea>

        <div class="grid">
          <div>
            <label>Engine giọng đọc</label>
            <select name="tts_engine">
              <option value="auto">auto</option>
              <option value="pyttsx3">pyttsx3</option>
              <option value="espeak">espeak</option>
              <option value="say">say</option>
            </select>
          </div>
          <div>
            <label>Voice</label>
            <input name="voice" placeholder="ví dụ: vi hoặc vi+f3">
          </div>
          <div>
            <label>Tốc độ đọc</label>
            <input name="speech_rate" type="number" placeholder="ví dụ: 150">
          </div>
          <div>
            <label>Thời lượng mỗi ảnh (giây)</label>
            <input name="image_duration" type="number" step="0.1" min="0.1" value="5">
          </div>
          <div>
            <label>FPS</label>
            <input name="fps" type="number" min="1" value="30">
          </div>
          <div>
            <label>Độ phân giải</label>
            <input name="resolution" value="1920:1080">
          </div>
          <div>
            <label>Âm lượng audio nền</label>
            <input name="background_volume" type="number" step="0.05" min="0.01" value="0.35">
          </div>
          <div>
            <label>Âm lượng giọng đọc</label>
            <input name="narration_volume" type="number" step="0.05" min="0.01" value="1.0">
          </div>
        </div>
        <button type="submit">Tạo video</button>
      </form>
    </div>
  </main>
</body>
</html>
"""


def render_page(message: str = "") -> bytes:
    """Render the upload form."""
    return PAGE_TEMPLATE.format(message=message).encode("utf-8")


def field_text(form: cgi.FieldStorage, name: str, default: str = "") -> str:
    """Read a text form field safely."""
    field = form[name] if name in form else None
    if field is None or field.value is None:
        return default
    return str(field.value).strip()


def uploaded_files(form: cgi.FieldStorage, name: str) -> list[cgi.FieldStorage]:
    """Return uploaded files for a multipart field."""
    if name not in form:
        return []
    field = form[name]
    files = field if isinstance(field, list) else [field]
    return [item for item in files if item.filename]


def safe_filename(filename: str) -> str:
    """Return a conservative filename for saved uploads."""
    cleaned = Path(filename).name.replace("\x00", "")
    return cleaned or f"upload-{uuid.uuid4().hex}"


def save_upload(upload: cgi.FieldStorage, destination: Path) -> Path:
    """Save one uploaded file to disk."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output_file:
        shutil.copyfileobj(upload.file, output_file)
    return destination


def parse_positive_field(form: cgi.FieldStorage, name: str, default: float) -> float:
    """Parse a positive numeric field from the web form."""
    value = field_text(form, name)
    return default if not value else positive_float(value)


def create_video_from_form(form: cgi.FieldStorage) -> Path:
    """Persist uploads, run optional TTS/mixing, and create the requested video."""
    job_id = uuid.uuid4().hex
    job_dir = OUTPUT_DIR / job_id
    image_dir = job_dir / "images"
    image_uploads = uploaded_files(form, "images")
    if not image_uploads:
        raise ValueError("Vui lòng chọn ít nhất một ảnh.")

    for index, upload in enumerate(image_uploads):
        filename = f"{index:04d}-{safe_filename(upload.filename)}"
        save_upload(upload, image_dir / filename)

    audio_uploads = uploaded_files(form, "audio")
    audio = None
    if audio_uploads:
        audio = save_upload(audio_uploads[0], job_dir / safe_filename(audio_uploads[0].filename))

    prompt_text = resolve_prompt_text(field_text(form, "text") or None, None)
    if audio is None and prompt_text is None:
        raise ValueError("Vui lòng tải audio lên hoặc nhập text/prompt để tạo giọng đọc.")

    output = job_dir / "video.mp4"
    tts_engine = field_text(form, "tts_engine", "auto") or "auto"
    voice = field_text(form, "voice") or None
    speech_rate_text = field_text(form, "speech_rate")
    speech_rate = int(speech_rate_text) if speech_rate_text else None
    image_duration = parse_positive_field(form, "image_duration", 5.0)
    fps = int(parse_positive_field(form, "fps", 30))
    resolution = field_text(form, "resolution", "1920:1080") or "1920:1080"
    background_volume = parse_positive_field(form, "background_volume", 0.35)
    narration_volume = parse_positive_field(form, "narration_volume", 1.0)

    if prompt_text is not None:
        narration_audio = synthesize_speech(
            text=prompt_text,
            output=job_dir / "narration.wav",
            engine=tts_engine,
            voice=voice,
            rate=speech_rate,
        )
        if audio is None:
            audio = narration_audio
        else:
            audio = mix_audio_files(
                background_audio=audio,
                narration_audio=narration_audio,
                output=job_dir / "mixed_audio.m4a",
                background_volume=background_volume,
                narration_volume=narration_volume,
            )

    images = collect_images(image_dir)
    create_video(
        images=images,
        audio=audio,
        output=output,
        image_duration=image_duration,
        fps=fps,
        resolution=resolution,
    )
    return output


class VideoToolHandler(BaseHTTPRequestHandler):
    """HTTP handler for the local video creation web UI."""

    def do_HEAD(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            body = render_page()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self.send_html(render_page())
            return
        if self.path.startswith("/generated_videos/"):
            self.serve_generated_file()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        if self.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > MAX_UPLOAD_SIZE:
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Upload too large")
            return

        try:
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": str(content_length),
                },
            )
            output = create_video_from_form(form)
            relative_url = "/" + output.relative_to(ROOT).as_posix()
            safe_url = html.escape(relative_url, quote=True)
            message = (
                '<div class="message success">Tạo video thành công: '
                f'<a href="{safe_url}" download>Tải video</a>'
                f'<video controls src="{safe_url}"></video></div>'
            )
            self.send_html(render_page(message))
        except (ValueError, subprocess.CalledProcessError) as exc:
            safe_error = html.escape(str(exc))
            self.send_html(
                render_page(f'<div class="message error">Lỗi: {safe_error}</div>'),
                status=HTTPStatus.BAD_REQUEST,
            )

    def send_html(self, body: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_generated_file(self) -> None:
        requested = unquote(self.path.lstrip("/"))
        path = (ROOT / requested).resolve()
        if not path.is_file() or OUTPUT_DIR.resolve() not in path.parents:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "video/mp4" if path.suffix == ".mp4" else "application/octet-stream")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as video_file:
            shutil.copyfileobj(video_file, self.wfile)


def run(host: str = HOST, port: int = PORT) -> None:
    """Start the local web server."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), VideoToolHandler)
    print(f"Open http://localhost:{port} to create videos")
    server.serve_forever()


if __name__ == "__main__":
    run()
