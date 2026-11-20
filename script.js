// Java Game Portal — CheerpJ 5.0 runtime

const GENERATED_PREFIX = "web-games/";
const GENERATED_LOAD_TIMEOUT_MS = 30000;

let cheerpjReady = false;
let cheerpjFontLogFilterInstalled = false;
let activeSession = 0;
let generatedFrame = null;
let generatedFrameCleanup = null;

const GAME_DEPENDENCIES = {
  "PaddleGame.jar": ["lib/AbsoluteLayout.jar"],
};

function suppressCheerpJFontLogs() {
  if (cheerpjFontLogFilterInstalled) return;

  const methods = ["log", "info", "warn", "error"];
  methods.forEach((method) => {
    const original = console[method];
    console[method] = (...args) => {
      if (typeof args[0] === "string" &&
          args[0].startsWith("CheerpJ: Font rempping for")) {
        return;
      }
      original.apply(console, args);
    };
  });

  cheerpjFontLogFilterInstalled = true;
}

async function initCheerpJ() {
  if (cheerpjReady) return;

  suppressCheerpJFontLogs();
  await cheerpjInit({ version: 25, status: "none" });
  cheerpjReady = true;
}

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
  document.querySelector(".loading-hint").textContent = hint;
  document.getElementById("loading-overlay").classList.remove("hidden");
  document.getElementById("canvas-wrapper").classList.add("hidden");
  document.getElementById("generated-wrapper").classList.add("hidden");
}

function showApplet() {
  document.getElementById("loading-overlay").classList.add("hidden");
  document.getElementById("generated-wrapper").classList.add("hidden");
  document.getElementById("canvas-wrapper").classList.remove("hidden");
}

function showGeneratedPlayer() {
  document.getElementById("loading-overlay").classList.add("hidden");
  document.getElementById("canvas-wrapper").classList.add("hidden");
  document.getElementById("generated-wrapper").classList.remove("hidden");
}

function clearLegacyApplet() {
  document.getElementById("applet").replaceChildren();
}

function teardownGeneratedPlayer() {
  if (generatedFrameCleanup) {
    const cleanup = generatedFrameCleanup;
    generatedFrameCleanup = null;
    cleanup();
  }

  const host = document.getElementById("generated-frame-host");
  host.querySelectorAll("iframe").forEach((frame) => {
    frame.src = "about:blank";
    frame.remove();
  });

  generatedFrame = null;
  document.getElementById("generated-wrapper").classList.add("hidden");
}

function beginSession(mode) {
  activeSession += 1;
  teardownGeneratedPlayer();
  clearLegacyApplet();
  document.body.dataset.playerMode = mode;
  return activeSession;
}

function isCurrentSession(session) {
  return session === activeSession;
}

function resolvePlayer(game) {
  const player = game.player && typeof game.player === "object" ? game.player : {};

  if (player.mode === "generated") {
    const entry = typeof player.entry === "string" ? player.entry.trim() : "";
    const invalidPath =
      !entry.startsWith(GENERATED_PREFIX) ||
      entry.startsWith("/") ||
      entry.includes("..") ||
      entry.includes("\\");

    if (invalidPath) {
      throw new Error("Path artifact game generated tidak valid.");
    }

    const frameUrl = new URL(entry, document.baseURI);
    if (frameUrl.origin !== window.location.origin) {
      throw new Error("Artifact game generated harus berada di origin yang sama.");
    }

    return { mode: "generated", entry, frameUrl };
  }

  return { mode: "legacy" };
}

async function loadGameJar(jarFile) {
  const jarName = jarFile.split("/").pop();
  const fileName = encodeURIComponent(jarName);
  const dependencies = GAME_DEPENDENCIES[jarName] || [];

  for (const dependency of dependencies) {
    await loadGameFile(dependency, `/str/${dependency}`);
  }

  await loadGameFile(jarName, `/str/${fileName}`);
  return `/str/${fileName}`;
}

