import copy
import csv
import io
import json
from datetime import datetime
from typing import Callable

from nicegui import ui
from pydantic import TypeAdapter

from tg_signer.sign_record_store import SignRecordStore
from tg_signer.webui.data import (
    CONFIG_META,
    ConfigKind,
    config_activation_status,
    delete_config,
    list_log_files,
    list_task_names,
    load_config,
    load_dashboard,
    load_logs,
    load_sign_records,
    load_user_infos,
    record_rows,
    save_config,
)
from tg_signer.webui.interactive import InteractiveSignerConfig
from tg_signer.webui.schema_utils import clean_schema
from tg_signer.webui.state import UIState


def notify_error(exc: Exception) -> None:
    ui.notify(str(exc), type="negative")


def page_heading(title: str, description: str, icon: str) -> None:
    with ui.row().classes("ts-page-heading"):
        with ui.column().classes("gap-0"):
            ui.label(title).classes("ts-heading").props("role=heading aria-level=1")
            ui.label(description).classes("ts-description")
        ui.icon(icon).classes("text-3xl text-slate-300")


def empty_state(title: str, description: str, icon: str = "inbox") -> None:
    with ui.column().classes("ts-empty"):
        ui.icon(icon).classes("ts-empty-icon")
        ui.label(title).classes("ts-empty-title")
        ui.label(description).classes("ts-muted")


