#!/usr/bin/env python3
"""Deterministic offline browser checks for the portal.

External network is blocked. The tests cover catalog rendering, metadata
injection safety, generated-entry validation, and iframe isolation attributes.
CheerpJ games are not launched; external CDN gameplay checks belong to
verify_pilot.py and the manual CDN workflow.
"""

from __future__ import annotations

import http.server
import json
import socket
import threading
import time
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
CHECKS: List[Dict[str, Any]] = []

MALICIOUS_NAME = '<img src=x onerror="window.__xss=(window.__xss||0)+1">'
MALICIOUS_IMAGE = 'x" onerror="window.__xss=42'
MALICIOUS_DESCRIPTION = '<svg onload="window.__xss=99"></svg>Literal description'
MALICIOUS_CATALOG = [
    {
        "name": MALICIOUS_NAME,
        "jar": "malicious.jar",
        "image": MALICIOUS_IMAGE,
        "description": MALICIOUS_DESCRIPTION,
        "player": {"mode": "legacy"},
    },
    {
        "name": "Invalid entry",
        "jar": "invalid.jar",
        "image": "./images/default.png",
        "description": "Path traversal must be rejected.",
        "player": {"mode": "generated", "entry": "../escape.html"},
    },
]


def check(name: str, passed: bool, detail: Any = None) -> None:
    CHECKS.append({"name": name, "passed": bool(passed), "detail": detail})
    status = "PASS" if passed else "FAIL"
    suffix = "" if detail is None else f" — {detail}"
    print(f"[{status}] {name}{suffix}")


class TestServer:
    def __init__(self, overrides: Dict[str, bytes] | None = None):
        self.overrides = overrides or {}
        root = str(ROOT)

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=root, **kwargs)

            def do_GET(self):
                request_path = self.path.split("?", 1)[0]
                body = self.overrides.get(request_path)
                if body is None:
                    super().do_GET()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def end_headers(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                super().end_headers()

            def log_message(self, fmt, *args):
                pass

        Handler.overrides = self.overrides
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_port
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        self.thread.start()
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.25):
                    return self
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("Test server did not start")

    def __exit__(self, exc_type, exc, tb):
        self.httpd.shutdown()
        self.httpd.server_close()


def card(page, name: str):
    return page.locator(".game-card").filter(has_text=name)


def new_offline_page(browser, allowed_origins: set[str]):
    context = browser.new_context()
    requests: List[str] = []
    external: List[str] = []

    def handler(route, request):
        requests.append(request.url)
        parsed = urlparse(request.url)
        if parsed.scheme in ("http", "https") and parsed.netloc in allowed_origins:
            route.continue_()
        else:
            external.append(request.url)
            route.abort()

    context.route("**/*", handler)
    return context, context.new_page(), requests, external


def verify_normal_gallery(browser, portal: TestServer) -> None:
    context, page, requests, external = new_offline_page(browser, {urlparse(portal.origin).netloc})
    try:
        page.goto(portal.origin + "/", wait_until="load", timeout=30000)
        page.wait_for_selector(".game-card", timeout=20000)
        page.wait_for_timeout(250)

        check("Offline: seven catalog cards render", page.locator(".game-card").count() == 7)
        check("Offline: no iframe before Play", page.locator("iframe").count() == 0)
        check(
            "Offline: no generated artifact loaded before Play",
            not any("/web-games/" in url for url in requests),
            [url for url in requests if "/web-games/" in url],
        )

        card(page, "Car Traffic").locator(".btn-play").click()
        page.wait_for_selector("#generated-frame", timeout=10000)
        frame = page.locator("#generated-frame")
        sandbox = frame.get_attribute("sandbox")
        check(
            "Same-origin mode: sandbox is explicit but only a lifecycle boundary",
            sandbox == "allow-scripts allow-same-origin",
            sandbox,
        )
        check(
            "Same-origin mode: trust boundary is marked in the DOM",
            frame.get_attribute("data-isolation") == "same-origin-trusted",
            frame.get_attribute("data-isolation"),
        )
        page.locator("#btn-back").click()
        page.wait_for_selector("#view-gallery:not(.hidden)", timeout=10000)
        check("Same-origin mode: Back removes the iframe", page.locator("#generated-frame").count() == 0)
    finally:
        context.close()


