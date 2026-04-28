# Index Pulse

极简 A 股估值日报，每个交易日 16:00（北京时间）推送沪深300、中证500、中证红利的 PE 百分位（10 年滚动）到 ntfy。

## 订阅推送

手机装 [ntfy app](https://ntfy.sh/) 或浏览器打开 `https://ntfy.sh/<你的-topic>` 订阅。

## 部署（GitHub Actions）

1. 到 repo **Settings → Secrets and variables → Actions → New repository secret**
2. 添加 secret：
   - Name: `NTFY_TOPIC`
   - Value: 你的 ntfy topic 名（不是完整 URL）
3. 到 **Settings → Actions → General → Workflow permissions**，确保选了 **Read and write permissions**（让 workflow 能 commit history.json 回来）
4. 第一次可以到 **Actions → Index Pulse → Run workflow** 手动触发，验证一切正常

之后每个交易日北京时间 16:00 自动跑（GitHub cron 通常会延迟 5–30 分钟）。

## 输出格式

```
【指数估值】

无明显变化（全部 <1pp）

中证红利：18%（+0.2）〔低估〕
沪深300：23%（+0.3）〔偏低〕
中证500：41%（-0.5）〔中性〕
```

第一行结论的优先级：
1. ⚠️ 接近极端区间（任意指数 <20% 或 >80%）
2. 出现变化（最大单点 ≥1pp）
3. 齐涨 / 齐跌（三者同向且每个 ≥0.5pp，取最小值）
4. 无明显变化

## 文件

- `index_pulse.py` — 主脚本
- `.github/workflows/pulse.yml` — 定时任务
- `history.json` — 每日百分位历史，由 Action 自动 commit
- `requirements.txt` — Python 依赖
