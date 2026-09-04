---
name: partner-site-tools
description: >
  合作方站点分析工具箱 —— 当用户要对一批 Amazon 推广合作方 / 联盟客 / 红人的站点做批量分析与评估时使用：
  站点有效性初筛、四维体检评级(A/B/C/D)、Common Crawl PageRank 扫描、站点推广类型分类
  (deal折扣券站 / 评测榜单站 / 返利站 / 比价站 / 内容博客种草 / 新闻媒体 / 论坛社区)、
  域名注册年龄尽调(识别新壳<2年/套壳嫌疑)、Wayback 主题漂移复查(坐实老域套壳)、
  以及把结果打标回写本地台账 CSV 或飞书多维表格。凡提到 claude-seo-team-tools 仓库、
  站点类型分类、域名尽调、套壳识别、榜单型联盟客开发池、合作方健康检查/四维体检时使用。
  本 skill 只做「分析+评级+分类+尽调」；红人发现/评分走 kol-fit-scoring 等其他 skill。
agent_created: true
---

# 合作方站点分析工具箱 (partner-site-tools)

调用 GitHub 仓库 **claude-seo-team-tools** 里的 6 个 Python 工具，对推广合作方站点做
「初筛 → 四维体检 → PageRank → 类型分类 → 域名尽调 → 主题漂移复查」的端到端评估。
本 skill 是**薄壳**：只写调用约定与业务口径，不复制脚本——改逻辑只改仓库，push 一次全局生效。

## 1. 仓库定位与准备

仓库默认位置（本机开发机）：

```
REPO=/Users/coscod/WorkBuddy/2026-08-21-15-58-03/outputs/claude-seo-team-tools
```

其他机器先 clone（公开仓库）：

```bash
git clone https://github.com/CNRudy/claude-seo-team-tools
cd claude-seo-team-tools && bash setup.sh        # 建 venv + 装依赖
```

运行统一用 venv 里的 Python（避免污染系统环境）：

```bash
PY=<仓库所在项目>/.venv-seo/bin/python   # 本机；clone 后按 setup.sh 提示
$PY tools/<脚本>.py ...
```

动手前先跑环境体检（Python/依赖/外网/PageRank 缓存，退出码 0 就绪 / 2 警告 / 1 错误）：

```bash
$PY tools/preflight_check.py            # 带 --no-net 可跳过联网；--proxy 走 HTTP 代理探测
```

## 2. 工具速查

| # | 脚本 | 功能 | 关键参数 |
|---|---|---|---|
| 1 | `batch_site_analyzer.py` | 站点有效性初筛（可访问/内容/标题/Meta/摘要） | `--input 每行URL的txt` 或 `--urls u1 u2`；`--workers 5` `--output out.xlsx` |
| 2 | `partner_health_check.py` | 四维体检 → 分级 A/B/C/D（内容/结构/权威/表现） | `--input urls.txt`；`--pagerank` 附加外链画像(慢) |
| 3 | `cc_batch_scan.py` | Common Crawl PageRank 批量查 | `--domains d.txt --ranks <cc索引.gz> --csv out.csv`（需先下载 CC 索引） |
| 4 | `site_type_classifier.py` | **站点推广类型分类**（7 类+未知） | 三种模式见 §3 |
| 5 | `domain_age_scan.py` | 域名注册年龄尽调（RDAP 优先+whois 兜底） | `--csv 台账.csv` 或 `--domains d.txt`；`-o out.csv`；`--workers 8` |
| 6 | `topic_shift_check.py` | Wayback 主题漂移复查（老域套壳坐实） | `--csv 台账.csv --only-band "老域(10年+)" -o out.csv` |

一键运行第 6 关（自带网络预检，认代理 env）：`bash run_topic_shift.sh [你的台账.csv]`

## 3. 站点类型分类器（核心高频）

7 类词表打分：强词 3 分 / 弱词 1 分 / 域名命中 4 分；取最高分类，全零 →「未知/待人工」。
输出列：`站点类型 / 类型得分 / 类型置信(高中低·无法判断) / 命中词`。命中词列供人工复核误判。

三种调用模式：

