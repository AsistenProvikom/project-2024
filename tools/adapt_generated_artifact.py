#!/usr/bin/env python3
"""Adapt and check generated artifacts for portal subdirectory hosting.

CheerpJ artifacts assume /app/ is served from the web root. The portal serves
each artifact under /web-games/<slug>/, so their players must load JAR files
into CheerpOS under /str/ instead.

Source-backed SwingJS artifacts already use relative URLs, an empty SwingJS
serverURL, and root-level index.html. This tool validates them as portal-safe
and deliberately leaves them unchanged.

Run after every artifact regeneration:

    python3 tools/adapt_generated_artifact.py web-games/car-traffic
    python3 tools/adapt_generated_artifact.py --check web-games/car-traffic

This tool is intentionally artifact-local; it does not modify the converter. It
validates and refreshes the converter ownership marker after manifest changes so the
marker SHA always matches the current raw manifest bytes without changing artifact
identity.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import posixpath
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List

MOUNT_ROOT = "/str/"
MARKER_FILENAME = ".provikom-artifact.json"
MARKER_SCHEMA_VERSION = "1.0"
MARKER_OWNER = "provikom-converter"
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value.lower())
    )


def read_json_bytes(path: Path) -> tuple[Dict[str, Any], bytes]:
    if path.is_symlink():
        raise ValueError(f"Refusing symlinked file: {path}")
    if not path.is_file():
        raise ValueError(f"Missing ownership file: {path}")
    raw = path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data, raw


def marker_bytes(manifest_raw: bytes, artifact_id: str) -> bytes:
    return json.dumps(
        {
            "schema_version": MARKER_SCHEMA_VERSION,
            "owner": MARKER_OWNER,
            "artifact_id": artifact_id,
            "manifest_sha256": sha256_bytes(manifest_raw),
        },
        indent=2,
    ).encode("utf-8")


def validate_ownership_identity(
    directory: Path,
    manifest: Dict[str, Any],
    manifest_raw: bytes,
) -> str:
    """Validate existing converter ownership proof without creating it."""
    if manifest.get("schema_version") not in {"1.0", "1.1"}:
        raise ValueError("Manifest schema_version is not supported")
    if not isinstance(manifest.get("provikom_converter_version"), str):
        raise ValueError("Manifest is missing provikom_converter_version")
    backend = manifest.get("backend")
    if backend not in {"cheerpj", "swingjs"} or manifest.get("entry_point") != "index.html":
        raise ValueError("Manifest does not describe a supported Provikom artifact")

    ownership = manifest.get("ownership")
    if not isinstance(ownership, dict):
        raise ValueError("Manifest has no ownership block")
    if ownership.get("owner") != MARKER_OWNER:
        raise ValueError("Manifest ownership owner is invalid")
    if ownership.get("marker") != MARKER_FILENAME:
        raise ValueError("Manifest ownership marker filename is invalid")
    artifact_id = ownership.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise ValueError("Manifest ownership artifact_id is invalid")

    marker_path = directory / MARKER_FILENAME
    marker, marker_raw = read_json_bytes(marker_path)
    if marker.get("schema_version") != MARKER_SCHEMA_VERSION:
        raise ValueError("Ownership marker schema_version is invalid")
    if marker.get("owner") != MARKER_OWNER:
        raise ValueError("Ownership marker owner is invalid")
    if marker.get("artifact_id") != artifact_id:
        raise ValueError("Ownership marker artifact_id does not match manifest")
    marker_digest = marker.get("manifest_sha256")
    if not valid_sha256(marker_digest):
        raise ValueError("Ownership marker manifest_sha256 is invalid")

    if marker_digest.lower() != sha256_bytes(manifest_raw):
        if backend != "cheerpj" or not isinstance(manifest.get("pilot_adaptation"), dict):
            raise ValueError(
                "Ownership marker digest is stale and the artifact has no prior "
                "pilot adaptation; refusing to create new ownership proof"
            )

    if backend == "cheerpj":
        _validate_cheerpj_payload(directory, manifest)
    else:
        _validate_swingjs_payload(directory, manifest)
        if marker_raw != marker_bytes(manifest_raw, artifact_id):
            raise ValueError("Ownership marker bytes do not match the SwingJS manifest")
    return artifact_id


def _safe_relative_file(directory: Path, name: object) -> Path:
    if not isinstance(name, str) or not name:
        raise ValueError("Artifact path is missing")
    normalized = name.replace("\\", "/")
    relative = PurePosixPath(normalized)
    if relative.is_absolute() or any(part in {"", ".."} for part in relative.parts):
        raise ValueError(f"Artifact path is unsafe: {name!r}")
    path = directory.joinpath(*relative.parts)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Artifact file is missing or unsafe: {name}")
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError as exc:
        raise ValueError(f"Artifact path escapes its directory: {name}") from exc
    return path


def _validate_cheerpj_payload(directory: Path, manifest: Dict[str, Any]) -> None:
    jar_name = manifest.get("jar_file")
    if not isinstance(jar_name, str) or not jar_name or Path(jar_name).name != jar_name:
        raise ValueError("Manifest jar_file is invalid")
    jar_path = directory / jar_name
    if jar_path.is_symlink() or not jar_path.is_file():
        raise ValueError(f"Manifest main JAR is missing or unsafe: {jar_name}")
    game = manifest.get("game")
    if not isinstance(game, dict):
        raise ValueError("Manifest game metadata is missing")
    expected_hash = game.get("sha256")
    expected_size = game.get("size_bytes")
    if (
        not valid_sha256(expected_hash)
        or not isinstance(expected_size, int)
        or isinstance(expected_size, bool)
    ):
        raise ValueError("Manifest game hash/size metadata is invalid")
    if jar_path.stat().st_size != expected_size or sha256_file(jar_path) != expected_hash.lower():
        raise ValueError("Manifest main JAR hash/size does not match")


def _validate_swingjs_payload(directory: Path, manifest: Dict[str, Any]) -> None:
    source = manifest.get("source_project")
    if not isinstance(source, dict):
        raise ValueError("SwingJS manifest is missing source_project")
    generated_name = source.get("generated_js")
    generated_path = _safe_relative_file(directory, generated_name)
    expected_js_hash = source.get("generated_js_sha256")
    if not valid_sha256(expected_js_hash):
        raise ValueError("SwingJS generated_js_sha256 is invalid")
    if sha256_file(generated_path) != expected_js_hash.lower():
        raise ValueError("SwingJS generated JavaScript hash does not match")
    if not valid_sha256(source.get("source_sha256")):
        raise ValueError("SwingJS source_sha256 is invalid")
    generated_files = manifest.get("generated_files")
    if not isinstance(generated_files, list) or not all(
        isinstance(name, str) for name in generated_files
    ):
        raise ValueError("SwingJS generated_files is invalid")
    for name in generated_files:
        _safe_relative_file(directory, name)
    if generated_name not in generated_files:
        raise ValueError("SwingJS generated_js is not listed in generated_files")
    index_path = _safe_relative_file(directory, "index.html")
    index_html = index_path.read_text(encoding="utf-8")
    if re.search(r"serverURL\s*:\s*['\"]https?://", index_html):
        raise ValueError("SwingJS index.html uses an external serverURL")


def load_json(path: Path) -> Dict[str, Any]:
    data, _raw = read_json_bytes(path)
    return data


def check_artifact(directory: Path) -> List[str]:
    errors: List[str] = []
    manifest_path = directory / "manifest.json"
    index_path = directory / "index.html"
    marker_path = directory / MARKER_FILENAME
    if not manifest_path.is_file():
        return [f"Missing {manifest_path}"]
    if not index_path.is_file():
        return [f"Missing {index_path}"]
    if not marker_path.is_file():
        return [f"Missing {marker_path}"]

    try:
        current_manifest, manifest_raw = read_json_bytes(manifest_path)
        artifact_id = validate_ownership_identity(directory, current_manifest, manifest_raw)
        _marker, marker_raw = read_json_bytes(marker_path)
        if marker_raw != marker_bytes(manifest_raw, artifact_id):
            errors.append(f"{marker_path} does not match current manifest bytes")

        if current_manifest.get("backend") == "cheerpj":
            app_path = directory / "app.js"
            if not app_path.is_file():
                return [f"Missing {app_path}"]
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
    marker_path = directory / MARKER_FILENAME

    current_manifest, current_manifest_raw = read_json_bytes(manifest_path)
    artifact_id = validate_ownership_identity(directory, current_manifest, current_manifest_raw)
    if current_manifest.get("backend") == "swingjs":
        return False

    expected_manifest = adapted_manifest(current_manifest)
    current_app = app_path.read_text(encoding="utf-8")
    expected_app = adapted_app_js(current_app)
    current_index = index_path.read_text(encoding="utf-8")
    expected_index = adapted_index_html(current_index)

    changed = False
    final_manifest_raw = current_manifest_raw
    if current_manifest != expected_manifest:
        final_manifest_raw = json.dumps(expected_manifest, indent=2).encode("utf-8")
        manifest_path.write_bytes(final_manifest_raw)
        changed = True

    expected_marker_raw = marker_bytes(final_manifest_raw, artifact_id)
    _marker, current_marker_raw = read_json_bytes(marker_path)
    if current_marker_raw != expected_marker_raw:
        marker_path.write_bytes(expected_marker_raw)
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
                backend = load_json(directory / "manifest.json").get("backend")
                kind = "source artifact" if backend == "swingjs" else "adapted artifact"
                print(f"[PASS] {kind}: {directory}")
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
