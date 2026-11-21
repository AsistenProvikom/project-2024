#!/usr/bin/env python3
"""Adapt and check generated CheerpJ artifacts for subdirectory hosting.

The converter emits artifacts that assume /app/ is served from the web root.
The portal serves each artifact under /web-games/<slug>/, so the generated
player must load its JAR files into CheerpOS under /str/ instead.

Run after every artifact regeneration:

    python3 tools/adapt_generated_artifact.py web-games/car-traffic
    python3 tools/adapt_generated_artifact.py --check web-games/car-traffic

This tool is intentionally artifact-local; it does not modify the converter.
"""

from __future__ import annotations

import argparse
import copy
import json
import posixpath
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

MOUNT_ROOT = "/str/"
CONFIG_PATTERN = re.compile(r"const CONFIG = (\{.*?\n\});", re.DOTALL)

ASSERT_BLOCK = """async function assertFileAvailable(relativePath) {
  const url = new URL(relativePath, document.baseURI);
  const response = await fetch(url, { method: "HEAD", cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Required file not found (HTTP ${response.status}): ${url.pathname}`);
  }
}"""

INSTALL_BLOCK = """async function installGameFiles() {
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
}"""

OLD_DEPENDENCY_CHECK = '''    updateLoadingStep("step-deps", "Checking Dependencies", "Verifying files served from the /app/ mount...");
    await assertFileAvailable(CONFIG.gameJar);
    for (const dep of CONFIG.dependencies) {
      await assertFileAvailable(dep.relative_path);
    }'''

NEW_DEPENDENCY_CHECK = '''    updateLoadingStep("step-deps", "Checking Dependencies", "Loading files from the artifact directory...");
    await installGameFiles();'''

PROVENANCE_NOTE = (
    "Pilot hosting adaptation: virtual paths use /str/ and dependency virtual paths "
    "are flattened for subdirectory hosting."
)
OLD_DEPENDENCY_NOTE = (
    "Manifest Class-Path dependencies are served from the web root and loaded via "
    "/app/: lib/AbsoluteLayout.jar."
)
NEW_DEPENDENCY_NOTE = (
    "Manifest Class-Path dependencies are loaded from the artifact directory and "
    "mounted under /str/: lib/AbsoluteLayout.jar."
)


def flatten_virtual_path(relative_path: str) -> str:
    name = posixpath.basename(relative_path.replace("\\", "/"))
    if not name or name in (".", ".."):
        raise ValueError(f"Invalid dependency path: {relative_path!r}")
    return MOUNT_ROOT + name


def extract_config(app_js: str) -> Dict[str, Any]:
    match = CONFIG_PATTERN.search(app_js)
    if not match:
        raise ValueError("Could not find the generated CONFIG block")
    try:
        config = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Generated CONFIG is not valid JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ValueError("Generated CONFIG must be an object")
    return config


