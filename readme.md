# Meme Generator (Python)

Create memes from your own images. Upload a file, add top and bottom text, then download the result.

## Features
- Upload an image (JPG, PNG, GIF, WEBP)
- Add top and bottom meme text
- Download the generated meme as PNG

## Run locally
1. Create and activate a virtual environment:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
2. Install dependencies:
   - `python3 -m pip install -r requirements.txt`
3. Start the app:
   - `python3 app.py`
4. Open `http://127.0.0.1:5000` in your browser.

## Run in an online editor
- Ensure the editor exposes port `5000`, or set a custom port with `PORT=8000 python3 app.py`.

## Notes
- Generated images are saved to `generated/`.
- Upload limit is 10MB per image.
