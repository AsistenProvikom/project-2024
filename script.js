// Java Game Portal — CheerpJ 5.0 runtime

let cheerpjReady = false;

async function initCheerpJ() {
  if (cheerpjReady) return;

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
}

function showApplet() {
  document.getElementById("loading-overlay").classList.add("hidden");
  document.getElementById("canvas-wrapper").classList.remove("hidden");
}

async function loadGameJar(jarFile) {
  const fileName = encodeURIComponent(jarFile.split("/").pop());
  const url = new URL(`games/${fileName}`, document.baseURI);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Gagal memuat JAR (${response.status}): ${url.pathname}`);
  }

  const bytes = new Uint8Array(await response.arrayBuffer());
  const virtualPath = `/str/${fileName}`;
  cheerpOSAddStringFile(virtualPath, bytes);
  return virtualPath;
}

async function playGame(jarFile, gameName) {
  showGameView();
  document.getElementById("game-topbar-title").textContent = gameName;
  showLoading(`Memulai ${gameName}...`, "Menginisialisasi CheerpJ 5.0 di browser...");

  try {
    await initCheerpJ();
    showLoading(`Menjalankan ${gameName}...`, "Memuat aplikasi Java...");

    const applet = document.getElementById("applet");
    applet.replaceChildren();
    cheerpjCreateDisplay(-1, -1, applet);
    showApplet();

    const virtualPath = await loadGameJar(jarFile);
    await cheerpjRunJar(virtualPath);
  } catch (error) {
    console.error("[Portal] Failed to run game:", error);
    showLoading(`⚠️ ${error.message}`, "Coba kembali atau refresh halaman.");
  }
}

function stopGame() {
  document.getElementById("applet").replaceChildren();
  showLoading("Game dihentikan.", "Klik 'Kembali' untuk ke gallery.");
}

function goBack() {
  stopGame();
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

      const start = () => playGame(game.jar || game.file || "", game.name);
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
