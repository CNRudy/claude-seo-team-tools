# 用 AI 工作台驱动 claude-seo —— 团队使用手册

> 面向「会用聊天框、不想碰命令行」的同事。你在 **WorkBuddy / Claude Code 这类 AI 工作台**里用人话下指令，AI 助手去调用本仓库里的工具把活干完——你只需要学会**把需求说清楚**。
>
> 配套先读仓库根 `README.md`（工具是什么）；本文档解决「怎么让 AI 帮我用」。

---

## 一、先记住一个前提：先体检，再开跑

本仓库里所有联网分析工具，运行前都建议先跑一次**环境体检**（检查 Python / 依赖 / 文件完整性 / 外网是否连通）。

在 AI 工作台的对话框里输入：

```text
运行 tools/preflight_check.py 帮我做一次运行前环境体检，把结果逐条解释给我听
```

AI 会执行 `python3 tools/preflight_check.py` 并返回类似：

```
[PASS] Python 版本    3.13.12 (要求 >= 3.9)
[PASS] 仓库完整性     必备文件齐全
[PASS] 依赖包         7 个必需包全部就绪
[WARN] 连通性         www.google.com  HTTPS 不通（需代理/VPN）
[PASS] 连通性         www.amazon.com  HTTP 202
[PASS] 网络结论       外网可达，可以开始抓取分析
结论：可以运行（有警告不影响主流程）
```

**怎么看结果：**

| 体检结论 | 含义 | 怎么办 |
|---|---|---|
| 出现 `[FAIL]` | 有硬伤，跑不了 | 让 AI 按提示解决（通常是：先 `bash setup.sh` 初始化、或检查网络） |
| 只有 `[WARN]` | 能跑，但部分受限 | 留意提示内容；例如「google/youtube 不通」→ 抓 YouTube 或 Google 系前先开代理/VPN，抓普通合作方网站不受影响 |
| `whois 未安装` | 域名历史检查用不了 | 其余功能不受影响，可忽略或让 AI 帮你装 |
| 全部 PASS | ✅ 就绪 | 直接开工 |

> 你自己想手动跑也可以：在仓库根目录执行 `python3 tools/preflight_check.py`（`--no-net` 跳过联网检测、`--json` 输出结构化结果）。

---

## 二、两种用法，选哪个？

| | **用法 A：AI 对话（推荐小白）** | **用法 B：命令行（进阶/无人值守）** |
|---|---|---|
| 怎么做 | 在对话框用人话描述任务 | 终端里敲 `python ...` 命令 |
| 上手难度 | 零门槛，会打字就行 | 需要会复制命令、看路径 |
| 适合 | 日常一两个任务、临时看看 | 定期批量跑、写进脚本/定时任务 |
| 例子 | “把这批网址体检分级” | `.venv-seo/bin/python tools/partner_health_check.py --input urls.txt` |

**本文档主推用法 A。** 下面第三节给你现成话术，直接复制改一改就能用。

---

## 三、用法 A：现成指令库（复制即用）

> 通用开头：告诉 AI 工作目录和你的身份。
> 一句话模板：`我在 <仓库路径> 目录，仓库是 claude-seo-team-tools。请<你要做的事>，输出<你要的格式>。`
>
> 💡 技巧：一次只说一类任务；要「先 A 再 B 再 C」的流水线，就按第四节的分步写法，别把好几个任务揉在一句话里。

### 场景 1：批量初筛（判断一批网站死没死 / 什么语言 / 哪个国家）

```text
请用 tools/batch_site_analyzer.py 分析我给你的网址列表（每行一个，见文件 xxx.txt），
输出一张 Excel：字段要有 URL / 状态(有效无效) / HTTP状态码 / 目标国家/地区 / 语言 / 标题 / 简要描述。
并发数用 8，超时 20 秒。
```

### 场景 2：合作方四维体检 + 分级（决定值不值得深入合作）

```text
对 xxx.txt 里的网址逐个做四维体检（tools/partner_health_check.py），
按 A/B/C/D 分级，重点标出内容空洞、技术硬伤(屏蔽搜索引擎)的站点。
输出 Excel 并给出：A/B/C/D 各多少家、点名最值得优先联系的 Top 20。
```

### 场景 3：域名尽调（新合作方是不是"过期域名灰产/站群"）

```text
用 claude-seo/scripts/domain_history.py 检查下面这些域名注册了几年、
内容主题和注册历史是否可疑（像不像拿老域名做灰产的），逐个给结论。
```

> 背景：一个站域名注册了 18 年、以前是宠物医疗站、现在全是投机内容——这是典型的「过期域名滥用」，Google 眼里是高风险，跟我们合作容易连坐。合作前先查这个能避雷。

### 场景 4：寄生 SEO 风险扫描（合作方主站能不能挂我们的推广内容）

```text
用 claude-seo/scripts/parasite_risk.py 扫描 xxx.com，
看它有没有子目录在搞寄生 SEO（第三方内容、联盟链接密度高、主题漂移），
报告它作为联盟营销合作方的风险等级。
```

### 场景 5：内容质量检测（一篇稿子/一个页面值不值得发）

