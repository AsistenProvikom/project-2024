"""
server.py — Java Game Portal: Custom Screenshot Streaming
===========================================================
Tidak pakai VNC/noVNC/websockify sama sekali.
- Screenshot: ImageMagick `import` command → capture Xvfb display → JPEG
- Input:      xdotool → inject mouse/keyboard ke Xvfb display
- Streaming:  Browser polling /api/screen setiap ~80ms (12fps)
"""

from flask import Flask, jsonify, request, send_file, Response
import subprocess
import os
import signal
import time
import threading
import io

app = Flask(__name__, static_folder="/app/static", static_url_path="")

# ── Config ────────────────────────────────────────────────────────────────────
GAMES_DIR   = "/games"
DISPLAY     = ":99"
SCREEN_W    = 1280
SCREEN_H    = 800
CAPTURE_FPS = 15
JPEG_QUALITY = 55

# ── State ─────────────────────────────────────────────────────────────────────
current_process = None
current_game    = None
java_stderr     = []

# Screenshot buffer (updated by background thread)
_frame_lock   = threading.Lock()
_latest_frame = None  # bytes (JPEG)

# ── Screenshot capture thread ────────────────────────────────────────────────

def _capture_loop():
    """Terus-menerus capture screenshot dari Xvfb display."""
    global _latest_frame
    interval = 1.0 / CAPTURE_FPS
    env = os.environ.copy()
    env["DISPLAY"] = DISPLAY

    # Tunggu Xvfb siap
    time.sleep(3)
    print("[CAPTURE] Starting screenshot capture loop", flush=True)

    while True:
        try:
            result = subprocess.run(
                [
                    "import",
                    "-window", "root",
                    "-display", DISPLAY,
                    "-quality", str(JPEG_QUALITY),
                    "-resize", f"{SCREEN_W}x{SCREEN_H}",
                    "jpeg:-",   # output JPEG ke stdout
                ],
                capture_output=True,
                timeout=5,
                env=env,
            )
            if result.returncode == 0 and result.stdout:
                with _frame_lock:
                    _latest_frame = result.stdout
        except Exception as e:
            print(f"[CAPTURE] Error: {e}", flush=True)

        time.sleep(interval)


# Start capture thread
_capture_thread = threading.Thread(target=_capture_loop, daemon=True)
_capture_thread.start()

# ── Java stderr reader ────────────────────────────────────────────────────────

