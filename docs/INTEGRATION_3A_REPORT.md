# Milestone 3A — Generated Player Pilot Integration

Date: 2026-11-21
Branch: `feature/converter-pilot-integration`
Base commit: `cf35f7def1333bf05b3de22206e803567bc7de3b`
Converter reference: `java-converter` `main` at `de4a505`

## Outcome

- Integrated generated CheerpJ players for Car Traffic, Flappy Bird, and Paddle Game.
- Preserved the existing CheerpJ launcher path for Froggie Cross the Road, Minesweeper, Pong, and Snake.
- Added a deterministic offline PR gate and kept external-cheerpJ browser checks in a separate manual workflow.
- Added a fail-closed release gate for the existing GitHub Pages deployment.
- Refreshed artifact ownership markers after adaptation while preserving each original `artifact_id`.
- No converter adapter/compiler changes, JAR rewrites, production deployment, or merge were performed.

The code is hardened for review. Publication is intentionally blocked until licensing and legacy visual acceptance are complete.

## Hardening Pass

### 1. Pull-request CI gate

- `.github/workflows/pilot-integrity.yml` runs on `pull_request`.
- `tools/verify_static.py` checks source hashes, catalog entries, artifact files, `/str/` manifests, runtime consistency, release-gate behavior, DOM-injection sinks, and workflow separation without network access.
- `tools/verify_offline.py` runs Chromium with all external requests aborted. It checks gallery rendering, metadata-injection safety, generated-path rejection, iframe lifecycle, and same-origin/cross-origin attributes.
- `.github/workflows/pilot-browser-cdn.yml` is `workflow_dispatch` only and runs `tools/verify_pilot.py`. It is not a PR pass and no skipped CDN check is represented as successful.

### 2. Manifest and `/str/` consistency

- All generated manifests now describe the actual runtime:
  - `paths.virtual_mount_root` is `/str/`.
  - `paths.main_jar_virtual_path` is `/str/<main>.jar`.
  - `paths.class_path` uses `/str/` only.
  - dependency `virtual_path` values are flattened under `/str/`.
- `tools/adapt_generated_artifact.py` applies the adaptation after regeneration and supports `--check`.
- `--check` is part of the static PR gate, so a regenerated, non-adapted artifact fails CI.
- The adapter validates the converter's existing ownership marker before writing. After manifest changes it refreshes only `manifest_sha256` against the new raw manifest bytes, preserving `artifact_id`, owner, and schema.
- Missing, mismatched, or unsupported ownership proof is rejected; the adapter does not create new ownership proof for unrelated directories.
- `tools/test_adaptation.py` covers marker validity, SHA refresh after manifest changes, repeated-adaptation idempotence, and rejection of missing/mismatched/stale markers.
- The adapter was tested against fresh converter output for Car Traffic and Paddle Game, including Paddle's nested `lib/AbsoluteLayout.jar` dependency and marker refresh.

### 3. Iframe trust boundary and isolation

- Same-origin mode is now described as a **trusted-content lifecycle boundary**, not security isolation. `allow-scripts` plus `allow-same-origin` cannot isolate same-origin content.
- Same-origin sandbox tokens were reduced to `allow-scripts allow-same-origin`; forms, modals, downloads, and clipboard access were removed.
- Optional cross-origin mode is implemented through `data/player-config.json`:
  - Set `generatedOrigin` to an absolute separate origin.
  - The iframe then omits `allow-same-origin`, uses `referrerPolicy="no-referrer"`, and is marked `data-isolation="cross-origin"`.
  - The generated origin must serve `/web-games/` with CORS headers. `nginx.conf` now provides them, including `OPTIONS 204`.
- The default remains same-origin because GitHub Pages cannot supply a second origin automatically. Only repository-controlled generated artifacts are permitted.

### 4. Legacy coverage

- Automated legacy checks now explicitly cover **launcher, snapshot, Stop, and Back** only.
- Evidence includes `verification_scope.legacy_gameplay = "not verified by this script"`.
- Snake's legacy window launches but is visually blank in the captured screenshot. This is recorded as an unresolved gameplay limitation, not a gameplay pass.
- Froggie, Minesweeper, Pong, and Snake gameplay still require manual acceptance.

