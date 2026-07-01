# 2026世界杯 · 预测准确率台账

📱 **手机可看的实盘台账（自动更新）：https://zhr2501007-del.github.io/wc2026-predictions/**

- 预测数据 SSOT：`data.json`（云端定时任务每天维护：回填真实结果 + 追加新预测）
- 手机页面：`index.html`（渲染 data.json：胜负 / 主比分 / 次比分 / 各自中不中 + 命中率汇总）
- 每日完整九维度推理：`analysis/YYYY-MM-DD.md`
- 盲测校准（回测，**不计入**实盘命中率）：`BACKTEST.md` → 晋级 6/7、精确比分 3/7

## 判定口径（用户已定）
- **胜负/晋级命中**：预测晋级方 == 实际晋级方（含加时/点球）。
- **比分命中（允许1次容错）**：主比分 **或** 次比分，任一 == 90分钟常规时间真实比分，即算命中。
- 页面另单列「主比分严格命中率」透明对照，不掩盖容错带来的宽松。

## data.json 每条字段
`round, date, match, winner(胜负预测), primary(主比分), secondary(次比分), actual(真实90'), advancer(实际晋级), hitWinner, hitPrimary, hitSecondary, settled`

## 每日维护流程（云端 agent 执行）
1. **核对**：读 data.json，对 `settled:false` 的场次用 web 检索真实终场比分与晋级方；回填 `actual/advancer` 及 `hitWinner/hitPrimary/hitSecondary`，置 `settled:true`。查不到保持 false，下次再补，绝不臆造。
2. **预测**：查未来约18小时内（北京时间）开赛的世界杯赛事；每场基于真实数据（FIFA排名/身价/伤病/小组赛攻防/战术/交锋）给出 `winner` + `primary` + `secondary`**两个比分**（务必都填，容错才成立），追加进 data.json（settled:false）；完整九维度推理写 `analysis/<北京日期>.md`。
3. **提交**：git add -A && commit && push origin main。

铁律：全部 web 检索、禁止臆造、缺数据保持 false/待核；每场必给主+次两个比分。