class OverviewBlock:
    def __init__(
        self,
        state: UIState,
        edit_task: Callable[[str], None],
        navigate: Callable[[str], None],
        new_task: Callable[[], None],
    ):
        self.state = state
        self.edit_task = edit_task
        hour = datetime.now().hour
        greeting = (
            "早上好" if 5 <= hour < 12 else "下午好" if 12 <= hour < 18 else "晚上好"
        )
        page_heading(
            f"{greeting}，欢迎来到工作台",
            "在一个清晰的工作区，管理任务、账号与每一次签到记录。",
            "space_dashboard",
        )
        self.metrics = []
        with ui.element("div").classes("ts-metrics"):
            for label, icon, color, background in [
                ("签到配置", "event_available", "#168b76", "#edf7f2"),
                ("监控配置", "radar", "#557eb8", "#eef3fb"),
                ("缓存账号", "person_outline", "#9277b7", "#f3eff9"),
                ("累计签到记录", "history", "#b28b4d", "#fcf5e9"),
            ]:
                with ui.column().classes("ts-panel ts-metric"):
                    with ui.row().classes("w-full justify-between items-center"):
                        ui.label(label).classes("ts-metric-label")
                        with (
                            ui.element("div")
                            .classes("ts-metric-icon")
                            .style(f"color: {color}; background: {background}")
                        ):
                            ui.icon(icon).classes("text-xl")
                    self.metrics.append(ui.label("—").classes("ts-metric-value"))

        with ui.element("div").classes("ts-overview-grid"):
            with ui.column().classes("ts-panel"):
                with ui.row().classes("ts-panel-header"):
                    ui.label("记录趋势").classes("ts-panel-title")
                    ui.label("最近 14 天").classes("ts-pill")
                self.chart = ui.echart(
                    {
                        "grid": {"left": 28, "right": 8, "top": 16, "bottom": 26},
                        "tooltip": {"trigger": "axis"},
                        "xAxis": {
                            "type": "category",
                            "data": [],
                            "axisLine": {"lineStyle": {"color": "#e9eef3"}},
                            "axisTick": {"show": False},
                            "axisLabel": {"color": "#90a0ae", "fontSize": 10},
                        },
                        "yAxis": {
                            "type": "value",
                            "minInterval": 1,
                            "axisLabel": {"color": "#90a0ae", "fontSize": 10},
                            "splitLine": {"lineStyle": {"color": "#f0f3f6"}},
                        },
                        "series": [
                            {
                                "name": "签到记录",
                                "type": "bar",
                                "data": [],
                                "barMaxWidth": 20,
                                "itemStyle": {
                                    "color": "#69b5a3",
                                    "borderRadius": [4, 4, 0, 0],
                                },
                            }
                        ],
                    }
                ).classes("ts-chart")
            with ui.column().classes("ts-panel"):
                with ui.row().classes("ts-panel-header"):
                    ui.label("最近记录").classes("ts-panel-title")
                    ui.button("查看全部", on_click=lambda: navigate("records")).props(
                        "flat dense size=sm"
                    )
                self.recent = ui.column().classes("w-full gap-0")

        with ui.column().classes("ts-panel"):
            with ui.row().classes("ts-panel-header"):
                ui.label("我的签到配置").classes("ts-panel-title")
                ui.button("新建配置", icon="add", on_click=new_task).props("unelevated")
            self.tasks = ui.column().classes("w-full gap-0")

        with ui.element("div").classes("ts-quick-actions"):
            for label, icon, callback in [
                ("打开配置向导", "tune", new_task),
                ("查看账号与聊天", "people_outline", lambda: navigate("users")),
                ("查看运行日志", "terminal", lambda: navigate("logs")),
            ]:
                ui.button(label, icon=icon, color=None, on_click=callback).classes(
                    "ts-quick-button"
                ).props("flat")

    def refresh(self) -> None:
        self.state.require_access()
        data = load_dashboard(self.state.workdir)
        values = [
            len(data.tasks),
            data.monitor_count,
            data.user_count,
            len(data.records),
        ]
        for label, value in zip(self.metrics, values, strict=True):
            label.set_text(f"{value:,}")
        self.chart.options["xAxis"]["data"] = [day[5:] for day, _ in data.activity]
        self.chart.options["series"][0]["data"] = [count for _, count in data.activity]
        self.chart.update()
        self.recent.clear()
        with self.recent:
            if not data.records:
                empty_state(
                    "还没有签到记录", "任务执行后，记录会显示在这里。", "history"
                )
            for row in data.records[:4]:
                with ui.row().classes("ts-activity-row"):
                    ui.icon("event_note").classes("ts-activity-icon")
                    with ui.column().classes("ts-activity-main"):
                        ui.label(row["task"]).classes("ts-activity-task")
                        ui.label(f"账号 {row['user']}").classes("ts-muted")
                    with ui.column().classes("gap-1"):
                        ui.label(row["date"]).classes("ts-activity-date")
                        ui.label(row["time"]).classes("ts-activity-date")
        self.tasks.clear()
        with self.tasks:
            if not data.tasks:
                empty_state(
                    "从第一个签到任务开始", "使用配置向导，选择聊天并添加签到动作。"
                )
            for task in data.tasks:
                with ui.row().classes("ts-activity-row"):
                    ui.icon("task_alt" if task.valid else "warning_amber").classes(
                        "ts-activity-icon"
                    )
                    with ui.column().classes("ts-activity-main"):
                        ui.label(task.name).classes("ts-activity-task")
                        ui.label(
                            f"{task.chat_count} 个聊天 · {task.action_count} 个动作"
                            if task.valid
                            else "配置缺失或格式有误，请检查后保存"
                        ).classes("ts-muted")
                        ui.label(task.runtime).classes("ts-muted")
                    ui.label(task.schedule if task.valid else "待修复").classes(
                        "ts-pill" if task.valid else "ts-pill ts-pill-amber"
                    ).tooltip("配置中的签到计划")
                    ui.button(
                        "编辑",
                        icon="edit",
                        on_click=lambda _, name=task.name: self.edit_task(name),
                    ).props("flat dense size=sm")