### 5. Production publication gate

- `.github/workflows/pages.yml` preserves the existing Pages deployment steps but adds a `release-gate` job.
- `deploy` depends on `release-gate`, and `tools/check_release_gate.py` fails closed unless repository variable `PILOT_RELEASE_APPROVED` is exactly `"true"`.
- Tested locally: unset, `false`, and `1` all block; `true` opens the gate.
- Do not set the variable until licensing/redistribution approval, CheerpJ Community Edition usage approval, and legacy visual acceptance are complete.

### 6. Catalog rendering

- Removed all dynamic `innerHTML`, `outerHTML`, `insertAdjacentHTML`, and `document.write` usage from `script.js`.
- Catalog cards are built with DOM APIs and `textContent`.
- Image paths are restricted to safe local relative paths; unsafe values fall back to `./images/default.png`.
- Offline regression test injects malicious name, description, image, and title metadata and confirms no script executes and no injected SVG/script/image node appears.

## Artifacts

| Game | Entry | Runtime | Target | Main class | Dependency |
| --- | --- | --- | --- | --- | --- |
| Car Traffic | `web-games/car-traffic/index.html` | Java 25 experimental | Java 22 | `main.Main` | none |
| Flappy Bird | `web-games/flappy/index.html` | Java 25 experimental | Java 22 | `MainMenu` | none |
| Paddle Game | `web-games/paddle-game/index.html` | Java 8 | Java 8 | `keyboarddemo.LevelFrame` | `lib/AbsoluteLayout.jar` |

Source hashes remained unchanged:

| Source | SHA-256 |
| --- | --- |
| `games/CarTraffic.jar` | `ff1e14564f77cb356ec9ffbee82fb1291981c57471082b7c0faa5cc6bcff1f2e` |
| `games/flappy.jar` | `c788986652405b12962066c61fc2c3cfe843335a6e3a4ae4ef6f4d3a0de4b0ea` |
| `games/PaddleGame.jar` | `41b423488d9aba93f184ce56281417a836996417e5ed85404b8174034973b8dd` |
| `games/lib/AbsoluteLayout.jar` | `cbe5600e86eb64761e11e4cb046804a070bc214e00b9fa61413b59017089dfd1` |

## Generated Artifact Adaptations

The generated players were built with the existing converter CLI and then adapted only in the generated browser entry points.

- Generated players assume CheerpJ `/app/` maps to the origin root. Under `/web-games/<slug>/`, CheerpJ requested `/CarTraffic.jar` and failed with `ClassNotFoundException: main.Main`.
- `overrideDocumentBase` was attempted and rejected because it caused `TypeError: Cannot read properties of null (reading 'f0')`.
- The adapted `app.js` fetches files relative to the artifact directory and installs them with `cheerpOSAddStringFile` under `/str/`.
- Paddle's `AbsoluteLayout.jar` is flattened to `/str/AbsoluteLayout.jar`; `cheerpOSAddStringFile` does not accept nested directories such as `/str/lib/AbsoluteLayout.jar`.
- The original generated dependency remains available under `web-games/paddle-game/lib/AbsoluteLayout.jar` for Range-serving verification.

Regeneration workflow:

```bash
python3 tools/adapt_generated_artifact.py \
  web-games/car-traffic web-games/flappy web-games/paddle-game
python3 tools/adapt_generated_artifact.py --check \
  web-games/car-traffic web-games/flappy web-games/paddle-game
python3 tools/test_adaptation.py
```

## Portal Integration

- `data/games.json` declares `player.mode` as `generated` or `legacy`; generated games also declare `player.entry`.
- Generated games load in an iframe only after the user selects Play. No generated JavaScript is loaded on the gallery.
- Generated entry paths must start with `web-games/`, may not be absolute or contain `..`/backslashes, and must remain under the generated root.
- Session counters and teardown guards prevent stale async legacy launches from replacing a newer generated session.
- Stop, Back, game switching, and restart remove generated iframes and clear legacy applet content.

## Verification Results

### Offline PR gate

```bash
python3 tools/verify_static.py
python3 tools/test_adaptation.py
python3 tools/verify_offline.py
```