```text
用 claude-seo/scripts/content_quality.py 检测 <网址或文本> 的内容质量，
看有没有低质/AI 填充信号；再用 content_verify.py 挑出没有引用来源的可核实断言。
```

### 场景 6：查单个重点域名的 PageRank / 权重画像

```text
用 claude-seo/scripts/commoncrawl_graph.py 查 xxx.com 的 PageRank 和外链主机数（--json）。
```

### 场景 7：找合作方站点的 sitemap / 优惠券目录页

```text
用 claude-seo/scripts/sitemap_discovery.py 找出 xxx.com 的 sitemap，
再顺着 sitemap 里找有没有 /coupons /deals /best-* 这类适合我们放推广链接的页面。
```

### 场景 8：站点类型分类（这个站是 deal / 评测榜单 / 内容博客？——决定上什么货）

```text
对 xxx.csv 里的站点做推广类型分类（tools/site_type_classifier.py）：
优先用"正文摘要"列判断；没有文本列就联网抓首页（--fetch，需要能访问外网）。
输出 Excel/CSV，加 站点类型/类型得分/类型置信/命中词 四列，
并统计每类各多少家，点名"评测榜单站"里综合评分最高的 Top 20（这类是单量主力，优先联系）。
```

> 背景：同为 A/B 级好站，deal 站适合清库存冲量、评测榜单站适合中高客单植入（做 Best-of/Top-N 榜）、
> 内容博客适合慢热种草、新闻媒体只做 PR 不做 CPS——先分清类型，才知道该上什么货、发什么话术。

### 场景 9：综合流水线（多步串联，一次交付）

分三条消息发更稳（AI 上下文太长容易乱）：

```text
① 先用 tools/batch_site_analyzer.py 初筛 xxx.txt，把有效站输出为 valid.txt
② 再对 valid.txt 用 tools/partner_health_check.py 做四维体检，A/B 级留下，输出 ab.txt
③ 对 ab.txt 用 tools/site_type_classifier.py 做站点类型分类（有正文列可直接分；无则加 --fetch）
④ 对分类结果里"评测榜单站"前 50 个补查 PageRank，按 分级+PR+类型 排序，最终出一张 Excel 给我
```

---

## 四、用法 B：命令行速查（进阶同事用）

在仓库根目录、且已完成 `bash setup.sh` 的前提下：

```bash
# 运行前体检
python3 tools/preflight_check.py

# 工具1 批量初筛
.venv-seo/bin/python tools/batch_site_analyzer.py --input urls.txt --workers 8 --output 初筛结果.xlsx

# 工具2 四维体检（A/B/C/D）
.venv-seo/bin/python tools/partner_health_check.py --input urls.txt --workers 6

# 工具3 PageRank 批量扫描（需先准备 Common Crawl 索引，见 README）
.venv-seo/bin/python tools/cc_batch_scan.py --domains domains.txt --ranks /path/to/cc-*.txt.gz --csv out.csv

# 工具4 站点类型分类（deal/评测榜单/返利/比价/内容博客/新闻/论坛）
.venv-seo/bin/python tools/site_type_classifier.py --input 体检结果.csv --text-col 正文摘要 --domain-col 域名 -o 分类.csv
.venv-seo/bin/python tools/site_type_classifier.py --fetch --input urls.txt -o 分类.csv   # 联网抓正文再分类

# 上游脚本直接用（示例：域名历史 / 寄生风险 / sitemap 发现 / 单站 PR）
.venv-seo/bin/python claude-seo/scripts/domain_history.py example.com
.venv-seo/bin/python claude-seo/scripts/parasite_risk.py https://example.com
.venv-seo/bin/python claude-seo/scripts/sitemap_discovery.py https://example.com
.venv-seo/bin/python claude-seo/scripts/commoncrawl_graph.py example.com --json
```

> ⚠️ 一律用 `.venv-seo/bin/python`（不是裸 `python`），否则会报缺依赖——这正是体检脚本 `[FAIL] 依赖包` 想帮你提前发现的问题。

---

## 五、这套引擎还能帮我们做什么？（能力 × 业务匹配）

claude-seo 内置了 53 个脚本 / 25 个子技能 / 30+ 条命令，远超我们已封装的 4 个工具。下面按**对我们的业务价值**筛选归类——我们做 Amazon 站外推广、联盟客和红人营销，真正用得上的是这些：

### 已用上（已封装成 tools/ 四个工具）

| 能力 | 位置 | 我们的用法 |
|---|---|---|
| 安全抓取 + 页面解析 | `fetch_page.py` / `parse_html.py` | 工具的底层 |
| 内容质量信号 | `content_quality.py`（同族思路） | 体检工具的内容维度 |
| Common Crawl PageRank | `commoncrawl_graph.py` | 已封装成批量版 `cc_batch_scan.py` |
| 站点推广类型识别（7 类词表打分） | 自研（`site_type_classifier.py`） | 分清 deal/评测榜单/内容博客…，决定上什么货、发什么话术 |

### 🟢 直接可用、免费无 key、强烈建议纳入日常（但还没封装成傻瓜工具）

