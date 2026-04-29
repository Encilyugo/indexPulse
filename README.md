# Index Pulse

极简 A 股估值日报，每个交易日 09:00 开盘前（北京时间）推送沪深300、中证500、中证红利的 PE 百分位（10 年滚动 TTM）到 ntfy。对比基准是上一个交易日（不是日历昨天）。

## 订阅推送

手机装 [ntfy app](https://ntfy.sh/) 或浏览器打开 `https://ntfy.sh/<你的-topic>` 订阅。

## 部署（GitHub Actions）

1. 到 repo **Settings → Secrets and variables → Actions → New repository secret**
2. 添加 secret：
   - Name: `NTFY_TOPIC`
   - Value: 你的 ntfy topic 名（不是完整 URL）
3. 到 **Settings → Actions → General → Workflow permissions**，确保选了 **Read and write permissions**（让 workflow 能 commit history.json 回来）
4. 第一次可以到 **Actions → Index Pulse → Run workflow** 手动触发，验证一切正常

之后每个交易日北京时间 09:00 自动跑（GitHub cron 通常会延迟 5–30 分钟）。

## 输出格式

body 第一行就是结论（锁屏锁屏第二行可见），下面三行是指数明细（按百分位升序）：

```
出现变化（最大 +1.5pp），接近极端区间
中证500：23%（-0.5）〔偏低〕
沪深300：41%（+1.5）〔中性〕
中证红利：85%（+0.2）〔高估〕
```

### 第一行结论的优先级（高 → 低）

1. `🚨 异动（最大 ±X.Xpp）` — 任意指数变化 ≥2pp
2. `出现变化（最大 ±X.Xpp）` — 1pp ≤ 最大变化 < 2pp
3. `齐涨 +X.Xpp` / `齐跌 -X.Xpp` — 三者同向且每个 ≥0.5pp，取最接近 0 的值
4. `无明显变化（全部 <1pp）`
5. `首次运行（无历史对比）` — history.json 为空时

### 极端区间追加规则

任意指数 PE 百分位 <20 或 >80 时，结论后追加：

- 平静日：`无明显变化（全部 <1pp），但接近极端区间`（带"但"，转折）
- 其他三类：`...，接近极端区间`（不带"但"，并列）

## 文件

- `index_pulse.py` — 主脚本
- `.github/workflows/pulse.yml` — 定时任务
- `history.json` — 每日百分位历史，由 Action 自动 commit
- `requirements.txt` — Python 依赖
