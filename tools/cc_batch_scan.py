#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地批量扫描 Common Crawl ranks 索引，为一批域名提取 PageRank 指标。

用法:
    python cc_batch_scan.py --domains ab_domains.txt --ranks <path>.txt.gz [--json out.json] [--csv out.csv]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import sys
import time

RANKS_DEFAULT = os.path.expanduser(
    "~/.cache/claude-seo/commoncrawl/cc-main-2026-jan-feb-mar-domain-ranks.txt.gz")


def reversed_domain(d: str) -> str:
    """google.com -> com.google"""
    d = d.strip().lower().rstrip(".")
    return ".".join(reversed(d.split(".")))


def scan(domains: list, ranks_path: str, max_lines: int = 0) -> dict:
    """Scan the gzip ranks file once, returning metrics per domain."""
    # Build lookup keyed by reversed domain
    want = {reversed_domain(d): d for d in domains}
    found = {}
    counts = {"total_lines": 0, "matched": 0}

    t0 = time.time()
    with gzip.open(ranks_path, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            counts["total_lines"] += 1
            fields = line.split("\t")
            if len(fields) < 6:
                continue
            # format: harmonicc_pos \t harmonicc_val \t pr_pos \t pr_val \t host_rev \t n_hosts
            host_rev = fields[4]
            if host_rev in want:
                domain = want[host_rev]
                found[domain] = {
                    "harmonic_centrality_rank": int(fields[0]) if fields[0].isdigit() else None,
                    "harmonic_centrality": float(fields[1]) if _isfloat(fields[1]) else None,
                    "pagerank_rank": int(fields[2]) if fields[2].isdigit() else None,
                    "pagerank": float(fields[3]) if _isfloat(fields[3]) else None,
                    "n_hosts": int(fields[5]) if fields[5].isdigit() else None,
                }
                counts["matched"] += 1
                if max_lines and counts["matched"] >= max_lines:
                    break
            if counts["total_lines"] % 5000000 == 0:
                print(f"... {counts['total_lines']/1e6:.0f}M 行已扫, 命中 {counts['matched']}, "
                      f"{time.time()-t0:.0f}s", flush=True)

    counts["seconds"] = round(time.time() - t0, 1)
    return {"found": found, "counts": counts}


def _isfloat(s: str) -> bool:
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="批量扫描 CC ranks 索引")
    ap.add_argument("--domains", required=True, help="域名列表文件（每行一个）")
    ap.add_argument("--ranks", default=RANKS_DEFAULT, help="ranks.txt.gz 路径")
    ap.add_argument("--json", help="输出 JSON 路径")
    ap.add_argument("--csv", help="输出 CSV 路径")
    args = ap.parse_args()

    with open(args.domains, "r", encoding="utf-8") as f:
        domains = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    domains = sorted(set(domains))
    print(f"待查询域名: {len(domains)}")
    if not os.path.exists(args.ranks):
        print(f"索引文件不存在: {args.ranks}")
        return 1

    res = scan(domains, args.ranks)
    found, counts = res["found"], res["counts"]
    print(f"\n扫描完成: {counts['total_lines']/1e6:.0f}M 行, 命中 {counts['matched']} 个域名, "
          f"耗时 {counts['seconds']}s")
    missing = [d for d in domains if d not in found]
    print(f"未命中(低于阈值/未被收录): {len(missing)}")

    # 输出命中详情
    rows = []
    for d in sorted(found):
        m = found[d]
        rows.append({
            "domain": d, "pagerank": m["pagerank"],
            "pagerank_rank": m["pagerank_rank"],
            "harmonic_centrality": m["harmonic_centrality"],
            "n_hosts": m["n_hosts"],
        })
        print(f"  {d}: PR={m['pagerank']} rank={m['pagerank_rank']} "
              f"HC={m['harmonic_centrality']} hosts={m['n_hosts']}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"found": found, "missing": missing, "counts": counts}, f,
                      ensure_ascii=False, indent=2)
        print(f"JSON: {args.json}")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["domain", "pagerank", "pagerank_rank",
                                              "harmonic_centrality", "n_hosts"])
            w.writeheader()
            w.writerows(rows)
            for d in sorted(missing):
                w.writerow({"domain": d, "pagerank": "", "pagerank_rank": "",
                            "harmonic_centrality": "", "n_hosts": ""})
        print(f"CSV: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
