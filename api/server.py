"""
api/server.py — Flask REST API
Launch/stop game JAR di virtual display Xvfb :99.
Sekarang capture stderr Java agar error bisa dilihat di log Render.
"""

from flask import Flask, jsonify, request
import subprocess
import os
import signal
import time
import threading

app = Flask(__name__)

# ── State ─────────────────────────────────────────────────────────────────────
current_process = None
current_game    = None
java_stderr     = []          # Buffer stderr Java (max 100 baris)

GAMES_DIR = "/games"
DISPLAY   = ":99"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_stderr(proc):
    """Baca stderr Java di thread terpisah, print ke log Render & simpan ke buffer."""
    global java_stderr
    try:
        for raw in iter(proc.stderr.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            print(f"[JAVA] {line}", flush=True)
            java_stderr.append(line)
            if len(java_stderr) > 100:
                java_stderr = java_stderr[-100:]
    except Exception:
        pass


def kill_current():
    global current_process, current_game
    if current_process is not None:
        try:
            pgid = os.getpgid(current_process.pid)
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(0.4)
            if current_process.poll() is None:
                os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, ProcessError):
            pass
        current_process = None
        current_game    = None


def is_running():
    return current_process is not None and current_process.poll() is None

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/api/launch", methods=["POST", "OPTIONS"])
def launch():
    global current_process, current_game, java_stderr

    if request.method == "OPTIONS":
        return _cors()

    data    = request.get_json(silent=True) or {}
    game    = data.get("game") or request.args.get("game", "")

    if not game:
        return jsonify({"error": "Parameter 'game' wajib diisi"}), 400
    if ".." in game or "/" in game or "\\" in game:
        return jsonify({"error": "Nama game tidak valid"}), 400

    jar_path = os.path.join(GAMES_DIR, game)
    if not os.path.isfile(jar_path):
        available = os.listdir(GAMES_DIR)
        return jsonify({"error": f"Game tidak ditemukan: {game}", "available": available}), 404

    kill_current()
    java_stderr = []   # reset log

    env = os.environ.copy()
    env["DISPLAY"] = DISPLAY
    env["HOME"]    = "/root"
    env["JAVA_TOOL_OPTIONS"] = "-Djava.awt.headless=false"

    print(f"[API] Launching: {jar_path}", flush=True)

    try:
        proc = subprocess.Popen(
            [
                "java",
                "-Djava.awt.headless=false",
                "-Dawt.useSystemAAFontSettings=on",
                "-Dswing.aatext=true",
                "-jar", jar_path,
            ],
            env=env,
            cwd=GAMES_DIR,            # working dir = /games agar resource relatif ketemu
            preexec_fn=os.setsid,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,   # capture stderr untuk debugging
        )

        # Baca stderr di background thread
        t = threading.Thread(target=_read_stderr, args=(proc,), daemon=True)
        t.start()

        # Tunggu sebentar: cek apakah langsung crash
        time.sleep(1.5)
        if proc.poll() is not None:
            # Process sudah exit — kembalikan stderr sebagai error
            err_lines = "\n".join(java_stderr[-20:]) or "(tidak ada output)"
            print(f"[API] Java exited immediately! stderr:\n{err_lines}", flush=True)
            return jsonify({
                "error": "Java process keluar langsung (crash).",
                "java_stderr": java_stderr[-20:]
            }), 500

        current_process = proc
        current_game    = game
        print(f"[API] Running: {game} PID={proc.pid}", flush=True)
        return jsonify({"status": "launched", "game": game, "pid": proc.pid})

    except Exception as exc:
        print(f"[API] Exception: {exc}", flush=True)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/status", methods=["GET"])
def status():
    running = is_running()
    return jsonify({
        "running": running,
        "game":    current_game if running else None,
        "stderr":  java_stderr[-10:],   # kirim 10 baris terakhir untuk debug
    })


@app.route("/api/stop", methods=["POST", "OPTIONS"])
def stop():
    if request.method == "OPTIONS":
        return _cors()
    kill_current()
    print("[API] Stopped", flush=True)
    return jsonify({"status": "stopped"})


@app.route("/api/games", methods=["GET"])
def list_games():
    try:
        jars = sorted(f for f in os.listdir(GAMES_DIR) if f.endswith(".jar"))
        return jsonify({"games": jars})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _cors():
    r = jsonify({"ok": True})
    r.headers["Access-Control-Allow-Origin"]  = "*"
    r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return r


if __name__ == "__main__":
    print("[API] Starting Flask on 127.0.0.1:5000", flush=True)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