class ConfigBlock:
    def __init__(
        self,
        kind: ConfigKind,
        template: dict,
        state: UIState,
        on_saved: Callable[[], None],
        goto_records: Callable[[str], None],
    ):
        self.kind, self.template, self.state = kind, template, state
        self.on_saved, self.goto_records = on_saved, goto_records
        self.selected_name = ""
        self.baseline = ""
        title = "签到配置" if kind == "signer" else "监控配置"
        page_heading(
            title,
            "组织聊天、动作与执行时间，使用向导或直接编辑配置。"
            if kind == "signer"
            else "管理消息匹配、自动回复与转发规则。",
            "event_available" if kind == "signer" else "radar",
        )
        with ui.element("div").classes("ts-config-grid"):
            with ui.column().classes("ts-panel ts-task-list"):
                with ui.row().classes("ts-panel-header ts-task-list-header"):
                    ui.label("配置列表").classes("ts-panel-title")
                    self.count = ui.label("0").classes("ts-pill")
                ui.button("新建配置", icon="add", on_click=self.new_config).props(
                    "outline"
                ).classes("w-full")
                self.task_list = ui.column().classes("w-full gap-1 ts-task-list-items")
            with ui.column().classes("ts-panel ts-editor-card"):
                with ui.row().classes("ts-panel-header"):
                    with ui.column().classes("gap-1"):
                        self.editor_title = ui.label("新建配置").classes(
                            "ts-panel-title"
                        )
                        self.status = ui.label("未保存草稿").classes("ts-muted")
                    if kind == "signer":
                        ui.button(
                            "配置向导", icon="tune", on_click=self.open_wizard
                        ).props("outline")
                with ui.row().classes("ts-config-tools"):
                    self.name_input = ui.input(
                        label="配置名称", placeholder="例如 my_sign"
                    ).props("outlined dense")
                    ui.button(
                        "使用示例", icon="auto_awesome", on_click=self.fill_template
                    ).props("flat")
                ui.label("高级编辑器 · 修改后请保存配置").classes("ts-muted")
                schema = clean_schema(
                    TypeAdapter(CONFIG_META[kind][1] | None).json_schema()
                )
                self.editor = ui.json_editor(
                    {"content": {"json": copy.deepcopy(template)}},
                    schema=schema,
                    on_change=self.mark_changed,
                ).classes("ts-json-editor")
                with ui.row().classes("ts-editor-footer"):
                    with ui.row().classes("gap-1"):
                        ui.button(
                            "重新加载", icon="refresh", on_click=self.reload
                        ).props("flat")
                        self.delete_button = ui.button(
                            "删除",
                            icon="delete_outline",
                            color="negative",
                            on_click=self.confirm_delete,
                        ).props("flat")
                        self.delete_button.disable()
                        if kind == "signer":
                            ui.button(
                                "签到记录", icon="history", on_click=self.show_records
                            ).props("flat")
                    ui.button("保存配置", icon="save", on_click=self.save).props(
                        "unelevated"
                    )

    def payload(self) -> dict:
        content = self.editor.properties["content"]
        return (
            content["json"]
            if "json" in content
            else json.loads(content.get("text", "{}"))
        )

    def mark_changed(self, event) -> None:
        self.editor.properties["content"] = event.content
        try:
            current = json.dumps(self.payload(), sort_keys=True)
            changed = current != self.baseline
        except (ValueError, TypeError):
            changed = True
        self.status.set_text("有未保存的修改" if changed else "已加载 · 可以编辑")

    def refresh(self) -> None:
        self.state.require_access()
        names = list_task_names(self.kind, self.state.workdir)
        self.count.set_text(str(len(names)))
        self.task_list.clear()
        with self.task_list:
            if not names:
                ui.label("暂无配置，点击上方新建").classes("ts-muted p-2")
            for name in names:
                button = (
                    ui.button(
                        name,
                        icon="description",
                        color=None,
                        on_click=lambda _, n=name: self.load(n),
                    )
                    .props("flat")
                    .classes("ts-task-button")
                )
                if name == self.selected_name:
                    button.classes(add="is-selected")
        if self.selected_name:
            try:
                payload = self.payload()
                if json.dumps(payload, sort_keys=True) == self.baseline:
                    self.status.set_text(
                        config_activation_status(
                            self.kind, self.selected_name, payload, self.state.workdir
                        )
                    )
            except (ValueError, TypeError):
                pass

    def load(self, name: str) -> None:
        try:
            self.state.require_access()
            entry = load_config(self.kind, name, self.state.workdir)
            self.selected_name = name
            self.name_input.set_value(name)
            self.editor.properties["content"] = {"json": entry.payload}
            self.baseline = json.dumps(entry.payload, sort_keys=True)
            self.editor.update()
            self.editor_title.set_text(name)
            self.status.set_text("已加载 · 可以编辑")
            self.delete_button.enable()
            self.refresh()
        except Exception as exc:
            notify_error(exc)

    def reload(self) -> None:
        if self.selected_name:
            self.load(self.selected_name)
        else:
            self.fill_template()

    def fill_template(self) -> None:
        self.editor.properties["content"] = {"json": copy.deepcopy(self.template)}
        self.editor.update()
        self.status.set_text("示例已加载 · 尚未保存")

    def new_config(self) -> None:
        self.selected_name = ""
        self.name_input.set_value("")
        self.editor_title.set_text("新建配置")
        self.delete_button.disable()
        self.baseline = ""
        self.fill_template()
        self.refresh()

    def save(self) -> None:
        name = (self.name_input.value or "").strip()
        if not name:
            ui.notify("请填写配置名称", type="warning")
            return
        try:
            self.state.require_access()
            save_config(self.kind, name, self.payload(), self.state.workdir)
            self.load(name)
            self.on_saved()
            ui.notify("配置已保存", type="positive")
        except Exception as exc:
            notify_error(exc)

    def confirm_delete(self) -> None:
        name = self.selected_name
        if not name:
            return
        with ui.dialog() as dialog, ui.card().classes("ts-dialog w-full max-w-md"):
            ui.icon("delete_outline").classes("text-3xl text-red-400")
            ui.label("删除配置？").classes("ts-panel-title")
            ui.label(f"即将删除 {name} 的配置文件，历史签到记录会保留。").classes(
                "ts-muted"
            )

            def remove() -> None:
                try:
                    self.state.require_access()
                    delete_config(self.kind, name, self.state.workdir)
                    self.new_config()
                    self.on_saved()
                    dialog.close()
                    ui.notify("配置已删除", type="positive")
                except Exception as exc:
                    notify_error(exc)

            with ui.row().classes("w-full justify-end mt-3"):
                ui.button("取消", on_click=dialog.close).props("flat")
                ui.button("确认删除", color="negative", on_click=remove).props(
                    "unelevated"
                )
        dialog.open()

    def show_records(self) -> None:
        self.goto_records(self.selected_name)

    def open_wizard(self, *, new: bool = False) -> None:
        try:
            initial = None if new else self.payload()
        except (ValueError, TypeError):
            ui.notify("请先修正配置内容，再打开向导", type="warning")
            return

        def completed() -> None:
            self.load(wizard.task_name)
            self.on_saved()

        wizard = InteractiveSignerConfig(
            self.state.workdir,
            completed,
            initial_config=initial,
            initial_name="" if new else self.name_input.value or "",
            authorize=self.state.require_access,
        )
        wizard.open()


