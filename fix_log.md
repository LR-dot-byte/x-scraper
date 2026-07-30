# Fix Log

## 记录说明

本日志把Git提交、真实数据问题、爬虫修复、回归测试和研究材料更新对应起来，以说明研究者在与智能体协作中“发现问题—形成规则—修改代码—验证结果—沉淀 harness”的过程。

## 一、代码迭代记录

| 提交/阶段 | 发现的问题 | 修复或改进 | 验证方式 |
|---|---|---|---|
| `04f4d0a`、`4e3d5dd` | 初始采集仍处于原型阶段 | 完成 twikit 初版及改进 | 小样本运行 |
| `4268fc9`、`4399884` | twikit 与页面和登录场景兼容不足 | 迁移到 Selenium + Chrome，重建页面解析与主流程 | 页面样例 |
| `45fe8ac` | Cookie 登录和时间线采集不稳定 | 修复 Cookie 注入、登录和时间线逻辑 | 登录与时间线试验 |
| `eeb85b4` | 高频请求易触发限流，失败原因不清 | 增加随机等待、批次暂停、限流冷却和异常信息 | 限流日志 |
| `a5d0ce8` | 大跨度滚动漏数，重复帖影响计数 | 改为小步滚动，使用稳定帖文 ID 去重 | 重复样例 |
| `493cbad` | 只能采集基础帖子，不能支持互动研究 | 增加搜索、回复和报告模式 | 多模式试验 |
| `f08e16f` | 不同 Chrome 环境稳定性有差异 | 增加可选 undetected-chromedriver 与 Profile | 双驱动试验 |
| `e094a60` | 置顶帖干扰日期早停，评论递归易错位 | 增加置顶保护和对话链归属逻辑 | 日期和回复样例 |
| `897dba5` | Profile 统计和 CSV 字段难以直接分析 | 统一帖文与评论字段 | CSV 表头核验 |
| `803c775` | 功能分散、错误处理不统一 | 完成五种采集模式和统一错误处理 | 全流程运行 |
| `fda4452` | 缺少依赖、说明和敏感文件规则 | 增加 `requirements.txt`、README 和 `.gitignore` | 仓库检查 |
| `cab5a7a` | 作者污染、评论误归属、时区边界、关键词误命中、公式注入和输入不严 | 增加作者精确匹配、UTC+8、词边界、CSV 转义、输入校验、统一重试与回归测试 | 离线单元测试 |
| `da8758b`—`d55ce6e` | 需要按账号和年度稳定召回涉疆帖子，并复核对话链 | 增加账号高级搜索、日期范围、本地相关性复核和评论采集 | 定稿 1.0—3.0 |
| `8e2200a` | 数据缺少可回查来源 | 为帖子和评论增加规范化原始链接 | 链接字段测试 |
| `9e180c5` | 折叠正文、表情和嵌套节点导致原文截断 | 重写正文遍历与“显示更多”展开逻辑 | 29 项回归测试中的正文完整性测试 |
| 最终工作区更新 | 首屏异步加载会被误判为零结果；媒体证据不便复核 | 增加首屏结果/空结果等待，并输出帖子媒体链接 | 29 项测试全部通过；人工核对代码差异 |

## 二、关键数据问题与 harness 沉淀

### 1. 时间线作者污染

X 用户页会插入推荐帖和其他账号内容。修复后，时间线以标准化账号 ID 精确匹配作者；该经验沉淀为 `CLAUDE.md` 的“时间线必须严格校验作者”规则。

对应测试：`test_expected_author_filters_reposts_and_recommendations`。

### 2. 日期边界与无效滚动

X 时间戳通常为 UTC，直接截取日期会在北京时间跨日处误分年份；如果先做关键词过滤，旧的不相关帖子又无法触发早停。修复后统一转换 UTC+8，并先更新日期状态、再做业务过滤。

对应测试：`test_utc_timestamp_is_filtered_by_cst_calendar_date`、`test_old_irrelevant_tweets_still_trigger_date_stop`。

### 3. 首屏异步加载

页面 `document.readyState` 完成不代表搜索结果已经进入 DOM。旧逻辑可能在首屏仍为空时连续滚动并过早停止。最终版本增加“出现帖文或明确空结果提示”的等待；真实页面仍超时时，继续滚动复核而不伪装成功。