async function loadGameFile(relativePath, virtualPath) {
  const url = new URL(`games/${relativePath}`, document.baseURI);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Gagal memuat JAR (${response.status}): ${url.pathname}`);
  }

  const bytes = new Uint8Array(await response.arrayBuffer());
  cheerpOSAddStringFile(virtualPath, bytes);
}

async function runLegacyGame(jarFile, gameName, session) {
  if (!jarFile) {
    throw new Error("File JAR game tidak tersedia.");
  }

  showLoading(`Memulai ${gameName}...`, "Menginisialisasi CheerpJ 5.0 di browser...");
  await initCheerpJ();
  if (!isCurrentSession(session)) return;

  showLoading(`Menjalankan ${gameName}...`, "Memuat aplikasi Java...");

  const applet = document.getElementById("applet");
  applet.replaceChildren();
  cheerpjCreateDisplay(-1, -1, applet);
  showApplet();

  const virtualPath = await loadGameJar(jarFile);
  if (!isCurrentSession(session)) return;
  await cheerpjRunJar(virtualPath);
}

function runGeneratedGame(player, gameName, session) {
  return new Promise((resolve, reject) => {
    const host = document.getElementById("generated-frame-host");
    host.replaceChildren();

    const frame = document.createElement("iframe");
    frame.id = "generated-frame";
    frame.className = "generated-frame";
    frame.title = `Pemutar game ${gameName}`;
    frame.loading = "eager";
    frame.referrerPolicy = "same-origin";
    frame.setAttribute("allow", "autoplay; fullscreen; clipboard-write; gamepad");
    frame.setAttribute(
      "sandbox",
      "allow-scripts allow-same-origin allow-forms allow-modals allow-downloads allow-pointer-lock"
    );

    let settled = false;
    const finish = (callback) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      if (generatedFrameCleanup === cancel) generatedFrameCleanup = null;
      callback();
    };
    const cancel = () => finish(resolve);
    const timeout = setTimeout(() => {
      finish(() => reject(new Error("Pemutar web game melewati batas waktu pemuatan.")));
    }, GENERATED_LOAD_TIMEOUT_MS);

    frame.addEventListener("load", () => {
      if (frame.src === "about:blank") return;
      finish(() => {
        if (!isCurrentSession(session)) return;
        showGeneratedPlayer();
        resolve();
      });
    }, { once: true });

    frame.addEventListener("error", () => {
      finish(() => reject(new Error("Gagal memuat pemutar web game.")));
    }, { once: true });

    generatedFrame = frame;
    generatedFrameCleanup = cancel;
    frame.src = player.frameUrl.href;
    host.appendChild(frame);
  });
}

async function playGame(game) {
  showGameView();
  document.getElementById("game-topbar-title").textContent = game.name;

  let player;
  try {
    player = resolvePlayer(game);
  } catch (error) {
    console.error("[Portal] Invalid player metadata:", error);
    beginSession(null);
    showLoading(`⚠️ ${error.message}`, "Periksa metadata game.");
    return;
  }

  const session = beginSession(player.mode);

  try {
    if (player.mode === "generated") {
      showLoading(`Memuat ${game.name}...`, "Menyiapkan pemutar web terisolasi...");
      await runGeneratedGame(player, game.name, session);
      return;
    }

    await runLegacyGame(game.jar || game.file || "", game.name, session);
  } catch (error) {
    if (!isCurrentSession(session)) return;
    console.error("[Portal] Failed to run game:", error);
    teardownGeneratedPlayer();
    showLoading(`⚠️ ${error.message}`, "Coba kembali atau refresh halaman.");
  }
}

function stopGame() {
  activeSession += 1;
  teardownGeneratedPlayer();
  clearLegacyApplet();
  showLoading("Game dihentikan.", "Klik 'Kembali' untuk ke gallery.");
}

function goBack() {
  activeSession += 1;
  teardownGeneratedPlayer();
  clearLegacyApplet();
  showLoading("Game dihentikan.", "Klik 'Kembali' untuk ke gallery.");
  showGallery();
}

async function loadGames() {
  const list = document.getElementById("game-list");
  list.innerHTML =
    `<div class="skeleton-grid">${"<div class='skeleton-card'></div>".repeat(6)}</div>`;

  try {
    const response = await fetch("data/games.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const games = await response.json();
    list.innerHTML = "";

    games.forEach((game, index) => {
      const card = document.createElement("div");
      card.className = "game-card";
      card.dataset.playerMode = game.player && game.player.mode === "generated"
        ? "generated"
        : "legacy";
      card.style.animationDelay = `${index * 60}ms`;
      card.innerHTML = `
        <div class="card-image-wrap">
          <img class="card-image" src="${game.image || "./images/default.png"}"
               alt="${game.name}" loading="lazy"
               onerror="this.src='./images/default.png'" />
          <div class="card-overlay">
            <button class="btn btn-play-big" type="button">▶ Main</button>
          </div>
        </div>
        <div class="card-body">
          <h3 title="${game.name}">${game.name}</h3>
          ${game.description ? `<p class="card-desc">${game.description}</p>` : ""}
          <button class="btn btn-play" type="button">▶ Mainkan</button>
        </div>`;

      const start = () => playGame(game);
      card.querySelector(".btn-play-big").addEventListener("click", start);
      card.querySelector(".btn-play").addEventListener("click", start);
      list.appendChild(card);
    });
  } catch (error) {
    console.error("[Portal] Failed to load games:", error);
    list.innerHTML = `
      <div class="error-panel">
        <h3>Gagal memuat daftar game</h3>
        <p>${error.message}</p>
        <button class="btn btn-play" type="button" onclick="loadGames()">Coba lagi</button>
      </div>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadGames();
  document.getElementById("btn-back").addEventListener("click", goBack);
  document.getElementById("btn-stop").addEventListener("click", stopGame);
});