class UserBlock:
    def __init__(self, state: UIState):
        self.state = state
        page_heading(
            "账号与聊天",
            "查看缓存的账号资料，快速找到任务需要的聊天 ID。",
            "people_outline",
        )
        self.container = ui.column().classes("w-full gap-5")

    def refresh(self) -> None:
        self.state.require_access()
        self.container.clear()
        entries = load_user_infos(self.state.workdir)
        with self.container:
            if not entries:
                with ui.column().classes("ts-panel"):
                    empty_state(
                        "还没有账号资料",
                        "通过 CLI 登录账号后，可在这里查看账号和最近聊天。",
                        "person_outline",
                    )
            for entry in entries:
                name = (
                    " ".join(
                        filter(
                            None,
                            [entry.data.get("first_name"), entry.data.get("last_name")],
                        )
                    )
                    or entry.user_id
                )
                with ui.column().classes("ts-panel ts-user-card"):
                    with ui.row().classes("ts-user-header"):
                        with ui.avatar(color=None, text_color=None).classes(
                            "ts-user-avatar"
                        ):
                            ui.label(name[:1].upper())
                        with ui.column().classes("gap-1 flex-1"):
                            ui.label(name).classes("ts-panel-title")
                            username = entry.data.get("username")
                            ui.label(
                                f"@{username} · {entry.user_id}"
                                if username
                                else entry.user_id
                            ).classes("ts-muted")
                        ui.label("缓存资料").classes("ts-pill")
                    with ui.column().classes("ts-user-body gap-3"):
                        ui.label(f"最近聊天 · {len(entry.latest_chats or [])}").classes(
                            "ts-panel-title"
                        )
                        if entry.latest_chats:
                            rows = [
                                {
                                    "id": chat.get("id"),
                                    "title": chat.get("title")
                                    or chat.get("first_name")
                                    or "未命名聊天",
                                    "type": str(chat.get("type", "")),
                                    "username": "@" + chat["username"]
                                    if chat.get("username")
                                    else "—",
                                }
                                for chat in entry.latest_chats
                            ]
                            ui.table(
                                columns=[
                                    {
                                        "name": key,
                                        "label": label,
                                        "field": key,
                                        "align": "left",
                                        "sortable": True,
                                    }
                                    for key, label in [
                                        ("title", "聊天名称"),
                                        ("id", "聊天 ID"),
                                        ("type", "类型"),
                                        ("username", "用户名"),
                                    ]
                                ],
                                rows=rows,
                                row_key="id",
                                pagination=8,
                            ).classes("ts-table").props("flat")
                        else:
                            ui.label(
                                "尚未缓存最近聊天，请通过 CLI 登录并刷新聊天列表。"
                            ).classes("ts-muted")
                        with ui.expansion(
                            "查看账户详细资料", icon="data_object"
                        ).classes("ts-user-detail"):
                            ui.code(
                                json.dumps(entry.data, ensure_ascii=False, indent=2),
                                language="json",
                            ).classes("w-full")


