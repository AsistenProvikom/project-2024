// Java Game Portal — CheerpJ 5.0 runtime

const GENERATED_PREFIX = "web-games/";
const GENERATED_LOAD_TIMEOUT_MS = 30000;
const DEFAULT_IMAGE = "./images/default.png";

let cheerpjReady = false;
let cheerpjFontLogFilterInstalled = false;
let activeSession = 0;
let generatedFrame = null;
let generatedFrameCleanup = null;
let generatedOrigin = "";

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

function normalizeGeneratedOrigin(value) {
  if (typeof value !== "string" || !value.trim()) return "";
  const parsed = new URL(value.trim());
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("Origin pemutar generated harus memakai HTTP atau HTTPS.");
  }
  if (parsed.username || parsed.password || parsed.pathname !== "/" || parsed.search || parsed.hash) {
    throw new Error("Origin pemutar generated hanya boleh berisi skema, host, dan port.");
  }
  return parsed.origin + "/";
}

async function loadPlayerConfig() {
  try {
    const response = await fetch("data/player-config.json", { cache: "no-store" });
    if (!response.ok) return;
    const config = await response.json();
    generatedOrigin = normalizeGeneratedOrigin(config.generatedOrigin);
  } catch (error) {
    console.error("[Portal] Invalid player configuration:", error);
    generatedOrigin = "";
  }
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

    const baseUrl = generatedOrigin || document.baseURI;
    const frameUrl = new URL(entry, baseUrl);
    const generatedRoot = new URL(GENERATED_PREFIX, baseUrl);
    if (frameUrl.origin !== generatedRoot.origin || !frameUrl.pathname.startsWith(generatedRoot.pathname)) {
      throw new Error("Artifact game generated keluar dari direktori pemutar yang diizinkan.");
    }

    return {
      mode: "generated",
      entry,
      frameUrl,
      crossOrigin: frameUrl.origin !== window.location.origin,
    };
  }

  return { mode: "legacy", crossOrigin: false };
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
    frame.referrerPolicy = player.crossOrigin ? "no-referrer" : "same-origin";
    frame.setAttribute("allow", "autoplay; fullscreen; gamepad");
    frame.dataset.isolation = player.crossOrigin ? "cross-origin" : "same-origin-trusted";
    frame.setAttribute(
      "sandbox",
      player.crossOrigin
        ? "allow-scripts allow-pointer-lock"
        : "allow-scripts allow-same-origin"
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
      const isolationHint = player.crossOrigin
        ? "Menyiapkan pemutar web pada origin terpisah..."
        : "Menyiapkan pemutar web dari origin tepercaya...";
      showLoading(`Memuat ${game.name}...`, isolationHint);
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

function safeImageSource(value) {
  if (typeof value !== "string") return DEFAULT_IMAGE;
  const candidate = value.trim();
  const hasScheme = /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(candidate);
  if (
    !candidate ||
    candidate.startsWith("//") ||
    candidate.startsWith("/") ||
    candidate.includes("..") ||
    candidate.includes("\\") ||
    hasScheme ||
    !/^[A-Za-z0-9._~!$&()*+,;=:@%/-]+$/.test(candidate)
  ) {
    return DEFAULT_IMAGE;
  }
  return candidate;
}

function gameText(value, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function showSkeleton(list) {
  const grid = document.createElement("div");
  grid.className = "skeleton-grid";
  for (let index = 0; index < 6; index += 1) {
    const card = document.createElement("div");
    card.className = "skeleton-card";
    grid.appendChild(card);
  }
  list.replaceChildren(grid);
}

function showCatalogError(list, error) {
  const panel = document.createElement("div");
  panel.className = "error-panel";

  const heading = document.createElement("h3");
  heading.textContent = "Gagal memuat daftar game";

  const message = document.createElement("p");
  message.textContent = error && error.message ? error.message : String(error);

  const retry = document.createElement("button");
  retry.className = "btn btn-play";
  retry.type = "button";
  retry.textContent = "Coba lagi";
  retry.addEventListener("click", loadGames);

  panel.append(heading, message, retry);
  list.replaceChildren(panel);
}

function createGameCard(game, index) {
  if (!game || typeof game !== "object") return null;
  const name = gameText(game.name, "Game");
  const description = gameText(game.description);
  const playerMode = game.player && game.player.mode === "generated" ? "generated" : "legacy";

  const card = document.createElement("div");
  card.className = "game-card";
  card.dataset.playerMode = playerMode;
  card.style.animationDelay = `${index * 60}ms`;

  const imageWrap = document.createElement("div");
  imageWrap.className = "card-image-wrap";

  const image = document.createElement("img");
  image.className = "card-image";
  image.src = safeImageSource(game.image);
  image.alt = name;
  image.loading = "lazy";
  image.addEventListener("error", () => {
    if (image.src !== new URL(DEFAULT_IMAGE, document.baseURI).href) {
      image.src = DEFAULT_IMAGE;
    }
  });

  const overlay = document.createElement("div");
  overlay.className = "card-overlay";
  const bigPlay = document.createElement("button");
  bigPlay.className = "btn btn-play-big";
  bigPlay.type = "button";
  bigPlay.textContent = "▶ Main";
  overlay.appendChild(bigPlay);
  imageWrap.append(image, overlay);

  const body = document.createElement("div");
  body.className = "card-body";

  const title = document.createElement("h3");
  title.title = name;
  title.textContent = name;
  body.appendChild(title);

  if (description) {
    const desc = document.createElement("p");
    desc.className = "card-desc";
    desc.textContent = description;
    body.appendChild(desc);
  }

  const play = document.createElement("button");
  play.className = "btn btn-play";
  play.type = "button";
  play.textContent = "▶ Mainkan";
  body.appendChild(play);

  const start = () => playGame(game);
  bigPlay.addEventListener("click", start);
  play.addEventListener("click", start);

  card.append(imageWrap, body);
  return card;
}

async function loadGames() {
  const list = document.getElementById("game-list");
  showSkeleton(list);

  try {
    await loadPlayerConfig();
    const response = await fetch("data/games.json");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const games = await response.json();
    if (!Array.isArray(games)) throw new Error("Format katalog game tidak valid.");

    const cards = games.map((game, index) => createGameCard(game, index)).filter(Boolean);
    list.replaceChildren(...cards);
  } catch (error) {
    console.error("[Portal] Failed to load games:", error);
    showCatalogError(list, error);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadGames();
  document.getElementById("btn-back").addEventListener("click", goBack);
  document.getElementById("btn-stop").addEventListener("click", stopGame);
});
