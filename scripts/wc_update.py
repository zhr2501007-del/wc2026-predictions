#!/usr/bin/env python3
"""2026世界杯台账自动维护（跑在 GitHub Actions cron 里）。
- 核对：对已过 kickoff+2h 仍待核的场次，用 Claude+web_search 查真实90分钟比分与晋级方回填。
- 预测：对未来24h内(北京时间)开赛、data.json 中尚无的对阵，用期望进球法给主/次比分+晋级方，追加。
数据源全部来自 web 检索；查不到就保持 settled:false，绝不臆造。
提交/推送由工作流用仓库自带 GITHUB_TOKEN 完成。
"""
import json, os, re, sys, pathlib
from datetime import datetime, timezone, timedelta

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ANTHROPIC_API_KEY 未设置——请在仓库 Settings→Secrets 添加后再跑。跳过。")
    sys.exit(0)

import anthropic

MODEL = "claude-sonnet-4-6"                       # 可改 claude-opus-4-8 提升分析深度(更贵)
WEB = [{"type": "web_search_20260209", "name": "web_search"}]
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data.json"
BJ = timezone(timedelta(hours=8))
now_bj = datetime.now(timezone.utc).astimezone(BJ)

client = anthropic.Anthropic()


def ask(prompt, max_tokens=8000):
    """单轮问答，自动续跑 server-tool 的 pause_turn，返回全部文本。"""
    messages = [{"role": "user", "content": prompt}]
    for _ in range(6):
        resp = client.messages.create(model=MODEL, max_tokens=max_tokens, tools=WEB, messages=messages)
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return ""


def extract(text):
    """从模型回复里抠出第一个 JSON 对象或数组。"""
    m = re.search(r"(\{.*\}|\[.*\])", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def parse_bj(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=BJ)
    except Exception:
        return None


data = json.loads(DATA.read_text(encoding="utf-8"))
changed = False

# ---------- 一·核对（结束时间感知）----------
due = []
for r in data:
    if r.get("settled"):
        continue
    ko = parse_bj(r.get("kickoff", ""))
    if ko and now_bj >= ko + timedelta(hours=2):        # 预计已终场
        due.append(r)

if due:
    lst = "\n".join(f'- {r["match"]}（开赛 {r["kickoff"]} 北京，预测 {r["winner"]} {r["primary"]}/{r["secondary"]}）' for r in due)
    prompt = (
        "你是足球赛事核对员。用 web_search 多来源核对下列2026世界杯比赛是否已【终场】及真实结果。\n"
        "只返回一个 JSON 对象：键=对阵原文，值={\"done\":bool,\"score90\":\"主-客\"(如\"2-1\"),\"advancer\":\"晋级方\",\"actual\":\"展示串(可注加时/点球)\"}。\n"
        "规则：仅当确认真正结束才 done:true 并填90分钟常规时间比分(主队在前)与最终晋级方(加时/点球晋级也算晋级方)；进行中/未开赛/查不到→done:false 留空。禁止编造。只输出JSON。\n\n"
        f"当前北京时间：{now_bj:%Y-%m-%d %H:%M}\n待核对：\n{lst}"
    )
    res = extract(ask(prompt)) or {}
    for r in due:
        info = res.get(r["match"])
        if isinstance(info, dict) and info.get("done") and info.get("score90"):
            s90 = str(info["score90"]).strip()
            adv = str(info.get("advancer", "")).strip()
            r["actual"] = info.get("actual") or f'{r["match"].split(" vs ")[0]} {s90}'
            r["advancer"] = adv
            r["hitWinner"] = (adv == r["winner"])
            r["hitPrimary"] = (s90 == r["primary"])
            r["hitSecondary"] = (s90 == r["secondary"])
            r["settled"] = True
            changed = True
            print(f'核对: {r["match"]} → {s90} 晋级{adv} 胜负{"✓" if r["hitWinner"] else "✗"}')

# ---------- 二·预测（仅新赛事，期望进球法）----------
existing = "、".join(r["match"] for r in data) or "（无）"
prompt = (
    f"你是资深足球分析师。现在北京时间 {now_bj:%Y-%m-%d %H:%M}。用 web_search 查未来24小时内(北京时间)开赛的全部2026世界杯比赛。\n"
    f"排除这些已存在对阵：{existing}。\n"
    "对每场【新】比赛：检索两队 FIFA排名/全队身价/伤病停赛/小组赛或近期场均进失球/主客场/交锋，用【期望进球法】估双方xG，"
    "选概率最高的两个低比分(0-0/1-0/1-1/2-1/2-0区间)作 primary(最可能)与 secondary(次可能，需与primary不同)，并给 winner(晋级方)。\n"
    '只返回 JSON 数组，元素 {\"round\",\"date\"(YYYY-MM-DD北京),\"kickoff\"(YYYY-MM-DD HH:MM北京),\"match\"(\"A vs B\"),\"winner\",\"primary\",\"secondary\",\"reason\"(一句话)}。'
    "查不到未来24h内的新比赛就返回 []。禁止编造。只输出JSON。"
)
arr = extract(ask(prompt))
if isinstance(arr, list):
    have = {r["match"] for r in data}
    lines = []
    for p in arr:
        m = str(p.get("match", "")).strip()
        if not m or m in have or not p.get("primary") or not p.get("secondary"):
            continue
        data.append({
            "round": p.get("round", "R32"), "date": p.get("date", ""), "kickoff": p.get("kickoff", ""),
            "match": m, "winner": p.get("winner", ""), "primary": p["primary"], "secondary": p["secondary"],
            "actual": "", "advancer": "", "hitWinner": None, "hitPrimary": None, "hitSecondary": None, "settled": False,
        })
        have.add(m)
        changed = True
        lines.append(f'- {p.get("kickoff","")} {m} → {p.get("winner","")} {p["primary"]}/{p["secondary"]}｜{p.get("reason","")}')
        print(f'预测: {m} → {p.get("winner","")} {p["primary"]}/{p["secondary"]}')
    if lines:
        adir = ROOT / "analysis"
        adir.mkdir(exist_ok=True)
        f = adir / f"{now_bj:%Y-%m-%d}.md"
        with f.open("a", encoding="utf-8") as fh:
            fh.write(f"\n## 自动预测 @ {now_bj:%Y-%m-%d %H:%M} 北京（期望进球法）\n" + "\n".join(lines) + "\n")

if changed:
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("data.json 已更新")
else:
    print("无变更")
