from __future__ import annotations

import json
import os
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .supabase import DEFAULT_SUPABASE_TABLE, SupabaseError, fetch_dashboard_items


DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8765


def run_dashboard(
    host: str = DEFAULT_DASHBOARD_HOST,
    port: int = DEFAULT_DASHBOARD_PORT,
    supabase_url: str | None = None,
    supabase_key: str | None = None,
    table: str = DEFAULT_SUPABASE_TABLE,
    open_browser: bool = True,
) -> None:
    handler_class = _make_handler(
        supabase_url=supabase_url,
        supabase_key=supabase_key,
        table=table,
    )
    server = ThreadingHTTPServer((host, port), handler_class)
    url = f"http://{host}:{port}"
    print(json.dumps({"dashboard_url": url, "table": table}, ensure_ascii=False, indent=2))
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


def _make_handler(supabase_url: str | None, supabase_key: str | None, table: str) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - http.server API
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._send_html(DASHBOARD_HTML)
                return
            if parsed.path == "/api/items":
                self._handle_items(parsed.query)
                return
            if parsed.path == "/api/health":
                self._send_json({"ok": True, "table": table})
                return
            self.send_error(404, "Not Found")

        def log_message(self, format: str, *args: Any) -> None:
            if os.environ.get("DASHBOARD_DEBUG"):
                super().log_message(format, *args)

        def _handle_items(self, raw_query: str) -> None:
            params = urllib.parse.parse_qs(raw_query)
            try:
                rows = fetch_dashboard_items(
                    supabase_url=supabase_url,
                    supabase_key=supabase_key,
                    table=table,
                    status=_first(params, "status"),
                    run_date=_first(params, "date"),
                    search=_first(params, "search"),
                    limit=_as_int(_first(params, "limit"), 100),
                )
            except SupabaseError as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=500)
                return
            self._send_json({"ok": True, "rows": rows})

        def _send_html(self, html: str) -> None:
            payload = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return DashboardHandler


def _first(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key) or []
    value = values[0].strip() if values else ""
    return value or None


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(value or default)
    except ValueError:
        return default