class RecordBlock:
    def __init__(self, state: UIState):
        self.state = state
        page_heading(
            "签到记录", "按任务、账号或日期检索历史记录，随时导出保存。", "history"
        )
        self.rows = []
        with ui.column().classes("ts-panel"):
            with ui.row().classes("ts-toolbar"):
                self.search = (
                    ui.input("搜索任务、账号或日期", on_change=self.filter_changed)
                    .props("outlined dense clearable debounce=200")
                    .classes("ts-search")
                )
                self.count = ui.label("—").classes("ts-pill")
                ui.button("导出 CSV", icon="download", on_click=self.export).props(
                    "outline"
                )
            self.table = (
                ui.table(
                    columns=[
                        {
                            "name": key,
                            "label": label,
                            "field": key,
                            "align": "left",
                            "sortable": True,
                        }
                        for key, label in [
                            ("date", "日期"),
                            ("time", "记录时间"),
                            ("task", "任务"),
                            ("user", "账号 ID"),
                        ]
                    ],
                    rows=[],
                    row_key="id",
                    pagination={
                        "rowsPerPage": 15,
                        "sortBy": "date",
                        "descending": True,
                    },
                )
                .classes("ts-table")
                .props(
                    'flat no-data-label="暂无匹配的签到记录" rows-per-page-label="每页行数"'
                )
            )

        with ui.expansion("最近执行结果", icon="fact_check").classes("ts-panel w-full"):
            ui.label(
                "记录每轮动作的完成、失败和中断情况；旧版历史记录保留原格式。"
            ).classes("ts-muted")
            self.run_table = (
                ui.table(
                    columns=[
                        {"name": key, "label": label, "field": key, "align": "left"}
                        for key, label in [
                            ("task_name", "任务"),
                            ("started_at", "开始时间"),
                            ("result", "结果"),
                            ("summary", "动作结果"),
                        ]
                    ],
                    rows=[],
                    row_key="id",
                    pagination=10,
                )
                .classes("ts-table")
                .props('flat no-data-label="尚无新版执行结果"')
            )

    def filter_changed(self, event) -> None:
        self.state.record_filter = event.value or ""
        self.table.filter = self.state.record_filter

    def filter_task(self, task: str) -> None:
        self.search.set_value(task)
        self.state.record_filter = task
        self.table.filter = task

    def refresh(self) -> None:
        self.state.require_access()
        self.rows = record_rows(load_sign_records(self.state.workdir))
        self.table.rows = self.rows
        self.table.update()
        self.count.set_text(f"{len(self.rows):,} 条记录")
        store = SignRecordStore(self.state.workdir)
        runs = store.recent_runs(limit=30) if store.db_path.is_file() else []
        labels = {
            "success": "完成",
            "partial": "部分完成",
            "failed": "失败",
            "interrupted": "中断",
            "running": "执行中",
        }
        self.run_table.rows = [
            {
                **run,
                "result": labels.get(run["status"], run["status"]),
                "summary": " · ".join(
                    f"{detail['chat']}：{labels.get(detail['status'], detail['status'])}"
                    for detail in run["details"]
                ),
            }
            for run in runs
        ]
        self.run_table.update()

    def export(self) -> None:
        self.state.require_access()
        keyword = self.state.record_filter.casefold()
        rows = [
            row for row in self.rows if keyword in " ".join(row.values()).casefold()
        ]
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["日期", "记录时间", "任务", "账号 ID"])
        writer.writerows(
            [row[key] for key in ("date", "time", "task", "user")] for row in rows
        )
        ui.download.content(
            buffer.getvalue().encode("utf-8-sig"),
            f"sign-records-{datetime.now():%Y%m%d}.csv",
        )


