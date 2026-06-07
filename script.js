// ─────────────────────────────────────────────────────────────────────────────
// script.js — Java Game Portal
// Mengganti CheerpJ dengan pendekatan server-side:
//   1. User klik Play → POST /api/launch { game: "GameName.jar" }
//   2. Server jalankan JAR di Java 21 + Xvfb virtual display
//   3. noVNC iframe streaming tampilan game ke browser
// ─────────────────────────────────────────────────────────────────────────────

const NOVNC_URL =
  "/novnc/vnc.html?autoconnect=1&resize=scale&path=websockify&reconnect=1";

// Delay (ms) sebelum menampilkan noVNC — beri waktu Java startup
const GAME_STARTUP_DELAY = 3000;

// ── View Management ───────────────────────────────────────────────────────────

function showGallery() {
  document.getElementById("view-gallery").classList.remove("hidden");
  document.getElementById("view-game").classList.add("hidden");
}

function showGameView() {
  document.getElementById("view-gallery").classList.add("hidden");
  document.getElementById("view-game").classList.remove("hidden");
}

function showLoadingOverlay(text) {
  document.getElementById("loading-text").textContent = text;
  document.getElementById("loading-overlay").classList.remove("hidden");
  document.getElementById("vnc-wrapper").classList.add("hidden");
}

function showVncFrame() {
  document.getElementById("loading-overlay").classList.add("hidden");
  document.getElementById("vnc-wrapper").classList.remove("hidden");
}

// ── API Calls ─────────────────────────────────────────────────────────────────

async function apiLaunch(jarFile) {
  const res = await fetch("/api/launch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ game: jarFile }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: "Server error" }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

async function apiStop() {
  await fetch("/api/stop", { method: "POST" }).catch(() => {});
}

// ── Play / Stop / Back ────────────────────────────────────────────────────────

let novncInitialized = false;

async function playGame(jarFile, gameName) {
  // Switch to game view
  showGameView();
  document.getElementById("game-topbar-title").textContent = gameName;
  showLoadingOverlay(`Memulai ${gameName}...`);

  try {
    // Tell server to launch the JAR
    await apiLaunch(jarFile);

    // Wait for Java process to open its window
    await wait(GAME_STARTUP_DELAY);

    // Load noVNC iframe (only set src once — it auto-reconnects after that)
    const frame = document.getElementById("vnc-frame");
    if (!novncInitialized) {
      frame.src = NOVNC_URL;
      novncInitialized = true;
    }

    showVncFrame();
  } catch (err) {
    console.error("[Portal] Launch failed:", err);
    showLoadingOverlay(`⚠️ Gagal: ${err.message}`);
    document.querySelector(".loading-hint").textContent =
      "Coba kembali atau refresh halaman.";
  }
}

async function stopGame() {
  await apiStop();
}

async function goBack() {
  await apiStop();
  showGallery();
}

// ── Game Gallery ──────────────────────────────────────────────────────────────

async function loadGames() {
  const list = document.getElementById("game-list");
  list.innerHTML = `<div class="skeleton-grid">${"<div class='skeleton-card'></div>".repeat(6)}</div>`;

  try {
    const res = await fetch("data/games.json");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const games = await res.json();

    list.innerHTML = "";

    games.forEach((game, idx) => {
      const jarFile = game.jar || game.file || game.filename || "";

      const card = document.createElement("div");
      card.className = "game-card";
      card.style.animationDelay = `${idx * 60}ms`;

      card.innerHTML = `
        <div class="card-image-wrap">
          <img
            class="card-image"
            src="${game.image || "./images/default.png"}"
            alt="${game.name}"
            loading="lazy"
            onerror="this.src='./images/default.png'"
          />
          <div class="card-overlay">
            <button
              class="btn btn-play-big"
              id="play-btn-${idx}"
              type="button"
              aria-label="Main ${game.name}"
            >
              ▶ Main
            </button>
          </div>
        </div>
        <div class="card-body">
          <h3 title="${game.name}">${game.name}</h3>
          ${game.description ? `<p class="card-desc">${game.description}</p>` : ""}
          <button
            class="btn btn-play"
            id="play-btn-bottom-${idx}"
            type="button"
          >
            ▶ Mainkan
          </button>
        </div>
      `;

      // Attach click handlers
      const startPlay = () => playGame(jarFile, game.name);
      card.querySelector(`#play-btn-${idx}`).addEventListener("click", startPlay);
      card.querySelector(`#play-btn-bottom-${idx}`).addEventListener("click", startPlay);

      list.appendChild(card);
    });
  } catch (err) {
    list.innerHTML = `
      <div class="error-panel">
        <h3>Gagal memuat daftar game</h3>
        <p>${err.message}</p>
        <button class="btn btn-play" onclick="loadGames()">Coba lagi</button>
      </div>`;
    console.error("[Portal] loadGames error:", err);
  }
}

// ── Utils ─────────────────────────────────────────────────────────────────────

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", loadGames);
