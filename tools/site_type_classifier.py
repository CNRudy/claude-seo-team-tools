#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具 4：站点推广类型分类器（site_type_classifier.py）
============================================================
一句话：给一批"网站域名/首页正文/摘要"，自动判断它属于哪种推广站点，
输出 CSV 新增 4 列：站点类型 / 类型得分 / 类型置信 / 命中词。

能分出的 7 类（+ 未知）：
    deal折扣券站 · 评测榜单站(⭐ 榜单/测评联盟客主力) · 返利站 · 比价站 ·
    内容博客/种草 · 新闻媒体 · 论坛/社区 · 未知/待人工

三种用法：
  ① 对已有表格(如四维体检结果)补一列类型 —— 纯离线，标准库即可，无需联网
     .venv-seo/bin/python tools/site_type_classifier.py \
         --input 体检结果.csv --text-col 正文摘要 --domain-col 域名 -o 分类结果.csv
  ② 给一批网址，联网抓首页正文后再分类（推荐：会优先用 trafilatura 提正文，更准）
     .venv-seo/bin/python tools/site_type_classifier.py \
         --fetch --input urls.txt -o 分类结果.csv
  ③ 单条快速试
     python3 tools/site_type_classifier.py --text "best wireless earbuds 2026 reviews tested"
     python3 tools/site_type_classifier.py --urls https://www.cnet.com

联网抓取注意：境外站点需要能访问外网；如在受限网络下运行，请先 export HTTPS_PROXY / HTTP_PROXY，
脚本会自动读取环境变量代理（也支持 --proxy 显式指定）。

