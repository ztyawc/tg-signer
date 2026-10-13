import os
import secrets
from datetime import datetime
from typing import Callable, Dict

from nicegui import app, ui

from tg_signer import __version__
from tg_signer.webui.auth import LoginLimiter, create_session, session_valid
from tg_signer.webui.data import DEFAULT_WORKDIR
from tg_signer.webui.state import UIState
from tg_signer.webui.theme import apply_theme
from tg_signer.webui.views import (
    ConfigBlock,
    LogBlock,
    OverviewBlock,
    RecordBlock,
    UserBlock,
    notify_error,
)

SIGNER_TEMPLATE: Dict[str, object] = {
    "chats": [
        {
            "chat_id": "@channel_or_user",
            "message_thread_id": None,
            "name": "示例任务",
            "delete_after": None,
            "actions": [{"action": 1, "text": "签到"}],
            "action_interval": 1,
        }
    ],
    "sign_at": "0 6 * * *",
    "random_seconds": 0,
    "sign_interval": 1,
}

MONITOR_TEMPLATE: Dict[str, object] = {
    "match_cfgs": [
        {
            "chat_id": "@channel_or_user",
            "rule": "contains",
            "rule_value": "关键词",
            "from_user_ids": None,
            "always_ignore_me": False,
            "default_send_text": "自动回复",
            "ai_reply": False,
            "ai_prompt": None,
            "send_text_search_regex": None,
            "send_text_template": None,
            "delete_after": None,
            "ignore_case": True,
            "forward_to_chat_id": None,
            "external_forwards": None,
            "push_via_server_chan": False,
            "server_chan_send_key": None,
        }
    ]
}


AUTH_CODE_ENV = "TG_SIGNER_GUI_AUTHCODE"
AUTH_STORAGE_KEY = "tg_signer_gui_auth_code"
LOGIN_LIMITER = LoginLimiter()

PAGES = {
    "overview": ("工作台", "space_dashboard", "任务与记录，一目了然"),
    "signer": ("签到配置", "event_available", "管理聊天、动作与签到计划"),
    "monitor": ("监控配置", "radar", "消息匹配、回复与转发"),
    "users": ("账号与聊天", "people_outline", "账号资料与最近聊天"),
    "records": ("签到记录", "history", "检索每一次历史记录"),
    "logs": ("运行日志", "terminal", "查看日志与执行信息"),
}


def brand() -> None:
    with ui.row().classes("ts-brand"):
        with ui.element("div").classes("ts-brand-mark"):
            ui.icon("send").classes("text-xl")
        with ui.column().classes("gap-0"):
            ui.label("TG Signer").classes("ts-brand-name")
            ui.label("管理控制台").classes("ts-brand-caption")


