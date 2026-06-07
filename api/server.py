"""
api/server.py — Flask REST API
Menerima request dari frontend untuk launch/stop game JAR di server.
Game berjalan di virtual display :99 (Xvfb), ditampilkan via noVNC.
"""

from flask import Flask, jsonify, request
import subprocess
import os
import signal
import time

app = Flask(__name__)

# State (per-process, single user)
current_process = None
current_game    = None

GAMES_DIR = "/games"
DISPLAY   = ":99"
JAVA_BIN  = "java"

# ── Helpers ───────────────────────────────────────────────────────────────────

def kill_current():
    """Terminate any currently running game process."""
    global current_process, current_game
    if current_process is not None:
        try:
            pgid = os.getpgid(current_process.pid)
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(0.5)
            # Force kill if still running
            if current_process.poll() is None:
                os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        current_process = None
        current_game    = None

def is_running():
    global current_process
    if current_process is None:
        return False
    return current_process.poll() is None

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/api/launch", methods=["POST", "OPTIONS"])
def launch():
    """
    POST /api/launch
    Body JSON: { "game": "Minesweeper.jar" }
    Kills existing game, launches the requested JAR with Java 21.
    """
    if request.method == "OPTIONS":
        return _cors_ok()

    global current_process, current_game

    data = request.get_json(silent=True) or {}
    game = data.get("game") or request.args.get("game", "")

    if not game:
        return jsonify({"error": "Parameter 'game' wajib diisi"}), 400

    # Security: prevent path traversal
    if ".." in game or "/" in game or "\\" in game:
        return jsonify({"error": "Nama game tidak valid"}), 400

    jar_path = os.path.join(GAMES_DIR, game)
    if not os.path.isfile(jar_path):
        return jsonify({"error": f"Game tidak ditemukan: {game}"}), 404

    # Kill existing game
    kill_current()

    # Launch new game
    env = os.environ.copy()
    env["DISPLAY"] = DISPLAY
    env["HOME"]    = "/root"

    try:
        current_process = subprocess.Popen(
            [JAVA_BIN, "-jar", jar_path],
            env=env,
            preexec_fn=os.setsid,          # Create new process group for clean kill
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        current_game = game
        print(f"[API] Launched: {game} (PID {current_process.pid})", flush=True)
        return jsonify({"status": "launched", "game": game, "pid": current_process.pid})

    except Exception as exc:
        print(f"[API] Error launching {game}: {exc}", flush=True)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/status", methods=["GET"])
def status():
    """GET /api/status — Returns whether a game is currently running."""
    running = is_running()
    if not running:
        current_game_local = None
    else:
        current_game_local = current_game

    return jsonify({"running": running, "game": current_game_local})


@app.route("/api/stop", methods=["POST", "OPTIONS"])
def stop():
    """POST /api/stop — Terminate the running game."""
    if request.method == "OPTIONS":
        return _cors_ok()

    kill_current()
    print("[API] Game stopped", flush=True)
    return jsonify({"status": "stopped"})


@app.route("/api/games", methods=["GET"])
def list_games():
    """GET /api/games — List available JAR files (for debugging)."""
    try:
        jars = [f for f in os.listdir(GAMES_DIR) if f.endswith(".jar")]
        return jsonify({"games": sorted(jars)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _cors_ok():
    resp = jsonify({"ok": True})
    resp.headers["Access-Control-Allow-Origin"]  = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[API] Flask API starting on 127.0.0.1:5000", flush=True)
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