分类逻辑：7 类词表打分 —— 强词(3分)/弱词(1分)/域名命中(额外4分)，取最高分类；
得 0 分 → "未知/待人工"（诚实标注，不硬塞）。
置信度：高(≥6分且≥2强词或命中域名关键词) / 中(≥3分) / 低(<3分) / 无法判断。
"""
import argparse
import csv
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------------- 分类器词表
TYPES = {
    "deal折扣券站": dict(
        strong=["coupon", "coupons", "discount code", "discount codes", "promo code", "promo codes",
                "voucher", "best deals", "top deals", "deal of the day", "today's best deals",
                "deals and discounts", "clearance", "coupon code", "promo"],
        weak=["discount", "deals", "% off", "free shipping", "save up", "sale prices",
              "biggest savings", "retailmenot", "groupon"],
        dom=["coupon", "deals", "deal", "discount", "promo", "voucher", "codes", "bargain",
             "penny", "grabon", "savings", "steals"],
    ),
    "评测榜单站": dict(
        strong=["review", "reviews", "best ", "top ", "roundup", "tested", "we buy and test",
                "buying guide", "gift guide", "we compare", "comparison", "hands-on",
                "best products", "picks", "editor's pick", "we tried", "to help you choose",
                "find your perfect", "choose the"],
        weak=["recommend", "rating", "favorite", "of 2024", "of 2025", "of 2026", "of 2027",
              "shopping decisions", "find the best", "help you find"],
        dom=["review", "top", "best", "pick", "choice", "rank", "roundup", "choosing",
             "compare", "score", "select", "critic", "verdict", "gear"],
    ),
    "返利站": dict(
        strong=["cashback", "cash back", "cash-back", "rebate"],
        weak=["refund", "points", "earn back", "rewards"],
        dom=["cashback", "rebate", "cash-back"],
    ),
    "比价站": dict(
        strong=["compare prices", "price comparison", "shopping comparison", "price tracker",
                "cheapest", "compare prices on"],
        weak=["price", "prices", "products from", "merchants"],
        dom=["price", "pricerunner", "idealo", "kelkoo", "compare", "prices"],
    ),
    "内容博客/种草": dict(
        strong=["how to", "tips", "ideas", "for mom", "parenting", "diy", "recipe", "lifestyle",
                "things to", "ways to", "inspiration", "story", "what to", "when mothers",
                "craft", "blog post"],
        weak=["guide", "advice", "feature", "article", "gift ideas", "family", "home",
              "thoughts", "community", "event", "announcement"],
        dom=["blog", "mom", "parenting", "lifestyle", "life", "diary", "tips", "magazine",
             "daily", "times", "post"],
    ),
    "新闻媒体": dict(
        strong=["latest news", "breaking", "announces", "launches", "unveils", "report says",
                "vulnerability", "wins award", "inducted"],
        weak=["news", "today", "says", "live", "update", "week"],
        dom=["news", "times", "post", "herald", "tribune", "chronicle", "observer", "mirror",
             "star", "daily", "journal", "wire", "cnet", "magazine"],
    ),
    "论坛/社区": dict(
        strong=["forum", "join the discussion", "discussion boards", "threads", "post your",
                "member login"],
        weak=["discussion", "community", "users"],
        dom=["forum", "community", "reddit", "board"],
    ),
}

_ORDER = ["deal折扣券站", "评测榜单站", "返利站", "比价站", "内容博客/种草", "新闻媒体", "论坛/社区"]
_DEFAULT_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


# ---------------------------------------------------------------- 分类核心
def _hit(text, w):
    w = w.lower()
    if " " in w or "-" in w:
        return w in text
    return re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text) is not None


def classify(dom="", text=""):
    """返回 (类型, 得分, 置信度, 命中词串)"""
    dom = str(dom or "").lower().replace("www.", "").strip()
    t = (" " + str(text or "").lower())[:2600]
    text_all = " ".join([dom, t])
    scores, sigs = {}, {}
    for typ, d in TYPES.items():
        s, ss = 0, []
        for w in d["strong"]:
            if _hit(text_all, w):
                s += 3
                ss.append(w)
        for w in d["weak"]:
            if _hit(text_all, w):
                s += 1
        db = [w for w in d["dom"] if w in dom]
        if db:
            s += 4
            ss += ["域:" + x for x in db[:2]]
        scores[typ], sigs[typ] = s, ss
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "未知/待人工", 0, "无法判断", ""
    sc = scores[best]
    wordsig = [x for x in sigs[best] if not x.startswith("域:")][:4]
    domsig = [x for x in sigs[best] if x.startswith("域:")][:2]
    nstrong = len(wordsig)
    if sc >= 6 and (nstrong >= 2 or domsig):
        conf = "高"
    elif sc >= 3:
        conf = "中"
    else:
        conf = "低"
    return best, sc, conf, "/".join(wordsig + domsig)[:200]


# ---------------------------------------------------------------- 联网抓正文
def _strip_html(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<(nav|footer|header|aside)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text)


def _fetch_one(url, proxy, timeout, with_trafilatura, retries=3):
    """抓单个 URL 正文；retries: 失败重试次数（代理出口节点偶发抖动，重试可显著提升成功率）"""
    url = url if url.lower().startswith("http") else "https://" + url
    last_err = ""
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(0.4 * attempt)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": _DEFAULT_UA,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.8,de;q=0.5",
                "Accept-Encoding": "identity",
                "Connection": "close",
            })
            if proxy:
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
            else:
                opener = urllib.request.build_opener()
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                status = getattr(resp, "status", 200)
                if not raw or status >= 400:
                    last_err = f"http-{status}"
                    continue
                data = raw.decode("utf-8", "ignore")
            text = ""
            if with_trafilatura:
                try:
                    import trafilatura
                    text = trafilatura.extract(data, include_comments=False,
                                               include_tables=False, favor_precision=True) or ""
                except Exception:
                    text = ""
            if len(text.strip()) < 200:
                fb = _strip_html(data)
                if len(fb) > len(text):
                    text = fb
            return text[:3000], None
        except Exception as e:
            reason = getattr(e, "reason", None)
            last_err = f"{type(e).__name__}:{str(reason)[:60]}" if reason else type(e).__name__[:30]
    return None, last_err


def _fetch_batch(urls, proxy, timeout, workers):
    try:
        import trafilatura  # noqa: F401
        has_trf = True
    except Exception:
        has_trf = False
    if not has_trf:
        print("  [warn] 未安装 trafilatura，正文提取降级为纯正则（精度略低）。"
              "建议先跑 bash setup.sh 安装依赖。", file=sys.stderr)
    out = {}

    def work(u):
        t, e = _fetch_one(u, proxy, timeout, has_trf)
        return u, t, e

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, u) for u in urls]
        n = 0
        for fut in as_completed(futs):
            u, t, e = fut.result()
            n += 1
            out[u] = (t, e)
            if n % 25 == 0:
                print(f"  ...抓取 {n}/{len(urls)}", file=sys.stderr)
    return out, has_trf


# ---------------------------------------------------------------- 加载输入
def _norm_url(u):
    u = str(u).strip().lower()
    m = re.search(r"\]\((https?://[^)]+)\)", u)
    if m:
        u = m.group(1)
    u = re.sub(r"^https?://", "", u).rstrip("/")
    return u


def load_inputs(args):
    """返回 list[dict]: {dom, text, src, extra}"""
    items = []
    if args.text:
        items.append({"dom": "", "text": args.text, "src": "命令行文本", "extra": {}})
    if args.urls:
        for u in args.urls:
            items.append({"dom": _norm_url(u), "text": "", "src": "待抓取", "extra": {"url": u}})
    if args.input:
        path = args.input
        if path.lower().endswith(".csv"):
            rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
            cols = rows[0].keys() if rows else []
            dom_col = args.domain_col or (args.domain_col in cols and args.domain_col) or \
                next((c for c in ("域名", "domain", "Domain", "URL", "url") if c in cols), None)
            txt_cols = [c for c in (args.text_col.split(",") if args.text_col else [])] or \
                [c for c in ("正文摘要", "Meta描述", "标题", "摘要", "text", "Text", "description", "title")
                 if c in cols]
            if not txt_cols:
                sys.exit(f"[err] 在 CSV 列中找不到文本列（现有列: {list(cols)}）。"
                         "请用 --text-col 指定。")
            for r in rows:
                text = " ".join(str(r.get(c) or "") for c in txt_cols).strip()
                dom = str(r.get(dom_col) or "") if dom_col else ""
                items.append({"dom": dom, "text": text, "src": f"文件 {os.path.basename(path)}",
                              "extra": dict(r)})
        else:
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "\t" in line:
                    dom, text = line.split("\t", 1)
                    items.append({"dom": dom.strip(), "text": text.strip(),
                                  "src": f"文件 {os.path.basename(path)}", "extra": {}})
                elif "|" in line:
                    dom, text = line.split("|", 1)
                    items.append({"dom": dom.strip(), "text": text.strip(),
                                  "src": f"文件 {os.path.basename(path)}", "extra": {}})
                else:
                    items.append({"dom": _norm_url(line), "text": "", "src": "待抓取",
                                  "extra": {"url": line.strip()}})
    return items


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description="站点推广类型分类器",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("--input", help="输入文件：CSV(按列) 或 TXT(每行: 域名|文本，或 --fetch 时的网址列表)")
    ap.add_argument("--text-col", help="CSV 中承载正文/摘要的列名（默认自动找 正文摘要/Meta描述/标题；多列用逗号分隔）")
    ap.add_argument("--domain-col", help="CSV 中域名列名（默认自动找 域名/Domain/URL）")
    ap.add_argument("--urls", nargs="*", help="直接给网址（配合 --fetch）")
    ap.add_argument("--text", help="单条文本试分类")
    ap.add_argument("--fetch", action="store_true", help="对网址联网抓首页正文后再分类")
    ap.add_argument("-o", "--output", help="输出 CSV 路径（默认自动生成）")
    ap.add_argument("--workers", type=int, default=8, help="抓取并发数（默认 8）")
    ap.add_argument("--timeout", type=float, default=15, help="单请求超时秒数（默认 15）")
    ap.add_argument("--proxy", default=os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"),
                    help="代理地址（默认读 HTTPS_PROXY/HTTP_PROXY 环境变量）")
    args = ap.parse_args()

    if not (args.input or args.urls or args.text):
        ap.print_help()
        sys.exit(1)

    items = load_inputs(args)
    if not items:
        sys.exit("[err] 没有读到任何输入。")
    print(f"[i] 共 {len(items)} 条待分类", file=sys.stderr)

    if args.fetch:
        urls = [it["extra"]["url"] if it["extra"].get("url") else
                ("https://" + it["dom"] if it["dom"] else "") for it in items]
        urls = [u for u in urls if u]
        if not urls:
            sys.exit("[err] --fetch 需要网址输入（--input 每行一个 URL，或 --urls）。")
        print(f"[i] 联网抓取 {len(urls)} 站 (并发 {args.workers}, 超时 {args.timeout}s, 代理={args.proxy or '直连'})",
              file=sys.stderr)
        fetched, _ = _fetch_batch(urls, args.proxy, args.timeout, args.workers)
        for it in items:
            key = it["extra"].get("url") or ("https://" + it["dom"])
            t, e = fetched.get(key, (None, "未抓取"))
            it["text"] = t or ""
            it["src"] = f"联网抓取({e})" if not t else "联网抓取正文"
            if not t:
                it["text"] = it["dom"]  # 抓取失败时至少保留域名信号

    out_rows, n_typed = [], 0
    for it in items:
        dom = it["dom"]
        typ, sc, conf, hits = classify(dom=dom, text=it["text"])
        if typ != "未知/待人工":
            n_typed += 1
        row = dict(it["extra"])
        row.setdefault("域名", dom)
        row["域名"] = dom
        row.setdefault("文本/摘要", it["text"][:120])
        row["站点类型"] = typ
        row["类型得分"] = sc
        row["类型置信"] = conf
        row["命中词"] = hits
        row["文本来源"] = it["src"]
        out_rows.append(row)

    fieldnames = list(out_rows[0].keys())
    out_path = args.output or ("站点类型分类结果.csv")
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(out_rows)
    print(f"\n[done] 已写 {out_path}（{len(out_rows)} 行；判出类型 {n_typed} 条，"
          f"未知/待人工 {len(out_rows) - n_typed} 条）")


if __name__ == "__main__":
    main()
