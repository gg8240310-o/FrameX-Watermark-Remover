---
title: FrameX Watermark Remover
emoji: ✨
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# FrameX Watermark Remover

Free, login-free Gemini watermark remover for images and videos. Flask + OpenCV + FFmpeg.

## How it works
- **Detection:** the sparkle is found by high-pass residual + a four-point star template, weighted toward Gemini's known corner position (48px/32px margin, 96px/64px above 1024px). If confidence is low it falls back to the expected position.
- **Removal:** the masked region is rebuilt with OpenCV inpainting and feathered back in (no blur box or crop). Images export as lossless PNG at original resolution.
- **Video:** the static overlay is located by a per-pixel minimum over 10 sampled frames, then every frame is inpainted and piped to FFmpeg (H.264, CRF 14, audio re-encoded to AAC). Resolution and FPS are preserved.

## Run locally
```
pip install -r requirements.txt     # also install ffmpeg (apt/brew/choco)
python app.py                       # http://localhost:7860
```
Env vars: `PORT`, `MAX_UPLOAD_MB` (default 1024), `WORK_DIR` (default /tmp/framex). Files auto-delete after 1 hour.

## Deploy
- **Docker:** `docker build -t framex . && docker run -p 7860:7860 framex` (works on Fly.io, Railway, Render, any VPS).
- **VPS:** `gunicorn -w 1 --threads 8 -t 600 -b 0.0.0.0:7860 app:app` behind nginx (`client_max_body_size 1g;`). Keep one worker, since job state is in memory.

## Limits (honest notes)
- Removes only the **visible** sparkle/“Veo” mark. Google's invisible SynthID stays.
- Inpainting is very clean on smooth or textured backgrounds, less so on fine detail directly under the mark.
- Video detection assumes a static, brighter-than-background overlay in the bottom-right.
- The reference page could not be fetched, so the design is my own modern layout (hero, tabbed tool, before/after slider, steps, FAQ), not a pixel match.
