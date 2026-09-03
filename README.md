# Claude-SEO 团队工具与使用指南

> 给"不想研究工具、只想拿到结果"的同事看的**中文使用说明书**。
> 一句话：这套工具能帮你**批量判断一批网站是否在运营、质量如何、主攻哪个国家市场**，输出可以直接打开的表，用于站外推广/联盟客/红人合作方的筛选与评估。

- 本仓库内容：**3 个自研分析工具**（基于开源项目 claude-seo 封装）+ **1 个运行前环境体检工具** + **内置的 claude-seo 上游副本**（`claude-seo/`，MIT 协议，版权归原作者 agricidaniel）+ **面向 AI 工作台的使用手册**
- 上游项目：<https://github.com/AgriciDaniel/claude-seo>（MIT 协议，本仓库已整包内置，clone 后无需联网下载）
- 系统要求：macOS / Linux、已装 Python 3.9+（git 仅在需要更新上游副本时用）

---

## 一、这套工具解决什么问题？

做海外市场（Amazon、独立站、联盟营销），我们常要回答这几个问题，而人工一个个点开网页又慢又不统一：

| 我们的问题 | 人工做的代价 | 用这套工具 |
|---|---|---|
| 这批推广合作方的网站还有没有在运营？ | 几百个链接逐个点开，要好几天 | 批量自动检测，几分钟出结果 |
| 内容质量、SEO 底子好不好？适不适合合作？ | 凭经验"感觉"，标准不统一 | 0-100 打分 + A/B/C/D 分级，口径统一 |
| 网站主攻哪个国家市场？说什么语言？ | 打开网页肉眼看 | 自动识别国家 / 语言 |
| 有哪些硬伤（打不开、被搜索引擎屏蔽、没联系页…）？ | 非技术人员看不出来 | 自动检查运营 / 技术 / 内容三维 |
| 网站权重如何？值不值得优先联系？ | 全靠猜 | 用公开数据算 PageRank（无需付费 API） |

---

## 二、仓库里有什么？

```
claude-seo-team-tools/
├── README.md                        ← 本文件（指南）
├── setup.sh                         ← 一键初始化（首次使用运行）
├── claude-seo/                      ← 内置的上游开源引擎（完整副本，勿改动）
├── docs/
│   └── AI工作台使用手册.md           ← 在 WorkBuddy/Claude Code 等 AI 工具里怎么用（含现成指令库）
├── tools/
│   ├── preflight_check.py           ← 工具0：运行前环境体检（依赖/文件/外网连通，开跑前先执行）
│   ├── batch_site_analyzer.py       ← 工具1：批量初筛（活没活/语言/国家/简介）
│   ├── partner_health_check.py      ← 工具2：四维体检（A/B/C/D 分级评分）
│   ├── cc_batch_scan.py             ← 工具3：PageRank 批量扫描（无需 API key）
│   └── requirements.txt             ← Python 依赖清单
└── examples/
    └── urls_sample.txt              ← 示例网址名单（可直接试跑）
```

> 说明：`tools/` 里的脚本运行时需要 claude-seo 提供的抓取/解析模块，仓库已将 claude-seo **完整内置**在 `claude-seo/` 目录（MIT 协议、含其 LICENSE），clone 后无需联网下载。
>
> 📖 **想在 WorkBuddy / Claude Code 这类 AI 工具里用人话下指令就让工具跑起来？先读 [docs/AI工作台使用手册.md](docs/AI工作台使用手册.md)** —— 里面有一份复制即用的指令库，还有 claude-seo 53 个脚本里"哪些适合我们业务"的完整盘点。

---

## 三、快速开始（3 步）

### 第 0 步：运行前环境体检（每次拿到新机器/报错时先做）

```bash
python3 tools/preflight_check.py
```

检查 Python 版本、仓库文件完整性、依赖包、外网连通性等，输出 `[PASS]/[WARN]/[FAIL]`。**看到 `[FAIL]` 先解决再往下**（通常是没初始化，做第 1 步即可）；只有 `[WARN]` 可以继续，留意提示（例如 Google/YouTube 不通 = 抓它们前需开代理/VPN）。

