#!/usr/bin/env python3
"""主题漂移复查 (topic_shift_check) —— 尽调流程第 5 关

对"老域10年+/新壳<2年"等高风险段的域名，用 Wayback Machine 最早快照
对比当前内容主题，识别"过期域名套壳"（注册很久的老域名被收购后整个换主题
做 coupon/折扣/灰产站），输出 topical_shift + high/medium/low 风险。

⚠️ 网络要求：需能访问 web.archive.org（当前沙箱/代理不可达时无法运行，
   可用"人工复查包"代替——见 docs/合作方尽调完整流程_v2.md 第 2.4 节）。

原理:
1. CDX API 查该域名最早一个 status=200 的 HTML 快照
2. 抓取快照正文(trafilatura) + 台账当前侧文本(标题/Meta描述/正文摘要)
3. 两边做关键词集比对(去停用词) → 主题相似度 → 是否漂移
4. 叠加上游 domain_history.assess_risk 规则评级:
   漂移 & (<2年 or ≥5年) → high | 漂移 & 2~5年 → medium | 未漂移 → low

用法:
    python topic_shift_check.py --csv 合作方台账_v2.csv -o 主题复查结果.csv
    python topic_shift_check.py --csv ... --only-band "老域(10年+)" -o ...   # 只查某年龄带
    python topic_shift_check.py --csv ... --domains 名单.txt -o ...         # 指定域名
    python topic_shift_check.py --csv ... --year 2008 -o ...                # 指定对比年份

输出列: 域名, 注册年限, 对比年份, 快照标题, 当前标题, 历史词数, 当前词数,
        相似度, 主题漂移(是/否/待人工/无法判断), 风险, 备注
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
for _p in (os.path.join(_REPO_ROOT, "claude-seo", "scripts"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import domain_history as dh
except Exception:
    dh = None

try:
    import trafilatura
except Exception:
    trafilatura = None

_CDX = "https://web.archive.org/cdx/search/cdx?url={d}&output=json&fl=timestamp,original,statuscode&filter=statuscode:200&filter=mimetype:text/html&from=1996&limit=1&collapse=digest"
_WAYBACK = "https://web.archive.org/web/{ts}id_/{orig}"

_STOP = set("""a an and are as at be but by for from has have he her his i if in into is it its
me my no not of on or our out she so that the their them then there these they this to
was we were what when which who will with you your about after all also am any been before
being between both did do does doing down during each few get got had how just more most
much must other over own same shall should some such than too under until up very while
why would www com net org html htm php https http co uk de the""".split())


def http_get(url: str, timeout: float = 25, ua: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)") -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
        for enc in ("utf-8", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", "replace")
    except Exception:
        return None


def earliest_snapshot(domain: str) -> tuple | None:
    txt = http_get(_CDX.format(d=domain), timeout=20)
    if not txt:
        return None
    try:
        rows = json.loads(txt)
    except Exception:
        return None
    if not isinstance(rows, list) or len(rows) < 2:
        return None
    ts, orig = rows[1][0], rows[1][1]
    return ts, orig


def text_of(html: str) -> str:
    if trafilatura is not None:
        t = trafilatura.extract(html, include_comments=False, include_tables=False)
        if t and len(t.strip()) > 80:
            return t.strip()
    # fallback: title + meta description
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    md = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', html, re.I | re.S)
    bits = [m.group(1).strip() if m else ""]
    if md:
        bits.append(md.group(1).strip())
    return " ".join(bits)


def keywords(text: str, n: int = 40) -> list:
    words = re.findall(r"[a-z][a-z0-9\-]{3,}", text.lower())
    freq: dict = {}
    for w in words:
        if w in _STOP or len(w) < 4 or w.isdigit():
            continue
        freq[w] = freq.get(w, 0) + 1
    return sorted(freq, key=lambda w: (-freq[w], w))[:n]


def compare(hist_text: str, now_text: str) -> dict:
    kw_h, kw_n = keywords(hist_text), keywords(now_text)
    sh, sn = set(kw_h), set(kw_n)
    if not sh or not sn:
        return {"hist_words": len(kw_h), "now_words": len(kw_n), "sim": None,
                "shift": None, "hist_kw": kw_h[:10], "now_kw": kw_n[:10],
                "note": "一侧无有效文本, 无法对比"}
    if len(kw_h) < 8:
        return {"hist_words": len(kw_h), "now_words": len(kw_n), "sim": None,
                "shift": None, "hist_kw": kw_h[:10], "now_kw": kw_n[:10],
                "note": f"历史快照词过少({len(kw_h)}个), 无法判断(可能为图片/导航页)"}
    inter = len(sh & sn)
    sim = inter / min(len(sh), len(sn))
    return {"hist_words": len(kw_h), "now_words": len(kw_n), "sim": round(sim, 3),
            "shift": None, "hist_kw": kw_h[:10], "now_kw": kw_n[:10], "note": ""}


def risk_of(age_years: float | None, shift: bool | None, note: str) -> str:
    if shift is True:
        if age_years is None:
            return "high-待核"
        return "high" if (age_years < 2 or age_years >= 5) else "medium"
    if shift is False:
        return "low"
    return "unknown" + ("-" + note if note else "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", help="台账 CSV(v2 含 标题/Meta描述/正文摘要/注册年限 列)")
    ap.add_argument("--domains", help="每行一个域名的 txt(与 --csv 二选一, 优先)")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--year", type=int, default=0, help="对比指定年份快照(默认最早)")
    ap.add_argument("--only-band", help="只处理某年龄带, 如 '老域(10年+)'/'新壳(<2年)'")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = []
    if args.domains:
        for line in open(args.domains, encoding="utf-8", errors="ignore"):
            d = line.strip().lower()
            if d:
                rows.append({"域名": d})
    else:
        import pandas as pd
        df = pd.read_csv(args.csv, dtype=str, encoding="utf-8-sig")
        need = {"域名": "域名", "注册年限": "注册年限", "标题": "标题", "Meta描述": "Meta描述", "正文摘要": "正文摘要"}
        missing = [k for k in need if k not in df.columns]
        if missing:
            print("台账缺列:", missing, file=sys.stderr)
            return 2
        df = df.drop_duplicates("域名")
        if args.only_band and "年龄带" in df.columns:
            df = df[df["年龄带"] == args.only_band]
        rows = df[list(need.values())].to_dict("records")
    if args.limit:
        rows = rows[: args.limit]
    print(f"待复查: {len(rows)} 个域名, 并发 {args.workers}", file=sys.stderr)

    def work(r):
        d = str(r.get("域名", "")).strip().lower()
        if not d or "." not in d:
            return None
        snap = earliest_snapshot(d)
        if not snap:
            return {"域名": d, "注册年限": r.get("注册年限", ""), "对比年份": "", "快照标题": "",
                    "当前标题": str(r.get("标题", ""))[:80], "历史词数": "", "当前词数": "",
                    "相似度": "", "主题漂移": "无法判断", "风险": "unknown-无历史快照", "备注": "Wayback 无该域名快照"}
        ts, orig = snap
        if args.year:
            ts = f"{args.year}0101000000"
            orig = d
        page = http_get(_WAYBACK.format(ts=ts, orig=orig))
        if not page:
            return {"域名": d, "注册年限": r.get("注册年限", ""), "对比年份": ts[:8], "快照标题": "",
                    "当前标题": str(r.get("标题", ""))[:80], "历史词数": "", "当前词数": "",
                    "相似度": "", "主题漂移": "无法判断", "风险": "unknown-快照抓取失败",
                    "备注": f"抓取失败 {ts[:8]}"}
        hist = text_of(page)
        now = " ".join(str(r.get(k, "") or "") for k in ("标题", "Meta描述", "正文摘要"))
        cmp = compare(hist, now)
        shift = None
        if cmp["sim"] is not None:
            shift = cmp["sim"] < 0.2
            if 0.2 <= cmp["sim"] <= 0.35:
                cmp["note"] = f"相似度{cmp['sim']} 处灰色地带, 建议人工开快照核对"
        age = None
        try:
            age = float(r.get("注册年限")) if r.get("注册年限") else None
        except ValueError:
            age = None
        risk = risk_of(age, shift, cmp["note"] or cmp["shift"] if shift is None else "")
        htitle = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        return {"域名": d, "注册年限": r.get("注册年限", ""), "对比年份": ts[:8],
                "快照标题": (htitle.group(1).strip()[:80] if htitle else ""),
                "当前标题": str(r.get("标题", ""))[:80],
                "历史词数": cmp["hist_words"], "当前词数": cmp["now_words"],
                "相似度": cmp["sim"] if cmp["sim"] is not None else "",
                "主题漂移": {True: "是", False: "否", None: "待人工"}.get(shift, "待人工"),
                "风险": risk,
                "备注": cmp["note"]}

    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(work, r): r for r in rows}
        done = 0
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"域名": r.get("域名", ""), "注册年限": r.get("注册年限", ""), "对比年份": "",
                       "快照标题": "", "当前标题": str(r.get("标题", ""))[:80], "历史词数": "",
                       "当前词数": "", "相似度": "", "主题漂移": "无法判断",
                       "风险": "unknown-异常", "备注": str(e)}
            if res:
                results.append(res)
            done += 1
            if done % 20 == 0:
                print(f"  {done}/{len(rows)} · {time.time()-t0:.0f}s", file=sys.stderr, flush=True)

    fieldnames = ["域名", "注册年限", "对比年份", "快照标题", "当前标题", "历史词数", "当前词数",
                  "相似度", "主题漂移", "风险", "备注"]
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)
    from collections import Counter
    print("完成:", len(results), "| 风险分布:", dict(Counter(r["风险"] for r in results)),
          file=sys.stderr)
    print(f"已写出: {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