class LogBlock:
    def __init__(self, state: UIState, is_visible: Callable[[], bool]):
        self.state, self.is_visible = state, is_visible
        page_heading("运行日志", "浏览最新日志，按级别筛选并定位执行问题。", "terminal")
        with ui.column().classes("ts-panel ts-log-panel gap-0"):
            with ui.row().classes("ts-log-toolbar items-center"):
                self.file = (
                    ui.select(
                        options={str(state.log_path): state.log_path.name},
                        label="日志文件",
                        value=str(state.log_path),
                        on_change=self.file_changed,
                    )
                    .props("outlined dense")
                    .classes("flex-1")
                )
                self.level = ui.select(
                    ["全部级别", "INFO", "WARNING", "ERROR"],
                    value="全部级别",
                    label="日志级别",
                    on_change=self.refresh,
                ).props("outlined dense")
                self.search = (
                    ui.input("搜索日志", on_change=self.refresh)
                    .props("outlined dense clearable debounce=250")
                    .classes("flex-1")
                )
            self.terminal = ui.column().classes("ts-terminal")
            with ui.row().classes("ts-log-footer"):
                self.status = ui.label("等待加载").classes("ts-muted")
                with ui.row().classes("items-center gap-3"):
                    self.live = ui.switch("自动刷新", value=False)
                    ui.button("刷新日志", icon="refresh", on_click=self.refresh).props(
                        "flat dense"
                    )
        with ui.expansion("日志读取设置", icon="tune").classes("w-full text-slate-500"):
            with ui.row().classes("ts-toolbar py-3"):
                self.path = (
                    ui.input("文件路径", value=str(state.log_path))
                    .props("outlined dense")
                    .classes("flex-1")
                )
                self.limit = (
                    ui.number("显示行数", value=200, min=10, max=2000)
                    .props("outlined dense")
                    .classes("w-36")
                )
                ui.button("应用", on_click=self.apply_settings).props("outline")
        self.timer = ui.timer(3, self.tick)

    def tick(self) -> None:
        if self.state.authorized() and self.live.value and self.is_visible():
            self.refresh()

    def file_changed(self, event) -> None:
        if event.value:
            self.state.set_log_path(event.value)
            self.path.set_value(event.value)
            self.refresh()

    def apply_settings(self) -> None:
        try:
            self.state.log_limit = max(10, min(2000, int(self.limit.value or 200)))
            self.state.set_log_path(self.path.value or str(self.state.log_path))
            self.refresh()
        except (ValueError, TypeError) as exc:
            notify_error(exc)

    @staticmethod
    def severity(line: str) -> str:
        upper = line.upper()
        return "ERROR" if "ERROR" in upper else "WARNING" if "WARN" in upper else "INFO"

    def refresh(self) -> None:
        self.state.require_access()
        options = {str(path): path.name for path in list_log_files()}
        options.setdefault(str(self.state.log_path), self.state.log_path.name)
        self.file.options = options
        self.file.value = str(self.state.log_path)
        self.file.update()
        path, lines = load_logs(self.state.log_limit, self.state.log_path)
        level = self.level.value
        keyword = (self.search.value or "").casefold()
        filtered = [
            line
            for line in lines
            if (level == "全部级别" or self.severity(line) == level)
            and keyword in line.casefold()
        ]
        self.terminal.clear()
        with self.terminal:
            if not filtered:
                ui.label(
                    "暂无匹配的日志"
                    if lines
                    else "尚未找到日志文件，任务执行后可在这里查看。"
                ).classes("ts-log-line text-slate-400")
            for line in filtered:
                color = {"ERROR": "error", "WARNING": "warn", "INFO": "info"}[
                    self.severity(line)
                ]
                ui.label(line).classes(f"ts-log-line ts-log-{color}")
        self.status.set_text(
            f"{path.name} · {len(filtered)} 行 · 更新于 {datetime.now():%H:%M:%S}"
        )