def _read_stderr(proc):
    global java_stderr
    try:
        for raw in iter(proc.stderr.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            print(f"[JAVA] {line}", flush=True)
            java_stderr.append(line)
            if len(java_stderr) > 50:
                java_stderr = java_stderr[-50:]
    except Exception:
        pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def kill_current():
    global current_process, current_game
    if current_process is not None:
        try:
            pgid = os.getpgid(current_process.pid)
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(0.3)
            if current_process.poll() is None:
                os.killpg(pgid, signal.SIGKILL)
        except Exception:
            pass
        current_process = None
        current_game    = None


def is_running():
    return current_process is not None and current_process.poll() is None


# ── Routes: Static ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return app.send_static_file("index.html")


# ── Routes: API ───────────────────────────────────────────────────────────────

@app.route("/api/launch", methods=["POST"])
def launch():
    global current_process, current_game, java_stderr

    data = request.get_json(silent=True) or {}
    game = data.get("game", "")

    if not game:
        return jsonify({"error": "game parameter required"}), 400
    if ".." in game or "/" in game or "\\" in game:
        return jsonify({"error": "invalid game name"}), 400

    jar_path = os.path.join(GAMES_DIR, game)
    if not os.path.isfile(jar_path):
        avail = [f for f in os.listdir(GAMES_DIR) if f.endswith(".jar")]
        return jsonify({"error": f"Not found: {game}", "available": avail}), 404

    kill_current()
    java_stderr = []

    env = os.environ.copy()
    env["DISPLAY"] = DISPLAY
    env["HOME"]    = "/root"

    print(f"[API] Launching: {jar_path}", flush=True)

    try:
        proc = subprocess.Popen(
            ["java", "-Djava.awt.headless=false", "-jar", jar_path],
            env=env,
            cwd=GAMES_DIR,
            preexec_fn=os.setsid,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        t = threading.Thread(target=_read_stderr, args=(proc,), daemon=True)
        t.start()

        time.sleep(1.5)
        if proc.poll() is not None:
            err = "\n".join(java_stderr[-15:]) or "(no output)"
            return jsonify({"error": "Java crashed", "java_stderr": java_stderr[-15:]}), 500

        current_process = proc
        current_game    = game
        print(f"[API] Running: {game} PID={proc.pid}", flush=True)
        return jsonify({"status": "launched", "game": game, "pid": proc.pid})

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/stop", methods=["POST"])
def stop():
    kill_current()
    return jsonify({"status": "stopped"})


@app.route("/api/status", methods=["GET"])
def status():
    running = is_running()
    return jsonify({
        "running": running,
        "game":    current_game if running else None,
    })


@app.route("/api/games", methods=["GET"])
def list_games():
    jars = sorted(f for f in os.listdir(GAMES_DIR) if f.endswith(".jar"))
    return jsonify({"games": jars})


# ── Routes: Screenshot Streaming ──────────────────────────────────────────────

@app.route("/api/screen")
def screen():
    """Return latest screenshot as JPEG."""
    with _frame_lock:
        frame = _latest_frame
    if not frame:
        # Kirim 1x1 pixel transparan jika belum ada frame
        return Response(b"", status=204)
    return Response(frame, mimetype="image/jpeg",
                    headers={"Cache-Control": "no-store"})


# ── Routes: Input Injection ───────────────────────────────────────────────────

# Map JavaScript key names → xdotool key names
KEY_MAP = {
    "ArrowUp": "Up", "ArrowDown": "Down",
    "ArrowLeft": "Left", "ArrowRight": "Right",
    "Enter": "Return", " ": "space",
    "Escape": "Escape", "Backspace": "BackSpace",
    "Tab": "Tab", "Delete": "Delete",
    "Shift": "Shift_L", "Control": "Control_L", "Alt": "Alt_L",
    "a": "a", "b": "b", "c": "c", "d": "d", "e": "e",
    "f": "f", "g": "g", "h": "h", "i": "i", "j": "j",
    "k": "k", "l": "l", "m": "m", "n": "n", "o": "o",
    "p": "p", "q": "q", "r": "r", "s": "s", "t": "t",
    "u": "u", "v": "v", "w": "w", "x": "x", "y": "y", "z": "z",
    "0": "0", "1": "1", "2": "2", "3": "3", "4": "4",
    "5": "5", "6": "6", "7": "7", "8": "8", "9": "9",
}

def _xdo(*args):
    """Run xdotool with DISPLAY set."""
    try:
        subprocess.run(
            ["xdotool"] + list(args),
            env={"DISPLAY": DISPLAY, "HOME": "/root"},
            timeout=2,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


@app.route("/api/input", methods=["POST"])
def handle_input():
    """Receive mouse/keyboard events from browser, inject into Xvfb via xdotool."""
    data = request.get_json(silent=True) or {}
    action = data.get("type", "")

    if action == "mousemove":
        _xdo("mousemove", "--screen", "0", str(data["x"]), str(data["y"]))

    elif action == "mousedown":
        btn = str(data.get("button", 1))
        _xdo("mousemove", "--screen", "0", str(data["x"]), str(data["y"]))
        _xdo("mousedown", btn)

    elif action == "mouseup":
        btn = str(data.get("button", 1))
        _xdo("mouseup", btn)

    elif action == "click":
        btn = str(data.get("button", 1))
        _xdo("mousemove", "--screen", "0", str(data["x"]), str(data["y"]))
        _xdo("click", btn)

    elif action == "keydown":
        key = KEY_MAP.get(data.get("key", ""), data.get("key", ""))
        if key:
            _xdo("keydown", key)

    elif action == "keyup":
        key = KEY_MAP.get(data.get("key", ""), data.get("key", ""))
        if key:
            _xdo("keyup", key)

    return jsonify({"ok": True})


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"[SERVER] Starting on 0.0.0.0:{port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
