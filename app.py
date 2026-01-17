from __future__ import annotations

import io
import os
from pathlib import Path
import re
import uuid
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from PIL import Image, ImageDraw, ImageFont

APP_ROOT = Path(__file__).resolve().parent
GENERATED_DIR = APP_ROOT / "generated"
STATIC_DIR = APP_ROOT / "static"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

GENERATED_DIR.mkdir(parents=True, exist_ok=True)


def is_allowed_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def secure_filename(filename: str) -> str:
    base = Path(filename).name
    base = base.replace(" ", "-")
    base = re.sub(r"[^A-Za-z0-9._-]", "", base)
    return base


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_name in ("Impact.ttf", "impact.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(font_name, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap_text(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    line = words[0]
    for word in words[1:]:
        trial = f"{line} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


def fit_font(
    draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int
) -> tuple[ImageFont.ImageFont, list[str]]:
    size = start_size
    while size >= 12:
        font = load_font(size)
        lines = wrap_text(text, draw, font, max_width)
        if not lines:
            return font, lines
        widest = max(draw.textlength(line, font=font) for line in lines)
        if widest <= max_width:
            return font, lines
        size -= 2
    font = load_font(12)
    return font, wrap_text(text, draw, font, max_width)


def line_height(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, stroke_width: int) -> int:
    bbox = draw.textbbox((0, 0), "Ay", font=font, stroke_width=stroke_width)
    return bbox[3] - bbox[1]


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    image_width: int,
    image_height: int,
    text: str,
    position: str,
) -> None:
    if not text:
        return

    margin = int(image_height * 0.05)
    max_width = int(image_width * 0.9)
    start_size = max(18, image_width // 10)
    font, lines = fit_font(draw, text.upper(), max_width, start_size)
    if not lines:
        return

    stroke_width = max(2, int(font.size * 0.08))
    block_line_height = line_height(draw, font, stroke_width)
    line_spacing = max(2, int(font.size * 0.15))
    block_height = len(lines) * block_line_height + (len(lines) - 1) * line_spacing

    if position == "top":
        y = margin
    else:
        y = max(margin, image_height - margin - block_height)

    for line in lines:
        line_width = draw.textlength(line, font=font)
        x = (image_width - line_width) / 2
        draw.text(
            (x, y),
            line,
            font=font,
            fill="white",
            stroke_width=stroke_width,
            stroke_fill="black",
        )
        y += block_line_height + line_spacing


def build_meme(image: Image.Image, top_text: str, bottom_text: str) -> Image.Image:
    if image.mode == "RGBA":
        background = Image.new("RGBA", image.size, (255, 255, 255, 255))
        background.alpha_composite(image)
        image = background.convert("RGB")
    elif image.mode != "RGB":
        image = image.convert("RGB")

    draw = ImageDraw.Draw(image)
    draw_text_block(draw, image.width, image.height, top_text, "top")
    draw_text_block(draw, image.width, image.height, bottom_text, "bottom")
    return image


def safe_generated_path(filename: str) -> Path:
    safe_name = secure_filename(filename)
    if not safe_name:
        raise FileNotFoundError
    path = (GENERATED_DIR / safe_name).resolve()
    if GENERATED_DIR.resolve() not in path.parents:
        raise FileNotFoundError
    if not path.exists():
        raise FileNotFoundError
    return path


def render_index(*, meme_filename: str | None, error: str | None, top_text: str, bottom_text: str) -> str:
    error_html = f'<div class="error">{error}</div>' if error else ""
    result_html = ""
    if meme_filename:
        result_html = (
            "<section class=\"card result\">"
            "<h2>Your meme</h2>"
            f"<img src=\"/meme/{meme_filename}\" alt=\"Generated meme preview\" />"
            "<div class=\"actions\">"
            f"<a class=\"button\" href=\"/download/{meme_filename}\">Download meme</a>"
            "</div>"
            "</section>"
        )
    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Meme Generator</title>
    <link rel=\"stylesheet\" href=\"/static/styles.css\" />
  </head>
  <body>
    <div class=\"container\">
      <header>
        <h1>Meme Generator</h1>
        <p>Upload an image, add text, and download your meme.</p>
      </header>

      <section class=\"card\">
        <form class=\"form-grid\" action=\"/generate\" method=\"post\" enctype=\"multipart/form-data\">
          <label for=\"image\">Image file</label>
          <input id=\"image\" name=\"image\" type=\"file\" accept=\"image/*\" required />

          <label for=\"top_text\">Top text</label>
          <input id=\"top_text\" name=\"top_text\" type=\"text\" placeholder=\"TOP TEXT\" value=\"{top_text}\" />

          <label for=\"bottom_text\">Bottom text</label>
          <input id=\"bottom_text\" name=\"bottom_text\" type=\"text\" placeholder=\"BOTTOM TEXT\" value=\"{bottom_text}\" />

          <button type=\"submit\">Generate meme</button>
        </form>

        {error_html}
      </section>

      {result_html}

      <footer>
        <p>Supported formats: JPG, PNG, GIF, WEBP. Max upload: 10MB.</p>
      </footer>
    </div>
  </body>
</html>"""


def parse_multipart(body: bytes, content_type: str) -> dict[str, dict[str, bytes | str]]:
    match = re.search(r"boundary=(.+)", content_type)
    if not match:
        return {}
    boundary = match.group(1).strip().strip('"')
    delimiter = f"--{boundary}".encode()
    parts: dict[str, dict[str, bytes | str]] = {}
    for chunk in body.split(delimiter):
        if not chunk or chunk in (b"--", b"--\r\n"):
            continue
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        if chunk.endswith(b"--"):
            chunk = chunk[:-2]
        header_bytes, _, payload = chunk.partition(b"\r\n\r\n")
        if not header_bytes:
            continue
        message = BytesParser(policy=default).parsebytes(header_bytes + b"\r\n\r\n")
        disposition = message.get("Content-Disposition", "")
        name_match = re.search(r'name="([^"]+)"', disposition)
        if not name_match:
            continue
        name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]+)"', disposition)
        filename = filename_match.group(1) if filename_match else ""
        parts[name] = {"filename": filename, "content": payload}
    return parts


def read_text_value(fields: dict[str, dict[str, bytes | str]], name: str) -> str:
    field = fields.get(name)
    if not field:
        return ""
    content = field.get("content", b"")
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace").strip()
    return str(content).strip()


class MemeRequestHandler(BaseHTTPRequestHandler):
    server_version = "MemeGeneratorHTTP/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            params = parse_qs(parsed.query)
            meme_filename = params.get("meme", [None])[0]
            self.respond_html(
                render_index(meme_filename=meme_filename, error=None, top_text="", bottom_text="")
            )
            return
        if parsed.path.startswith("/static/"):
            self.serve_static(parsed.path)
            return
        if parsed.path.startswith("/meme/"):
            self.serve_generated(parsed.path.removeprefix("/meme/"), download=False)
            return
        if parsed.path.startswith("/download/"):
            self.serve_generated(parsed.path.removeprefix("/download/"), download=True)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path != "/generate":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length > MAX_UPLOAD_BYTES:
            self.respond_html(
                render_index(
                    meme_filename=None,
                    error="That file is too large. Please upload an image up to 10MB.",
                    top_text="",
                    bottom_text="",
                ),
                status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            )
            return

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return

        body = self.rfile.read(content_length)
        fields = parse_multipart(body, content_type)

        image_field = fields.get("image")
        top_text = read_text_value(fields, "top_text")
        bottom_text = read_text_value(fields, "bottom_text")

        filename = image_field.get("filename", "") if image_field else ""
        if not image_field or not filename:
            self.respond_html(
                render_index(
                    meme_filename=None,
                    error="Please choose an image file to upload.",
                    top_text=top_text,
                    bottom_text=bottom_text,
                )
            )
            return

        if not is_allowed_filename(filename):
            self.respond_html(
                render_index(
                    meme_filename=None,
                    error="Unsupported file type. Upload a JPG, PNG, GIF, or WEBP image.",
                    top_text=top_text,
                    bottom_text=bottom_text,
                )
            )
            return

        try:
            file_bytes = image_field.get("content", b"")
            if not isinstance(file_bytes, bytes):
                raise OSError
            image = Image.open(io.BytesIO(file_bytes))
        except OSError:
            self.respond_html(
                render_index(
                    meme_filename=None,
                    error="That file could not be read as an image.",
                    top_text=top_text,
                    bottom_text=bottom_text,
                )
            )
            return

        meme_image = build_meme(image, top_text, bottom_text)
        output_name = f"meme-{uuid.uuid4().hex}.png"
        output_path = GENERATED_DIR / output_name
        meme_image.save(output_path, format="PNG")

        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", f"/?meme={output_name}")
        self.end_headers()

    def serve_static(self, path: str) -> None:
        relative = path.removeprefix("/static/")
        safe_name = secure_filename(relative)
        if not safe_name:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        file_path = (STATIC_DIR / safe_name).resolve()
        if STATIC_DIR.resolve() not in file_path.parents or not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type = "text/plain"
        if file_path.suffix == ".css":
            content_type = "text/css"
        self.send_file(file_path, content_type)

    def serve_generated(self, filename: str, *, download: bool) -> None:
        try:
            path = safe_generated_path(filename)
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        headers = {}
        if download:
            headers["Content-Disposition"] = f"attachment; filename=\"{path.name}\""
        self.send_file(path, "image/png", extra_headers=headers)

    def respond_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, content_type: str, extra_headers: dict[str, str] | None = None) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), MemeRequestHandler)
    print(f"Serving on http://0.0.0.0:{port}")
    server.serve_forever()
