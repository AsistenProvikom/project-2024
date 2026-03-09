// Java Game Portal - CheerpJ v4.2 Runtime

let cheerpjReady = false;

async function initCheerpJ() {
  if (cheerpjReady) return;
  await cheerpjInit({
    version: 17,
  });
  cheerpjReady = true;
  console.log("CheerpJ initialized");
}

function showGallery() {
  document.getElementById("gallery-section").classList.remove("hidden");
  document.getElementById("game-section").classList.add("hidden");
}

function showGame() {
  document.getElementById("gallery-section").classList.add("hidden");
  document.getElementById("game-section").classList.remove("hidden");
}

async function loadGames() {
  try {
    const response = await fetch("data/games.json");
    const games = await response.json();
    const listContainer = document.getElementById("game-list");
    listContainer.innerHTML = "";

    games.forEach((game) => {
      const card = document.createElement("div");
      card.className = "game-card";

      let jarPath = game.jar || game.file || `games-jdk17/${game.filename}`;
      jarPath = jarPath.replace(/^\.\//, "");
      if (!jarPath.startsWith("/app/")) {
        jarPath = "/app/" + jarPath;
      }

      card.innerHTML = `
        <img class="card-image" src="${game.image}" alt="${game.name}">
        <div class="card-body">
          <h3>${game.name}</h3>
          <button class="btn btn-play" type="button">Play</button>
        </div>
      `;

      const btn = card.querySelector("button");
      btn.addEventListener("click", () => playGame(jarPath, game.name));
      listContainer.appendChild(card);
    });
  } catch (e) {
    document.getElementById("game-list").innerHTML =
      `<div class="error-panel"><h3>Failed to load games</h3><p>${e.message}</p></div>`;
    console.error("Failed to load games:", e);
  }
}

async function playGame(jarPath, gameName) {
  const container = document.getElementById("game-container");
  showGame();

  // Show loading state
  container.innerHTML = `
    <button class="btn btn-back" onclick="showGallery()">Back to Library</button>
    <div class="loader">
      <div class="spinner"></div>
      <p id="status">Initializing runtime...</p>
    </div>
  `;

  try {
    const statusEl = document.getElementById("status");

    statusEl.textContent = "Initializing CheerpJ runtime...";
    await initCheerpJ();

    statusEl.textContent = "Launching " + gameName + "...";

    container.innerHTML = `
      <button class="btn btn-back" onclick="showGallery()">Back to Library</button>
      <h2 class="game-title">${gameName}</h2>
      <div id="applet" style="width:800px; height:600px;"></div>
    `;

    cheerpjCreateDisplay(800, 600, document.getElementById("applet"));

    console.log("Running jar:", jarPath);
    await cheerpjRunJar(jarPath);
    console.log("Game running");
  } catch (err) {
    console.error("Error:", err);

    container.innerHTML = `
      <button class="btn btn-back" onclick="showGallery()">Back to Library</button>
      <div class="error-panel">
        <h3>Failed to run ${gameName}</h3>
        <p>${err.message}</p>
        <details>
          <summary>Debug Info</summary>
          <pre>${err.stack}</pre>
        </details>
        <h4 style="margin-top:1rem; color: var(--text-secondary); font-size:0.9rem;">Troubleshooting</h4>
        <ol class="solutions">
          <li>Refresh the page and try again</li>
          <li>CheerpJ may take a moment to download on first load</li>
          <li>Open browser console (F12) for more details</li>
        </ol>
      </div>
    `;
  }
}

// Load games when page ready
document.addEventListener("DOMContentLoaded", loadGames);
if (document.readyState !== "loading") {
  loadGames();
}
