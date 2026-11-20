#!/usr/bin/env python3
"""Verify the Milestone 3A generated/legacy game portal integration.

Requirements:
    python3 -m pip install playwright pillow
    python3 -m playwright install chromium

Usage:
    python3 tools/verify_pilot.py

The script serves the repository with HTTP Range support, drives Chromium
through generated and legacy players, writes screenshots to docs/screenshots/,
and writes machine-readable evidence to docs/verification/3a-integration.json.
It requires network access to the CheerpJ CDN.
"""

from __future__ import annotations

import hashlib
import http.server
import io
import json
import os
import re
import socket
import threading
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = ROOT / "docs" / "screenshots"
EVIDENCE_PATH = ROOT / "docs" / "verification" / "3a-integration.json"
CDN_URL = "https://cjrtnc.leaningtech.com/5.0/loader.js"

GENERATED = {
    "Car Traffic": "web-games/car-traffic/index.html",
    "Flappy Bird": "web-games/flappy/index.html",
    "Paddle Game": "web-games/paddle-game/index.html",
}
LEGACY = ("Froggie Cross the Road", "Minesweeper", "Pong", "Snake")

CHECKS: List[Dict] = []
CONSOLE: List[str] = []
PAGE_ERRORS: List[str] = []
REQUESTS: List[str] = []
SERVER_REQUESTS: List[Dict] = []


class RangeFileWrapper:
    def __init__(self, file_obj, length: int):
        self.file_obj = file_obj
        self.remaining = length

    def read(self, size: int = -1) -> bytes:
        if self.remaining <= 0:
            return b""
        if size < 0 or size > self.remaining:
            size = self.remaining
        chunk = self.file_obj.read(size)
        self.remaining -= len(chunk)
        return chunk

    def close(self) -> None:
        self.file_obj.close()


class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def end_headers(self) -> None:
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range, Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def parse_byte_range(self, value: str, file_size: int) -> Optional[Tuple[int, int]]:
        match = re.match(r"^bytes=(\d*)-(\d*)$", value.strip())
        if not match:
            return None
        start_text, end_text = match.groups()
        if not start_text and not end_text:
            return None
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else file_size - 1
        else:
            length = int(end_text)
            if length <= 0:
                return None
            start = max(0, file_size - length)
            end = file_size - 1
        if start >= file_size or start > end:
            return None
        return start, min(end, file_size - 1)

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            if not self.path.split("?")[0].endswith("/"):
                self.send_response(301)
                self.send_header("Location", self.path + "/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            for index in ("index.html", "index.htm"):
                candidate = os.path.join(path, index)
                if os.path.exists(candidate):
                    path = candidate
                    break
            else:
                return self.list_directory(path)

        content_type = self.guess_type(path)
        try:
            handle = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        try:
            file_size = os.fstat(handle.fileno()).st_size
            range_header = self.headers.get("Range")
            if range_header:
                byte_range = self.parse_byte_range(range_header, file_size)
                if byte_range is None:
                    self.send_response(416, "Range Not Satisfiable")
                    self.send_header("Content-Range", f"bytes */{file_size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    handle.close()
                    return None
                start, end = byte_range
                length = end - start + 1
                self.send_response(206, "Partial Content")
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Last-Modified", self.date_time_string(os.fstat(handle.fileno()).st_mtime))
                self.end_headers()
                handle.seek(start)
                return RangeFileWrapper(handle, length)

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Last-Modified", self.date_time_string(os.fstat(handle.fileno()).st_mtime))
            self.end_headers()
            return handle
        except Exception:
            handle.close()
            raise

    def log_message(self, fmt, *args) -> None:
        pass


class LocalServer:
    def __init__(self, directory: Path):
        directory_text = str(directory)

        class Handler(RangeRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=directory_text, **kwargs)

            def end_headers(self) -> None:
                SERVER_REQUESTS.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "range": self.headers.get("Range", ""),
                    }
                )
                super().end_headers()

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.port = self.server.server_port

    def __enter__(self):
        self.thread.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.25):
                    return self
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("Local HTTP server did not start")

    def __exit__(self, exc_type, exc, tb):
        self.server.shutdown()
        self.server.server_close()


