from nicegui import ui

THEME_CSS = """
:root {
  --ts-bg: #f4f6f9;
  --ts-surface: #ffffff;
  --ts-ink: #172b3a;
  --ts-muted: #7b8998;
  --ts-border: #e7ecf1;
  --ts-accent: #168b76;
  --ts-sidebar: #152b38;
}
body {
  margin: 0;
  background: var(--ts-bg);
  color: var(--ts-ink);
  font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI',
    'PingFang SC', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', sans-serif;
  font-size: 14px;
  -webkit-font-smoothing: antialiased;
}
.nicegui-content { padding: 0 !important; gap: 0 !important; }
.q-page { min-height: 100vh; }
.q-btn { text-transform: none; border-radius: 9px; font-weight: 550; }
.q-btn--rectangle { padding: 8px 15px; }
.q-btn--round { border-radius: 9px; }
.q-field--outlined .q-field__control { border-radius: 10px; background: #fff; }
.q-field--outlined .q-field__control:before { border-color: #dfe6ec; }
.q-field__label { color: #80909e; }
.q-table__container { border-radius: 12px; box-shadow: none; max-width: 100%; }
.q-table th {
  background: #f7f9fb; color: #738190; font-weight: 600;
  border-color: var(--ts-border); height: 46px;
}
.q-table td { height: 54px; border-color: #f0f3f6; color: #405364; }
.q-table__bottom { border-top: 1px solid var(--ts-border); color: #7b8998; }
.q-tooltip { border-radius: 7px; background: #213746; }
.ts-root, .ts-shell { width: 100%; min-height: 100dvh; }
.ts-sidebar {
  position: fixed; inset: 0 auto 0 0; width: 248px; z-index: 100;
  background: var(--ts-sidebar); color: #b4c4d0;
  display: flex; flex-direction: column; padding: 28px 18px 18px;
}
.ts-brand { gap: 12px; align-items: center; padding: 0 12px; }
.ts-brand-mark {
  display: flex; align-items: center; justify-content: center;
  width: 40px; height: 40px; border-radius: 12px;
  background: #168b76; color: #fff; flex-shrink: 0;
}
.ts-brand-name { font-size: 20px; letter-spacing: -.5px; font-weight: 700; color: #fff; }
.ts-brand-caption { color: #8298a8; font-size: 11px; letter-spacing: 1.5px; }
.ts-nav-heading { margin: 35px 14px 12px; font-size: 11px; color: #78909f; }
.ts-nav { width: 100%; gap: 7px; }
.ts-nav-button { width: 100%; min-height: 46px; color: #aebfcb !important; padding: 10px 15px; }
.ts-nav-button .q-btn__content { justify-content: flex-start; gap: 12px; }
.ts-nav-button .q-icon { font-size: 20px; opacity: .85; }
.ts-nav-button:hover { color: #fff !important; background: #203c4b; }
.ts-nav-button.is-active { background: #214a4b; color: #b9efdb !important; }
.ts-nav-button.is-active .q-icon { opacity: 1; color: #69d9b7; }
.ts-sidebar-footer { margin-top: auto; padding: 18px 10px 0; width: 100%; }
.ts-sidebar-rule { height: 1px; width: 100%; background: #2d4553; margin-bottom: 16px; }
.ts-sidebar-footnote { font-size: 11px; color: #77909f; margin-top: 14px; }
.ts-main { margin-left: 248px; width: calc(100% - 248px); min-width: 0; }
.ts-topbar {
  position: sticky; top: 0; z-index: 30; min-height: 78px;
  background: rgba(255,255,255,.96); backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--ts-border);
  padding: 16px 34px; display: flex; align-items: center;
  justify-content: space-between; gap: 16px;
}
.ts-topbar-title { font-size: 17px; font-weight: 650; color: #213746; }
.ts-topbar-caption { color: var(--ts-muted); font-size: 12px; margin-top: 3px; }
.ts-topbar-actions { gap: 10px; align-items: center; flex-shrink: 0; }
.ts-access-chip { font-size: 12px; color: #658276; background: #edf7f2; padding: 7px 11px; border-radius: 8px; }
.ts-content { padding: 30px 34px 36px; max-width: 1600px; margin: 0 auto; }
.ts-page { width: 100%; min-width: 0; gap: 22px; }
.ts-page-heading { width: 100%; align-items: flex-end; justify-content: space-between; gap: 16px; }
.ts-heading { font-size: 27px; font-weight: 700; letter-spacing: -.7px; line-height: 1.35; }
.ts-description { font-size: 13px; color: var(--ts-muted); line-height: 1.8; margin-top: 7px; }
.ts-eyebrow { color: #8b9ba7; font-size: 11px; letter-spacing: 1.8px; }
.ts-panel {
  background: #fff; border: 1px solid var(--ts-border); border-radius: 15px;
  box-shadow: 0 3px 18px #1d374a03; padding: 24px;
  width: 100%; min-width: 0; gap: 18px;
}
.ts-panel-header { width: 100%; align-items: center; justify-content: space-between; gap: 14px; }
.ts-panel-title { font-size: 15px; font-weight: 650; }
.ts-muted { color: var(--ts-muted); font-size: 12px; line-height: 1.7; }
.ts-metrics { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 18px; width: 100%; }
.ts-metric { padding: 21px 23px; gap: 14px; }
.ts-metric-icon { width: 42px; height: 42px; border-radius: 12px; display: flex; align-items: center; justify-content: center; }
.ts-metric-value { font-size: 30px; line-height: 1.15; font-weight: 700; letter-spacing: -.7px; }
.ts-metric-label { font-size: 12px; color: #7b8998; }
.ts-overview-grid { display: grid; grid-template-columns: minmax(0,1.55fr) minmax(0,1fr); gap: 22px; width: 100%; }
.ts-chart { width: 100%; height: 230px; }
.ts-activity-row { width: 100%; align-items: center; padding: 13px 0; gap: 13px; border-bottom: 1px solid #f0f3f6; }
.ts-activity-row:last-child { border-bottom: 0; }
.ts-activity-icon { background: #edf6f2; color: #168b76; border-radius: 10px; padding: 10px; }
.ts-activity-main { min-width: 0; flex: 1; gap: 3px; }
.ts-activity-task { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.ts-activity-date { font-size: 11px; color: #93a0ad; text-align: right; }
.ts-pill { padding: 5px 9px; border-radius: 6px; font-size: 11px; color: #60778a; background: #f0f4f7; }
.ts-pill-green { color: #19866c; background: #eaf6ef; }
.ts-pill-amber { color: #a87627; background: #fff5e5; }
.ts-quick-actions { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); width: 100%; gap: 16px; }
.ts-quick-button { justify-content: flex-start; border: 1px solid var(--ts-border); padding: 19px; background: white; color: #4e6577 !important; min-height: 65px; }
.ts-quick-button .q-btn__content { justify-content: flex-start; gap: 12px; }
.ts-config-grid { display: grid; grid-template-columns: 230px minmax(0,1fr); gap: 20px; width: 100%; }
.ts-task-list { padding: 18px 12px; align-self: start; min-height: 230px; gap: 10px; }
.ts-task-list-header { padding: 4px 8px 12px; width: 100%; }
.ts-task-button { width: 100%; color: #687b8b !important; min-height: 43px; padding: 10px 12px; }
.ts-task-button .q-btn__content { justify-content: flex-start; gap: 9px; overflow: hidden; text-overflow: ellipsis; }
.ts-task-button.is-selected { color: #137f68 !important; background: #edf7f2; }
.ts-config-tools { display: flex; gap: 12px; width: 100%; flex-wrap: wrap; }
.ts-config-tools .q-field { flex: 1; min-width: 180px; }
.ts-editor-card { gap: 20px; }
.ts-editor-footer { width: 100%; align-items: center; justify-content: space-between; gap: 12px; border-top: 1px solid var(--ts-border); padding-top: 18px; flex-wrap: wrap; }
.ts-json-editor { width: 100%; min-width: 0; --jse-theme-color: #168b76; --jse-theme-color-highlight: #edf7f2; --jse-font-family: inherit; --jse-font-family-mono: 'SFMono-Regular', Consolas, monospace; }
.ts-json-editor .jse-main { min-height: 360px; border-radius: 10px; overflow: hidden; }
.ts-json-editor .jse-menu { min-height: 34px; }
.ts-empty { width: 100%; min-height: 190px; align-items: center; justify-content: center; text-align: center; gap: 10px; color: #91a1af; padding: 26px 18px; }
.ts-empty-icon { font-size: 36px; color: #b9c8d3; background: #f1f5f8; padding: 17px; border-radius: 18px; }
.ts-empty-title { color: #5e7586; font-size: 14px; font-weight: 600; }
.ts-toolbar { width: 100%; gap: 12px; align-items: center; flex-wrap: wrap; }
.ts-search { flex: 1; min-width: 200px; }
.ts-table { width: 100%; min-width: 0; }
.ts-user-card { padding: 0; overflow: hidden; }
.ts-user-header { padding: 24px; width: 100%; align-items: center; gap: 14px; }
.ts-user-avatar { background: #e6f1f2; color: #307e82; font-size: 20px; font-weight: 650; }
.ts-user-body { padding: 0 24px 24px; width: 100%; min-width: 0; }
.ts-user-detail { width: 100%; color: #8795a2; margin-top: 16px; border-top: 1px solid var(--ts-border); padding-top: 12px; }
.ts-user-detail .q-expansion-item__content { overflow: auto; max-width: 100%; }
.ts-log-panel { padding: 0; overflow: hidden; }
.ts-log-toolbar { padding: 20px 24px; width: 100%; gap: 14px; }
.ts-log-toolbar .q-field { min-width: 140px; }
.ts-terminal {
  background: #152735; color: #becdd9; padding: 18px 22px;
  width: 100%; min-height: 360px; max-height: 520px; overflow: auto;
  font-family: 'SFMono-Regular', Consolas, monospace; font-size: 12px;
  line-height: 1.9; display: flex; flex-direction: column; gap: 1px;
}
.ts-log-line { white-space: pre-wrap; overflow-wrap: anywhere; }
.ts-log-info { color: #a9c8de; }
.ts-log-warn { color: #f6cb88; }
.ts-log-error { color: #f5a6ac; }
.ts-log-footer { padding: 14px 24px; width: 100%; justify-content: space-between; align-items: center; gap: 10px; }
.ts-dialog { border-radius: 16px; padding: 26px; box-shadow: 0 20px 80px #12263626; }
.ts-wizard-grid { grid-template-columns: repeat(2,minmax(0,1fr)); }
.ts-dialog .q-card { border: 1px solid var(--ts-border); box-shadow: none; border-radius: 12px; }
.ts-dialog .q-scrollarea { min-height: 0; }
.ts-dialog .q-field { min-width: 0; }
.ts-mobile-only { display: none !important; }
.ts-backdrop { position: fixed; inset: 0; background: #14273566; z-index: 90; }
.ts-login {
  width: 100%; min-height: 100dvh; display: grid;
  grid-template-columns: minmax(0,1fr) minmax(0,1fr);
  background: #f8fafc;
}
.ts-login-story {
  background: #152b38; color: #d3e0e8; padding: 50px 12%;
  display: flex; flex-direction: column; justify-content: space-between;
  position: relative; overflow: hidden; min-height: 100dvh;
}
.ts-login-story:after {
  content: ''; width: 420px; height: 420px; border-radius: 50%;
  position: absolute; right: -180px; top: 20%;
  background: radial-gradient(circle, #278b7840 0, transparent 68%);
  pointer-events: none;
}
.ts-login-copy { gap: 25px; margin: 65px 0; z-index: 1; }
.ts-login-heading { font-size: 40px; font-weight: 650; line-height: 1.5; letter-spacing: -1px; color: #fff; }
.ts-login-lead { color: #a1b7c6; line-height: 1.9; font-size: 14px; max-width: 350px; }
.ts-login-feature { align-items: center; gap: 12px; font-size: 13px; color: #adc5ce; }
.ts-login-feature .q-icon { color: #6ed4b2; font-size: 19px; }
.ts-login-footer { color: #73909f; font-size: 11px; letter-spacing: .6px; }
.ts-login-form { display: flex; align-items: center; justify-content: center; padding: 45px; }
.ts-login-card { width: 100%; max-width: 400px; gap: 22px; padding: 38px; box-shadow: 0 12px 60px #18354708; }
.ts-login-welcome { font-size: 26px; font-weight: 700; letter-spacing: -.5px; }
.ts-login-card .q-field { width: 100%; }
.ts-login-submit { width: 100%; min-height: 46px; }
.ts-login-error { color: #c45b65; font-size: 12px; min-height: 18px; }
.ts-login-lock { color: #8b9ba8; font-size: 11px; align-items: center; gap: 7px; justify-content: center; }
@media (max-width: 1200px) {
  .ts-sidebar { width: 224px; padding-left: 14px; padding-right: 14px; }
  .ts-main { margin-left: 224px; width: calc(100% - 224px); }
  .ts-content { padding: 25px; }
  .ts-topbar { padding: 16px 25px; }
  .ts-metric { padding: 19px; }
  .ts-config-grid { grid-template-columns: 200px minmax(0,1fr); }
}
@media (max-width: 1023px) {
  .ts-sidebar { width: 248px; transform: translateX(-100%); visibility: hidden; transition: transform .2s ease, visibility .2s; }
  .ts-sidebar.ts-sidebar-open { transform: translateX(0); visibility: visible; }
  .ts-main { margin-left: 0; width: 100%; }
  .ts-mobile-only { display: inline-flex !important; }
  .ts-overview-grid { grid-template-columns: minmax(0,1fr); }
}
@media (max-width: 700px) {
  .ts-content { padding: 22px 16px; }
  .ts-topbar { padding: 13px 16px; min-height: 70px; }
  .ts-topbar-caption, .ts-access-chip { display: none; }
  .ts-topbar-actions { gap: 3px; }
  .ts-heading { font-size: 23px; }
  .ts-page { gap: 18px; }
  .ts-panel { padding: 18px; }
  .ts-metrics { grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px; }
  .ts-metric { padding: 17px; }
  .ts-metric-value { font-size: 26px; }
  .ts-metric-icon { width: 34px; height: 34px; border-radius: 9px; }
  .ts-quick-actions { grid-template-columns: minmax(0,1fr); gap: 10px; }
  .ts-quick-button { min-height: 52px; padding: 13px 17px; }
  .ts-config-grid { grid-template-columns: minmax(0,1fr); }
  .ts-task-list { min-height: 0; padding: 14px; }
  .ts-task-list-items { display: flex; flex-direction: row; flex-wrap: wrap; gap: 5px; }
  .ts-task-button { width: auto; min-height: 36px; }
  .ts-user-header, .ts-user-body { padding: 18px; }
  .ts-log-toolbar { padding: 16px; }
  .ts-log-panel { padding: 0; }
  .ts-terminal { padding: 15px; font-size: 11px; }
  .ts-log-footer { padding: 12px 16px; }
  .ts-dialog { padding: 18px; max-width: calc(100vw - 24px) !important; }
  .ts-wizard-grid { grid-template-columns: minmax(0,1fr) !important; }
  .ts-login { grid-template-columns: minmax(0,1fr); }
  .ts-login-story { min-height: 0; padding: 26px; }
  .ts-login-copy, .ts-login-footer { display: none; }
  .ts-login-form { padding: 36px 20px; align-items: flex-start; }
  .ts-login-card { padding: 27px; }
}
@media (prefers-reduced-motion: reduce) {
  .ts-sidebar { transition: none; }
}
"""


def apply_theme() -> None:
    ui.colors(primary="#168b76", secondary="#405364", negative="#c45b65")
    ui.add_css(THEME_CSS)
