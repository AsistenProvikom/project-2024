// ─────────────────────────────────────────────────────────────────────────────
// script.js — Java Game Portal (Custom Screenshot Streaming)
//
// Tidak pakai VNC/noVNC. Cara kerjanya:
//   1. Polling GET /api/screen → JPEG screenshot → render di <canvas>
//   2. Mouse/keyboard events → POST /api/input → xdotool inject ke Xvfb
// ─────────────────────────────────────────────────────────────────────────────

const SCREEN_W = 1280;
const SCREEN_H = 800;
const POLL_INTERVAL = 80; // ms (~12 fps)

let streamingActive = false;
let pollTimer = null;
let gameActive = false;

// ── View Helpers ──────────────────────────────────────────────────────────────

function showGallery() {
  document.getElementById("view-gallery").classList.remove("hidden");
  document.getElementById("view-game").classList.add("hidden");
}

function showGameView() {
  document.getElementById("view-gallery").classList.add("hidden");
  document.getElementById("view-game").classList.remove("hidden");
}

function showLoading(text, hint) {
  document.getElementById("loading-text").textContent = text;
  if (hint) document.querySelector(".loading-hint").textContent = hint;
  document.getElementById("loading-overlay").classList.remove("hidden");
  document.getElementById("canvas-wrapper").classList.add("hidden");
}

function showCanvas() {
  document.getElementById("loading-overlay").classList.add("hidden");
  document.getElementById("canvas-wrapper").classList.remove("hidden");
}

// ── Screenshot Streaming ─────────────────────────────────────────────────────

function startStreaming() {
  const canvas = document.getElementById("game-canvas");
  const ctx    = canvas.getContext("2d");
  canvas.width  = SCREEN_W;
  canvas.height = SCREEN_H;

  streamingActive = true;
  let frameCount = 0;
  let lastFpsTime = performance.now();
  const fpsEl = document.getElementById("fps-counter");

  function fetchFrame() {
    if (!streamingActive) return;

    const img = new Image();
    img.onload = () => {
      ctx.drawImage(img, 0, 0, SCREEN_W, SCREEN_H);
      frameCount++;

      // FPS counter (update setiap detik)
      const now = performance.now();
      if (now - lastFpsTime >= 1000) {
        fpsEl.textContent = `${frameCount} FPS`;
        frameCount = 0;
        lastFpsTime = now;
      }

      // Request next frame
      if (streamingActive) {
        pollTimer = setTimeout(fetchFrame, POLL_INTERVAL);
      }
    };
    img.onerror = () => {
      // Retry after short delay
      if (streamingActive) {
        pollTimer = setTimeout(fetchFrame, 500);
      }
    };
    // Cache-bust to prevent browser caching
    img.src = `/api/screen?t=${Date.now()}`;
  }

  fetchFrame();
}

function stopStreaming() {
  streamingActive = false;
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

// ── Input Handling ───────────────────────────────────────────────────────────

function getCanvasCoords(e) {
  const canvas = document.getElementById("game-canvas");
  const rect   = canvas.getBoundingClientRect();
  const scaleX = SCREEN_W / rect.width;
  const scaleY = SCREEN_H / rect.height;
  return {
    x: Math.round((e.clientX - rect.left) * scaleX),
    y: Math.round((e.clientY - rect.top)  * scaleY),
  };
}

function mouseButtonId(e) {
  // JavaScript: 0=left, 1=middle, 2=right → xdotool: 1=left, 2=middle, 3=right
  return e.button + 1;
}

function sendInput(data) {
  // Fire-and-forget (no await), keep it fast
  fetch("/api/input", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }).catch(() => {});
}

function setupInputListeners() {
  const canvas = document.getElementById("game-canvas");

  // Mouse events
  canvas.addEventListener("mousemove", (e) => {
    if (!gameActive) return;
    const pos = getCanvasCoords(e);
    sendInput({ type: "mousemove", x: pos.x, y: pos.y });
  });

  canvas.addEventListener("mousedown", (e) => {
    if (!gameActive) return;
    e.preventDefault();
    canvas.focus();
    const pos = getCanvasCoords(e);
    sendInput({ type: "mousedown", x: pos.x, y: pos.y, button: mouseButtonId(e) });
  });

  canvas.addEventListener("mouseup", (e) => {
    if (!gameActive) return;
    e.preventDefault();
    sendInput({ type: "mouseup", button: mouseButtonId(e) });
  });

  canvas.addEventListener("click", (e) => {
    if (!gameActive) return;
    e.preventDefault();
    const pos = getCanvasCoords(e);
    sendInput({ type: "click", x: pos.x, y: pos.y, button: mouseButtonId(e) });
  });

  // Prevent context menu on right-click
  canvas.addEventListener("contextmenu", (e) => e.preventDefault());

  // Keyboard events (canvas needs focus + tabindex)
  canvas.addEventListener("keydown", (e) => {
    if (!gameActive) return;
    e.preventDefault();
    sendInput({ type: "keydown", key: e.key });
  });

  canvas.addEventListener("keyup", (e) => {
    if (!gameActive) return;
    e.preventDefault();
    sendInput({ type: "keyup", key: e.key });
  });
}