def verify_metadata_injection(browser, portal: TestServer) -> None:
    malicious_name = MALICIOUS_NAME
    malicious_description = MALICIOUS_DESCRIPTION
    context, page, requests, external = new_offline_page(browser, {urlparse(portal.origin).netloc})
    try:
        page.goto(portal.origin + "/", wait_until="load", timeout=30000)
        page.wait_for_selector(".game-card", timeout=20000)
        page.wait_for_timeout(250)

        check("Injection: malicious catalog renders two cards", page.locator(".game-card").count() == 2)
        check(
            "Injection: no script executed from metadata",
            page.evaluate("() => window.__xss === undefined"),
            page.evaluate("() => window.__xss"),
        )
        check(
            "Injection: no injected SVG/script/extra image nodes",
            page.locator(".game-card svg, .game-card script, .game-card img:not(.card-image)").count() == 0,
        )
        actual_name = page.locator(".game-card h3").first.text_content()
        actual_description = page.locator(".game-card .card-desc").first.text_content()
        check(
            "Injection: name is rendered as literal text",
            actual_name == malicious_name,
            actual_name,
        )
        check(
            "Injection: description is rendered as literal text",
            actual_description == malicious_description,
            actual_description,
        )
        check(
            "Injection: unsafe image path falls back to the local default",
            page.locator(".game-card .card-image").first.get_attribute("src") == "./images/default.png",
        )
        actual_title = page.locator(".game-card h3").first.get_attribute("title")
        check(
            "Injection: title attribute is set as a property, not HTML",
            actual_title == malicious_name,
            actual_title,
        )

        card(page, "Invalid entry").locator(".btn-play").click()
        page.wait_for_selector("#loading-overlay:not(.hidden)", timeout=10000)
        message = page.locator("#loading-text").text_content() or ""
        check(
            "Path validation: traversal entry is rejected",
            "Path artifact" in message and page.locator("#generated-frame").count() == 0,
            message,
        )
    finally:
        context.close()


def verify_cross_origin_mode(browser, portal: TestServer, generated: TestServer) -> None:
    config = json.dumps({"generatedOrigin": generated.origin + "/"}).encode("utf-8")
    context, page, requests, external = new_offline_page(
        browser,
        {urlparse(portal.origin).netloc, urlparse(generated.origin).netloc},
    )
    try:
        page.goto(portal.origin + "/", wait_until="load", timeout=30000)
        page.wait_for_selector(".game-card", timeout=20000)
        page.wait_for_timeout(250)
        check(
            "Cross-origin mode: no generated artifact loaded before Play",
            not any("/web-games/" in url for url in requests),
            [url for url in requests if "/web-games/" in url],
        )

        card(page, "Car Traffic").locator(".btn-play").click()
        page.wait_for_selector("#generated-frame", timeout=10000)
        frame = page.locator("#generated-frame")
        source = frame.get_attribute("src") or ""
        sandbox = frame.get_attribute("sandbox")
        check(
            "Cross-origin mode: iframe uses the configured generated origin",
            source.startswith(generated.origin + "/web-games/car-traffic/"),
            source,
        )
        check(
            "Cross-origin mode: sandbox omits allow-same-origin",
            sandbox == "allow-scripts allow-pointer-lock",
            sandbox,
        )
        check(
            "Cross-origin mode: isolation mode is marked in the DOM",
            frame.get_attribute("data-isolation") == "cross-origin",
            frame.get_attribute("data-isolation"),
        )
        check(
            "Cross-origin mode: referrer policy is no-referrer",
            frame.get_attribute("referrerpolicy") == "no-referrer",
            frame.get_attribute("referrerpolicy"),
        )
        page.locator("#btn-back").click()
        page.wait_for_selector("#view-gallery:not(.hidden)", timeout=10000)
        check("Cross-origin mode: Back removes the iframe", page.locator("#generated-frame").count() == 0)
    finally:
        context.close()


def main() -> int:
    from playwright.sync_api import sync_playwright

    with TestServer() as portal:
        with TestServer(
            {"/data/games.json": json.dumps(MALICIOUS_CATALOG).encode("utf-8")}
        ) as malicious_portal:
            with TestServer() as generated:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    try:
                        with TestServer(
                            {
                                "/data/player-config.json": json.dumps(
                                    {"generatedOrigin": generated.origin + "/"}
                                ).encode("utf-8")
                            }
                        ) as cross_portal:
                            verify_normal_gallery(browser, portal)
                            verify_metadata_injection(browser, malicious_portal)
                            verify_cross_origin_mode(browser, cross_portal, generated)
                    finally:
                        browser.close()

    failed = [item for item in CHECKS if not item["passed"]]
    print(f"\n{len(CHECKS) - len(failed)}/{len(CHECKS)} offline browser checks passed")
    if failed:
        print("Failed checks:")
        for item in failed:
            print(f"- {item['name']}: {item['detail']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
