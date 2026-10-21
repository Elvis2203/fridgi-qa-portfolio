"""Small stable-app smoke suite. Every test owns its server and temporary database."""

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest
from demo.processes import stop_process
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[2]


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, "rep_" + report.when, report)


def failed(item):
    return any(
        getattr(item, "rep_" + phase, None) and getattr(item, "rep_" + phase).failed
        for phase in ("setup", "call")
    )


def artifact_dir(item):
    name = re.sub(r"[^a-zA-Z0-9_.-]", "-", item.name)
    digest = hashlib.sha256(item.nodeid.encode()).hexdigest()[:8]
    folder = ROOT / "test-results/browser" / (name + "-" + digest)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def capture_failure(driver, item):
    folder = artifact_dir(item)
    errors = []
    for name, action in (
        ("screenshot", lambda: driver.save_screenshot(str(folder / "screenshot.png"))),
        ("page", lambda: (folder / "page.html").write_text(driver.page_source, encoding="utf-8")),
        (
            "browser",
            lambda: (folder / "browser.json").write_text(
                json.dumps(
                    {"url": driver.current_url, "capabilities": driver.capabilities}, indent=2
                ),
                encoding="utf-8",
            ),
        ),
    ):
        try:
            action()
        except Exception as exc:
            # Diagnostic failures must not hide the original test failure.
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    if errors:
        (folder / "capture-errors.txt").write_text("\n".join(errors), encoding="utf-8")


@pytest.fixture
def site(request, tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/alembic.ini").write_text(
        (ROOT / "backend/alembic.ini")
        .read_text()
        .replace("%(here)s/migrations", (ROOT / "backend/migrations").as_posix())
    )
    shutil.copytree(ROOT / "frontend/dist", tmp_path / "frontend/dist")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, PYTHONPATH=str(ROOT / "backend"), FRIDGI_RECIPE_PROVIDER="groq")
    for key in (
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "FRIDGI_ENABLE_AI",
        "FRIDGI_DATABASE_URL",
    ):
        env.pop(key, None)
    code = (
        "from pathlib import Path; import uvicorn; from demo.server import demo_app; "
        f"uvicorn.run(demo_app(Path({str(tmp_path)!r})), host='127.0.0.1', port={port})"
    )
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", code],
            env=env,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    with urlopen(url + "/api/pantry", timeout=1):
                        break
                except OSError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        pytest.fail((tmp_path / "server.log").read_text())
                    time.sleep(0.1)  # Poll server readiness, never browser timing.
            yield url
        finally:
            stop_process(process)
            if failed(request.node):
                shutil.copy2(tmp_path / "server.log", artifact_dir(request.node) / "server.log")


@pytest.fixture(params=os.environ.get("BROWSERS", "chrome").split(","))
def browser(request, site):
    name = request.param.strip()
    if name not in ("chrome", "firefox"):
        raise ValueError("BROWSERS supports chrome and firefox only.")
    if name == "firefox":
        options = webdriver.FirefoxOptions()
        options.add_argument("-headless")
        driver = webdriver.Firefox(options=options)
    else:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=options)
    captured = False
    try:
        request.node.user_properties.extend(
            [
                ("browser", name),
                ("browser_version", driver.capabilities.get("browserVersion", "unknown")),
                ("platform", driver.capabilities.get("platformName", "unknown")),
            ]
        )
        driver.set_window_size(1100, 950)
        driver.get(site)
        wait = WebDriverWait(driver, 10)
        wait.until(lambda _: driver.find_element(By.ID, "ingredients").is_enabled())
        yield driver, wait
    except BaseException:
        capture_failure(driver, request.node)
        captured = True
        raise
    finally:
        try:
            if not captured and failed(request.node):
                capture_failure(driver, request.node)
        finally:
            driver.quit()
