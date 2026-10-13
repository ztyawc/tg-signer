import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

pytest.importorskip("nicegui")
playwright = pytest.importorskip("playwright.sync_api")


@pytest.fixture
def console(tmp_path):
    workdir, logdir = tmp_path / "workdir", tmp_path / "logs"
    config = workdir / "signs" / "demo" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            {
                "chats": [
                    {"chat_id": 123, "actions": [{"action": 1, "text": "synthetic"}]}
                ],
                "sign_at": "0 6 * * *",
                "random_seconds": 0,
            }
        )
    )
    logdir.mkdir()
    (logdir / "tg-signer.log").write_text("[INFO] synthetic log entry\n")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    output = tmp_path / "server.log"
    environment = os.environ.copy()
    environment.pop("TG_SIGNER_GUI_AUTHCODE", None)
    environment.pop("PYTEST_CURRENT_TEST", None)
    environment.pop("TG_SIGNER_GUI_HTTPS_ONLY", None)
    with output.open("w") as log:
        process = subprocess.Popen(
            [
                str(
                    Path(sys.executable).with_name(
                        "tg-signer.exe" if os.name == "nt" else "tg-signer"
                    )
                ),
                "--workdir",
                str(workdir),
                "--log-dir",
                str(logdir),
                "webgui",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--auth-code",
                "test-only-access",
                "--storage-secret",
                "test-only-storage",
            ],
            cwd=tmp_path,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        url = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail(output.read_text())
                try:
                    if httpx.get(url, timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("WebUI did not become ready: " + output.read_text())
            yield url, config, output
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.fixture
def browser():
    with playwright.sync_playwright() as engine:
        options = {"headless": True, "args": ["--no-sandbox"]}
        if binary := os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"):
            options["executable_path"] = binary
        chrome = engine.chromium.launch(**options)
        try:
            yield chrome
        finally:
            chrome.close()


def login(page, url):
    page.goto(url)
    page.get_by_label("访问码", exact=True).fill("test-only-access")
    page.get_by_role("button", name="进入控制台", exact=True).click()
    playwright.expect(page.get_by_text("欢迎来到工作台", exact=False)).to_be_visible()


def test_browser_login_save_and_mobile_navigation(console, browser):
    url, config, _ = console
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    playwright.expect(page.locator(".ts-sidebar")).to_have_count(0)
    page.get_by_label("访问码", exact=True).fill("wrong-test-code")
    page.get_by_role("button", name="进入控制台", exact=True).click()
    playwright.expect(
        page.get_by_text("访问码不正确，请重试", exact=True)
    ).to_be_visible()
    page.get_by_label("访问码", exact=True).fill("test-only-access")
    page.get_by_role("button", name="进入控制台", exact=True).click()
    page.get_by_role("button", name="签到配置", exact=True).click()
    page.get_by_role("button", name="demo", exact=True).click()
    page.get_by_role("button", name="配置向导", exact=True).click()
    page.get_by_label("随机延迟 (秒)", exact=True).fill("15")
    page.get_by_role("button", name="保存配置", exact=True).last.click()
    playwright.expect(
        page.get_by_text("配置 demo 保存成功", exact=True)
    ).to_be_visible()
    assert json.loads(config.read_text())["random_seconds"] == 15
    playwright.expect(
        page.get_by_text("已保存 · 尚无任务运行状态", exact=True)
    ).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    for name in [
        "工作台",
        "签到配置",
        "监控配置",
        "账号与聊天",
        "签到记录",
        "运行日志",
    ]:
        page.get_by_role("button", name="打开导航", exact=True).click()
        page.get_by_role("button", name=name, exact=True).click()
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )
    assert errors == []
    page.close()


def test_browser_login_rate_limit(console, browser):
    url, _, _ = console
    page = browser.new_page()
    page.goto(url)
    for index in range(5):
        page.get_by_label("访问码", exact=True).fill(f"wrong-{index}")
        page.get_by_role("button", name="进入控制台", exact=True).click()
        playwright.expect(page.get_by_label("访问码", exact=True)).to_have_value("")
    page.get_by_label("访问码", exact=True).fill("test-only-access")
    page.get_by_role("button", name="进入控制台", exact=True).click()
    playwright.expect(page.get_by_text("尝试次数过多", exact=False)).to_be_visible()
    playwright.expect(page.locator(".ts-sidebar")).to_have_count(0)
    page.close()


def test_browser_separate_sessions_keep_workspaces_independent(console, browser):
    url, config, _ = console
    contexts = [browser.new_context() for _ in range(2)]
    pages = [context.new_page() for context in contexts]
    for page in pages:
        login(page, url)
    pages[0].get_by_role("button", name="工作区设置", exact=True).first.click()
    empty = config.parents[3] / "empty-workspace"
    pages[0].get_by_label("工作目录", exact=True).fill(str(empty))
    pages[0].get_by_role("button", name="应用设置", exact=True).click()
    playwright.expect(
        pages[0].get_by_text("从第一个签到任务开始", exact=True)
    ).to_be_visible()
    pages[1].get_by_role("button", name="刷新数据", exact=True).click()
    playwright.expect(pages[1].get_by_text("demo", exact=True).first).to_be_visible()
    for context in contexts:
        context.close()
