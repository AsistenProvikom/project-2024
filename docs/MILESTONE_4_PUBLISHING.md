# Milestone 4 - Reproducible Artifact Publishing

Date: 2026-11-23

## Scope

Publishing must not depend on an undocumented manual rewrite step.

- **CheerpJ JAR artifacts:** the converter emits `/app/` virtual paths. The
  portal serves each artifact below `/web-games/<slug>/`, so
  `tools/adapt_generated_artifact.py` performs a tested, deterministic bridge to
  `/str/` and refreshes the converter ownership marker.
- **SwingJS source artifacts:** generated with root-level `index.html`,
  relative runtime URLs, and an empty SwingJS `serverURL`. They are already
  safe below a portal subdirectory and must not be rewritten.

## Changes

`tools/adapt_generated_artifact.py` now:

1. Recognizes both `cheerpj` and `swingjs` artifacts.
2. Keeps the existing CheerpJ `/app/` -> `/str/` adaptation and marker refresh.
3. Validates SwingJS artifacts without modifying them:
   - `index.html`, `manifest.json`, and ownership marker exist;
   - manifest ownership identity and marker digest are valid;
   - every `generated_files` path stays inside the artifact;
   - `source_project.generated_js` is listed and stays inside the artifact;
   - generated JavaScript SHA-256 matches the manifest;
   - `source_sha256` is a valid SHA-256;
   - `index.html` does not use an external `serverURL`.
4. Rejects unsafe paths, tampered generated JavaScript, stale markers, and
   external SwingJS server URLs.
5. Remains idempotent: repeated checks/adaptation produce no byte changes for
   already-valid artifacts.

## Tests

`tools/test_adaptation.py` now covers:

- existing CheerpJ adaptation and ownership behavior (7 tests);
- SwingJS no-op check/adaptation (1 test);
- SwingJS generated-JavaScript tampering rejection (1 test);
- SwingJS external `serverURL` rejection (1 test);
- SwingJS symlinked-entry rejection (1 test);
- SwingJS path-traversal rejection (2 tests: generated target and generated-file list).

Result: `13/13 passed`.

## Publishing Procedure

CheerpJ:

```bash
python3 tools/adapt_generated_artifact.py web-games/<slug>
python3 tools/adapt_generated_artifact.py --check web-games/<slug>
```

SwingJS source artifact:

```bash
python3 tools/adapt_generated_artifact.py --check web-games/<slug>
```

For SwingJS, `--check` must pass and `adapt_generated_artifact.py` reports no
changes because the artifact is already relative-path safe.

## Remaining Work

- Add a real SwingJS entry to the portal catalog only after licensing approval
  and product review (B-002/B-004).
- Re-run the complete project-2024 static and offline checks after catalog or
  artifact changes.
- Manual legacy gameplay acceptance remains open (B-005).
