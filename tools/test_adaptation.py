#!/usr/bin/env python3
"""Regression tests for artifact adaptation and ownership marker integrity."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import adapt_generated_artifact as adapt

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = {
    "car-traffic": ROOT / "web-games/car-traffic",
    "flappy": ROOT / "web-games/flappy",
    "paddle-game": ROOT / "web-games/paddle-game",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def marker_raw(directory: Path) -> bytes:
    return (directory / adapt.MARKER_FILENAME).read_bytes()


def write_swingjs_artifact(directory: Path, *, server_url: str = "") -> None:
    generated = directory / "swingjs" / "j2s" / "demo" / "Game.js"
    generated.parent.mkdir(parents=True)
    generated.write_text("Clazz.newClass('demo.Game');\n", encoding="utf-8")
    (directory / "index.html").write_text(
        "<!doctype html><script src=\"swingjs/swingjs2.js\"></script>"
        "<script>Info = {serverURL: '" + server_url + "', j2sPath: 'swingjs/j2s'};</script>",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "1.1",
        "provikom_converter_version": "0.1.0",
        "backend": "swingjs",
        "entry_point": "index.html",
        "game": {"title": "SwingJS Test", "main_class": "demo.Game", "has_audio": False},
        "source_project": {
            "name": "test",
            "main_class": "demo.Game",
            "source_sha256": "a" * 64,
            "source_file_count": 1,
            "files": [{"path": "src/demo/Game.java", "sha256": "b" * 64}],
            "generated_js": "swingjs/j2s/demo/Game.js",
            "generated_js_sha256": adapt.sha256_file(generated),
        },
        "paths": {"entry": "index.html", "web_root": "/", "virtual_mount_root": "/"},
        "generated_files": [
            "index.html",
            "manifest.json",
            adapt.MARKER_FILENAME,
            "swingjs/j2s/demo/Game.js",
        ],
        "notes": [],
        "ownership": {
            "owner": adapt.MARKER_OWNER,
            "marker": adapt.MARKER_FILENAME,
            "artifact_id": "c" * 32,
        },
        "lifecycle": {
            "state": "built",
            "prediction_only": True,
            "execution_verified": False,
            "source": "artifact_generation",
        },
    }
    raw = json.dumps(manifest, indent=2).encode("utf-8")
    (directory / "manifest.json").write_bytes(raw)
    (directory / adapt.MARKER_FILENAME).write_bytes(
        adapt.marker_bytes(raw, manifest["ownership"]["artifact_id"])
    )


class AdaptationOwnershipTests(unittest.TestCase):
    def copy_artifact(self, name: str, parent: Path) -> Path:
        destination = parent / name
        shutil.copytree(ARTIFACTS[name], destination)
        return destination

    def assert_marker_matches(self, directory: Path) -> None:
        manifest_bytes = (directory / "manifest.json").read_bytes()
        manifest = load(directory / "manifest.json")
        marker = load(directory / adapt.MARKER_FILENAME)
        artifact_id = manifest["ownership"]["artifact_id"]
        self.assertEqual(marker["artifact_id"], artifact_id)
        self.assertEqual(marker["owner"], adapt.MARKER_OWNER)
        self.assertEqual(marker["schema_version"], adapt.MARKER_SCHEMA_VERSION)
        self.assertEqual(marker["manifest_sha256"], adapt.sha256_bytes(manifest_bytes))
        self.assertEqual(
            marker_raw(directory), adapt.marker_bytes(manifest_bytes, artifact_id)
        )

    def test_adapted_artifacts_have_valid_ownership_metadata(self) -> None:
        for name, directory in ARTIFACTS.items():
            with self.subTest(name=name):
                self.assertEqual(adapt.check_artifact(directory), [])
                self.assert_marker_matches(directory)

    def test_repeated_adaptation_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            for name in ARTIFACTS:
                with self.subTest(name=name):
                    directory = self.copy_artifact(name, parent)
                    manifest_before = (directory / "manifest.json").read_bytes()
                    marker_before = marker_raw(directory)
                    self.assertFalse(adapt.adapt_artifact(directory))
                    self.assertFalse(adapt.adapt_artifact(directory))
                    self.assertEqual(
                        (directory / "manifest.json").read_bytes(), manifest_before
                    )
                    self.assertEqual(marker_raw(directory), marker_before)
                    self.assert_marker_matches(directory)

    def test_manifest_adaptation_refreshes_marker_and_preserves_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = self.copy_artifact("car-traffic", Path(temporary))
            manifest_path = directory / "manifest.json"
            marker_path = directory / adapt.MARKER_FILENAME
            manifest = load(manifest_path)
            artifact_id = manifest["ownership"]["artifact_id"]
            manifest["paths"]["virtual_mount_root"] = "/app/"
            manifest["paths"]["main_jar_virtual_path"] = "/app/" + manifest["jar_file"]
            manifest["paths"]["class_path"] = [
                "/app/" + manifest["jar_file"]
            ] + [
                "/app/" + dependency["relative_path"]
                for dependency in manifest.get("dependencies", [])
            ]
            manifest.pop("pilot_adaptation", None)
            manifest_path.write_bytes(json.dumps(manifest, indent=2).encode("utf-8"))
            marker_path.write_bytes(
                adapt.marker_bytes(manifest_path.read_bytes(), artifact_id)
            )

            self.assertTrue(adapt.adapt_artifact(directory))
            updated_manifest = load(manifest_path)
            self.assertEqual(updated_manifest["ownership"]["artifact_id"], artifact_id)
            self.assertEqual(updated_manifest["paths"]["virtual_mount_root"], "/str/")
            self.assert_marker_matches(directory)
            self.assertFalse(adapt.adapt_artifact(directory))

    def test_missing_marker_is_not_created(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = self.copy_artifact("car-traffic", Path(temporary))
            marker_path = directory / adapt.MARKER_FILENAME
            marker_path.unlink()
            with self.assertRaisesRegex(ValueError, "Missing ownership file"):
                adapt.adapt_artifact(directory)
            self.assertFalse(marker_path.exists())

    def test_mismatched_marker_identity_is_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = self.copy_artifact("car-traffic", Path(temporary))
            marker_path = directory / adapt.MARKER_FILENAME
            marker = load(marker_path)
            marker["artifact_id"] = "0" * 32
            marker_path.write_bytes(json.dumps(marker, indent=2).encode("utf-8"))
            before = marker_raw(directory)
            with self.assertRaisesRegex(ValueError, "artifact_id does not match"):
                adapt.adapt_artifact(directory)
            self.assertEqual(marker_raw(directory), before)

    def test_stale_marker_without_prior_adaptation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = self.copy_artifact("car-traffic", Path(temporary))
            manifest_path = directory / "manifest.json"
            manifest = load(manifest_path)
            manifest.pop("pilot_adaptation", None)
            manifest_path.write_bytes(json.dumps(manifest, indent=2).encode("utf-8"))
            before = marker_raw(directory)
            with self.assertRaisesRegex(ValueError, "no prior pilot adaptation"):
                adapt.adapt_artifact(directory)
            self.assertEqual(marker_raw(directory), before)

    def test_swingjs_source_artifact_needs_no_path_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "web-games" / "swing-demo"
            write_swingjs_artifact(directory)
            self.assertEqual(adapt.check_artifact(directory), [])
            manifest_before = (directory / "manifest.json").read_bytes()
            marker_before = marker_raw(directory)
            self.assertFalse(adapt.adapt_artifact(directory))
            self.assertFalse(adapt.adapt_artifact(directory))
            self.assertEqual((directory / "manifest.json").read_bytes(), manifest_before)
            self.assertEqual(marker_raw(directory), marker_before)

    def test_swingjs_generated_javascript_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "swing-demo"
            write_swingjs_artifact(directory)
            generated = directory / "swingjs" / "j2s" / "demo" / "Game.js"
            generated.write_text("Clazz.newClass('demo.Tampered');\n", encoding="utf-8")
            errors = adapt.check_artifact(directory)
            self.assertTrue(any("hash does not match" in error for error in errors), errors)
            with self.assertRaisesRegex(ValueError, "hash does not match"):
                adapt.adapt_artifact(directory)

    def test_swingjs_external_server_url_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "swing-demo"
            write_swingjs_artifact(directory, server_url="https://example.invalid/")
            errors = adapt.check_artifact(directory)
            self.assertTrue(any("external serverURL" in error for error in errors), errors)

    def test_swingjs_symlinked_index_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "swing-demo"
            write_swingjs_artifact(directory)
            index = directory / "index.html"
            target = directory / "real-index.html"
            index.rename(target)
            index.symlink_to(target)
            errors = adapt.check_artifact(directory)
            self.assertTrue(any("index.html" in error and "unsafe" in error for error in errors), errors)

    def test_swingjs_unsafe_generated_file_list_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "swing-demo"
            write_swingjs_artifact(directory)
            manifest_path = directory / "manifest.json"
            manifest = load(manifest_path)
            artifact_id = manifest["ownership"]["artifact_id"]
            manifest["generated_files"].append("../escape.txt")
            raw = json.dumps(manifest, indent=2).encode("utf-8")
            manifest_path.write_bytes(raw)
            (directory / adapt.MARKER_FILENAME).write_bytes(
                adapt.marker_bytes(raw, artifact_id)
            )
            errors = adapt.check_artifact(directory)
            self.assertTrue(any("path is unsafe" in error for error in errors), errors)

    def test_swingjs_unsafe_generated_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "swing-demo"
            write_swingjs_artifact(directory)
            manifest_path = directory / "manifest.json"
            manifest = load(manifest_path)
            artifact_id = manifest["ownership"]["artifact_id"]
            manifest["source_project"]["generated_js"] = "../Game.js"
            raw = json.dumps(manifest, indent=2).encode("utf-8")
            manifest_path.write_bytes(raw)
            (directory / adapt.MARKER_FILENAME).write_bytes(
                adapt.marker_bytes(raw, artifact_id)
            )
            errors = adapt.check_artifact(directory)
            self.assertTrue(any("path is unsafe" in error for error in errors), errors)

    def test_check_detects_stale_marker_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = self.copy_artifact("car-traffic", Path(temporary))
            marker_path = directory / adapt.MARKER_FILENAME
            marker = load(marker_path)
            marker["manifest_sha256"] = "0" * 64
            marker_path.write_bytes(json.dumps(marker, indent=2).encode("utf-8"))
            errors = adapt.check_artifact(directory)
            self.assertTrue(
                any("does not match current manifest bytes" in error for error in errors),
                errors,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