- Static integrity: **68/68 passed**.
- Ownership/adaptation regression: **7/7 tests passed**.
- Offline Chromium: **20/20 passed**.
- External network: blocked during the offline browser run.
- Static checks include release-gate fail-closed and pass-open behavior.

### GitHub Actions PR gate

- Marker-fix run: `https://github.com/AsistenProvikom/project-2024/actions/runs/44884953000`
- Commit: `148da568cfa25f79dff5e81cee062f362f6ceaf3`
- Result: **success**
- `Static integrity and release gate`: **pass**, 9 seconds. This job also runs the ownership/adaptation regression tests.
- `Offline browser/catalog checks`: **pass**, 32 seconds.
- The external CDN workflow was not run as part of this PR gate and is not represented as a pass.

### External CDN browser suite

```bash
python3 tools/verify_pilot.py
```

Latest successful local run: **53/53 checks passed**. Evidence was regenerated at `2026-11-21T07:33:29Z`.

Coverage includes:

- All seven catalog cards and their declared player modes.
- No generated artifact loaded before Play and no iframe present on the gallery.
- Car Traffic generated launch, canvas mount, menu render, interaction, restart, Stop, and Back teardown.
- Flappy generated launch, canvas mount, menu render, PLAY transition, Stop, and Back teardown.
- Paddle generated launch, level selection, Easy-mode transition, dependency Range request, Stop, and Back teardown.
- Paddle `AbsoluteLayout.jar` Range response: HTTP 206 with `Accept-Ranges: bytes`.
- Snake legacy launcher surface, snapshot, Stop cleanup, and Back navigation.
- Source hash preservation and absence of fatal console/page errors.
- Pong was not launched; the catalog discloses its known browser-audio/runtime limitation.

Evidence: `docs/verification/3a-integration.json`.

### Docker

- `docker build -t java-game-portal:3a-hardening .` succeeds.
- `/web-games/car-traffic/index.html` returns HTTP 200 with CORS and `Cross-Origin-Resource-Policy: cross-origin`.
- Paddle dependency Range request returns HTTP 206 with `Content-Range: bytes 0-1/17218`.
- `OPTIONS /web-games/car-traffic/index.html` returns HTTP 204 with the expected CORS headers.

### Screenshots

- `docs/screenshots/3a-gallery.png`
- `docs/screenshots/3a-car-traffic-generated.png`
- `docs/screenshots/3a-car-traffic-interaction.png`
- `docs/screenshots/3a-flappy-generated.png`
- `docs/screenshots/3a-flappy-gameplay.png`
- `docs/screenshots/3a-paddle-level.png`
- `docs/screenshots/3a-paddle-easy.png`
- `docs/screenshots/3a-legacy-snake.png`

## Manual Visual Review

- Gallery layout and seven cards look correct.
- Car Traffic generated menu renders and responds to interaction.
- Flappy generated menu and PLAY gameplay render.
- Paddle level selection and Easy gameplay render.
- Snake's legacy window launches but appears mostly blank; gameplay remains unverified.
- Froggie, Minesweeper, and Pong were not visually confirmed in this milestone.

No claim is made that all legacy games are visually fully playable in the browser.

## Known Limitations and Blockers

- **Blocker — licensing/redistribution:** generated files duplicate the original JARs. Redistribution permission and CheerpJ Community Edition licensing must be approved before publication.
- **Blocker — legacy acceptance:** legacy gameplay, especially Snake's blank window, still needs manual acceptance.
- **Release gate:** `PILOT_RELEASE_APPROVED` must remain unset/false until the blockers are resolved. Merging to `main` will not deploy while the gate is closed.
- CheerpJ CDN availability is an external dependency. CDN browser checks are manual and can fail independently of the deterministic PR gate.
- Same-origin generated content is trusted code. The iframe is not a security boundary unless the optional separate-origin mode is configured.
- Pong's browser audio limitation is disclosed; it remains legacy-only.
- No auto-merge or deployment is included in this PR.

## Final Status

The PR is code-reviewed, locally tested, and its hardening commit passed the offline PR gate. It is **not safe to publish** until licensing and legacy visual acceptance are complete. The fail-closed release gate prevents accidental GitHub Pages publication. Do not merge with the intent to deploy until the blockers above are cleared.
