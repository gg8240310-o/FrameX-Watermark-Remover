import os, time, uuid, threading
import cv2, numpy as np
from flask import Flask, request, jsonify, send_file, send_from_directory
import engine

MAX_MB = int(os.environ.get("MAX_UPLOAD_MB", 1024))
TMP = os.environ.get("WORK_DIR", "/tmp/framex")
os.makedirs(TMP, exist_ok=True)
IMG_EXT = {"png", "jpg", "jpeg", "webp"}
VID_EXT = {"mp4", "mov", "webm", "mkv", "avi", "m4v"}

app = Flask(__name__, static_folder=None)
PUBLIC = {"style.css", "app.js", "logo.svg"}
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024
jobs, lock = {}, threading.Lock()


def ext_of(name):
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


@app.errorhandler(413)
def too_big(_):
    return jsonify(error=f"File too large (max {MAX_MB} MB)."), 413


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/<name>")
def public(name):
    if name not in PUBLIC:
        return jsonify(error="Not found."), 404
    return send_from_directory(".", name)


@app.post("/api/image")
def image():
    f = request.files.get("file")
    if not f or ext_of(f.filename) not in IMG_EXT:
        return jsonify(error="Please upload a PNG, JPG, JPEG or WEBP image."), 400
    img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return jsonify(error="This image could not be read."), 400
    out, found = engine.remove_image(img)
    ok, buf = cv2.imencode(".png", out, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    jid = uuid.uuid4().hex
    path = os.path.join(TMP, jid + ".png")
    open(path, "wb").write(buf.tobytes())
    return jsonify(url=f"/api/download/{jid}.png", detected=found)


def run_video(jid, src, dst):
    def prog(p):
        jobs[jid]["progress"] = p
    try:
        engine.remove_video(src, dst, prog)
        jobs[jid].update(status="done", url=f"/api/download/{jid}.mp4")
    except Exception as e:
        jobs[jid].update(status="error", error=str(e))
    finally:
        if os.path.exists(src):
            os.remove(src)


@app.post("/api/video")
def video():
    f = request.files.get("file")
    ext = ext_of(f.filename) if f else ""
    if ext not in VID_EXT:
        return jsonify(error="Supported video formats: " + ", ".join(sorted(VID_EXT))), 400
    jid = uuid.uuid4().hex
    src = os.path.join(TMP, f"{jid}_in.{ext}")
    f.save(src)
    with lock:
        jobs[jid] = {"status": "processing", "progress": 0, "t": time.time()}
    threading.Thread(target=run_video, args=(jid, src, os.path.join(TMP, jid + ".mp4")), daemon=True).start()
    return jsonify(job=jid)


@app.get("/api/job/<jid>")
def job(jid):
    j = jobs.get(jid)
    return (jsonify(j), 200) if j else (jsonify(error="Unknown job."), 404)


@app.get("/api/download/<name>")
def download(name):
    if not name.rsplit(".", 1)[0].isalnum():
        return jsonify(error="Invalid file."), 400
    p = os.path.join(TMP, name)
    if not os.path.exists(p):
        return jsonify(error="File expired."), 404
    return send_file(p, as_attachment=request.args.get("dl") == "1",
                     download_name="framex-" + name)


def cleanup():
    while True:
        time.sleep(300)
        for n in os.listdir(TMP):
            p = os.path.join(TMP, n)
            if time.time() - os.path.getmtime(p) > 3600:
                os.remove(p)


threading.Thread(target=cleanup, daemon=True).start()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
