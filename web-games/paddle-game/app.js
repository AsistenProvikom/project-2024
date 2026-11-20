// Provikom Converter - CheerpJ 5.0 Runtime Controller
// Official APIs: cheerpjInit, cheerpjCreateDisplay, cheerpjRunJar, cheerpjRunMain

const CONFIG = {
  "gameJar": "PaddleGame.jar",
  "runtimeVersion": 8,
  "runtimeLabel": "Java 8",
  "isExperimental": false,
  "mainClass": "keyboarddemo.LevelFrame",
  "classPath": [
    "/str/PaddleGame.jar",
    "/str/AbsoluteLayout.jar"
  ],
  "virtualMountRoot": "/str/",
  "jarVirtualPath": "/str/PaddleGame.jar",
  "dependencies": [
    {
      "relative_path": "lib/AbsoluteLayout.jar",
      "virtual_path": "/str/AbsoluteLayout.jar",
      "size_bytes": 17218,
      "sha256": "cbe5600e86eb64761e11e4cb046804a070bc214e00b9fa61413b59017089dfd1"
    }
  ]
};

const FATAL_PATTERNS = [
  /ExceptionInInitializerError/,
  /NoClassDefFoundError/,
  /UnsatisfiedLinkError/,
  /No line matching interface/,
  /Exception in thread/,
  /Caused by:/
];

let initialized = false;
let starting = false;
let javaFailureReported = false;
let consoleBuffer = [];

function setStatus(status, detail) {
  document.body.dataset.status = status;
  if (detail) {
    document.body.dataset.statusDetail = detail;
  } else {
    delete document.body.dataset.statusDetail;
  }
}

function showOverlay(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("hidden");
}

function hideOverlay(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add("hidden");
}

function updateLoadingStep(stepId, heading, subtext) {
  const steps = ["step-env", "step-deps", "step-jar", "step-run"];
  let passed = true;
  for (const step of steps) {
    const el = document.getElementById(step);
    if (!el) continue;
    if (step === stepId) {
      el.className = "step step-active";
      passed = false;
    } else if (passed) {
      el.className = "step step-done";
    } else {
      el.className = "step";
    }
  }
  if (heading) document.getElementById("loading-heading").textContent = heading;
  if (subtext) document.getElementById("loading-subtext").textContent = subtext;
}

function showError(title, message, details) {
  setStatus("error", title);
  hideOverlay("overlay-start");
  hideOverlay("overlay-loading");
  showOverlay("overlay-error");

  document.getElementById("error-title").textContent = title;
  document.getElementById("error-message").textContent = message;

  const detailsEl = document.getElementById("error-details");
  if (details) {
    detailsEl.textContent = details;
    detailsEl.classList.remove("hidden");
  } else {
    detailsEl.textContent = "";
    detailsEl.classList.add("hidden");
  }
  console.error("[Provikom Player Error]", title, message, details || "");
}

function reportJavaFailure() {
  if (javaFailureReported) return;
  javaFailureReported = true;

  const relevant = consoleBuffer.filter((line) =>
    FATAL_PATTERNS.some((pattern) => pattern.test(line))
  );
  const summary = relevant[0] || "The Java runtime reported an exception.";
  setStatus("error", "java-exception");
  showError(
    "Java Runtime Error Detected",
    "The Java process raised an exception. The game window may not appear or may not be playable.",
    (relevant.length ? relevant : consoleBuffer).join("\n")
  );
  document.body.dataset.javaError = summary;
}

function installRuntimeDiagnostics() {
  const methods = ["log", "info", "warn", "error"];
  methods.forEach((method) => {
    const original = console[method];
    console[method] = (...args) => {
      const text = args.map((arg) => String(arg)).join(" ");
      if (text.startsWith("CheerpJ: Font remapping for")) return;
      consoleBuffer.push(text);
      if (consoleBuffer.length > 80) consoleBuffer.shift();
      if (FATAL_PATTERNS.some((pattern) => pattern.test(text))) {
        setTimeout(reportJavaFailure, 150);
      }
      original.apply(console, args);
    };
  });

  window.addEventListener("error", (event) => {
    showError("JavaScript Error", event.message || "Unexpected browser error", event.error ? String(event.error.stack || event.error) : null);
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    showError("Unhandled Promise Rejection", String(reason && reason.message ? reason.message : reason), reason && reason.stack ? String(reason.stack) : null);
  });
}

