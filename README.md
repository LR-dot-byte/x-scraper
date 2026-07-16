# X (Twitter) 帖子抓取工具

基于 Selenium + Chrome，抓取 X (Twitter) 推文详情、用户时间线、关键词搜索、评论和子评论，输出 UTF-8 BOM CSV。

当前版本重点改进了：

- 按目标推文 ID 和回复对象精确归属数据；
- 使用北京时间过滤日期，并在关键词过滤前判断早停；
- 小步滚动和显式等待，减少漏抓和无效等待；
- 实体词匹配、作者校验与中英文互动数据解析；
- Cookie 文件权限保护、CSV 公式注入防护和输入校验。
- 账号级 X 高级搜索，在服务器端预先限定作者、任一关键词和日期范围。

## 安装

```bash
pip install -r requirements.txt
```

需要本机已安装 Chrome。Selenium 4.6+ 会通过 Selenium Manager 自动管理匹配的驱动。

## 快速开始

```bash
python3 x_scraper.py config                    # 生成配置模板
python3 x_scraper.py tweet <推文ID>             # 获取单条推文
python3 x_scraper.py timeline <用户> --count 50 # 用户时间线
python3 x_scraper.py search "关键词" --count 20 # 搜索推文
python3 x_scraper.py account-search <用户>      # 高级搜索 2024-2025 涉疆帖子
python3 x_scraper.py replies <推文ID> --count 30 # 获取回复
python3 x_scraper.py report <用户> --replies 20 --depth 1  # 高级搜索 + 评论报告
```

## 配置

编辑 `config.json`，设置 Cookie 文件路径。Cookie 从浏览器开发者工具导出。

建议先生成模板：

```bash
python3 x_scraper.py config
```

Cookie 等同于登录凭据：不要提交到 Git，也不要分享给他人。程序在 POSIX 系统上会尝试将 Cookie 文件权限收紧为 `600`。

### 账号高级搜索

`account-search` 和 `report` 默认等价于在 X 高级搜索中设置：

- **Any of these words**：`Xinjiang 维吾尔 新疆 Uyghur`
- **From these accounts**：命令中指定的账号
- **From date**：`2024-01-01`
- **To date**：`2025-12-31`（包含当日）

例如：

```bash
python3 x_scraper.py account-search UHRP_Chinese
python3 x_scraper.py report UHRP_Chinese --replies 10 --depth 0
```

可以覆盖日期或关键词：

```bash
python3 x_scraper.py account-search UHRP_Chinese \
  --since 2024-06-01 --until 2025-06-30 \
  --any-words Xinjiang 维吾尔 新疆 Uyghur UFLPA
```

如果 X 高级搜索临时不可用，报告模式可回退到旧的主页扫描：

```bash
python3 x_scraper.py report UHRP_Chinese --timeline-scan
```

## 准确度说明

评论模式只保留页面上能明确证明回复目标作者的记录。当 X 页面未提供可验证的回复标记时，程序会倾向少抓，避免将推荐帖误判为评论。