| 脚本 | 一句话功能 | 对我们业务的用法 |
|---|---|---|
| `domain_history.py` | 查域名注册年限，识别「过期域名做灰产」 | **合作方尽调第一步**：老域名突然变投机内容 = 高风险，避雷 |
| `parasite_risk.py` | 扫描站内子目录的寄生 SEO / 联盟链接密度 | **评估合作方主站能不能挂我们链接**，防 Google 连坐 |
| `sitemap_discovery.py` | 通过 robots.txt 发现 sitemap | 找合作方站点的优惠券/deals 目录页，规划投放位置 |
| `content_verify.py` | 挑出正文里缺引用来源的可核实断言 | 审核红人脚本/联盟客稿件有没有「张口就来」的数据 |
| `content_quality.py` | 检测低质/AI 填充/凑字信号 | 单篇深度检测：红人寄回来的稿子质量把关 |

> 用法：上面这几个复制给 AI 就能跑（见第三节场景 3–5）。如果跑得多，可以让 AI 把其中 1–2 个也封装成 `tools/` 下的批量版——和当初封装四个工具一个套路。

### 🟡 可用，但需申请免费 key（要联网去 console 申请，约 10 分钟）

| 脚本 | 功能 | 对我们的价值 |
|---|---|---|
| `youtube_search.py` | YouTube Data API v3：官方搜频道/视频、拉订阅数等元数据 | **红人开发加分项**：用官方接口拿频道粉丝量、视频数据，替代手工点开一个个频道（需 Google 免费 key） |
| `pagespeed_check.py` / `crux_history.py` | 谷歌 PageSpeed 实验室 + CrUX 真实用户速度、25 周趋势 | 给重点合作方站点测手机端速度——联盟站太慢 = 用户不点，影响我们的转化 |

### 🔴 暂不推荐（要付费数据源 / 重度账户门槛）

| 脚本/命令 | 原因 |
|---|---|
| `moz_api.py`、DataForSEO 系列、Ahrefs 扩展 | 外链画像数据虽有用，但需付费订阅，先不碰 |
| `keyword_planner.py` | 需 Google Ads Manager + developer token，门槛高 |
| `bing_webmaster.py` 系 | 需验证站点所有权——我们不是那些站点的站长 |

### ⚪ 用不上（除非哪天我们做自家品牌站的 SEO）

整站 audit / technical / schema / geo(sxo) / drift / programmatic / hreflang / GSC、GA4 报表 / IndexNow 提交索引……这些是给「自己运营的网站」做 SEO 优化的，跟我们「评估别人的站、做站外推广」不是一回事。若未来启动品牌独立站/官网的 SEO 再启用。

---

## 六、常见报错对照表

| 报错/现象 | 原因 | 解决 |
|---|---|---|
| `ModuleNotFoundError: No module named 'requests'` | 用错了 Python（用了系统 python 而不是 .venv-seo） | 用 `.venv-seo/bin/python`；或先 `bash setup.sh` |
| `[FAIL] 依赖包 缺少: …` | 环境没初始化 | 在仓库根运行 `bash setup.sh` |
| 全部站点 `403` | 站点反爬，属「受限但有效」 | 正常现象，不算无效（我们的判定已把 403 算有效） |
| 某批站点全超时，尤其 Google/YouTube | 当前网络到不了（直连无代理/VPN） | 先跑体检脚本看网络结论；开代理/VPN 后再试 |
| `url_safety ... loopback proxy` 之类 | 走了本地代理被 SSRF 防护拦 | 我们工具默认直连；不要手动给它们配 `127.0.0.1` 类代理 |
| 输出的 Excel 打不开/中文乱码 | 用错打开方式或老版 Office | 用 Excel/WPS 打开，别用文本编辑器 |
| PageRank 工具提示找不到索引 | 还没下载 Common Crawl 索引文件 | 见 README 工具3 说明；或让 AI 下载 |

---

## 七、边界与安全（务必知道）

1. **这些是"诊断工具"，不是"一键定生死"**：体检/分级/PR 用于**排序和初筛**，合作与否最终结合人工背景核实（公司是否诚信、报价、结算周期等工具判断不了）。
2. **判断口径偏 Google SEO 质量**：一个站 SEO 好 ≠ 一定适合我们；SEO 差 ≠ 一定不能合作（有时流量来自社媒而非搜索）。
3. **数据只在你自己机器上处理**：仓库工具默认不把数据发到第三方；用 API key 的功能（YouTube/PageSpeed 等），key 存在本机，不外传。
4. **免费 ≠ 无限**：Common Crawl 索引、YouTube/PageSpeed 免费额度都有配额，大批量跑注意节奏。

---

## 八、给小白同事的 5 分钟上手路径

```text
1. 拿到仓库（zip 解压 或 git clone）
2. 终端：bash setup.sh            （初始化，首次一次）
3. 终端：python3 tools/preflight_check.py   （体检，看有没有 [FAIL]）
4. 回到 AI 工作台，复制第三节任意一段话术，改一改文件路径/网址
5. 拿到 Excel，双击打开
```

遇到任何一步看不懂——**直接把报错贴给 AI**，让它帮你解决，这是这套工作方式最大的优点。
