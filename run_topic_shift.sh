#!/usr/bin/env bash
# ============================================================
# 主题漂移复查（尽调流水线第 5 关）一键运行
#
# 作用: 对比"老域名当年的内容主题 vs 现在的内容主题"，
#       识别灰产最爱用的"过期老域名套壳"(expired-domain abuse)。
#
# 网络要求: 本脚本需要访问 web.archive.org（Wayback Machine）。
#          中国大陆网络直连不通 —— 请先开启 VPN/代理再运行！
#          预检: curl -s -m 5 -o /dev/null -w "%{http_code}" https://web.archive.org/
#                返回 200 再跑本脚本。
#
# 用法:
#   bash run_topic_shift.sh                 # 用内置样例(30 个老域C/D级嫌疑)
#   bash run_topic_shift.sh 你的台账.csv    # 或指定自己的台账
# ============================================================
set -e
cd "$(dirname "$0")"

INPUT="${1:-examples/套壳嫌疑30_主题复查输入.csv}"
OUT="主题漂移复查结果.csv"

echo "==== 第 0 步: 运行前网络检查 ===="
CODE=$(curl -s -m 6 -o /dev/null -w "%{http_code}" "https://web.archive.org/" 2>/dev/null || echo 000)
if [ "$CODE" = "200" ]; then
  echo "  [PASS] web.archive.org 可达 (HTTP $CODE)"
else
  echo "  [FAIL] web.archive.org 不可达 (HTTP $CODE)"
  echo "  -> 请先开启能访问 archive.org 的 VPN/代理, 再重跑本脚本"
  echo "  -> 检查: curl -s -m 5 -o /dev/null -w '%{http_code}' https://web.archive.org/"
  exit 1
fi

echo ""
echo "==== 第 1 步: 准备 Python 环境 ===="
PY="python3"
[ -x .venv-seo/bin/python ] && PY=".venv-seo/bin/python"
if [ "$PY" = "python3" ]; then
  echo "  未找到 .venv-seo, 尝试用系统 python3 (需已装 pandas/trafilatura)"
fi
if ! "$PY" -c "import pandas" 2>/dev/null; then
  echo "  缺少 pandas, 尝试安装..."
  "$PY" -m pip install -q pandas 2>/dev/null || { echo "  [FAIL] pandas 安装失败, 请先运行 bash setup.sh"; exit 1; }
fi
echo "  [PASS] Python 环境就绪 ($PY)"

echo ""
echo "==== 第 2 步: 开始主题漂移复查 ===="
echo "  输入: $INPUT  |  输出: $OUT"
"$PY" tools/topic_shift_check.py --csv "$INPUT" -o "$OUT" --workers 8

echo ""
echo "✅ 完成! 结果文件: $(pwd)/$OUT"
echo "  打开后看 '风险' 列: high = 坐实套壳(拉黑) / medium = 警惕 / low = 正常老站"
