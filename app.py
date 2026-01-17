from __future__ import annotations

from pathlib import Path
import uuid

from flask import Flask, abort, redirect, render_template, request, send_file, url_for
from PIL import Image, ImageDraw, ImageFont
from werkzeug.utils import secure_filename

APP_ROOT = Path(__file__).resolve().parent
GENERATED_DIR = APP_ROOT / "generated"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

GENERATED_DIR.mkdir(parents=True, exist_ok=True)


def is_allowed_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


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
        abort(404)
    path = (GENERATED_DIR / safe_name).resolve()
    if GENERATED_DIR.resolve() not in path.parents:
        abort(404)
    if not path.exists():
        abort(404)
    return path


@app.route("/", methods=["GET"])
def index() -> str:
    meme_filename = request.args.get("meme")
    return render_template(
        "index.html",
        meme_filename=meme_filename,
        error=None,
        top_text="",
        bottom_text="",
    )


@app.route("/generate", methods=["POST"])
def generate() -> str:
    uploaded_file = request.files.get("image")
    top_text = request.form.get("top_text", "").strip()
    bottom_text = request.form.get("bottom_text", "").strip()

    if not uploaded_file or uploaded_file.filename == "":
        return render_template(
            "index.html",
            meme_filename=None,
            error="Please choose an image file to upload.",
            top_text=top_text,
            bottom_text=bottom_text,
        )

    if not is_allowed_filename(uploaded_file.filename):
        return render_template(
            "index.html",
            meme_filename=None,
            error="Unsupported file type. Upload a JPG, PNG, GIF, or WEBP image.",
            top_text=top_text,
            bottom_text=bottom_text,
        )

    try:
        image = Image.open(uploaded_file.stream)
    except OSError:
        return render_template(
            "index.html",
            meme_filename=None,
            error="That file could not be read as an image.",
            top_text=top_text,
            bottom_text=bottom_text,
        )

    meme_image = build_meme(image, top_text, bottom_text)
    filename = f"meme-{uuid.uuid4().hex}.png"
    output_path = GENERATED_DIR / filename
    meme_image.save(output_path, format="PNG")

    return redirect(url_for("index", meme=filename))


@app.route("/meme/<filename>")
def meme_file(filename: str):
    path = safe_generated_path(filename)
    return send_file(path, mimetype="image/png")


@app.route("/download/<filename>")
def download_file(filename: str):
    path = safe_generated_path(filename)
    return send_file(path, mimetype="image/png", as_attachment=True, download_name=path.name)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