def check(name: str, passed: bool, detail=None) -> None:
    CHECKS.append({"name": name, "passed": bool(passed), "detail": detail})
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail is not None else ""))
    if not passed:
        raise AssertionError(f"{name}: {detail}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def image_stats(data: bytes) -> Dict[str, float]:
    from PIL import Image

    image = Image.open(io.BytesIO(data)).convert("RGB").resize((120, 90))
    raw = image.tobytes()
    pixels = list(zip(raw[0::3], raw[1::3], raw[2::3]))
    luminances = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in pixels]
    mean = sum(luminances) / len(luminances)
    variance = sum((value - mean) ** 2 for value in luminances) / len(luminances)
    return {
        "unique_colors": float(len(set(pixels))),
        "luminance_stddev": variance ** 0.5,
        "non_dark_ratio": sum(max(p) > 24 for p in pixels) / len(pixels),
    }


def assert_rendered(data: bytes, label: str, min_unique=45, min_stddev=8, min_non_dark=0.03):
    stats = image_stats(data)
    if stats["unique_colors"] < min_unique:
        raise AssertionError(f"{label}: canvas looks blank ({stats})")
    if stats["luminance_stddev"] < min_stddev:
        raise AssertionError(f"{label}: too little visual variance ({stats})")
    if stats["non_dark_ratio"] < min_non_dark:
        raise AssertionError(f"{label}: canvas is almost entirely dark ({stats})")
    return stats


def difference_ratio(before: bytes, after: bytes) -> float:
    from PIL import Image

    def pixels(data: bytes):
        image = Image.open(io.BytesIO(data)).convert("RGB").resize((120, 90))
        raw = image.tobytes()
        return list(zip(raw[0::3], raw[1::3], raw[2::3]))

    first, second = pixels(before), pixels(after)
    changed = sum(
        max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2])) > 18
        for a, b in zip(first, second)
    )
    return changed / len(first)


def assert_changed(before: bytes, after: bytes, label: str, minimum=0.02) -> float:
    ratio = difference_ratio(before, after)
    if ratio < minimum:
        raise AssertionError(f"{label}: expected visible change, got {ratio:.4f}")
    return ratio


def card(page, name: str):
    return page.locator(".game-card").filter(has_text=name)


