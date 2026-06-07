// ─────────────────────────────────────────────────────────────────────────────
// script.js — Java Game Portal
// ─────────────────────────────────────────────────────────────────────────────

// noVNC viewer URL. `path=websockify` → WebSocket connects to /websockify
const NOVNC_URL =
  "/novnc/vnc.html?autoconnect=1&resize=scale&reconnect=1&reconnect_delay=2000&path=websockify";

// ── View helpers ──────────────────────────────────────────────────────────────

function showGallery() {
  document.getElementById("view-gallery").classList.remove("hidden");
  document.getElementById("view-game").classList.add("hidden");
}

function showGameView() {
  document.getElementById("view-gallery").classList.add("hidden");
  document.getElementById("view-game").classList.remove("hidden");
}

function setLoadingText(text, hint) {
  document.getElementById("loading-text").textContent = text;
  if (hint !== undefined) {
    document.querySelector(".loading-hint").textContent = hint;
  }
}

function showLoadingOverlay(text, hint) {
  setLoadingText(text, hint ?? "Java 21 sedang diinisialisasi di server...");
  document.getElementById("loading-overlay").classList.remove("hidden");
  document.getElementById("vnc-wrapper").classList.add("hidden");
}

function showVncFrame() {
  document.getElementById("loading-overlay").classList.add("hidden");
  document.getElementById("vnc-wrapper").classList.remove("hidden");
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function apiLaunch(jarFile) {
  const res = await fetch("/api/launch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ game: jarFile }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // Sertakan stderr Java jika ada
    const javaErr = data.java_stderr?.join("\n") || "";
    const msg = data.error || `Server error ${res.status}`;
    throw new Error(javaErr ? `${msg}\n\nJava stderr:\n${javaErr}` : msg);
  }
  return data;
}

async function apiStop() {
  await fetch("/api/stop", { method: "POST" }).catch(() => {});
}

async function apiStatus() {
  try {
    const res = await fetch("/api/status");
    return await res.json();
  } catch {
    return { running: false };
  }
}

// Poll /api/status setiap detik sampai game berjalan (max 15 detik)
async function waitUntilRunning(maxSec = 15) {
  for (let i = 0; i < maxSec; i++) {
    await wait(1000);
    const s = await apiStatus();
    if (s.running) return true;
    setLoadingText(
      `Memulai game... (${i + 1}s)`,
      "Java sedang dimuat, mohon tunggu..."
    );
  }
  return false;
}

// ── Play / Stop / Back ────────────────────────────────────────────────────────

let novncInitialized = false;

async function playGame(jarFile, gameName) {
  showGameView();
  document.getElementById("game-topbar-title").textContent = gameName;
  showLoadingOverlay(`Memulai ${gameName}...`);

  try {
    // 1. Kirim request ke server untuk launch JAR
    setLoadingText("Menghubungi server...", "Mengirim perintah launch ke backend...");
    await apiLaunch(jarFile);

    // 2. Poll sampai proses Java benar-benar jalan
    setLoadingText("Menunggu Java startup...", "Java 21 sedang memuat game...");
    const started = await waitUntilRunning(15);

    if (!started) {
      throw new Error(
        "Game tidak dapat dijalankan dalam 15 detik. " +
        "Kemungkinan JAR crash saat startup."
      );
    }

    // 3. Delay singkat agar jendela game sempat muncul di virtual display
    setLoadingText("Membuka tampilan...", "Menunggu jendela game muncul...");
    await wait(1500);

    // 4. Tampilkan noVNC iframe
    const frame = document.getElementById("vnc-frame");
    if (!novncInitialized) {
      frame.src = NOVNC_URL;
      novncInitialized = true;
    }
    showVncFrame();

  } catch (err) {
    console.error("[Portal] playGame error:", err);
    document.getElementById("loading-text").textContent = `⚠️ ${err.message}`;
    document.querySelector(".loading-hint").textContent =
      "Coba kembali atau buka halaman ini di tab baru.";
  }
}

async function stopGame() {
  await apiStop();
}

async function goBack() {
  await apiStop();
  showGallery();
}

// ── Gallery ───────────────────────────────────────────────────────────────────

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
              id="play-btn-overlay-${idx}"
              type="button"
              aria-label="Main ${game.name}"
            >▶ Main</button>
          </div>
        </div>
        <div class="card-body">
          <h3 title="${game.name}">${game.name}</h3>
          ${game.description ? `<p class="card-desc">${game.description}</p>` : ""}
          <button
            class="btn btn-play"
            id="play-btn-${idx}"
            type="button"
          >▶ Mainkan</button>
        </div>
      `;

      const startPlay = () => playGame(jarFile, game.name);
      card.querySelector(`#play-btn-overlay-${idx}`).addEventListener("click", startPlay);
      card.querySelector(`#play-btn-${idx}`).addEventListener("click", startPlay);

      list.appendChild(card);
    });

  } catch (err) {
    list.innerHTML = `
      <div class="error-panel">
        <h3>Gagal memuat daftar game</h3>
        <p>${err.message}</p>
        <button class="btn btn-play" onclick="loadGames()" style="margin-top:1rem;width:auto;padding:.55rem 1.5rem">
          Coba lagi
        </button>
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
