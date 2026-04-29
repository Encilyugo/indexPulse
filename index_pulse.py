"""
Enci Index Pulse - 极简 A 股估值日报
推送沪深300、中证500、中证红利的 PE 百分位（10年滚动 TTM）到 ntfy。
设计跑在 GitHub Actions 上，history.json 由 workflow commit 回 repo。
数据源: 中证指数公司官方 OSS (oss-ch.csindex.com.cn)
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}" if NTFY_TOPIC else ""

SCRIPT_DIR = Path(__file__).resolve().parent
HISTORY_FILE = SCRIPT_DIR / "history.json"

CN_TZ = timezone(timedelta(hours=8))

INDEXES = [
    {"display": "沪深300", "code": "000300"},
    {"display": "中证500", "code": "000905"},
    {"display": "中证红利", "code": "000922"},
]

PERCENTILE_WINDOW_YEARS = 10
SINGLE_MOVE_THRESHOLD = 1.0      # pp
SYNC_MOVE_THRESHOLD = 0.5        # pp
EXTREME_LOW = 20                 # 严格 <
EXTREME_HIGH = 80                # 严格 >


@dataclass
class IndexSnapshot:
    display: str
    percentile: float            # 0-100
    delta: float | None          # pp，首日为 None


def today_cn() -> date:
    """A 股交易日以北京时间为准，runner 跑在 UTC 上必须显式转换。"""
    return datetime.now(CN_TZ).date()


def is_trading_day(today: date) -> bool:
    """周末直接判否；节假日通过 akshare 的交易日历判断。"""
    if today.weekday() >= 5:
        return False
    import akshare as ak
    cal = ak.tool_trade_date_hist_sina()
    trade_dates = set(cal["trade_date"].astype(str).tolist())
    return today.isoformat() in trade_dates


def fetch_pe_percentile(code: str, today: date) -> float:
    """拉取指定指数（中证代码）的 TTM PE 历史，返回最新值在近 10 年中的百分位（0-100）。"""
    import akshare as ak
    df = ak.stock_zh_index_value_csindex(symbol=code)
    df = df.copy()
    df["日期"] = df["日期"].astype(str)
    df = df.sort_values("日期")

    cutoff = (today - timedelta(days=PERCENTILE_WINDOW_YEARS * 365)).isoformat()
    window = df[df["日期"] >= cutoff].dropna(subset=["市盈率1"])
    if window.empty:
        raise RuntimeError(f"{code}: 10 年窗口内无 PE 数据")

    series = window["市盈率1"].astype(float)
    latest_pe = float(series.iloc[-1])

    rank = (series < latest_pe).sum() + (series == latest_pe).sum() / 2
    percentile = rank / len(series) * 100
    return round(percentile, 1)


def label_for(p: float) -> str:
    if p < 20: return "低估"
    if p < 40: return "偏低"
    if p < 60: return "中性"
    if p < 80: return "偏高"
    return "高估"


def load_yesterday() -> dict[str, float] | None:
    if not HISTORY_FILE.exists():
        return None
    try:
        records = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not records:
        return None
    return records[-1]["percentiles"]


def append_history(today: date, snapshots: list[IndexSnapshot]) -> None:
    records = []
    if HISTORY_FILE.exists():
        try:
            records = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            records = []
    records.append({
        "date": today.isoformat(),
        "percentiles": {s.display: s.percentile for s in snapshots},
    })
    HISTORY_FILE.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_headline(snapshots: list[IndexSnapshot], is_first_run: bool) -> str:
    if is_first_run:
        return "首次运行（无历史对比）"

    if any(s.percentile < EXTREME_LOW or s.percentile > EXTREME_HIGH for s in snapshots):
        return "⚠️ 接近极端区间（需关注）"

    deltas = [s.delta for s in snapshots if s.delta is not None]
    if deltas:
        max_abs = max(deltas, key=abs)
        if abs(max_abs) >= SINGLE_MOVE_THRESHOLD:
            sign = "+" if max_abs >= 0 else "-"
            return f"出现变化（最大 {sign}{abs(max_abs):.1f}pp）"

        all_up = all(d >= SYNC_MOVE_THRESHOLD for d in deltas)
        all_down = all(d <= -SYNC_MOVE_THRESHOLD for d in deltas)
        if all_up:
            return f"齐涨 +{min(deltas):.1f}pp"
        if all_down:
            return f"齐跌 {max(deltas):.1f}pp"  # 最接近 0 的负值

    return "无明显变化（全部 <1pp）"


def format_body(headline: str, snapshots: list[IndexSnapshot]) -> str:
    """body 第一行即 headline（锁屏第二行只能展示 1-2 行 body，结论必须先出）。"""
    lines = [headline]
    for s in sorted(snapshots, key=lambda x: x.percentile):
        if s.delta is None:
            delta_str = "—"
        else:
            delta_str = f"{'+' if s.delta >= 0 else ''}{s.delta:.1f}"
        lines.append(f"{s.display}：{s.percentile:.0f}%（{delta_str}）〔{label_for(s.percentile)}〕")
    return "\n".join(lines)


def push_ntfy(body: str) -> None:
    if not NTFY_URL:
        raise RuntimeError("NTFY_TOPIC 未设置")
    requests.post(
        NTFY_URL,
        data=body.encode("utf-8"),
        timeout=15,
    )


def push_error(err: str) -> None:
    if not NTFY_URL:
        return
    try:
        requests.post(
            NTFY_URL,
            data=f"❌ 执行失败\n{err}".encode("utf-8"),
            headers={"Priority": "high"},
            timeout=15,
        )
    except Exception:
        pass


def main() -> int:
    today = today_cn()

    if not is_trading_day(today):
        print(f"{today} 非交易日，跳过。")
        return 0

    yesterday = load_yesterday()
    is_first_run = yesterday is None

    snapshots: list[IndexSnapshot] = []
    for idx in INDEXES:
        p = fetch_pe_percentile(idx["code"], today)
        delta = None if is_first_run else round(p - yesterday.get(idx["display"], p), 1)
        snapshots.append(IndexSnapshot(display=idx["display"], percentile=p, delta=delta))

    headline = build_headline(snapshots, is_first_run)
    body = format_body(headline, snapshots)
    print(body)
    push_ntfy(body)
    append_history(today, snapshots)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        last = err.strip().splitlines()[-1] if err.strip() else "unknown error"
        push_error(last)
        sys.exit(1)