// ── API ──────────────────────────────────────────────────────────────────────

async function apiLaunch(jarFile) {
  const res = await fetch("/api/launch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ game: jarFile }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const javaErr = data.java_stderr?.join("\n") || "";
    const msg = data.error || `Server error ${res.status}`;
    throw new Error(javaErr ? `${msg}\n\n${javaErr}` : msg);
  }
  return data;
}

async function apiStop() {
  await fetch("/api/stop", { method: "POST" }).catch(() => {});
}

// ── Play / Stop / Back ───────────────────────────────────────────────────────

async function playGame(jarFile, gameName) {
  showGameView();
  document.getElementById("game-topbar-title").textContent = gameName;
  showLoading(`Memulai ${gameName}...`, "Mengirim request ke server...");

  try {
    await apiLaunch(jarFile);

    showLoading("Game dimulai!", "Menunggu tampilan game muncul...");
    await wait(2500);

    // Start screenshot streaming
    gameActive = true;
    showCanvas();
    startStreaming();

    // Focus canvas for keyboard input
    document.getElementById("game-canvas").focus();

  } catch (err) {
    console.error("[Portal] playGame error:", err);
    showLoading(`⚠️ ${err.message}`, "Coba kembali atau refresh halaman.");
  }
}

async function goBack() {
  gameActive = false;
  stopStreaming();
  await apiStop();
  showGallery();
}

async function stopGame() {
  gameActive = false;
  stopStreaming();
  await apiStop();
  showLoading("Game dihentikan.", "Klik 'Kembali' untuk ke gallery.");
}

// ── Gallery ──────────────────────────────────────────────────────────────────

async function loadGames() {
  const list = document.getElementById("game-list");
  list.innerHTML =
    `<div class="skeleton-grid">${"<div class='skeleton-card'></div>".repeat(6)}</div>`;

  try {
    const res = await fetch("data/games.json");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const games = await res.json();
    list.innerHTML = "";

    games.forEach((game, idx) => {
      const jarFile = game.jar || game.file || "";
      const card = document.createElement("div");
      card.className = "game-card";
      card.style.animationDelay = `${idx * 60}ms`;

      card.innerHTML = `
        <div class="card-image-wrap">
          <img class="card-image"
               src="${game.image || './images/default.png'}"
               alt="${game.name}" loading="lazy"
               onerror="this.src='./images/default.png'" />
          <div class="card-overlay">
            <button class="btn btn-play-big" id="play-o-${idx}" type="button">▶ Main</button>
          </div>
        </div>
        <div class="card-body">
          <h3 title="${game.name}">${game.name}</h3>
          ${game.description ? `<p class="card-desc">${game.description}</p>` : ""}
          <button class="btn btn-play" id="play-b-${idx}" type="button">▶ Mainkan</button>
        </div>`;

      const start = () => playGame(jarFile, game.name);
      card.querySelector(`#play-o-${idx}`).addEventListener("click", start);
      card.querySelector(`#play-b-${idx}`).addEventListener("click", start);
      list.appendChild(card);
    });

  } catch (err) {
    list.innerHTML = `
      <div class="error-panel">
        <h3>Gagal memuat daftar game</h3>
        <p>${err.message}</p>
        <button class="btn btn-play" onclick="loadGames()" style="margin-top:1rem;width:auto;padding:.55rem 1.5rem">Coba lagi</button>
      </div>`;
  }
}

// ── Utils ────────────────────────────────────────────────────────────────────

function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  loadGames();
  setupInputListeners();

  document.getElementById("btn-back").addEventListener("click", goBack);
  document.getElementById("btn-stop").addEventListener("click", stopGame);
});
