#!/usr/bin/env bash
# =============================================================
#  claude-seo 团队工具 - 一键初始化脚本 (macOS / Linux)
#
#  做什么：
#    1. 检查上游依赖 claude-seo 是否就绪（本仓库已内置 vendor 副本）
#    2. 创建独立的 Python 环境 .venv-seo
#    3. 安装全部 Python 依赖
#
#  用法：  首次使用执行一次即可
#    bash setup.sh
# =============================================================
set -euo pipefail

cd "$(dirname "$0")"

echo "==> [1/3] 检查上游依赖 claude-seo (内置 vendor)..."
if [ -d "claude-seo/scripts" ]; then
  echo "    已就绪：仓库内置了 claude-seo 副本（scripts/ 共 $(ls claude-seo/scripts/*.py 2>/dev/null | wc -l | tr -d ' ') 个脚本）。"
else
  echo "    未找到内置 claude-seo，尝试从 GitHub 下载..."
  if command -v git >/dev/null 2>&1; then
    git clone --depth 1 https://github.com/AgriciDaniel/claude-seo.git claude-seo
  else
    echo "    未检测到 git 且缺少内置副本，请先安装 git 后重试。"
    exit 1
  fi
fi

echo "==> [2/3] 创建 Python 虚拟环境 .venv-seo ..."
if [ ! -d ".venv-seo" ]; then
  python3 -m venv .venv-seo
fi

echo "==> [3/3] 安装 Python 依赖..."
.venv-seo/bin/pip install --quiet --upgrade pip
.venv-seo/bin/pip install --quiet -r tools/requirements.txt

echo ""
echo "✅ 初始化完成！现在可以开始使用："
echo ""
echo "   # ① 批量初筛：网址一行一个放进 urls.txt"
echo "   .venv-seo/bin/python tools/batch_site_analyzer.py --input urls.txt"
echo ""
echo "   # ② 四维体检（A/B/C/D 分级）"
echo "   .venv-seo/bin/python tools/partner_health_check.py --input 有效名单.txt"
echo ""
echo "   # 示例文件可直接体验："
echo "   .venv-seo/bin/python tools/batch_site_analyzer.py --input examples/urls_sample.txt"