def adapted_config(config: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(config)
    main_jar = posixpath.basename(str(result.get("gameJar", "")).replace("\\", "/"))
    if not main_jar:
        raise ValueError("CONFIG.gameJar is missing")

    dependencies: List[Dict[str, Any]] = []
    for dependency in result.get("dependencies", []):
        if not isinstance(dependency, dict):
            raise ValueError("CONFIG.dependencies entries must be objects")
        item = copy.deepcopy(dependency)
        relative_path = str(item.get("relative_path", ""))
        item["virtual_path"] = flatten_virtual_path(relative_path)
        dependencies.append(item)

    result["virtualMountRoot"] = MOUNT_ROOT
    result["jarVirtualPath"] = MOUNT_ROOT + main_jar
    result["classPath"] = [MOUNT_ROOT + main_jar] + [
        item["virtual_path"] for item in dependencies
    ]
    result["dependencies"] = dependencies
    return result


def replace_config(app_js: str, config: Dict[str, Any]) -> str:
    replacement = "const CONFIG = " + json.dumps(config, indent=2) + ";"
    updated, count = CONFIG_PATTERN.subn(lambda _match: replacement, app_js, count=1)
    if count != 1:
        raise ValueError("Expected exactly one CONFIG block")
    return updated


def adapted_app_js(app_js: str) -> str:
    config = adapted_config(extract_config(app_js))
    updated = replace_config(app_js, config)

    if "async function installGameFiles()" in updated:
        if "assertFileAvailable" in updated:
            raise ValueError("Artifact has both installGameFiles and assertFileAvailable")
    else:
        if ASSERT_BLOCK not in updated:
            raise ValueError("Could not find the generated assertFileAvailable block")
        updated = updated.replace(ASSERT_BLOCK, INSTALL_BLOCK, 1)

    if OLD_DEPENDENCY_CHECK in updated:
        updated = updated.replace(OLD_DEPENDENCY_CHECK, NEW_DEPENDENCY_CHECK, 1)
    if "await installGameFiles();" not in updated:
        raise ValueError("Could not find the adapted dependency installation call")
    if "cheerpOSAddStringFile" not in updated:
        raise ValueError("Adapted app.js does not install files with cheerpOSAddStringFile")
    return updated


def adapted_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(manifest)
    jar_name = str(result.get("jar_file") or result.get("game", {}).get("jar_file") or "")
    if not jar_name:
        raise ValueError("Manifest is missing jar_file")

    dependencies: List[Dict[str, Any]] = []
    for dependency in result.get("dependencies", []):
        if not isinstance(dependency, dict):
            raise ValueError("Manifest dependency entries must be objects")
        item = copy.deepcopy(dependency)
        item["virtual_path"] = flatten_virtual_path(str(item.get("relative_path", "")))
        dependencies.append(item)

    main_virtual_path = MOUNT_ROOT + posixpath.basename(jar_name)
    class_path = [main_virtual_path] + [item["virtual_path"] for item in dependencies]

    result["dependencies"] = dependencies
    paths = copy.deepcopy(result.get("paths", {}))
    paths["virtual_mount_root"] = MOUNT_ROOT
    paths["main_jar_virtual_path"] = main_virtual_path
    paths["class_path"] = class_path
    result["paths"] = paths
    result["pilot_adaptation"] = {
        "schema_version": "1.0",
        "tool": "tools/adapt_generated_artifact.py",
        "mount_root": MOUNT_ROOT,
        "dependency_virtual_paths_flattened": True,
        "reason": "Artifact is hosted below /web-games/<slug>/ instead of the origin root.",
    }

    notes = result.get("notes")
    if not isinstance(notes, list):
        notes = []
    notes = [
        NEW_DEPENDENCY_NOTE if note == OLD_DEPENDENCY_NOTE else note
        for note in notes
        if isinstance(note, str)
    ]
    if PROVENANCE_NOTE not in notes:
        notes.append(PROVENANCE_NOTE)
    result["notes"] = notes
    return result


def adapted_index_html(index_html: str) -> str:
    return index_html.replace(OLD_DEPENDENCY_NOTE, NEW_DEPENDENCY_NOTE)


def load_json(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def check_artifact(directory: Path) -> List[str]:
    errors: List[str] = []
    manifest_path = directory / "manifest.json"
    app_path = directory / "app.js"
    index_path = directory / "index.html"
    if not manifest_path.is_file():
        return [f"Missing {manifest_path}"]
    if not app_path.is_file():
        return [f"Missing {app_path}"]
    if not index_path.is_file():
        return [f"Missing {index_path}"]

    try:
        current_manifest = load_json(manifest_path)
        expected_manifest = adapted_manifest(current_manifest)
        if current_manifest != expected_manifest:
            errors.append(f"{manifest_path} is not adapted")

        current_app = app_path.read_text(encoding="utf-8")
        expected_app = adapted_app_js(current_app)
        if current_app != expected_app:
            errors.append(f"{app_path} is not adapted")

        current_index = index_path.read_text(encoding="utf-8")
        if adapted_index_html(current_index) != current_index:
            errors.append(f"{index_path} is not adapted")
    except ValueError as exc:
        errors.append(f"{directory}: {exc}")

    return errors


def adapt_artifact(directory: Path) -> bool:
    manifest_path = directory / "manifest.json"
    app_path = directory / "app.js"
    index_path = directory / "index.html"
    current_manifest = load_json(manifest_path)
    expected_manifest = adapted_manifest(current_manifest)
    current_app = app_path.read_text(encoding="utf-8")
    expected_app = adapted_app_js(current_app)
    current_index = index_path.read_text(encoding="utf-8")
    expected_index = adapted_index_html(current_index)

    changed = False
    if current_manifest != expected_manifest:
        manifest_path.write_text(
            json.dumps(expected_manifest, indent=2) + "\n", encoding="utf-8"
        )
        changed = True
    if current_app != expected_app:
        app_path.write_text(expected_app, encoding="utf-8")
        changed = True
    if current_index != expected_index:
        index_path.write_text(expected_index, encoding="utf-8")
        changed = True
    return changed


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--check", action="store_true", help="Fail instead of writing changes")
    args = parser.parse_args(argv)

    failed = False
    for directory in args.directories:
        if args.check:
            errors = check_artifact(directory)
            if errors:
                failed = True
                for error in errors:
                    print(f"[FAIL] {error}", file=sys.stderr)
            else:
                print(f"[PASS] adapted artifact: {directory}")
        else:
            try:
                changed = adapt_artifact(directory)
            except (OSError, ValueError) as exc:
                failed = True
                print(f"[FAIL] {directory}: {exc}", file=sys.stderr)
            else:
                state = "updated" if changed else "already adapted"
                print(f"[PASS] {directory}: {state}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
