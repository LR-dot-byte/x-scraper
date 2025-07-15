# X (Twitter) 帖子爬虫工具

基于 Selenium + Chrome，模拟真实浏览器操作，抓取 X (Twitter) 推文详情、用户时间线、关键词搜索、评论回复。输出 CSV 格式（UTF-8 BOM）。

## 安装

```bash
pip install -r requirements.txt
```

## 快速开始

```bash
python3 x_scraper.py config                    # 生成配置模板
python3 x_scraper.py tweet <推文ID>             # 获取单条推文
python3 x_scraper.py timeline <用户> --count 50 # 用户时间线
python3 x_scraper.py search "关键词" --count 20 # 搜索推文
python3 x_scraper.py replies <推文ID> --count 30 # 获取回复
python3 x_scraper.py report <用户> --since 2025-01-01 --replies 20 --depth 1  # 一站式报告
```

## 配置

编辑 `config.json`，设置 Cookie 文件路径。Cookie 从浏览器开发者工具导出。