DASHBOARD_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Crypto Intelligence</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f8;
      --panel: #ffffff;
      --ink: #172026;
      --muted: #65717b;
      --line: #dfe5e8;
      --accent: #0f766e;
      --accent-weak: #d9f2ee;
      --warn: #a16207;
      --bad: #b42318;
      --radius: 8px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      min-height: 64px;
      padding: 14px 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      position: sticky;
      top: 0;
      z-index: 3;
    }
    h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 650;
      letter-spacing: 0;
    }
    button, input, select {
      font: inherit;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      border-radius: var(--radius);
      height: 36px;
    }
    button {
      cursor: pointer;
      padding: 0 12px;
      background: var(--accent);
      border-color: var(--accent);
      color: white;
      font-weight: 600;
    }
    input, select { padding: 0 10px; min-width: 150px; }
    main {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      gap: 16px;
      padding: 16px 24px 24px;
    }
    aside, section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
    }
    aside {
      padding: 14px;
      align-self: start;
      position: sticky;
      top: 82px;
    }
    label {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin: 12px 0 6px;
    }
    aside input, aside select, aside button { width: 100%; }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }
    .metric {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 12px;
    }
    .metric strong { display: block; font-size: 20px; }
    .metric span { color: var(--muted); font-size: 12px; }
    .table-wrap {
      overflow: auto;
      max-height: calc(100vh - 166px);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 980px;
    }
    th, td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      text-align: left;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      background: #fbfcfc;
      position: sticky;
      top: 0;
      z-index: 1;
    }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .title { font-weight: 650; max-width: 360px; }
    .summary { color: var(--muted); max-width: 420px; }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 8px;
      border-radius: 999px;
      background: #eef2f3;
      color: #334047;
      font-size: 12px;
      white-space: nowrap;
    }
    .pill.selected, .pill.sent { background: var(--accent-weak); color: #075e57; }
    .pill.skipped_date, .pill.skipped_rule { background: #fef3c7; color: var(--warn); }
    .pill.noise, .pill.archived { background: #fee4e2; color: var(--bad); }
    .tags {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .muted { color: var(--muted); }
    .empty, .error {
      padding: 32px;
      color: var(--muted);
    }
    .error { color: var(--bad); }
    @media (max-width: 900px) {
      header { align-items: flex-start; flex-direction: column; }
      main { grid-template-columns: 1fr; padding: 12px; }
      aside { position: static; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <header>
    <h1>Crypto Intelligence</h1>
    <button id="refreshBtn" type="button">刷新</button>
  </header>
  <main>
    <aside>
      <label for="statusFilter">状态</label>
      <select id="statusFilter">
        <option value="">全部</option>
        <option value="selected">Selected</option>
        <option value="sent">Sent</option>
        <option value="analyzed">Analyzed</option>
        <option value="collected">Collected</option>
        <option value="skipped_rule">Skipped Rule</option>
        <option value="skipped_date">Skipped Date</option>
        <option value="noise">Noise</option>
        <option value="archived">Archived</option>
      </select>
      <label for="dateFilter">日期</label>
      <input id="dateFilter" type="date" />
      <label for="searchInput">搜索</label>
      <input id="searchInput" type="search" placeholder="标题、来源、摘要" />
      <label for="limitInput">数量</label>
      <select id="limitInput">
        <option value="50">50</option>
        <option value="100" selected>100</option>
        <option value="200">200</option>
        <option value="500">500</option>
      </select>
    </aside>
    <div>
      <div class="metrics">
        <div class="metric"><strong id="totalMetric">0</strong><span>记录</span></div>
        <div class="metric"><strong id="sourceMetric">0</strong><span>Sources</span></div>
        <div class="metric"><strong id="projectMetric">0</strong><span>Projects</span></div>
        <div class="metric"><strong id="avgMetric">0</strong><span>Avg importance</span></div>
      </div>
      <section>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>name</th>
                <th>source</th>
                <th>importance</th>
                <th>projects</th>
                <th>asset_classes</th>
              </tr>
            </thead>
            <tbody id="rows"></tbody>
          </table>
          <div id="message" class="empty">加载中</div>
        </div>
      </section>
    </div>
  </main>
  <script>
    const rowsEl = document.querySelector("#rows");
    const messageEl = document.querySelector("#message");
    const statusFilter = document.querySelector("#statusFilter");
    const dateFilter = document.querySelector("#dateFilter");
    const searchInput = document.querySelector("#searchInput");
    const limitInput = document.querySelector("#limitInput");

    document.querySelector("#refreshBtn").addEventListener("click", loadRows);
    [statusFilter, dateFilter, limitInput].forEach((el) => el.addEventListener("change", loadRows));
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") loadRows();
    });

    async function loadRows() {
      messageEl.className = "empty";
      messageEl.textContent = "加载中";
      rowsEl.innerHTML = "";
      const params = new URLSearchParams();
      if (statusFilter.value) params.set("status", statusFilter.value);
      if (dateFilter.value) params.set("date", dateFilter.value);
      if (searchInput.value.trim()) params.set("search", searchInput.value.trim());
      params.set("limit", limitInput.value);
      try {
        const response = await fetch(`/api/items?${params.toString()}`);
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error || "加载失败");
        renderRows(payload.rows || []);
      } catch (error) {
        messageEl.className = "error";
        messageEl.textContent = error.message;
      }
    }

    function renderRows(rows) {
      setMetrics(rows);
      rowsEl.innerHTML = rows.map(renderRow).join("");
      messageEl.textContent = rows.length ? "" : "暂无记录";
    }

    function renderRow(row) {
      const projects = row.projects || [];
      const assetClasses = row.asset_classes || [];
      return `
        <tr>
          <td class="title"><a href="${escapeAttr(row.url || "#")}" target="_blank" rel="noreferrer">${escapeHtml(row.name || "Untitled")}</a></td>
          <td>${escapeHtml(row.source || "")}</td>
          <td>${Number(row.importance || 0)}</td>
          <td><div class="tags">${projects.map((label) => `<span class="pill">${escapeHtml(label)}</span>`).join("")}</div></td>
          <td><div class="tags">${assetClasses.map((label) => `<span class="pill">${escapeHtml(label)}</span>`).join("")}</div></td>
        </tr>
      `;
    }

    function setMetrics(rows) {
      const total = rows.length;
      const sources = new Set(rows.map((row) => row.source).filter(Boolean)).size;
      const projects = new Set(rows.flatMap((row) => row.projects || [])).size;
      const avg = total ? Math.round(rows.reduce((sum, row) => sum + Number(row.importance || 0), 0) / total) : 0;
      document.querySelector("#totalMetric").textContent = total;
      document.querySelector("#sourceMetric").textContent = sources;
      document.querySelector("#projectMetric").textContent = projects;
      document.querySelector("#avgMetric").textContent = avg;
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[char]));
    }

    function escapeAttr(value) {
      return escapeHtml(value).replace(/`/g, "&#96;");
    }

    loadRows();
  </script>
</body>
</html>
"""
