#!/usr/bin/env python3
"""域名遗产尽调·批量扫描 (domain_age_scan)

对一批域名批量做"注册年龄 + 到期 + 注册商"硬信号扫描：
- 主通道: 系统 whois 命令（复用 claude-seo/scripts/domain_history.py 的 lookup 解析）
- 兜底通道: RDAP over HTTPS (ICANN 标准, 443 端口, verisign 直连或 rdap.org 聚合)

背景：SEO 灰产常用"过期老域名套壳"（注册很久的老域名被收购后整个换主题做
coupon/赌博/黑五站）。注册年龄是尽调第一道硬信号——<2 年的新域名本身可疑
（正规联盟客站点极少用新域名），配合下游"内容主题对比"才能定 high/medium/low。

用法:
    python domain_age_scan.py --domains d.txt -o out.csv          # 域名列表
    python domain_age_scan.py --csv 台账.csv -o out.csv           # 从台账读"域名"列(自动去重+取注册域)
    python domain_age_scan.py --csv 台账.csv --workers 12 -o out.csv

输出列: 域名, 注册日期, 注册年限, 到期日, 注册商, 来源(whois/rdap/fail), 年龄带, 备注
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

# ---- 定位内置 claude-seo 并复用 domain_history.lookup（whois 主通道）----
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_SEO_SCRIPTS = os.path.join(_REPO_ROOT, "claude-seo", "scripts")
if not os.path.isdir(_SEO_SCRIPTS):
    _SEO_SCRIPTS = os.path.join(_REPO_ROOT, "batch_analyzer", "claude-seo", "scripts")
for _p in (_SEO_SCRIPTS, _HERE):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import domain_history as dh  # 上游脚本: lookup() + assess_risk()
except Exception as _e:  # 上游不可用则回退到纯 RDAP
    dh = None
    print(f"[warn] claude-seo domain_history 不可用, 仅走 RDAP: {_e}", file=sys.stderr)

try:
    from tldextract import TLDExtract
    _tldex = TLDExtract(suffix_list_urls=())
except Exception:
    _tldex = None


def reg_domain(host: str) -> str:
    """取 eTLD+1 注册域(小写, 去 www/协议/路径/端口)。whois/RDAP 查子域无效。"""
    h = host.strip().lower()
    h = re.sub(r"^[a-z]+://", "", h)
    h = h.split("/")[0].split("?")[0].split("#")[0]
    h = h.split(":")[0]
    h = h.removeprefix("www.")
    if not h or "." not in h:
        return h
    if _tldex is not None:
        try:
            r = _tldex(h)
            if r.domain and r.suffix:
                return f"{r.domain}.{r.suffix}"
        except Exception:
            pass
    parts = h.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else h


# ---- RDAP 兜底通道 ----
_RDAP_COM_NET = "https://rdap.verisign.com/{tld}/v1/domain/{d}"
_RDAP_ORG = "https://rdap.org/domain/{d}"


def _rdap_fetch(url: str, timeout: float = 10) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "domain-age-scan/1.0", "Accept": "application/rdap+json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None


def rdap_lookup(domain: str) -> dict:
    """RDAP 查询: .com/.net 直连 verisign, 其它走 rdap.org(自动重定向到注册局)。"""
    tld = domain.rsplit(".", 1)[-1].lower()
    urls = []
    if tld in ("com", "net"):
        urls.append(_RDAP_COM_NET.format(tld=tld, d=domain))
    urls.append(_RDAP_ORG.format(d=domain))

    for u in urls:
        data = _rdap_fetch(u)
        if not data:
            continue
        events = {e.get("eventAction"): e.get("eventDate") for e in data.get("events", []) if e.get("eventDate")}
        created = (events.get("registration") or "").replace("Z", "").split(".")[0]
        expires = (events.get("expiration") or "").replace("Z", "").split(".")[0]
        registrar = None
        for ent in data.get("entities", []):
            if "registrar" in (ent.get("roles") or []):
                vc = ent.get("vcardArray") or []
                if len(vc) >= 2:
                    for item in vc[1]:
                        if item and len(item) >= 3 and item[0] == "fn":
                            registrar = item[3]
                            break
                break
        return {"domain": domain, "whois_source": "rdap", "created": created or None,
                "updated": None, "expires": expires or None,
                "registrar": registrar, "years_registered": None, "notes": ["rdap"]}
    return {"domain": domain, "whois_source": "fail", "created": None, "updated": None,
            "expires": None, "registrar": None, "years_registered": None, "notes": ["rdap-unreachable"]}


def lookup_one(domain: str) -> dict:
    """先 whois(上游 lookup), 无 created 再 RDAP 兜底。"""
    rec = None
    if dh is not None:
        try:
            rec = dh.lookup(domain)
        except Exception:
            rec = None
    if rec and rec.get("created"):
        rec["whois_source"] = "whois"
        return rec
    rd = rdap_lookup(domain)
    if rd.get("created"):
        if rec and not rd.get("registrar"):
            rd["registrar"] = rec.get("registrar")
        return rd
    # 双通道都失败: 保留 whois 原始 notes(若有)
    return rec if rec else rd


def years_of(created: str) -> float | None:
    if not created:
        return None
    try:
        d0 = datetime.fromisoformat(created).date()
    except ValueError:
        try:
            d0 = datetime.strptime(created, "%Y-%m-%d").date()
        except ValueError:
            return None
    return round((date.today() - d0).days / 365.25, 2)


def age_band(years: float | None) -> str:
    if years is None:
        return "未知"
    if years < 2:
        return "新壳(<2年)"
    if years < 5:
        return "年轻(2-5年)"
    if years < 10:
        return "中年(5-10年)"
    return "老域(10年+)"


def _norm_dt(dt_str: str | None) -> str:
    if not dt_str:
        return ""
    return dt_str[:10]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--domains", help="每行一个域名的文本文件")
    src.add_argument("--csv", help="含'域名'列的台账 CSV(自动去重、取注册域)")
    ap.add_argument("-o", "--out", required=True, help="输出 CSV 路径")
    ap.add_argument("--workers", type=int, default=8, help="并发数(默认8)")
    ap.add_argument("--limit", type=int, default=0, help="只扫前 N 个(测试用)")
    args = ap.parse_args()

    if args.domains:
        doms = []
        for line in open(args.domains, encoding="utf-8", errors="ignore"):
            d = reg_domain(line.strip())
            if d and "." in d:
                doms.append(d)
    else:
        with open(args.csv, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if "域名" not in (reader.fieldnames or []):
                print("台账缺少'域名'列, 现有列:", reader.fieldnames, file=sys.stderr)
                return 2
            doms = [reg_domain(r.get("域名") or "") for r in reader]
    doms = sorted(set(d for d in doms if d and "." in d))
    if args.limit:
        doms = doms[: args.limit]
    print(f"待扫描唯一注册域: {len(doms)} 个, 并发 {args.workers}", file=sys.stderr)

    results = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(lookup_one, d): d for d in doms}
        done = 0
        for fut in as_completed(futs):
            d = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:
                rec = {"domain": d, "whois_source": "fail", "created": None, "updated": None,
                       "expires": None, "registrar": None, "years_registered": None, "notes": [f"err:{e}"]}
            yrs = rec.get("years_registered")
            if yrs is None:
                yrs = years_of(rec.get("created"))
            results.append({
                "域名": rec.get("domain", d),
                "注册日期": _norm_dt(rec.get("created")),
                "注册年限": yrs if yrs is not None else "",
                "到期日": _norm_dt(rec.get("expires")),
                "注册商": rec.get("registrar") or "",
                "来源": rec.get("whois_source", "fail"),
                "年龄带": age_band(yrs),
            })
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(doms)} 完成, 已用 {time.time()-t0:.0f}s", file=sys.stderr)

    ok = sum(1 for r in results if r["注册年限"] != "")
    print(f"完成 {len(results)} 个, 成功取得注册日期 {ok} 个 ({ok/len(results)*100:.1f}%), "
          f"总耗时 {time.time()-t0:.0f}s", file=sys.stderr)

    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["域名", "注册日期", "注册年限", "到期日", "注册商", "来源", "年龄带"])
        w.writeheader()
        w.writerows(sorted(results, key=lambda r: (r["注册年限"] == "", r["注册年限"] or 0)))
    print(f"已写出: {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
