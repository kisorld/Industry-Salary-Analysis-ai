from __future__ import annotations

import html
import json
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from generate_baseline_report import build_docx
from salary_core import analyze, clean_jobs, load_jobs, make_insight_text, write_cleaned_csv, write_stats_csv


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "baseline_jobs.csv"
OUTPUT_DIR = ROOT / "outputs"
REPORT_DIR = ROOT / "reports"
PORT = 8501


def bar_chart(rows: list[dict[str, object]], label: str) -> str:
    if not rows:
        return "<p>暂无数据</p>"
    max_value = max(float(row["中位数"]) for row in rows) or 1
    parts = []
    for row in rows:
        value = float(row["中位数"])
        width = max(4, value / max_value * 100)
        parts.append(
            f"""
            <div class="bar-row">
              <div class="bar-label">{html.escape(str(row['维度']))}</div>
              <div class="bar-track"><div class="bar" style="width:{width:.1f}%"></div></div>
              <div class="bar-value">{value:.2f}K</div>
            </div>
            """
        )
    return f"<h3>{label}</h3>" + "\n".join(parts)


def table_html(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<p>暂无数据</p>"
    headers = list(rows[0].keys())
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{html.escape(str(row[h]))}</td>" for h in headers) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def run_analysis(data_path: Path = DATA_PATH) -> dict[str, object]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    REPORT_DIR.mkdir(exist_ok=True)
    jobs = clean_jobs(load_jobs(data_path))
    analysis = analyze(jobs)
    write_cleaned_csv(jobs, OUTPUT_DIR / "cleaned_jobs.csv")
    write_stats_csv(analysis["by_category"], OUTPUT_DIR / "stats_by_category.csv")
    write_stats_csv(analysis["by_city"], OUTPUT_DIR / "stats_by_city.csv")
    write_stats_csv(analysis["by_experience"], OUTPUT_DIR / "stats_by_experience.csv")
    build_docx(analysis, REPORT_DIR / "演示系统生成报告.docx")
    return analysis


def page(analysis: dict[str, object] | None = None, message: str = "") -> bytes:
    if analysis is None:
        analysis = run_analysis()
    overall = analysis["overall"]
    insights = "".join(f"<li>{html.escape(text)}</li>" for text in make_insight_text(analysis))
    payload = json.dumps(analysis, ensure_ascii=False, indent=2)
    body = f"""
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8">
      <title>行业薪酬洞察 AI 智能体</title>
      <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; font-family: "Microsoft YaHei", Arial, sans-serif; color: #172033; background: #f5f7fb; }}
        header {{ background: #17324d; color: #fff; padding: 22px 36px; }}
        header h1 {{ margin: 0 0 6px; font-size: 28px; letter-spacing: 0; }}
        header p {{ margin: 0; color: #d8e4ef; }}
        main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
        section {{ background: #fff; border: 1px solid #dce3ec; border-radius: 8px; padding: 20px; margin-bottom: 18px; }}
        .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }}
        .metric {{ border-left: 4px solid #1f7a8c; background: #f8fbfc; padding: 14px; border-radius: 6px; }}
        .metric b {{ display: block; font-size: 24px; color: #17324d; margin-top: 4px; }}
        .actions {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }}
        button, .button {{ border: 0; background: #1f7a8c; color: white; padding: 10px 14px; border-radius: 6px; cursor: pointer; text-decoration: none; display: inline-block; font-size: 14px; }}
        input[type=file] {{ padding: 8px; background: #f7f9fc; border: 1px solid #ced8e3; border-radius: 6px; }}
        table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
        th, td {{ border: 1px solid #d9e1ea; padding: 9px; text-align: left; }}
        th {{ background: #edf3f8; color: #17324d; }}
        .bar-row {{ display: grid; grid-template-columns: 120px 1fr 80px; gap: 10px; align-items: center; margin: 8px 0; }}
        .bar-track {{ height: 18px; background: #e7edf4; border-radius: 999px; overflow: hidden; }}
        .bar {{ height: 100%; background: #1f7a8c; }}
        .notice {{ color: #6a3d00; background: #fff7e6; border: 1px solid #f0d49a; padding: 10px 12px; border-radius: 6px; }}
        pre {{ white-space: pre-wrap; background: #101923; color: #edf7ff; padding: 14px; border-radius: 8px; overflow:auto; max-height: 360px; }}
        @media (max-width: 800px) {{ .grid {{ grid-template-columns: 1fr 1fr; }} .bar-row {{ grid-template-columns: 90px 1fr 64px; }} }}
      </style>
    </head>
    <body>
      <header>
        <h1>行业薪酬洞察 AI 智能体</h1>
        <p>第2周可运行基线演示：CSV 导入、薪资清洗、分位值统计、可视化和 Word 报告导出</p>
      </header>
      <main>
        {f'<p class="notice">{html.escape(message)}</p>' if message else ''}
        <section>
          <form class="actions" method="post" enctype="application/x-www-form-urlencoded">
            <button name="action" value="sample">使用内置样例数据重新分析</button>
            <a class="button" href="/download/report">下载 Word 报告</a>
            <a class="button" href="/download/cleaned">下载清洗后 CSV</a>
            <a class="button" href="/download/sample">下载样例 CSV</a>
          </form>
        </section>
        <section>
          <form class="actions" method="post" enctype="multipart/form-data">
            <input type="file" name="file" accept=".csv">
            <button name="action" value="upload">上传 CSV 并分析</button>
          </form>
        </section>
        <section class="grid">
          <div class="metric">总样本数<b>{analysis['total']}</b></div>
          <div class="metric">有效薪资样本<b>{analysis['valid']}</b></div>
          <div class="metric">解析成功率<b>{analysis['parse_accuracy']}%</b></div>
          <div class="metric">月薪中位数<b>{overall['中位数K/月']}K</b></div>
        </section>
        <section>
          <h2>AI 报告基线摘要</h2>
          <ul>{insights}</ul>
        </section>
        <section>{bar_chart(analysis['by_category'], '按岗位类别的中位月薪')}</section>
        <section>{bar_chart(analysis['by_city'], '按城市的中位月薪')}</section>
        <section><h2>岗位类别统计表</h2>{table_html(analysis['by_category'])}</section>
        <section><h2>城市统计表</h2>{table_html(analysis['by_city'])}</section>
        <section><h2>经验统计表</h2>{table_html(analysis['by_experience'])}</section>
        <section><h2>分析 JSON 输出</h2><pre>{html.escape(payload)}</pre></section>
      </main>
    </body>
    </html>
    """
    return body.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/":
            self._send(page())
        elif self.path == "/download/report":
            self._download(REPORT_DIR / "演示系统生成报告.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        elif self.path == "/download/cleaned":
            self._download(OUTPUT_DIR / "cleaned_jobs.csv", "text/csv")
        elif self.path == "/download/sample":
            self._download(DATA_PATH, "text/csv")
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", "0"))
        content = self.rfile.read(length)
        if "multipart/form-data" in ctype and b"\r\n\r\n" in content:
            tmp = self._extract_uploaded_csv(content)
            if tmp:
                analysis = run_analysis(tmp)
                self._send(page(analysis, "已使用上传 CSV 完成分析，并生成新的报告。"))
                return
        form = parse_qs(content.decode("utf-8", errors="ignore"))
        if form.get("action", [""])[0] == "sample":
            analysis = run_analysis()
            self._send(page(analysis, "已使用内置样例数据重新分析。"))
            return
        self._send(page(message="未识别上传内容，请使用 CSV 文件。"))

    def _extract_uploaded_csv(self, content: bytes) -> Path | None:
        marker = b"\r\n\r\n"
        start = content.find(marker)
        if start == -1:
            return None
        data = content[start + len(marker) :]
        end = data.rfind(b"\r\n--")
        if end != -1:
            data = data[:end]
        if not data.strip():
            return None
        tmp = Path(tempfile.gettempdir()) / "salary_uploaded.csv"
        tmp.write_bytes(data)
        return tmp

    def _send(self, data: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _download(self, path: Path, content_type: str) -> None:
        if not path.exists():
            run_analysis()
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f"attachment; filename={path.name.encode('utf-8').decode('latin1', errors='ignore')}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    run_analysis()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"演示系统已启动：http://127.0.0.1:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