def find_frame(page, entry: str, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for frame in page.frames:
            if frame != page.main_frame and frame.url.endswith(entry):
                return frame
        page.wait_for_timeout(100)
    raise AssertionError(f"iframe frame not found: {entry}")


def generated_frame_count(page) -> int:
    return sum(1 for frame in page.frames if "/web-games/" in frame.url)


def wait_for_portal_loaded(page):
    page.wait_for_selector("#generated-wrapper:not(.hidden)", timeout=30000)
    page.wait_for_selector("#loading-overlay", state="hidden", timeout=30000)


def wait_for_canvas(frame, timeout=120):
    deadline = time.time() + timeout
    status = "?"
    while time.time() < deadline:
        status = frame.evaluate("() => document.body.dataset.status || ''")
        if status == "error":
            return False, status
        if frame.evaluate(
            """() => [...document.querySelectorAll('#cheerpj-display canvas')].some((c) => {
                const r = c.getBoundingClientRect();
                const s = getComputedStyle(c);
                return r.width > 20 && r.height > 20
                    && s.display !== 'none' && s.visibility !== 'hidden';
            })"""
        ):
            return True, status
        time.sleep(0.5)
    return False, status


def main_canvas(frame):
    return frame.locator("#cheerpj-display canvas").last


def click_generated_canvas(page, canvas, x: float, y: float) -> None:
    iframe_box = page.locator("#generated-frame").bounding_box()
    rect = canvas.evaluate(
        "el => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y }; }"
    )
    if not iframe_box:
        raise AssertionError("Generated iframe has no bounding box")
    page.mouse.click(iframe_box["x"] + rect["x"] + x, iframe_box["y"] + rect["y"] + y)


def open_generated(page, name: str, entry: str):
    attempts = []
    for attempt in range(1, 6):
        card(page, name).locator(".btn-play").click()
        page.wait_for_selector("#generated-wrapper:not(.hidden)", timeout=30000)
        frame = find_frame(page, entry)
        frame.wait_for_selector("#btn-start", timeout=30000)
        frame.wait_for_selector('body[data-status="idle"]', timeout=30000)
        page.wait_for_timeout(2500)
        check(f"{name}: generated iframe loaded", generated_frame_count(page) == 1)

        frame.locator("#btn-start").click()
        mounted, status = wait_for_canvas(frame)
        if mounted:
            attempts.append({"attempt": attempt, "status": status})
            check(f"{name}: canvas mounted", True, {"attempts": attempts})
            frame.wait_for_timeout(1500)
            return frame

        error_message = frame.evaluate(
            "() => document.querySelector('#error-message')?.textContent || ''"
        )
        error_details = frame.evaluate(
            "() => document.querySelector('#error-details')?.textContent || ''"
        )
        attempts.append(
            {
                "attempt": attempt,
                "status": status,
                "error": error_message,
                "details": error_details[:1200],
            }
        )

        page.locator("#btn-back").click()
        page.wait_for_selector("#view-gallery:not(.hidden)", timeout=10000)
        assert_generated_removed(page, f"{name} retry cleanup")

        if attempt == 5:
            check(f"{name}: canvas mounted", False, {"attempts": attempts})

        page.wait_for_timeout(4000 * attempt)

    raise AssertionError(f"{name}: canvas did not mount after retries")

def screenshot(page, name: str) -> Path:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / name
    page.screenshot(path=str(path), full_page=True)
    return path


def assert_generated_removed(page, label: str) -> None:
    page.wait_for_timeout(200)
    count = page.locator("#generated-frame").count()
    check(f"{label}: iframe removed from DOM", count == 0, {"iframe_count": count})
    check(f"{label}: no live generated frames", generated_frame_count(page) == 0)


def click_portal_back(page) -> None:
    page.locator("#btn-back").click()
    page.wait_for_selector("#view-gallery:not(.hidden)", timeout=10000)
    assert_generated_removed(page, "Back to gallery")


def click_portal_stop(page) -> None:
    page.locator("#btn-stop").click()
    page.wait_for_selector("#loading-overlay:not(.hidden)", timeout=10000)
    text = page.locator("#loading-text").text_content()
    check("Stop: stopped state shown", "dihentikan" in (text or "").lower(), text)
    assert_generated_removed(page, "Stop")


def verify_generated_car_traffic(page):
    frame = open_generated(page, "Car Traffic", GENERATED["Car Traffic"])
    wait_for_portal_loaded(page)
    frame.wait_for_timeout(5500)
    canvas = main_canvas(frame)
    menu_bytes = canvas.screenshot()
    screenshot(page, "3a-car-traffic-generated.png")
    stats = assert_rendered(menu_bytes, "Car Traffic menu")
    check("Car Traffic: menu rendered", True, stats)

    click_generated_canvas(page, canvas, 155, 380)
    page.wait_for_timeout(500)
    click_generated_canvas(page, canvas, 415, 460)
    frame.wait_for_timeout(2500)
    interaction_bytes = canvas.screenshot()
    screenshot(page, "3a-car-traffic-interaction.png")
    stats = assert_rendered(interaction_bytes, "Car Traffic interaction")
    ratio = assert_changed(menu_bytes, interaction_bytes, "Car Traffic character selection", 0.04)
    check("Car Traffic: menu interaction changes UI", True, {"difference_ratio": ratio, **stats})

    frame.locator("#btn-restart").click()
    page.frame_locator("#generated-frame").locator("#btn-start").wait_for(timeout=30000)
    check("Car Traffic: restart keeps one generated iframe", generated_frame_count(page) == 1)

    click_portal_stop(page)
    click_portal_back(page)


def verify_generated_flappy(page):
    frame = open_generated(page, "Flappy Bird", GENERATED["Flappy Bird"])
    wait_for_portal_loaded(page)
    frame.wait_for_timeout(2500)
    canvas = main_canvas(frame)
    menu_bytes = canvas.screenshot()
    screenshot(page, "3a-flappy-generated.png")
    stats = assert_rendered(menu_bytes, "Flappy menu", min_unique=20, min_stddev=3, min_non_dark=0.05)
    check("Flappy: menu rendered", True, stats)

    click_generated_canvas(page, canvas, 170, 440)
    frame.wait_for_timeout(2000)
    running_bytes = canvas.screenshot()
    screenshot(page, "3a-flappy-gameplay.png")
    stats = assert_rendered(running_bytes, "Flappy gameplay", min_unique=20, min_stddev=3, min_non_dark=0.05)
    ratio = assert_changed(menu_bytes, running_bytes, "Flappy PLAY", 0.02)
    check("Flappy: PLAY starts gameplay", True, {"difference_ratio": ratio, **stats})

    click_portal_stop(page)
    click_portal_back(page)


def verify_generated_paddle(page):
    range_path = "/web-games/paddle-game/lib/AbsoluteLayout.jar"
    request = urllib.request.Request(
        f"http://127.0.0.1:{SERVER_PORT}{range_path}",
        headers={"Range": "bytes=0-1"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = response.read()
        status = response.status
        accept_ranges = response.headers.get("Accept-Ranges")
    check(
        "Paddle: AbsoluteLayout.jar supports Range",
        status == 206 and body == b"PK" and accept_ranges == "bytes",
        {"status": status, "body": body.hex(), "accept_ranges": accept_ranges},
    )

    frame = open_generated(page, "Paddle Game", GENERATED["Paddle Game"])
    wait_for_portal_loaded(page)
    frame.wait_for_timeout(3500)
    canvas = main_canvas(frame)
    level_bytes = canvas.screenshot()
    screenshot(page, "3a-paddle-level.png")
    stats = assert_rendered(
        level_bytes, "Paddle level select", min_unique=150, min_stddev=18, min_non_dark=0.25
    )
    check("Paddle: level select rendered", True, stats)

    click_generated_canvas(page, canvas, 365, 258)
    frame.wait_for_timeout(6500)
    game_bytes = canvas.screenshot()
    screenshot(page, "3a-paddle-easy.png")
    stats = assert_rendered(
        game_bytes, "Paddle easy mode", min_unique=120, min_stddev=12, min_non_dark=0.10
    )
    ratio = assert_changed(level_bytes, game_bytes, "Paddle Easy mode", 0.05)
    check("Paddle: Easy mode starts game", True, {"difference_ratio": ratio, **stats})

    dependency_requests = [
        item for item in SERVER_REQUESTS if "AbsoluteLayout.jar" in item["path"]
    ]
    ranged = [item for item in dependency_requests if "bytes=" in item["range"]]
    check(
        "Paddle: dependency requested by generated browser player",
        bool(dependency_requests),
        {
            "requests": len(dependency_requests),
            "range_requests": len(ranged),
            "sample": dependency_requests[:3],
        },
    )

    click_portal_stop(page)
    click_portal_back(page)


def verify_legacy_snake(page):
    check(
        "Catalog: Pong limitation is explicit",
        "audio" in card(page, "Pong").locator(".card-desc").text_content().lower(),
    )
    entry = card(page, "Snake")
    check("Snake: catalog marks legacy mode", entry.get_attribute("data-player-mode") == "legacy")
    entry.locator(".btn-play").click()
    page.wait_for_selector("#view-game:not(.hidden)", timeout=10000)
    deadline = time.time() + 90
    mounted = False
    while time.time() < deadline:
        mounted = page.evaluate(
            """() => [...document.querySelectorAll('#applet canvas')].some((c) => {
                const r = c.getBoundingClientRect();
                return r.width > 20 && r.height > 20;
            })"""
        )
        if mounted:
            break
        page.wait_for_timeout(500)
    check("Snake: legacy CheerpJ canvas mounted", mounted)
    page.wait_for_timeout(4000)
    canvas = page.locator("#applet canvas").last
    stats = assert_rendered(
        canvas.screenshot(), "Snake legacy window", min_unique=20, min_stddev=3, min_non_dark=0.03
    )
    screenshot(page, "3a-legacy-snake.png")
    check(
        "Snake: legacy CheerpJ window captured",
        True,
        {"note": "Visual gameplay completeness is reviewed separately; launcher/teardown are the automated checks.", **stats},
    )

    page.locator("#btn-stop").click()
    page.wait_for_timeout(300)
    check(
        "Snake: legacy stop clears applet DOM",
        page.locator("#applet *").count() == 0,
    )
    page.locator("#btn-back").click()
    page.wait_for_selector("#view-gallery:not(.hidden)", timeout=10000)
    check("Snake: legacy back returns to gallery", page.locator(".game-card").count() == 7)


def fatal_messages(messages: List[str]) -> List[str]:
    patterns = (
        "ExceptionInInitializerError",
        "NoClassDefFoundError",
        "UnsatisfiedLinkError",
        "No line matching interface",
        "Exception in thread",
    )
    return [line for line in messages if any(pattern in line for pattern in patterns)]


def main():
    global SERVER_PORT
    from playwright.sync_api import sync_playwright

    try:
        with urllib.request.urlopen(CDN_URL, timeout=10) as response:
            if not 200 <= response.status < 400:
                raise RuntimeError(f"CheerpJ CDN returned HTTP {response.status}")
    except Exception as exc:
        raise SystemExit(f"CheerpJ CDN is required for this verification: {exc}")

    expected_hashes = {
        "games/CarTraffic.jar": "ff1e14564f77cb356ec9ffbee82fb1291981c57471082b7c0faa5cc6bcff1f2e",
        "games/flappy.jar": "c788986652405b12962066c61fc2c3cfe843335a6e3a4ae4ef6f4d3a0de4b0ea",
        "games/PaddleGame.jar": "41b423488d9aba93f184ce56281417a836996417e5ed85404b8174034973b8dd",
        "games/lib/AbsoluteLayout.jar": "cbe5600e86eb64761e11e4cb046804a070bc214e00b9fa61413b59017089dfd1",
    }
    for relative, expected in expected_hashes.items():
        actual = sha256(ROOT / relative)
        check(f"Source hash unchanged: {relative}", actual == expected, actual)

    with LocalServer(ROOT) as server:
        SERVER_PORT = server.port
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=["--autoplay-policy=no-user-gesture-required"],
            )
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.on("pageerror", lambda error: PAGE_ERRORS.append(str(error)))
            page.on("console", lambda message: CONSOLE.append(f"{message.type}: {message.text}"))
            page.on("request", lambda request: REQUESTS.append(request.url))

            page.goto(f"http://127.0.0.1:{server.port}/", wait_until="load", timeout=30000)
            page.wait_for_selector(".game-card", timeout=20000)
            page.wait_for_timeout(500)

            cards = page.locator(".game-card")
            check("Catalog: all seven games render", cards.count() == 7, {"cards": cards.count()})
            page.screenshot(path=str(SCREENSHOT_DIR / "3a-gallery.png"), full_page=True)

            for name, entry in GENERATED.items():
                check(
                    f"Catalog: {name} uses generated player",
                    card(page, name).get_attribute("data-player-mode") == "generated",
                    entry,
                )
            for name in LEGACY:
                check(
                    f"Catalog: {name} stays on legacy player",
                    card(page, name).get_attribute("data-player-mode") == "legacy",
                )

            check(
                "Isolation: no generated artifact loaded before play",
                not any("/web-games/" in url for url in REQUESTS),
                [url for url in REQUESTS if "/web-games/" in url],
            )
            check("Isolation: no iframe exists on gallery", page.locator("iframe").count() == 0)

            verify_generated_car_traffic(page)
            verify_generated_flappy(page)
            verify_generated_paddle(page)
            verify_legacy_snake(page)

            fatal = fatal_messages(PAGE_ERRORS + CONSOLE)
            check("Browser: no fatal console/page errors", not fatal, fatal)
            check("Isolation: no generated frames at end", generated_frame_count(page) == 0)
            iframe_inventory = page.evaluate(
                "() => [...document.querySelectorAll('iframe')].map((el) => ({ id: el.id, src: el.src }))"
            )
            check(
                "Isolation: no generated iframe remains in DOM",
                not any("/web-games/" in item["src"] for item in iframe_inventory),
                iframe_inventory,
            )

            browser.close()

    generated_checks = [item for item in CHECKS if item["passed"]]
    evidence = {
        "schema_version": "1.0",
        "milestone": "3A",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base_commit": os.popen("git rev-parse HEAD").read().strip(),
        "portal_url": f"http://127.0.0.1:{SERVER_PORT}/",
        "checks": CHECKS,
        "summary": {
            "total": len(CHECKS),
            "passed": len(generated_checks),
            "failed": len(CHECKS) - len(generated_checks),
        },
        "screenshots": sorted(str(path.relative_to(ROOT)) for path in SCREENSHOT_DIR.glob("3a-*.png")),
        "page_errors": PAGE_ERRORS,
        "console": CONSOLE,
        "server_requests": SERVER_REQUESTS,
        "artifact_hashes": {
            path: sha256(ROOT / path)
            for path in (
                "web-games/car-traffic/CarTraffic.jar",
                "web-games/flappy/flappy.jar",
                "web-games/paddle-game/PaddleGame.jar",
                "web-games/paddle-game/lib/AbsoluteLayout.jar",
            )
        },
        "notes": [
            "Automated Chromium verification with local HTTP Range support.",
            "Screenshots require separate visual/manual review.",
            "Pong was not launched; its known browser audio limitation is disclosed in the catalog.",
        ],
    }
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    print(f"\n{len(generated_checks)}/{len(CHECKS)} checks passed")
    print(f"Evidence: {EVIDENCE_PATH.relative_to(ROOT)}")
    print(f"Screenshots: {SCREENSHOT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
