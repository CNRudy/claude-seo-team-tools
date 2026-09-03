#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preflight_check.py — 运行前环境体检（一键确认"这台机器能不能跑这套工具"）

在开始分析网址 / 跑体检 / 查 PageRank 之前，先执行本脚本：
它会逐项检查 ——
  1. Python 版本是否达标（>= 3.9）
  2. 仓库文件是否完整（内置 claude-seo 上游 + 3 个自研工具 + 示例）
  3. 依赖包是否装齐（requests / bs4 / lxml / trafilatura / openpyxl / langdetect / tldextract）
  4. 工具脚本能否被正常加载（导入冒烟测试，不发网络请求）
  5. 外网能否连通（先看 DNS，再发 HTTPS 请求；默认测 google / amazon / youtube / example）
  6. 可选能力探测（whois 命令、Common Crawl 缓存）——缺失不影响主流程，仅提示

用法：
  python3 tools/preflight_check.py                 # 标准体检
  python3 tools/preflight_check.py --json          # 输出 JSON（便于程序/表格读取）
  python3 tools/preflight_check.py --no-net        # 跳过联网检测（离线 / 纯内网用）
  python3 tools/preflight_check.py --targets https://a.com https://b.com  # 追加自定义连通目标
  python3 tools/preflight_check.py --timeout 6     # 每个站点的超时秒数（默认 8）

退出码：
  0 = 就绪（可能有"提示"级信息，不影响使用）
  2 = 有警告：能跑，但部分功能受限（如未装 whois / 个别站点连不通）
  1 = 有错误：不能正常跑（缺依赖 / 缺文件 / 完全没有外网）

纯 Python 标准库实现，任何 Python 3.9+ 环境都能直接运行。
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import importlib.util
import json
import os
import platform
import shutil
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------- 常量
MIN_PY = (3, 9)
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS_DIR)

# (相对路径, 说明) —— 仓库里必须具备的文件
REQUIRED_FILES = [
    ("claude-seo/scripts/fetch_page.py", "上游：安全抓取模块"),
    ("claude-seo/scripts/parse_html.py", "上游：页面解析模块"),
    ("claude-seo/scripts/url_safety.py", "上游：URL 安全层(SSRF 防护)"),
    ("claude-seo/scripts/content_quality.py", "上游：内容质量评分"),
    ("claude-seo/LICENSE", "上游 MIT 许可证(合规)"),
    ("tools/batch_site_analyzer.py", "自研：工具1 批量初筛"),
    ("tools/partner_health_check.py", "自研：工具2 四维体检"),
    ("tools/cc_batch_scan.py", "自研：工具3 PageRank 扫描"),
    ("examples/urls_sample.txt", "示例：可直接试跑的网址名单"),
]

# 必需 Python 包（batch_site_analyzer / partner_health_check 依赖）
REQUIRED_PKGS = [
    ("requests", "HTTP 请求"),
    ("bs4", "页面解析(BeautifulSoup)"),
    ("lxml", "XML/HTML 解析"),
    ("trafilatura", "正文抽取"),
    ("openpyxl", "Excel 导出"),
    ("langdetect", "语言检测"),
    ("tldextract", "域名提取"),
]

# 可选包（只在做台账统计/分析时用，跑工具本身不需要）
OPTIONAL_PKGS = [
    ("pandas", "台账统计/数据透视(可选)"),
]

# 默认外网连通性目标
DEFAULT_TARGETS = [
    "https://www.google.com",
    "https://www.amazon.com",
    "https://www.youtube.com",
    "https://example.com",
]


# ---------------------------------------------------------------- 工具函数
def path_ok(rel: str) -> bool:
    return os.path.isfile(os.path.join(ROOT, rel))