def _build_dashboard(root, state: UIState, logout: Callable[[], None] | None) -> None:
    active = {"page": "overview"}
    pages, buttons, blocks = {}, {}, {}

    def close_navigation() -> None:
        sidebar.classes(remove="ts-sidebar-open")
        backdrop.set_visibility(False)

    def navigate(name: str) -> None:
        active["page"] = name
        for key, panel in pages.items():
            panel.set_visibility(key == name)
            buttons[key].classes(
                add="is-active" if key == name else "",
                remove="is-active" if key != name else "",
            )
        header_title.set_text(PAGES[name][0])
        header_caption.set_text(PAGES[name][2])
        close_navigation()

    def refresh_all() -> None:
        state.require_access()
        for block in blocks.values():
            try:
                block.refresh()
            except Exception as exc:
                notify_error(exc)
        refreshed.set_text(f"更新于 {datetime.now():%H:%M}")

    def settings() -> None:
        with ui.dialog() as dialog, ui.card().classes("ts-dialog w-full max-w-lg"):
            ui.icon("folder_open").classes("text-3xl text-teal-600")
            ui.label("工作区设置").classes("ts-panel-title")
            ui.label("切换要管理的配置、账号缓存和记录所在的工作目录。").classes(
                "ts-muted"
            )
            path = (
                ui.input("工作目录", value=str(state.workdir))
                .props("outlined")
                .classes("w-full")
            )

            def apply() -> None:
                try:
                    state.set_workdir(path.value or str(DEFAULT_WORKDIR))
                    blocks["signer"].new_config()
                    blocks["monitor"].new_config()
                    refresh_all()
                    dialog.close()
                    ui.notify("工作区已切换", type="positive")
                except Exception as exc:
                    notify_error(exc)

            with ui.row().classes("w-full justify-end mt-3"):
                ui.button("取消", on_click=dialog.close).props("flat")
                ui.button("应用设置", icon="check", on_click=apply).props("unelevated")
        dialog.open()

    def edit_task(name: str) -> None:
        navigate("signer")
        blocks["signer"].load(name)

    def new_task() -> None:
        navigate("signer")
        blocks["signer"].open_wizard(new=True)

    def goto_records(name: str) -> None:
        navigate("records")
        blocks["records"].filter_task(name)

    with root, ui.element("div").classes("ts-shell"):
        backdrop = (
            ui.element("div").classes("ts-backdrop").on("click", close_navigation)
        )
        backdrop.set_visibility(False)
        with ui.element("aside").classes("ts-sidebar") as sidebar:
            with ui.row().classes("w-full items-center justify-between"):
                brand()
                ui.button(icon="close", on_click=close_navigation).props(
                    'flat round aria-label="关闭导航"'
                ).classes("ts-mobile-only")
            ui.label("工作空间").classes("ts-nav-heading")
            with ui.column().classes("ts-nav"):
                for key, (label, icon, _) in PAGES.items():
                    buttons[key] = (
                        ui.button(
                            label,
                            icon=icon,
                            color=None,
                            on_click=lambda _, page=key: navigate(page),
                        )
                        .props("flat")
                        .classes("ts-nav-button")
                    )
            with ui.column().classes("ts-sidebar-footer gap-1"):
                ui.element("div").classes("ts-sidebar-rule")
                ui.button(
                    "工作区设置", icon="settings", color=None, on_click=settings
                ).props("flat").classes("ts-nav-button")
                if logout:
                    ui.button(
                        "退出登录", icon="logout", color=None, on_click=logout
                    ).props("flat").classes("ts-nav-button")
                ui.label(f"TG Signer · v{__version__}").classes("ts-sidebar-footnote")
        with ui.element("main").classes("ts-main"):
            with ui.element("header").classes("ts-topbar"):
                with ui.row().classes("items-center gap-3"):

                    def open_navigation() -> None:
                        sidebar.classes(add="ts-sidebar-open")
                        backdrop.set_visibility(True)

                    ui.button(icon="menu", on_click=open_navigation).props(
                        'flat round aria-label="打开导航"'
                    ).classes("ts-mobile-only")
                    with ui.column().classes("gap-0"):
                        header_title = ui.label("工作台").classes("ts-topbar-title")
                        header_caption = ui.label(PAGES["overview"][2]).classes(
                            "ts-topbar-caption"
                        )
                with ui.row().classes("ts-topbar-actions"):
                    ui.label("已验证访问" if logout else "本地访问").classes(
                        "ts-access-chip"
                    )
                    ui.button(icon="refresh", on_click=refresh_all).props(
                        'flat round aria-label="刷新数据"'
                    ).tooltip("刷新工作区数据")
                    ui.button(icon="settings", on_click=settings).props(
                        'flat round aria-label="工作区设置"'
                    ).tooltip("工作区设置")
            with ui.column().classes("ts-content w-full"):
                for key in PAGES:
                    with ui.column().classes("ts-page") as panel:
                        pages[key] = panel
                        if key == "overview":
                            blocks[key] = OverviewBlock(
                                state, edit_task, navigate, new_task
                            )
                        elif key in {"signer", "monitor"}:
                            blocks[key] = ConfigBlock(
                                key,
                                SIGNER_TEMPLATE
                                if key == "signer"
                                else MONITOR_TEMPLATE,
                                state,
                                refresh_all,
                                goto_records,
                            )
                        elif key == "users":
                            blocks[key] = UserBlock(state)
                        elif key == "records":
                            blocks[key] = RecordBlock(state)
                        else:
                            blocks[key] = LogBlock(
                                state, lambda: active["page"] == "logs"
                            )
                with ui.row().classes("w-full justify-between mt-2"):
                    ui.label("TG Signer 管理控制台").classes("ts-muted")
                    refreshed = ui.label("").classes("ts-muted")
    navigate("overview")
    refresh_all()