### 第 1 步：初始化环境（首次使用只做一次）

```bash
bash setup.sh
```

它会自动：确认内置的 claude-seo 已就绪 → 创建虚拟环境 → 安装依赖。看到 `✅ 初始化完成` 即成功。

### 第 2 步：跑一个例子

```bash
.venv-seo/bin/python tools/batch_site_analyzer.py --input examples/urls_sample.txt
```

运行完当前目录会多出 `xxx.xlsx`，双击用 Excel/WPS 打开即可看到每个网站的状态、语言、目标国家、简介。

---

## 四、工具逐个说明

### 工具 0：运行前环境体检 —— 先确认"这台机器能跑"

- **用途**：跑任何联网分析前，一键确认 Python 版本 / 仓库文件 / 依赖包 / 外网连通性是否就绪；顺带探测 whois、Common Crawl 缓存等可选能力
- **典型场景**：新同事第一次跑、换电脑、突然全部超时/报缺依赖时
- **纯标准库实现**：任何 Python 3.9+ 环境（包括没初始化依赖的系统 python）都能独立运行，专门用来"诊断环境"

```bash
python3 tools/preflight_check.py                       # 标准体检
python3 tools/preflight_check.py --no-net              # 跳过联网检测（离线/内网）
python3 tools/preflight_check.py --targets https://x.com   # 追加自定义连通目标
python3 tools/preflight_check.py --json                # 结构化输出
```

退出码：`0` 就绪 · `2` 可运行但有警告 · `1` 有错误需先解决。

### 工具 1：批量网站分析器 —— 给一批网址做"初筛"

- **用途**：判断网站是否还活着、说什么语言、面向哪个国家、是什么内容的站
- **典型场景**：合作方名单几百上千个链接，先筛掉死链/无效站，再决定谁进入下一步
- **我们实测**：1505 条链接全量检测，几分钟判定约 89% 有效

```bash
.venv-seo/bin/python tools/batch_site_analyzer.py --input urls.txt        # 文件输入，一行一个
.venv-seo/bin/python tools/batch_site_analyzer.py --urls https://a.com https://b.com   # 直接传网址
.venv-seo/bin/python tools/batch_site_analyzer.py --input urls.txt --workers 8 --output result.xlsx
```

| 参数 | 说明 | 默认 |
|---|---|---|
| `--input` | 输入文件（每行一个网址） | — |
| `--urls` | 直接传网址 | — |
| `--workers` | 并发数 | 5 |
| `--timeout` | 单请求超时(秒) | 20 |
| `--output` | 输出 xlsx 路径 | 自动生成 |

输出字段：URL / 状态(有效·无效) / HTTP状态码 / 目标国家/地区 / 语言 / 语言代码 / 网站标题 / 简要描述 / 响应时间 / 最终URL / 错误信息。

### 工具 2：合作方"四维体检" —— 决定值不值得深入合作

- **用途**：对网站做多维度体检打分：**运营状态(20) + 技术SEO(35) + 内容质量(45)**，综合 0-100 分并自动分 A/B/C/D 级
- **典型场景**：红人/联盟客/外链合作方质量评估——内容空洞（AI 拼凑、空壳站）、技术硬伤（屏蔽搜索引擎）直接降级，不用逐个点开排查
- **我们实测**：美国 916 + 德国 68 个站点全量体检并分级

```bash
.venv-seo/bin/python tools/partner_health_check.py --input urls.txt --workers 8
.venv-seo/bin/python tools/partner_health_check.py --input urls.txt --pagerank --workers 4   # 附加权重画像
```

输出 26 列，包括：URL / 域名 / 状态 / **综合评分** / **分级(A≥85·B≥70·C≥55·D<55)** / HTTPS / robots.txt / sitemap / 标题 / Meta / 移动适配 / Canonical / 正文质量分 / 正文词数 / 关于页 / 联系页 / 隐私页 / PageRank / 外链主机数 / 体检说明 等。
Excel 按分级着色（A绿/B浅绿/C黄/D红），带筛选和冻结窗格。

