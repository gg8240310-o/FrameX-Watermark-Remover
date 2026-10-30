"""FrameX engine: detect the Gemini/Veo corner watermark and reconstruct the pixels
underneath with inpainting (no blur box, no crop)."""
import subprocess
import cv2
import numpy as np


def _star(size):
    """Four-pointed sparkle (astroid-like) template, 0..255."""
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) / 2
    u, v = np.abs(x - c) / (size / 2), np.abs(y - c) / (size / 2)
    return ((u ** 0.6 + v ** 0.6) <= 1).astype(np.uint8) * 255


def _residual(gray, k=41):
    """Bright semi-transparent overlay = positive high-pass residual."""
    k = min(k, (min(gray.shape) // 2) * 2 - 1) | 1
    return np.clip(gray.astype(np.float32) - cv2.medianBlur(gray, k), 0, None)


def locate_image(img):
    """Returns (box, mask, found). box=(x0,y0,x1,y1) crop; mask is uint8 for that crop."""
    h, w = img.shape[:2]
    L = 96 if min(h, w) > 1024 else 48          # Gemini logo size / margin convention
    L = min(L, max(16, min(h, w) // 4))
    m = L * 2 // 3
    cx, cy = w - m - L // 2, h - m - L // 2
    r = int(L * 1.6)
    x0, y0, x1, y1 = max(0, cx - r), max(0, cy - r), min(w, cx + r), min(h, cy + r)
    gray = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    res = _residual(gray)
    tpl = _star(L).astype(np.float32) / 255
    sc = cv2.matchTemplate(res, tpl, cv2.TM_CCORR)
    ys, xs = np.mgrid[0:sc.shape[0], 0:sc.shape[1]]
    ex, ey = (cx - x0) - L / 2, (cy - y0) - L / 2
    sc = sc * np.exp(-((xs - ex) ** 2 + (ys - ey) ** 2) / (2 * (L * 0.8) ** 2))
    by, bx = np.unravel_index(np.argmax(sc), sc.shape)
    inside = res[by:by + L, bx:bx + L][tpl > 0]
    conf = float(inside.mean() / (res.mean() + 1e-3)) if inside.size else 0
    found = conf > 1.5
    if not found:                                   # fall back to the known position
        bx, by = int(round(ex)), int(round(ey))
    big = int(L * 1.3)
    mask = np.zeros(gray.shape, np.uint8)
    ox, oy = bx - (big - L) // 2, by - (big - L) // 2
    st = cv2.resize(_star(L), (big, big), interpolation=cv2.INTER_LINEAR)
    sx0, sy0 = max(0, ox), max(0, oy)
    sx1, sy1 = min(mask.shape[1], ox + big), min(mask.shape[0], oy + big)
    if sx1 > sx0 and sy1 > sy0:
        mask[sy0:sy1, sx0:sx1] = st[sy0 - oy:sy1 - oy, sx0 - ox:sx1 - ox]
    mask |= ((res > 10).astype(np.uint8) * 255) & cv2.dilate(mask, np.ones((9, 9), np.uint8))
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    return (x0, y0, x1, y1), mask, found


def apply_mask(img, box, mask):
    x0, y0, x1, y1 = box
    crop = img[y0:y1, x0:x1]
    fixed = cv2.inpaint(crop, mask, 5, cv2.INPAINT_TELEA)
    a = cv2.GaussianBlur(mask, (0, 0), 1.5).astype(np.float32)[..., None] / 255
    img[y0:y1, x0:x1] = (fixed * a + crop * (1 - a)).astype(np.uint8)
    return img


def remove_image(img):
    box, mask, found = locate_image(img)
    return apply_mask(img.copy(), box, mask), found


def locate_video(cap, samples=10):
    """Static overlay => survives a per-pixel minimum across frames."""
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w, h = int(cap.get(3)), int(cap.get(4))
    x0, y0 = int(w * 0.70), int(h * 0.82)
    mins = None
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i * max(n - 1, 1) / samples))
        ok, f = cap.read()
        if not ok:
            continue
        r = _residual(cv2.cvtColor(f[y0:, x0:], cv2.COLOR_BGR2GRAY), 21)
        mins = r if mins is None else np.minimum(mins, r)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    if mins is None:
        raise ValueError("Could not read video frames.")
    mask = (mins > 6).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    if int(mask.sum() / 255) < 25:
        return (x0, y0, w, h), None
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    return (x0, y0, w, h), mask


def remove_video(src, dst, progress=lambda p: None):
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise ValueError("Unsupported or corrupted video.")
    w, h = int(cap.get(3)), int(cap.get(4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    total = max(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
    box, mask = locate_video(cap)
    if mask is None:
        cap.release()
        raise ValueError("No watermark detected in this video.")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-i", src, "-map", "0:v", "-map", "1:a?",
           "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-crf", "14",
           "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", "-shortest", dst]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    x0, y0, x1, y1 = box
    i = 0
    try:
        while True:
            ok, f = cap.read()
            if not ok:
                break
            apply_mask(f, (x0, y0, x1, y1), mask)
            ff.stdin.write(f.tobytes())
            i += 1
            if i % 5 == 0:
                progress(min(i / total, 0.99))
        ff.stdin.close()
        if ff.wait() != 0:
            raise RuntimeError("Video encoding failed.")
    finally:
        cap.release()
        if ff.poll() is None:
            ff.kill()
    progress(1.0)
