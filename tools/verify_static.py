#!/usr/bin/env python3
"""Offline static integrity checks for the generated-player pilot.

This verifier is deterministic, requires no network access, and is safe for a
pull-request CI gate. External CheerpJ browser checks live in verify_pilot.py
and are intentionally not part of this gate.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import adapt_generated_artifact as adapt  # noqa: E402

CHECKS: List[Dict[str, Any]] = []

EXPECTED_SOURCES = {
    "games/CarTraffic.jar": "ff1e14564f77cb356ec9ffbee82fb1291981c57471082b7c0faa5cc6bcff1f2e",
    "games/flappy.jar": "c788986652405b12962066c61fc2c3cfe843335a6e3a4ae4ef6f4d3a0de4b0ea",
    "games/PaddleGame.jar": "41b423488d9aba93f184ce56281417a836996417e5ed85404b8174034973b8dd",
    "games/lib/AbsoluteLayout.jar": "cbe5600e86eb64761e11e4cb046804a070bc214e00b9fa61413b59017089dfd1",
}


def check(name: str, passed: bool, detail: Any = None) -> None:
    CHECKS.append({"name": name, "passed": bool(passed), "detail": detail})
    status = "PASS" if passed else "FAIL"
    suffix = "" if detail is None else f" — {detail}"
    print(f"[{status}] {name}{suffix}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check_release_gate() -> None:
    gate = TOOLS / "check_release_gate.py"
    cases = [
        (None, 1, "unset"),
        ("false", 1, "false"),
        ("1", 1, "non-boolean"),
        ("true", 0, "true"),
    ]
    for value, expected, label in cases:
        env = os.environ.copy()
        env.pop("PILOT_RELEASE_APPROVED", None)
        if value is not None:
            env["PILOT_RELEASE_APPROVED"] = value
        result = subprocess.run(
            [sys.executable, str(gate)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        check(
            f"Release gate: {label} returns {expected}",
            result.returncode == expected,
            {"returncode": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()},
        )


def main() -> int:
    required = [
        "index.html",
        "script.js",
        "data/games.json",
        "data/player-config.json",
        "tools/verify_pilot.py",
        "tools/verify_offline.py",
        "tools/check_release_gate.py",
        ".github/workflows/pages.yml",
        ".github/workflows/pilot-integrity.yml",
        ".github/workflows/pilot-browser-cdn.yml",
    ]
    missing = [path for path in required if not (ROOT / path).is_file()]
    check("Static: required files exist", not missing, missing)

    for relative, expected in EXPECTED_SOURCES.items():
        actual = sha256(ROOT / relative)
        check(f"Source hash unchanged: {relative}", actual == expected, actual)

    catalog = load_json(ROOT / "data/games.json")
    check("Catalog: is a list of seven games", isinstance(catalog, list) and len(catalog) == 7, len(catalog) if isinstance(catalog, list) else type(catalog).__name__)

    generated_games = []
    if isinstance(catalog, list):
        for game in catalog:
            if not isinstance(game, dict):
                continue
            player = game.get("player") if isinstance(game.get("player"), dict) else {}
            if player.get("mode") == "generated":
                generated_games.append((game, player))
    check("Catalog: exactly three generated games", len(generated_games) == 3, len(generated_games))

    player_config = load_json(ROOT / "data/player-config.json")
    origin = player_config.get("generatedOrigin") if isinstance(player_config, dict) else None
    valid_origin = origin == "" or (
        isinstance(origin, str)
        and origin.startswith(("https://", "http://"))
        and origin.endswith("/")
    )
    check("Portal config: generatedOrigin is empty or an absolute origin", valid_origin, origin)

    for game, player in generated_games:
        name = str(game.get("name", "<unnamed>"))
        entry = player.get("entry")
        valid_entry = (
            isinstance(entry, str)
            and entry.startswith("web-games/")
            and "/" in entry[len("web-games/"):]
            and not entry.startswith("/")
            and ".." not in entry
            and "\\" not in entry
        )
        check(f"{name}: generated entry is safe", valid_entry, entry)
        if not valid_entry:
            continue

        artifact_dir = ROOT / Path(entry).parent
        manifest_path = artifact_dir / "manifest.json"
        app_path = artifact_dir / "app.js"
        index_path = artifact_dir / "index.html"
        marker_path = artifact_dir / ".provikom-artifact.json"

        files_exist = all(path.is_file() for path in (manifest_path, app_path, index_path, marker_path))
        check(f"{name}: artifact files exist", files_exist, str(artifact_dir.relative_to(ROOT)))
        if not files_exist:
            continue

        marker = load_json(marker_path)
        check(
            f"{name}: converter ownership marker is intact",
            marker.get("owner") == "provikom-converter",
            marker.get("owner"),
        )

        adaptation_errors = adapt.check_artifact(artifact_dir)
        check(f"{name}: /str/ adaptation is current", not adaptation_errors, adaptation_errors)

        manifest = load_json(manifest_path)
        app_js = app_path.read_text(encoding="utf-8")
        try:
            config = adapt.extract_config(app_js)
        except ValueError as exc:
            config = None
            check(f"{name}: CONFIG block parses", False, str(exc))
        else:
            check(f"{name}: CONFIG block parses", True)

        paths = manifest.get("paths", {})
        dependencies = manifest.get("dependencies", [])
        class_path = paths.get("class_path", [])
        check(
            f"{name}: manifest mount root is /str/",
            paths.get("virtual_mount_root") == "/str/",
            paths.get("virtual_mount_root"),
        )
        check(
            f"{name}: manifest classpath uses only /str/",
            isinstance(class_path, list)
            and bool(class_path)
            and all(isinstance(item, str) and item.startswith("/str/") for item in class_path),
            class_path,
        )
        check(
            f"{name}: dependency virtual paths are flattened",
            all(
                isinstance(item, dict)
                and item.get("virtual_path") == "/str/" + Path(str(item.get("relative_path", ""))).name
                for item in dependencies
            ),
            [item.get("virtual_path") for item in dependencies if isinstance(item, dict)],
        )
        check(
            f"{name}: manifest main JAR virtual path matches",
            paths.get("main_jar_virtual_path") == "/str/" + str(manifest.get("jar_file", "")),
            paths.get("main_jar_virtual_path"),
        )
        manifest_text = manifest_path.read_text(encoding="utf-8")
        index_text = index_path.read_text(encoding="utf-8")
        check(
            f"{name}: adapted files have no stale /app/ mount",
            "/app/" not in app_js and "/app/" not in manifest_text and "/app/" not in index_text,
            {
                "app": "/app/" in app_js,
                "manifest": "/app/" in manifest_text,
                "index": "/app/" in index_text,
            },
        )
        check(
            f"{name}: app.js installs files into CheerpOS",
            "installGameFiles" in app_js
            and "cheerpOSAddStringFile" in app_js
            and "assertFileAvailable" not in app_js,
        )

        if config is not None:
            check(
                f"{name}: app.js runtime matches manifest",
                config.get("gameJar") == manifest.get("jar_file")
                and config.get("mainClass") == manifest.get("game", {}).get("main_class")
                and config.get("runtimeVersion") == manifest.get("runtime_version")
                and config.get("virtualMountRoot") == paths.get("virtual_mount_root")
                and config.get("jarVirtualPath") == paths.get("main_jar_virtual_path")
                and config.get("classPath") == class_path,
                {
                    "gameJar": config.get("gameJar"),
                    "mainClass": config.get("mainClass"),
                    "classPath": config.get("classPath"),
                },
            )
            config_deps = config.get("dependencies", [])
            expected_deps = [
                {
                    "relative_path": item.get("relative_path"),
                    "virtual_path": item.get("virtual_path"),
                }
                for item in dependencies
                if isinstance(item, dict)
            ]
            actual_deps = [
                {
                    "relative_path": item.get("relative_path"),
                    "virtual_path": item.get("virtual_path"),
                }
                for item in config_deps
                if isinstance(item, dict)
            ]
            check(f"{name}: app.js dependencies match manifest", actual_deps == expected_deps, actual_deps)

        jar_name = str(manifest.get("jar_file", ""))
        jar_path = artifact_dir / jar_name
        expected_source = EXPECTED_SOURCES.get(f"games/{jar_name}")
        jar_ok = jar_path.is_file() and sha256(jar_path) == expected_source
        check(f"{name}: bundled main JAR matches source", jar_ok, jar_name)

        deps_ok = True
        deps_detail = []
        for dependency in dependencies:
            if not isinstance(dependency, dict):
                deps_ok = False
                continue
            relative = str(dependency.get("relative_path", ""))
            path = artifact_dir / relative
            actual_hash = sha256(path) if path.is_file() else None
            actual_size = path.stat().st_size if path.is_file() else None
            item_ok = (
                actual_hash == dependency.get("sha256")
                and actual_size == dependency.get("size_bytes")
            )
            deps_ok = deps_ok and item_ok
            deps_detail.append({"path": relative, "hash_ok": actual_hash == dependency.get("sha256"), "size_ok": actual_size == dependency.get("size_bytes")})
        check(f"{name}: bundled dependencies match manifest", deps_ok, deps_detail)

        generated_files = manifest.get("generated_files", [])
        missing_generated = [
            relative for relative in generated_files if not (artifact_dir / relative).is_file()
        ]
        check(f"{name}: generated_files entries exist", not missing_generated, missing_generated)

        check(
            f"{name}: index loads the adapted app.js",
            'src="app.js"' in index_text and "loader.js" in index_text,
        )

    script = (ROOT / "script.js").read_text(encoding="utf-8")
    unsafe_dom = [
        token for token in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write")
        if token in script
    ]
    check("Catalog: no dynamic HTML injection sinks", not unsafe_dom, unsafe_dom)
    check(
        "Iframe: same-origin and cross-origin sandbox modes are explicit",
        'dataset.isolation' in script
        and 'cross-origin' in script
        and 'same-origin-trusted' in script
        and 'allow-same-origin' in script,
    )

    integrity_workflow = (ROOT / ".github/workflows/pilot-integrity.yml").read_text(encoding="utf-8")
    check(
        "CI: PR offline gate runs static and offline checks",
        "pull_request:" in integrity_workflow
        and "verify_static.py" in integrity_workflow
        and "verify_offline.py" in integrity_workflow,
    )
    cdn_workflow = (ROOT / ".github/workflows/pilot-browser-cdn.yml").read_text(encoding="utf-8")
    check(
        "CI: CDN browser workflow is manual only",
        "workflow_dispatch:" in cdn_workflow
        and "pull_request:" not in cdn_workflow
        and "verify_pilot.py" in cdn_workflow,
    )
    pages_workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    check(
        "Release: Pages deployment is behind the release gate",
        "check_release_gate.py" in pages_workflow
        and "needs: release-gate" in pages_workflow
        and "actions/deploy-pages" in pages_workflow,
    )

    check_release_gate()

    failed = [item for item in CHECKS if not item["passed"]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} static checks passed")
    if failed:
        print("Failed checks:")
        for item in failed:
            print(f"- {item['name']}: {item['detail']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