```bash
# ① 单条文本试分类（快速验证词表）
$PY tools/site_type_classifier.py --text "Best wireless earbuds 2026: we tested 20 pairs, these are our picks"

# ② CSV 补列（最常用：给台账/候选清单批量打类型）
$PY tools/site_type_classifier.py --input 台账.csv --text-col 正文摘要 --domain-col 域名 -o 结果.csv
#   --text-col 默认自动找 正文摘要/Meta描述/标题；--domain-col 默认自动找 域名/Domain/URL

# ③ 联网抓正文再分类（数据源太短/被截断时用，如 <150 字符的摘要）
$PY tools/site_type_classifier.py --fetch --urls https://a.com https://b.com -o 结果.csv
#   --fetch 模式也可配 --input txt(每行一个网址)；自动读 HTTPS_PROXY/HTTP_PROXY env，
#   内置 3 次重试抗代理节点抖动；--workers 8 并发
```

联网抓取前确认代理可用：`curl -s -o /dev/null -w "%{http_code}" -m 8 -x http://127.0.0.1:7890 https://web.archive.org/`

## 4. 业务口径（写结果/汇报时保持一致）

- **状态**：`有效` = 可开发联系池；`已拉黑-套壳坐实` / `已降级-历史无实质` = 从池中排除（按状态筛选即自然过滤）。
- **分级** A/B/C/D 来自四维体检综合；**A/B 级** = 优先开发；C/D = 边缘/存疑。
- **站点类型对业务的意义**：评测榜单站→中高客单产品植入（Amazon 联盟单量主力）；deal 折扣券站→清库存/低价冲量；内容博客→故事化种草(节奏慢)；新闻媒体→只做 PR 不做 CPS；返利/比价/论坛→一般不做联盟客。
- 榜单型联盟客优先：**评测榜单站 ∩ A/B 级** 是首选开发池。

## 5. 端到端编排（典型链路）

```text
第0关 preflight_check.py           环境体检（Python/依赖/外网）
第1关 batch_site_analyzer.py       候选 URL → 有效站（有内容可访问）
第2关 partner_health_check.py      有效站 → 四维体检 A/B/C/D
第3关 cc_batch_scan.py             A/B 级补 PageRank（可选，需 CC 索引）
第4关 site_type_classifier.py      A/B 级 → 站点推广类型（deal/评测榜单/…）
第5关 domain_age_scan.py           A/B 级 → 域名年龄（抓 新壳<2年 防坑）
第6关 topic_shift_check.py         老域×C/D 级 → Wayback 主题漂移（套壳坐实）
收尾 打标回写：结论/处置建议 列 → 本地台账；飞书主表用 record-batch-update(≤200条/批)
```

只跑其中某关时，输入可直接用上一关输出 CSV；每关都支持 `--limit N` 小样验证。

## 6. 已知坑（务必先读，省试错时间）

- **网络**：中国大陆直连 Google/archive.org 不通；沙箱/本机先 `export HTTPS_PROXY=http://127.0.0.1:7890 HTTP_PROXY=http://127.0.0.1:7890`（Clash 系端口；7891 为 SOCKS5）。脚本抓取自动读代理 env，无需额外参数。
- **抓取偶发 URLError**：多为代理出口节点组抖动，非脚本问题；重试已内置，仍失败换出口节点再跑一次。
- **Wayback CDX 大域名超时**：dailymail 等海量快照域名查询可能 >20s，脚本超时须给足（topic_shift_check 已内置，勿手动改短）。
- **飞书批量写**：`record-batch-update` 单次上限 **200 条**，超了报 800010701，务必 ≤200 分批；select(单选)字段直接传选项名文本即可。
- **CSV 编码**：所有输出统一 `utf-8-sig`（Excel 打开不乱码）；列名含中文，读回用 `encoding="utf-8-sig"`。
- **域名归一化**：去协议/www/尾斜杠、转小写后去重；US/DE 双市场同域会各占一行，统计"唯一站点"先按域名去重。
- **摘要截断**：老台账正文摘要被截断到 <300 字符，关键词命中率低——需要可靠分类时先走 §3 模式③联网重抓。
- **B2B 噪声**：affiliate 网络/平台本身（flexoffers、awin、impact、skimlinks…）不是内容联盟客，开发清单里先剔除（域名黑名单+正文 B2B 信号）。

## 7. 与数据产出的衔接

- 本地台账/开发池 CSV 一律落在 `outputs/` 下：`合作方台账_US_DE_汇总_v3_含套壳复查.csv`（998行基准）、`联盟客_站点类型分类_963.csv`、`联盟客_榜单型开发池_163_含类型.csv`、`联盟客_补判新增_内容站AB级.csv`(199)。
- 新市场候选（如 UK 345 个「待加市场候选」）按 §5 链路跑一遍即得该市场开发池。
- 重抓补判已有脚本 `refetch_classify.py`（固定走 Clash 代理、14 并发、jsonl 增量落盘可断点续跑）——换市场改输入 CSV 即可复用。
