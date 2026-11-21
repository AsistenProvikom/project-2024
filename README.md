# Java Game Portal

A static web portal that runs the bundled Java `.jar` games directly in the browser
using [CheerpJ 5.0](https://cheerpj.com/). No backend, no build step — just static
files served over HTTP.

---

## Contents

- [Requirements](#requirements)
- [Project structure](#project-structure)
- [Local development with DDEV (Windows/macOS/Linux)](#local-development-with-ddev)
- [Local preview without DDEV](#local-preview-without-ddev)
- [Production with Podman](#production-with-podman)
- [Accessing the server from Windows](#accessing-the-server-from-windows)
- [Using Docker instead of Podman](#using-docker-instead-of-podman)
- [Verification](#verification)
- [Generated-player pilot](#generated-player-pilot)
- [CI checks](#ci-checks)
- [Troubleshooting](#troubleshooting)
- [Deployment](#deployment)

---

## Requirements

| Environment | Needs |
| --- | --- |
| Local dev (recommended) | Docker Desktop (running) + [DDEV](https://ddev.com/) |
| Local preview (minimal) | Python 3 or Node.js |
| Production | Podman ≥ 5 (rootless is fine) |
| Browser | Internet access on first load (CheerpJ loads from a CDN) |

---

## Project structure

```
.
├── index.html            # App shell (gallery + game viewer)
├── style.css
├── script.js             # CheerpJ runtime + game launcher
├── data/games.json       # Game catalog
├── data/player-config.json # Optional separate-origin generated player setting
├── games/                # Java .jar games (+ games/lib dependencies)
├── web-games/            # Generated CheerpJ pilot artifacts
├── docs/                 # Integration report and verification evidence
├── tools/                # Static/offline/CDN verification and adaptation tools
├── images/               # Card images
├── Dockerfile            # nginx image for production
├── nginx.conf            # Listens on 8080, caches /games/ and /web-games/
├── .dockerignore
└── .ddev/config.yaml     # Local development environment (not in the image)
```

The catalog is `data/games.json`. Legacy entries load JARs from `games/<file>`;
generated entries load `web-games/<slug>/index.html` in an iframe. Generated files
assume CheerpOS paths under `/str/` and are adapted for subdirectory hosting.

---

## Local development with DDEV

The repository ships with `.ddev/config.yaml`, so a fresh clone only needs `ddev start`.

### 1. Clone

```powershell
# If the SSH host alias "github-provikom" is configured (see below):
git clone git@github-provikom:AsistenProvikom/project-2024.git

# Otherwise, use HTTPS:
git clone https://github.com/AsistenProvikom/project-2024.git

cd project-2024
```

The SSH alias lives in `~/.ssh/config` (`C:\Users\<you>\.ssh\config` on Windows):

```
Host github-provikom
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
```

Verify with `ssh -T git@github-provikom`.

### 2. Start

Make sure Docker Desktop is running, then:

```bash
ddev start
ddev launch
```

The site is available at **https://project2024.ddev.site**.

DDEV serves the repository root (`docroot: ""`) with its own nginx, so `index.html`,
`data/games.json`, and `games/*.jar` resolve exactly like production.
The repository's `nginx.conf` is **not** used locally — that file only applies to the
production container.

### 3. Common commands

```bash
ddev describe     # URLs, ports, status
ddev logs -f      # follow web server logs
ddev ssh          # shell inside the web container
ddev restart      # apply config changes
ddev stop         # stop this project
ddev poweroff     # stop all DDEV projects
```

> The DDEV project name is pinned to `project2024`. If you keep two clones on the same
> machine, change it in the second one: `ddev config --project-name=project2024-dev`.

---

## Local preview without DDEV

Any static file server works:

```bash
python3 -m http.server 8080      # then open http://localhost:8080
# or
npx serve . -l 8080
```

Do not open `index.html` via `file://` — the catalog and JARs are fetched with
`fetch()`, which fails for local files.

---

## Production with Podman

The container is plain nginx serving the static files on port **8080**.

### Build

```bash
podman build -t java-game-portal .
```

> The base image is fully qualified (`docker.io/library/nginx:1.27-alpine`) because
> Ubuntu's Podman has no `unqualified-search-registries` configured. Keep the prefix
> when changing the base image.

### Run

```bash
podman run -d --rm \
  --name java-game-portal \
  -p 8080:8080 \
  java-game-portal
```

Port 8080 is above 1024, so this works rootless without extra privileges.

### Operate

```bash
podman ps                                  # is it running?
podman logs -f java-game-portal            # nginx access/error logs
podman stats --no-stream                   # CPU / memory
podman stop java-game-portal               # stop (container is removed due to --rm)
podman run -d --rm --name java-game-portal -p 8080:8080 java-game-portal
```

Because of `--rm`, the container is deleted on stop; the image remains, so
`podman run` brings it back instantly.

### Rebuild after changes

```bash
podman stop java-game-portal
podman build -t java-game-portal .
podman run -d --rm --name java-game-portal -p 8080:8080 java-game-portal
```

---

## Accessing the server from Windows

If the Linux host is a NAT'd VM (e.g. VirtualBox, guest IP `10.0.2.15`), the browser
cannot reach it directly. Use an SSH local port forward from **PowerShell**:

```powershell
ssh -N -L 18080:localhost:8080 <user>@<server>
```

Then open **http://localhost:18080** and keep the SSH session open.

Port 18080 on purpose: Windows often blocks binding 8080 (already used, or inside a
Hyper-V/WinNAT excluded range). If 18080 is also busy, pick another high port.

Alternative (no tunnel): VirtualBox → *Settings → Network → Advanced → Port
Forwarding*, map host `18080` → guest `8080`.

---

## Using Docker instead of Podman

The same `Dockerfile` works with Docker (fully-qualified base images are valid there too):

```bash
docker build -t java-game-portal .
docker run -d --rm --name java-game-portal -p 18080:8080 java-game-portal
```

Use 18080 locally so it doesn't collide with DDEV's router (80/443).

---

## Verification

After starting (container or DDEV), these should all return `200`:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/data/games.json
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/games/CarTraffic.jar
curl -s -o /dev/null -w '%{http_code}\n' 'http://localhost:8080/games/Snake%20Game%20FinPro.jar'
```

In a container, `GET /games/...` must be served — that's why the Dockerfile copies
`games/` to `/usr/share/nginx/html/games/` and `nginx.conf` caches `location /games/`.

On Windows PowerShell, use `curl.exe` (the `curl` alias maps to `Invoke-WebRequest`).

---

## Generated-player pilot

Generated artifacts are produced by the converter and then adapted for hosting below
`/web-games/<slug>/`. Re-run the adaptation after every regeneration:

```bash
python3 tools/adapt_generated_artifact.py \
  web-games/car-traffic web-games/flappy web-games/paddle-game
python3 tools/adapt_generated_artifact.py --check web-games/car-traffic
```

`--check` is part of the offline PR gate. The adapted manifests now describe the
actual `/str/` mount and flattened dependency paths.

The adapter validates the converter's existing ownership proof first. After any
manifest change it refreshes `.provikom-artifact.json` so `manifest_sha256` matches
the new raw manifest bytes, while preserving the original `artifact_id`, owner, and
schema. It never creates a marker for a missing or mismatched artifact and refuses
to rewrite stale ownership proof that was not previously adapted by this tool.

By default the generated player stays on the portal origin. The iframe is therefore
a lifecycle boundary, not a security sandbox: only repository-controlled generated
artifacts may be used there. Set `generatedOrigin` in `data/player-config.json` to an
absolute, separate origin to use cross-origin mode, where the iframe omits
`allow-same-origin`. That origin must serve `/web-games/` with CORS headers; the
provided `nginx.conf` includes them.

## CI checks

- `.github/workflows/pilot-integrity.yml` is the pull-request gate. It runs
  `tools/verify_static.py` (no network), `tools/test_adaptation.py` (ownership and
  idempotence regression tests), and `tools/verify_offline.py` (Chromium with
  external network blocked). These checks are deterministic and do not require CheerpJ.
- `.github/workflows/pilot-browser-cdn.yml` is manual-only. It runs
  `tools/verify_pilot.py`, requires the external CheerpJ CDN, and is never counted as
  a PR pass.
- `tools/verify_pilot.py` verifies generated gameplay and legacy launcher/teardown.
  Legacy gameplay remains a manual acceptance item.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `short-name "nginx:..." did not resolve` | Use a fully-qualified base image (`docker.io/library/...`). Already fixed in the Dockerfile. |
| Games show "Gagal memuat JAR (404)" | `/games/` path mismatch between Dockerfile and `script.js`. Verify with the curl checks above. |
| `bind [127.0.0.1]:8080: Permission denied` when tunneling | Windows port conflict/reserved range. Use `-L 18080:localhost:8080`. |
| `podman run` fails to bind 8080 | Port already in use: `ss -ltnp \| grep 8080`, or map `-p 18080:8080`. |
| `ddev start` fails | Docker Desktop not running, or ports 80/443 occupied. |
| DDEV site returns 404/403 | Check `ddev describe`; `docroot` must be the repository root. |
| Game stays on loading / blank screen | Browser console + `podman logs` / `ddev logs`. CheerpJ needs internet on first load. |

---

## Deployment

- **GitHub Pages:** `.github/workflows/pages.yml` preserves the existing Pages
  deployment, but it now starts with a fail-closed `release-gate` job. Publication
  requires the repository variable `PILOT_RELEASE_APPROVED=true` after licensing,
  redistribution, and legacy visual acceptance are complete.
- **Container host:** build and run with Podman as described above. The image is
  stateless and can be rebuilt from any commit.

Do not set `PILOT_RELEASE_APPROVED` just to make a workflow green. Without it, the
Pages deployment job is skipped because the gate fails first.

---

## Notes for contributors

- `.ddev/` is excluded from the container build via `.dockerignore`.
- `games/` is large but required; do not add it to `.dockerignore` or `.gitignore`.
- After changing `script.js` paths or the Dockerfile, re-run the [verification](#verification) checks.