def _auth_gate(root, auth_code: str, on_success: Callable[[], None]) -> None:
    with root, ui.element("div").classes("ts-login"):
        with ui.element("section").classes("ts-login-story"):
            brand()
            with ui.column().classes("ts-login-copy"):
                ui.label("管理你的任务，\n让签到井然有序。").classes(
                    "ts-login-heading whitespace-pre-line"
                )
                ui.label(
                    "从任务配置到执行记录，一个安静、清晰的 Telegram 管理工作区。"
                ).classes("ts-login-lead")
                for icon, text in [
                    ("event_available", "统一管理签到与监控配置"),
                    ("history", "随时查阅账号与历史记录"),
                    ("terminal", "清晰查看每一次执行日志"),
                ]:
                    with ui.row().classes("ts-login-feature"):
                        ui.icon(icon)
                        ui.label(text)
            ui.label(f"TG SIGNER  /  v{__version__}").classes("ts-login-footer")
        with ui.element("section").classes("ts-login-form"):
            with ui.column().classes("ts-panel ts-login-card"):
                with ui.column().classes("gap-2"):
                    ui.label("欢迎回来").classes("ts-login-welcome")
                    ui.label("输入访问码，进入你的任务工作台。").classes("ts-muted")
                code_input = (
                    ui.input(
                        label="访问码",
                        placeholder="请输入访问码",
                        password=True,
                        password_toggle_button=True,
                    )
                    .props("outlined")
                    .classes("w-full")
                )
                status = ui.label("").classes("ts-login-error").props('role="alert"')

                def verify() -> None:
                    peer = ui.context.client.ip or "unknown"
                    if remaining := LOGIN_LIMITER.remaining(peer):
                        status.set_text(f"尝试次数过多，请 {remaining} 秒后重试")
                        return
                    code = (code_input.value or "").strip()
                    if not code:
                        status.set_text("请输入访问码")
                        return
                    if not secrets.compare_digest(code.encode(), auth_code.encode()):
                        LOGIN_LIMITER.failed(peer)
                        status.set_text("访问码不正确，请重试")
                        code_input.set_value("")
                        return
                    LOGIN_LIMITER.succeeded(peer)
                    app.storage.user[AUTH_STORAGE_KEY] = create_session(auth_code)
                    on_success()

                code_input.on("keydown.enter", verify)
                ui.button("进入控制台", icon="arrow_forward", on_click=verify).props(
                    "unelevated"
                ).classes("ts-login-submit")
                with ui.row().classes("ts-login-lock w-full"):
                    ui.icon("lock_outline").classes("text-sm")
                    ui.label("访问验证保护你的管理工作区")


def build_ui(auth_code: str = None) -> None:
    ui.page_title("TG Signer · 管理控制台")
    apply_theme()
    root = ui.column().classes("ts-root gap-0")
    state = UIState(app.storage.user)
    auth_code = auth_code or (os.environ.get(AUTH_CODE_ENV) or "").strip()
    if isinstance(app.storage.user.get(AUTH_STORAGE_KEY), str):
        app.storage.user.pop(AUTH_STORAGE_KEY, None)
    state.authorized = lambda: not auth_code or session_valid(
        app.storage.user.get(AUTH_STORAGE_KEY), auth_code
    )

    def logout() -> None:
        app.storage.user.pop(AUTH_STORAGE_KEY, None)
        root.clear()
        _auth_gate(root, auth_code, render_dashboard)

    def render_dashboard() -> None:
        root.clear()
        _build_dashboard(root, state, logout if auth_code else None)
        if auth_code:
            with root:
                ui.timer(30, lambda: logout() if not state.authorized() else None)

    if state.authorized():
        render_dashboard()
    else:
        _auth_gate(root, auth_code, render_dashboard)


def main(
    host: str = None,
    port: int = None,
    storage_secret: str = None,
    ssl_certfile: str = None,
    ssl_keyfile: str = None,
) -> None:
    import ipaddress

    host = host or "127.0.0.1"
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host.lower() == "localhost"
    if not local and not (os.environ.get(AUTH_CODE_ENV) or "").strip():
        raise ValueError("公网监听需要设置 WebUI 访问码")
    ui.run(
        build_ui,
        title="TG Signer · 管理控制台",
        favicon="⚙️",
        reload=False,
        host=host,
        port=port,
        show=False,
        storage_secret=storage_secret or os.urandom(10).hex(),
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
        session_middleware_kwargs={
            "https_only": bool(ssl_certfile)
            or os.environ.get("TG_SIGNER_GUI_HTTPS_ONLY") == "1"
        },
    )