def check_pkg(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def detect_socks_env() -> list:
    """检测环境变量里是否有 SOCKS 代理（urllib/requests 不原生支持 socks5）。"""
    hits = []
    for k in ("ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "all_proxy", "https_proxy", "http_proxy"):
        v = os.environ.get(k, "").strip().lower()
        if v.startswith("socks"):
            hits.append(f"{k}={os.environ.get(k)}")
    return hits


def detect_http_proxy_env():
    for k in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        v = os.environ.get(k, "").strip()
        if v.lower().startswith("http"):
            return f"{k}={v}"
    return None


# ---------------------------------------------------------------- 网络探测
def _dns_ok(host: str, timeout: float) -> tuple:
    try:
        socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def _http_probe(url: str, timeout: float, no_proxy: bool) -> tuple:
    """返回 (是否到达服务器, 描述)。HTTP 4xx/5xx 也算到达（服务器有响应）。"""
    ctx = ssl.create_default_context()
    if no_proxy:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx))
    else:
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0 preflight-check"})
    try:
        with opener.open(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        # 4xx/5xx = 服务器可达，只是拒绝/限制，视为“网络通”
        return True, f"HTTP {e.code}(站点可达，被反爬限制属正常)"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def probe_target(url: str, timeout: float, no_proxy: bool) -> dict:
    host = urllib.parse.urlparse(url).netloc
    dns_ok, dns_msg = _dns_ok(host, timeout)
    if not dns_ok:
        return {"url": url, "host": host, "dns": False, "dns_msg": dns_msg, "http": False, "http_msg": "DNS 解析失败，跳过 HTTP"}
    http_ok, http_msg = _http_probe(url, timeout, no_proxy)
    return {"url": url, "host": host, "dns": True, "dns_msg": "OK", "http": http_ok, "http_msg": http_msg}


# ---------------------------------------------------------------- 冒烟测试
def smoke_import() -> tuple:
    """尝试加载 3 个自研工具（会连带加载上游 fetch_page/parse_html）。

    只 import 不执行，不发任何网络请求。返回 (ok, 细节文本)。
    """
    scripts_dir = os.path.join(ROOT, "claude-seo", "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    if TOOLS_DIR not in sys.path:
        sys.path.insert(0, TOOLS_DIR)

    mods = ["fetch_page", "parse_html", "batch_site_analyzer", "partner_health_check", "cc_batch_scan"]
    failed = []
    for m in mods:
        try:
            importlib.import_module(m)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{m}: {type(e).__name__}: {e}")
    if failed:
        return False, "导入失败: " + " | ".join(failed)
    return True, "fetch_page / parse_html / 3 个自研工具全部可加载"


# ---------------------------------------------------------------- 主流程
def main() -> int:
    ap = argparse.ArgumentParser(description="claude-seo-team-tools 运行前环境体检")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--no-net", action="store_true", help="跳过联网检测")
    ap.add_argument("--targets", nargs="*", default=[], help="追加自定义连通目标(https://...)")
    ap.add_argument("--timeout", type=float, default=8.0, help="网络超时秒数(默认 8)")
    ap.add_argument("--proxy", action="store_true", help="用系统 HTTP 代理探测(默认模拟工具直连，不带代理)")
    args = ap.parse_args()

    results = []  # (level, tag, msg)  level: pass/warn/fail/info

    # 1) Python 版本
    py = sys.version_info
    if (py.major, py.minor) >= MIN_PY:
        results.append(("pass", "Python 版本", f"{platform.python_version()} (要求 >= 3.9)"))
    else:
        results.append(("fail", "Python 版本", f"{platform.python_version()} 过低，要求 >= 3.9"))

    # 2) 仓库完整性
    missing = [f"{p}({d})" for p, d in REQUIRED_FILES if not path_ok(p)]
    if missing:
        results.append(("fail", "仓库完整性", f"缺少文件: {'; '.join(missing)}"))
    else:
        results.append(("pass", "仓库完整性", f"必备文件齐全 (内置 claude-seo + {len(REQUIRED_FILES)} 项)"))
    # 提示：claude-seo 目录是否为空壳
    if not os.path.isdir(os.path.join(ROOT, "claude-seo", "scripts")):
        results.append(("fail", "上游副本", "claude-seo/scripts 目录不存在，请重新 clone/解压完整仓库"))

    # 3) 依赖包
    miss_pkgs = [f"{p}({d})" for p, d in REQUIRED_PKGS if not check_pkg(p)]
    if miss_pkgs:
        results.append(("fail", "依赖包", "缺少: " + "; ".join(miss_pkgs) + " —— 请先运行 bash setup.sh"))
    else:
        results.append(("pass", "依赖包", f"{len(REQUIRED_PKGS)} 个必需包全部就绪"))
    for p, d in OPTIONAL_PKGS:
        if not check_pkg(p):
            results.append(("warn", f"可选包 {p}", f"未安装({d})；跑工具本身不需要，做台账统计时才用"))

    # 4) 冒烟加载
    if not miss_pkgs:
        ok, msg = smoke_import()
        if ok:
            results.append(("pass", "模块加载", msg))
        else:
            results.append(("fail", "模块加载", msg))

    # 5) 网络
    if args.no_net:
        results.append(("info", "联网检测", "已按 --no-net 跳过"))
    else:
        targets = list(DEFAULT_TARGETS) + [t for t in args.targets if t.startswith("http")]
        # SOCKS 代理提示
        socks = detect_socks_env()
        if socks:
            results.append(("warn", "SOCKS 代理", "检测到 " + "、".join(socks[:2]) + " —— Python 默认请求不自动走 SOCKS；若探测失败，请改用 HTTP 代理或先开启全局 VPN"))
        hp = detect_http_proxy_env()
        if hp and not args.proxy:
            results.append(("info", "HTTP 代理", f"环境变量 {hp} 存在；默认按工具实际行为做直连探测，如需走代理请加 --proxy"))

        with cf.ThreadPoolExecutor(max_workers=min(len(targets), 8)) as ex:
            futures = {ex.submit(probe_target, u, args.timeout, not args.proxy): u for u in targets}
            net_reports = [f.result() for f in futures]

        for r in net_reports:
            if r["dns"] and r["http"]:
                results.append(("pass", "连通性", f"{r['url']}  DNS OK · {r['http_msg']}"))
            elif r["url"] == "https://example.com":
                # example.com 是“全网通用探针”，它不通 = 完全没有外网，判为错误
                results.append(("fail", "连通性", f"{r['url']} 探测失败: {r['http_msg'] or r['dns_msg']}"))
            elif r["dns"] and not r["http"]:
                results.append(("warn", "连通性", f"{r['url']}  DNS 可解析但 HTTPS 不通: {r['http_msg']}"))
            else:
                results.append(("warn", "连通性", f"{r['url']}  DNS 失败: {r['dns_msg']}"))

        # 综合判定：example 通了就算“有外网”
        ex_ok = any(r["url"] == "https://example.com" and r["http"] for r in net_reports)
        ga_ok = sum(1 for r in net_reports if r["url"] in DEFAULT_TARGETS[:3] and r["http"])
        if not ex_ok:
            results.append(("fail", "网络结论", "通用探针 example.com 不通 —— 当前没有可用外网，请检查网络/代理后重试"))
        elif ga_ok < 3:
            bad = [r["url"].split("//")[1].split("/")[0] for r in net_reports if r["url"] in DEFAULT_TARGETS[:3] and not r["http"]]
            results.append(("warn", "网络结论", f"外网基本可达，但 {'、'.join(bad)} 不通 —— 抓 Google 系站点/YouTube 前请开启代理或 VPN；抓普通合作方站点不受影响"))
        else:
            results.append(("pass", "网络结论", "外网可达，可以开始抓取分析"))

    # 6) 可选能力
    if shutil.which("whois"):
        results.append(("pass", "whois", "已安装(域名历史检查可用)"))
    else:
        results.append(("warn", "whois", "未安装(域名历史检查 domain_history.py 不可用；macOS: brew install whois / Debian: apt install whois)"))
    cc_dir = os.path.expanduser("~/.cache/claude-seo/commoncrawl")
    if os.path.isdir(cc_dir) and any(f.endswith(".gz") for f in os.listdir(cc_dir)):
        results.append(("pass", "Common Crawl 缓存", f"已找到索引缓存: {cc_dir}"))
    else:
        results.append(("warn", "Common Crawl 缓存", f"未找到缓存({cc_dir})；PageRank 工具需先下载索引文件，其余工具不受影响"))

    # 汇总
    n_fail = sum(1 for lv, *_ in results if lv == "fail")
    n_warn = sum(1 for lv, *_ in results if lv == "warn")
    summary = {
        "python": platform.python_version(),
        "required": "ok" if not any(lv == "fail" and tag in ("依赖包", "仓库完整性", "上游副本") for lv, tag, _ in results) else "missing",
        "network": "ok" if not any(lv == "fail" and tag == "连通性" for lv, tag, _ in results) else "blocked",
        "fail": n_fail,
        "warn": n_warn,
    }

    if args.json:
        print(json.dumps({
            "summary": summary,
            "checks": [{"level": lv, "item": tag, "message": msg} for lv, tag, msg in results],
        }, ensure_ascii=False, indent=2))
    else:
        print("\n==== claude-seo-team-tools 运行前环境体检 ====\n")
        for lv, tag, msg in results:
            icon = {"pass": "[PASS]", "warn": "[WARN]", "fail": "[FAIL]", "info": "[INFO]"}[lv]
            print(f"  {icon} {tag:<16} {msg}")
        print("\n----------------------------------------------")
        if n_fail:
            print(f"  结论：发现 {n_fail} 个错误 / {n_warn} 个警告 —— 先解决错误再运行工具\n")
        elif n_warn:
            print(f"  结论：可以运行（有 {n_warn} 个警告，不影响主流程，留意提示即可）\n")
        else:
            print("  结论：✅ 环境就绪，可以开始分析\n")

    if n_fail:
        return 1
    if n_warn:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
