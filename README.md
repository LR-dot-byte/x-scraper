# X (Twitter) 帖子抓取工具

基于 Selenium + Chrome，抓取 X (Twitter) 推文详情、用户时间线、关键词搜索、评论和子评论，输出 UTF-8 BOM CSV。

## 唯一项目主目录

本项目后续唯一维护目录为：

```text
/Users/lirong/Documents/知情代理人/李荣-2244313043-大作业
```

以后对 X 爬虫的代码、测试、文档和配置修改都应在此目录完成；抓取结果统一写入
`x_output/`，评论统一写入 `x_output/comments/`。运行前先进入该目录：

```bash
cd "/Users/lirong/Documents/知情代理人/李荣-2244313043-大作业"
python3 x_scraper.py account-search <用户>
```

`config.json`、`x_cookies*.json`、`x_output/` 和 `archive/` 只保存在本机，已被
Git 忽略，不会上传到 GitHub。

当前版本重点改进了：

- 按目标推文 ID 和回复对象精确归属数据；
- 使用北京时间过滤日期，并在关键词过滤前判断早停；
- 小步滚动和显式等待，减少漏抓和无效等待；
- 实体词匹配、作者校验与中英文互动数据解析；
- Cookie 文件权限保护、CSV 公式注入防护和输入校验。
- 账号级 X 高级搜索，在服务器端预先限定作者、任一关键词和日期范围；
- 严格涉疆审核：`新疆/Xinjiang` 等直接通过，仅提到维吾尔时还需中国与事件语境；
- 自动进入有回复的帖子核对实际可见评论，并输出到独立 `comments/` 目录。

## 安装

建议使用 Python 3.11 或更高版本。本项目当前开发环境为 Python 3.13。

```bash
pip install -r requirements.txt
```

### Python工具与用途

| 工具 | 用途 |
|---|---|
| Selenium | 控制Chrome，采集X平台帖子、时间线和评论 |
| undetected-chromedriver | 可选Chrome驱动模式；默认不启用 |
| pandas | 读取、合并和清洗CSV数据 |
| NumPy | 数值计算、标准化和数组处理 |
| scikit-learn | K-means聚类、轮廓系数和数据预处理 |
| SciPy | 统计检验及科学计算 |
| NetworkX | 构建账号关系网络并计算中心性等指标 |
| Matplotlib | 绘制基础统计图和年度趋势图 |
| Seaborn | 绘制聚类、分布和对比类统计图 |

### 外部软件

- **Google Chrome：** 爬虫运行所需。Selenium会通过Selenium Manager自动管理匹配的驱动。
- **Gephi 0.9.7：** 用于构建分年度关注关系网络和评论互动网络，计算网络密度、平均路径长度、聚类系数、模块度及节点中心性。

目前Git仓库中的可执行代码主要使用Selenium；其余Python工具已为后续数据清洗、聚类、网络分析和图表生成预先列入，待相应分析代码完成后使用。

## 快速开始

```bash
python3 x_scraper.py config                    # 生成配置模板
python3 x_scraper.py tweet <推文ID>             # 获取单条推文
python3 x_scraper.py timeline <用户> --count 50 # 用户时间线
python3 x_scraper.py search "关键词" --count 20 # 搜索推文
python3 x_scraper.py account-search <用户>      # 高级搜索 2024-2025 涉疆帖子
python3 x_scraper.py replies <推文ID> --count 30 # 获取回复
python3 x_scraper.py report <用户> --since 2025-01-01 --replies 20 --depth 1  # 一站式报告
```

## 配置

编辑 `config.json`，设置 Cookie 文件路径。Cookie 从浏览器开发者工具导出。

建议先生成模板：

```bash
python3 x_scraper.py config
```

Cookie 等同于登录凭据：不要提交到 Git，也不要分享给他人。程序在 POSIX 系统上会尝试将 Cookie 文件权限收紧为 `600`。

### 账号高级搜索

`account-search` 和 `report` 默认在 X 高级搜索中限定：

- **Any of these words**：包括 `Xinjiang 维吾尔 新疆 Uyghur/Uighur`、
  `Uiguren`、`East Turkistan/East Turkestan` 等常见变体；
- **From these accounts**：命令中指定的账号；
- **From date**：`2024-01-01`；
- **To date**：`2025-12-31`（包含当日）。

例如：

```bash
python3 x_scraper.py account-search UHRP_Chinese
python3 x_scraper.py account-search UHRP_Chinese \
  --since 2024-06-01 --until 2025-06-30 \
  --any-words Xinjiang 维吾尔 新疆 Uyghur Uighur "East Turkistan"
```

如果 X 高级搜索临时不可用，报告模式可回退到主页时间线扫描：

```bash
python3 x_scraper.py report UHRP_Chinese --timeline-scan
```

### 严格涉疆审核

- 命中 `新疆`、`Xinjiang`、`East Turkistan/East Turkestan` 等直接涉疆词时保留；
- 仅出现 `维吾尔/Uyghur/Uighur` 时，还必须同时出现中国语境和拘留、监禁、
  强迫劳动、人权、遣返、制裁等具体事件语境；
- 普通饮食、文化、音乐或只有族群名称的帖子不收录。

### 自动评论核对

`timeline` 和 `account-search` 默认只打开页面显示有回复的帖子，收集
详情页中的对话链前后文、直接回复及二、三级回复，并在“Discover more /
更多推文”推荐区边界处停止。结果写入 `x_output/comments/`，列固定为：

`序号、account、tweet_id、link、time、text、贴主ID`

帖子 CSV 的 `reply` 保留 X 页面展示的回复数，`评论条数`记录实际抓取并验证的
唯一评论数，`原始链接`保留每条帖文的 X 原帖 URL。可以临时关闭或调整抓取量：

```bash
python3 x_scraper.py account-search UHRP_Chinese --no-comments
python3 x_scraper.py account-search UHRP_Chinese --max-comments 1000 --comment-depth 1
```

推荐配置：

```json
{
  "filter": {
    "xinjiang_only": true,
    "strict_china_context": true
  },
  "comments": {
    "enabled": true,
    "directory": "comments",
    "max_per_post": 1000,
    "max_depth": 2
  }
}
```

## 准确度说明

评论模式保留详情页推荐区边界之前的对话链内容。已删除、折叠、
受保护或当前账号不可见的回复仍可能无法抓取；程序会排除明确的推广和
“Discover more / 更多推文”之后的推荐内容。