### 工具 3：PageRank 批量扫描 —— 看网站"江湖地位"

- **用途**：基于公开的 Common Crawl 搜索索引，批量查域名 PageRank 与外链规模，**免费、无需 API key**
- **典型场景**：A/B 级合格站点里再按"江湖地位"排序，权重高的优先联系

```bash
.venv-seo/bin/python tools/cc_batch_scan.py --domains domains.txt --ranks /path/to/cc-index-*.txt.gz --csv out.csv
```

（`--ranks` 为 Common Crawl domain ranks 索引文件，见上游项目说明。）

---

## 五、小白最常踩的 3 个坑

1. **网址必须带 `https://`**，一行一个，中间不要有空格/逗号；
2. 跑大批量前先用几个网址小试，确认输出格式符合预期；
3. 部分境外网站需要能正常访问外网的环境才能抓到。

---

## 六、背景：这套工具的开源"引擎" claude-seo

本仓库的工具并非从零开发，而是把开源项目 **claude-seo** 的抓取 / 解析 / 内容质量评分能力封装成了上面的傻瓜式脚本。claude-seo 本身是一个功能更全的 AI SEO 审计插件（跑在 Claude Code 里，25 个子技能、32 条命令，能对任意网址做整站 SEO 体检、Schema 结构化数据检查、AI 搜索优化、外链分析等），对我们的价值主要是它的底层模块稳定、可信。

为便于团队内部使用与版本固定，**仓库在 `claude-seo/` 目录内置了该项目的完整副本（MIT 协议，含其 LICENSE）**。日常不需要动它；若要升级到上游新版本，可整目录替换为最新 clone（见官方仓库）。

- 官方仓库：<https://github.com/AgriciDaniel/claude-seo>
- 内置副本版本：v2.2.4（2026-07 上游发布）
- 命令示例（需 Claude Code 环境）：`/seo audit https://example.com`（全站审计）· `/seo content <url>`（内容质量）· `/seo schema <url>`（结构化数据）

> 上游 53 个脚本里，还有 `domain_history`（域名历史/过期域名灰产识别）、`parasite_risk`（寄生 SEO 风险）、`sitemap_discovery`（发现优惠券/目录页）、`content_verify`（稿件事实核查）等**免费可直接用、且贴合我们联盟客/红人业务**的能力，逐一说明与指令模板见 **[docs/AI工作台使用手册.md](docs/AI工作台使用手册.md) 第五节**。需要的话可让 AI 把其中某几个也封装成 `tools/` 下的批量工具。

---

## 七、限制与注意事项

| 事项 | 说明 |
|---|---|
| 是"诊断工具"，不是"一键上首页" | 它输出的是问题和优先级，改还是需要人去执行 |
| 判断偏 Google SEO 质量 | 用于评估网站健康度/权重，**不等于判断公司是否诚信，合作决策请结合人工背景核实** |
| 部分高级功能需付费数据源 | 那是可选扩展；本仓库 3 个工具都不需要额外付费 key |
| 数据隐私 | 工具默认只在本机处理，结果表是你主动导出/推送的 |
| 开源协议 | 本仓库代码（`tools/`、`setup.sh`、指南）以 MIT 发布（见 LICENSE）；内置的 `claude-seo/` 为上游 MIT 项目，版权归其原作者，已随附其 LICENSE，未做改动 |

---

## 八、License

本仓库代码（`tools/`、`setup.sh`）以 MIT 协议发布，详见 [LICENSE](LICENSE)。
内置的上游引擎 [claude-seo](https://github.com/AgriciDaniel/claude-seo)（存放于 `claude-seo/`）为原作者 agricidaniel 的 MIT 开源项目，完整副本已随仓库分发、**未做任何改动**，其版权与许可条款以该目录内 LICENSE 为准。