### 4. 正文截断

只读取第一个节点或未经展开的 `innerText` 会漏掉折叠内容、链接后文本和图片表情。最终版本按 DOM 顺序遍历文本节点，处理 `<br>`、块级换行和图片 `alt`，并在批量提取前重新查询“显示更多”控件。

对应测试：`test_extractor_walks_all_text_nodes_and_preserves_structure`、`test_extractor_preserves_image_emoji_and_text_after_it`、`test_show_more_expansion_requeries_dom_after_each_click`。

### 5. 评论归属与推荐区混入

页面相邻并不等于真实回复关系。修复后使用回复对象、目标帖 ID 和推荐区边界共同判断，并区分页面显示回复数与实际保留评论数。

对应测试：`test_only_explicit_reply_handle_matches`、`test_selects_thread_context_and_replies_until_recommendations`、`test_only_posts_with_reported_replies_open_details`。

### 6. 关键词误命中

英文子字符串和泛化人权词会造成误判。修复后对英文词使用边界匹配，区分直接地域词、身份词、中国语境和事件语境；弱文本候选需要外链或图片证据。

对应测试：`test_direct_xinjiang_keywords_match_without_more_context`、`test_uyghur_requires_china_and_event_context`、`test_generic_context_words_do_not_match_alone`。

### 7. 安全和可复核性

CSV 外部文本先经过公式注入防护；账号、帖文 ID 和日期在启动前校验；Cookie 不写入日志、Git 和最终包；帖子与评论保留稳定 ID 和原始链接。

对应测试：`test_formula_prefixes_are_escaped`、`test_screen_name_validation`、`test_tweet_id_validation`、`test_comment_csv_has_requested_columns_in_order`。

## 三、研究材料迭代

| 阶段 | 问题 | 调整 |
|---|---|---|
| 2024—2025 初步整理 | 研究问题局限于两年探索，无法支持长期网络演化 | 补齐 2021—2023 历史表并统一账号、日期和字段 |
| 非知情代理人补采 | 仅凭维吾尔/东突词可能误收无中国语境内容 | 对 351 个账号执行两组高级搜索，弱文本逐条核查外链和媒体 |
| 五年数据衔接 | 总体账号、知情代理人子样本和发帖样本量容易混淆 | 明确 1,128 → 557 → 206 的嵌套关系 |
| 网络图初版 | 只有统计折线图，难以呈现关系结构 | 在 Codex 指导下使用 Gephi 绘制关注与评论网络 |
| 图表第 4—10 批 | 初版信息密度、配色和叙事顺序不统一 | 依次完成结构整合、二次修订、角色图重构、Nature/Science 候选和冷暖色比较 |
| 论文终稿对齐 | 过程文档仍停留在两年研究和旧统计口径 | 统一为 2021—2025 年最终研究问题、数据采集、清洗和自查口径 |
| 最终数据复核 | 过程母表同时保留 4,953 和 4,952 两套数字 | 保留母表痕迹，新增“论文最终统计口径.csv”，明确终稿统一使用 4,952 |

## 四、最终验证

2026-07-29 使用 Python 3.13、Selenium 4.45.0 和 undetected-chromedriver 3.5.5 执行：

```bash
python3 -m py_compile x_scraper.py 注释.py test_x_scraper.py
python3 -m unittest -v
```

结果：

- 29 项测试全部通过；
- `x_scraper.py`、`注释.py` 和 `test_x_scraper.py` 语法检查通过；
- `注释.py` 与 `x_scraper.py` 的抽象语法树哈希完全一致；
- 凭据移出并清除 Finder 元数据后，26 个非 Git 目录中的 313 个项目文件全部可读取；
- Git 对象完整性检查通过：开发迭代、代码定稿与材料归档记录均可见，共 27 次提交。

## 五、仍需运行者注意

真实 X 页面会持续变化。每次正式采集仍需用原创帖、引用帖、回复、推荐帖和中英文界面做小样本抽查，并记录 DOM 变化、限流、超时和数量不足原因。自动测试证明的是既定规则没有回归，不等于平台实时页面永远不变。