async function installGameFiles() {
  const files = [
    { relative_path: CONFIG.gameJar, virtual_path: CONFIG.jarVirtualPath },
    ...CONFIG.dependencies,
  ];

  for (const file of files) {
    const url = new URL(file.relative_path, document.baseURI);
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Required file not found (HTTP ${response.status}): ${url.pathname}`);
    }
    const bytes = new Uint8Array(await response.arrayBuffer());
    cheerpOSAddStringFile(file.virtual_path, bytes);
  }
}

function focusCanvas() {
  const display = document.getElementById("cheerpj-display");
  const canvas = display.querySelector("canvas");
  if (canvas) {
    canvas.tabIndex = 0;
    canvas.focus();
  }
}

async function launchGame() {
  if (starting) return;
  starting = true;

  hideOverlay("overlay-start");
  showOverlay("overlay-loading");
  setStatus("initializing");

  try {
    updateLoadingStep("step-env", "Initializing Java Runtime", `Configuring CheerpJ 5.0 (${CONFIG.runtimeLabel})...`);
    if (typeof cheerpjInit !== "function") {
      throw new Error("The CheerpJ loader script did not load. Check network access to the CheerpJ CDN.");
    }

    await cheerpjInit({ version: CONFIG.runtimeVersion, status: "none" });
    initialized = true;

    updateLoadingStep("step-deps", "Checking Dependencies", "Loading files from the artifact directory...");
    await installGameFiles();

    updateLoadingStep("step-jar", "Mounting Game Archive", `Preparing ${CONFIG.gameJar}...`);
    const displayElement = document.getElementById("cheerpj-display");
    displayElement.replaceChildren();
    cheerpjCreateDisplay(-1, -1, displayElement);

    updateLoadingStep("step-run", "Starting Game", "Executing the Java entry point...");
    hideOverlay("overlay-loading");
    setStatus("running");
    setTimeout(focusCanvas, 250);

    let exitCode;
    if (CONFIG.mainClass) {
      exitCode = await cheerpjRunMain(CONFIG.mainClass, CONFIG.classPath.join(":"));
    } else {
      exitCode = await cheerpjRunJar(CONFIG.jarVirtualPath);
    }

    if (typeof exitCode === "number" && exitCode !== 0) {
      showError("Game Exited", `The Java process exited with code ${exitCode}.`, null);
    } else {
      setStatus("exited");
    }
  } catch (error) {
    showError("Launch Error", error && error.message ? error.message : String(error), error && error.stack ? String(error.stack) : null);
  } finally {
    starting = false;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  installRuntimeDiagnostics();
  setStatus("idle");

  document.getElementById("btn-start").addEventListener("click", launchGame);
  document.getElementById("btn-retry").addEventListener("click", () => window.location.reload());
  document.getElementById("btn-dismiss").addEventListener("click", () => {
    hideOverlay("overlay-error");
    setStatus(initialized ? "running" : "idle");
  });
  document.getElementById("btn-copy-error").addEventListener("click", () => {
    const text = document.getElementById("error-details").textContent;
    navigator.clipboard.writeText(text).then(
      () => alert("Error details copied to clipboard."),
      () => alert("Could not copy error details.")
    );
  });
  document.getElementById("btn-restart").addEventListener("click", () => window.location.reload());
  document.getElementById("btn-fullscreen").addEventListener("click", () => {
    const container = document.getElementById("canvas-container");
    if (!document.fullscreenElement) {
      container.requestFullscreen().catch((error) => console.warn("Fullscreen request denied:", error));
    } else {
      document.exitFullscreen();
    }
  });
});
