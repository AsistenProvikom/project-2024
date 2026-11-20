# Milestone 3A — Generated Player Pilot Integration

Date: 2026-11-20  
Branch: `feature/converter-pilot-integration`  
Base commit: `cf35f7def1333bf05b3de22206e803567bc7de3b`  
Converter reference: `java-converter` `main` at `de4a505`

## Outcome

- Integrated generated CheerpJ players for Car Traffic, Flappy Bird, and Paddle Game.
- Preserved the existing CheerpJ launcher path for Froggie Cross the Road, Minesweeper, Pong, and Snake.
- Automated Chromium verification passed all 53 checks; evidence is in `docs/verification/3a-integration.json`.
- Docker image builds and serves the portal and generated artifacts with HTTP 200/206 responses.
- No converter adapter/compiler changes, JAR rewrites, production deployment, or merge were performed.

The generated player path is usable for the pilot. Remaining limitations are listed below, most notably external CheerpJ CDN availability, legacy-game visual verification, and licensing review.

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
- Each generated `app.js` now fetches its game files relative to the artifact directory and installs them with `cheerpOSAddStringFile` under `/str/`.
- Paddle's `AbsoluteLayout.jar` is flattened to `/str/AbsoluteLayout.jar`; `cheerpOSAddStringFile` does not accept nested directories such as `/str/lib/AbsoluteLayout.jar`.
- Paddle's runtime classpath was updated to the flattened virtual path. The original generated dependency remains available under `web-games/paddle-game/lib/AbsoluteLayout.jar` for Range-serving verification.

These edits are artifact-local. Re-running the converter will regenerate `app.js` and require the same adaptation unless the converter is changed in a later milestone.

## Portal Integration

- `data/games.json` declares `player.mode` as `generated` or `legacy`; generated games also declare `player.entry`.
- Generated games load in a same-origin iframe only after the user selects Play. No generated JavaScript is loaded on the gallery.
- Generated entry paths must start with `web-games/`, may not be absolute or contain `..`/backslashes, and must remain on the portal origin.
- Session counters and teardown guards prevent stale async legacy launches from replacing a newer generated session.
- Stop, Back, game switching, and restart remove generated iframes and clear legacy applet content.
- The legacy CheerpJ launcher path remains available for the four non-pilot games.

## Automated Verification

Command:

```bash
python3 tools/verify_pilot.py
```

The script serves the repository with HTTP Range support, drives Chromium via Playwright, writes screenshots, and records machine-readable evidence. Evidence generated at `2026-11-20T10:21:41Z`:

- Total checks: 53
- Passed: 53
- Failed: 0
- Page errors: none
- Evidence: `docs/verification/3a-integration.json`

Coverage includes:

- All seven catalog cards and their declared player modes.
- No generated artifact loaded before Play and no iframe present on the gallery.
- Car Traffic generated launch, canvas mount, menu render, interaction, restart, Stop, and Back teardown.
- Flappy generated launch, canvas mount, menu render, PLAY transition, Stop, and Back teardown.
- Paddle generated launch, level selection, Easy-mode transition, dependency Range request, Stop, and Back teardown.
- Paddle `AbsoluteLayout.jar` Range response: HTTP 206 with `Accept-Ranges: bytes`.
- Snake legacy launcher, Stop cleanup, and Back navigation.
- Source hash preservation and absence of fatal console/page errors.
- Pong was not launched; the catalog discloses its known browser-audio/runtime limitation.

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
- Snake's legacy window appeared mostly blank in the review screenshot. The automated test confirms the legacy launcher/teardown path, not full visual gameplay.
- Froggie, Minesweeper, and Pong were not visually confirmed in this milestone. Pong remains legacy-only with its limitation disclosed.

No claim is made that all legacy games are visually fully playable in the browser.

## Docker and HTTP Checks

- `docker build -t java-game-portal:3a .` succeeds.
- Container runs as `java-game-portal-3a` on `127.0.0.1:18084`.
- `/` returns HTTP 200.
- `/web-games/car-traffic/index.html` returns HTTP 200.
- A Range request for `/web-games/paddle-game/lib/AbsoluteLayout.jar` returns HTTP 206 with `Content-Range: bytes 0-1/17218`.
- Generated directories were created with restrictive permissions, causing an initial Nginx 403. This was fixed in the source tree and in the image with `chmod -R a+rX /usr/share/nginx/html/web-games`.
- A final Docker browser smoke attempt reached the generated player but the external CheerpJ CDN stalled while repeatedly loading `https://cjrtnc.leaningtech.com/5.0/25/lib/modules`. The same stall occurred outside Docker, so it is not treated as a container defect. No invalid Docker screenshot is retained.

## Known Limitations and Follow-up

- CheerpJ CDN availability is an external dependency. `tools/verify_pilot.py` retries up to five times because replies such as `Failed to fetch dynamically imported module: https://cjrtnc.leaningtech.com/5.0/cj3.js` occur intermittently.
- Legacy visual gameplay for Froggie, Minesweeper, Pong, and Snake needs separate manual acceptance.
- Pong's browser audio limitation is disclosed in the catalog; it was not converted in this milestone.
- Generated files duplicate the original JARs. Redistribution and CheerpJ Community Edition licensing require review before publication. CheerpJ Community Edition is documented for personal and non-business use only.
- The generated iframe uses both `allow-scripts` and `allow-same-origin` because the CheerpJ runtime requires same-origin behavior. Browsers warn that this combination can escape sandboxing; the iframe only loads repository-controlled artifacts.
- No CI workflow was added. Automated verification currently requires local Chromium/Playwright and network access to the CheerpJ CDN.

## Reproduction

```bash
cd /home/hafidz/project/java-converter
python3 -m provikom_converter build /home/hafidz/project/project-2024/games/CarTraffic.jar \
  --backend cheerpj --output /home/hafidz/project/project-2024/web-games/car-traffic \
  --title "Car Traffic"

cd /home/hafidz/project/project-2024
python3 tools/verify_pilot.py

docker build -t java-game-portal:3a .
docker run --rm -d --name java-game-portal-3a -p 18084:8080 java-game-portal:3a
```

The Flappy and Paddle builds use the same command with their respective JAR paths and output directories. Artifact-local `app.js` adaptations must be preserved after regeneration.

## Final Status

Milestone 3A is ready for review as a pilot integration. Do not merge or deploy until the PR review, legacy visual acceptance, and licensing review are complete.
