#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 上面两行分别指定 Python 解释器和 UTF-8 源码编码。
# 本文件依据最终 x_scraper.py 生成，用于逐行解释代码含义；不改变程序行为。
# 下方模块文档字符串说明程序用途、输出格式和基本用法。
"""
X (Twitter) 帖子爬虫工具
基于 Selenium + Chrome，模拟真实浏览器操作，抓取推文详情、用户时间线、关键词搜索、评论回复。
输出 CSV 格式，UTF-8 编码。

使用示例:
  python3 x_scraper.py tweet 1903791436349997063
  python3 x_scraper.py timeline elonmusk --count 50
  python3 x_scraper.py search "python" --count 20
  python3 x_scraper.py replies 1903791436349997063 --count 30
  python3 x_scraper.py config
"""


# 导入本行所需模块或对象。
import argparse
# 导入本行所需模块或对象。
import csv
# 导入本行所需模块或对象。
import json
# 导入本行所需模块或对象。
import os
# 导入本行所需模块或对象。
import random
# 导入本行所需模块或对象。
import re
# 导入本行所需模块或对象。
import sys
# 导入本行所需模块或对象。
import time
# 导入本行所需模块或对象。
import traceback
# 导入本行所需模块或对象。
import unicodedata
# 导入本行所需模块或对象。
from datetime import datetime, timezone, timedelta
# 导入本行所需模块或对象。
from urllib.parse import quote_plus, urlparse


# 导入本行所需模块或对象。
from selenium import webdriver
# 导入本行所需模块或对象。
from selenium.webdriver.chrome.options import Options
# 导入本行所需模块或对象。
from selenium.webdriver.common.by import By
# 导入本行所需模块或对象。
from selenium.webdriver.support import expected_conditions as EC
# 导入本行所需模块或对象。
from selenium.webdriver.support.ui import WebDriverWait


# 开始可能抛出异常的受保护操作。
try:
    # 导入本行所需模块或对象。
    import undetected_chromedriver as uc
    # 设置或更新本行涉及的变量值。
    HAS_UC = True
# 捕获并处理指定的异常情况。
except ImportError:
    # 设置或更新本行涉及的变量值。
    HAS_UC = False




# ============================================================
#  新疆相关关键词（用于过滤帖子）
# ============================================================
# 设置或更新本行涉及的变量值。
XINJIANG_DIRECT_KEYWORDS = [
    # 地名、地区别称和新疆专属法案：命中即可直接保留。
    # 续写当前数据结构、参数列表或表达式。
    "新疆", "东突", "东突厥", "Xinjiang", "XUAR",
    # 续写当前数据结构、参数列表或表达式。
    "East Turkestan", "East Turkistan", "UFLPA",
# 结束上一行开始的数据结构或表达式。
]


# 设置或更新本行涉及的变量值。
UYGHUR_IDENTITY_KEYWORDS = [
    # 仅出现族群名称还不够，必须同时具备中国语境和事件语境。
    # 续写当前数据结构、参数列表或表达式。
    "维吾尔", "Uyghur", "Uyghurs", "Uighur", "Uighurs",
    # 续写当前数据结构、参数列表或表达式。
    "Uygur", "Uygurs", "Uigur", "Uiguren", "ウイグル", "อุยกูร์",
# 结束上一行开始的数据结构或表达式。
]


# 设置或更新本行涉及的变量值。
CHINA_CONTEXT_KEYWORDS = [
    # 续写当前数据结构、参数列表或表达式。
    "中国", "中國", "中共", "北京", "China", "Chinese", "CCP", "PRC",
    # 续写当前数据结构、参数列表或表达式。
    "Beijing", "Chinese government", "Chinese authorities",
    # 续写当前数据结构、参数列表或表达式。
    "Chinese Communist Party",
# 结束上一行开始的数据结构或表达式。
]


# 设置或更新本行涉及的变量值。
UYGHUR_EVENT_KEYWORDS = [
    # 续写当前数据结构、参数列表或表达式。
    "拘留", "关押", "监禁", "逮捕", "判刑", "失踪", "集中营", "再教育营",
    # 续写当前数据结构、参数列表或表达式。
    "强迫劳动", "人权", "镇压", "迫害", "遣返", "引渡", "制裁", "释放",
    # 续写当前数据结构、参数列表或表达式。
    "detain", "detained", "detention", "interned", "internment",
    # 续写当前数据结构、参数列表或表达式。
    "imprison", "imprisoned", "prison", "arrest", "arrested", "sentence",
    # 续写当前数据结构、参数列表或表达式。
    "sentenced", "disappear", "disappeared", "camp", "re-education",
    # 续写当前数据结构、参数列表或表达式。
    "forced labor", "forced labour", "genocide", "human rights",
    # 续写当前数据结构、参数列表或表达式。
    "persecution", "repression", "surveillance", "deport", "deported",
    # 续写当前数据结构、参数列表或表达式。
    "deportation", "repatriation", "extradition", "sanction", "sanctions",
    # 续写当前数据结构、参数列表或表达式。
    "release", "released", "asylum", "activist", "political prisoner",
# 结束上一行开始的数据结构或表达式。
]


# 对应 X 高级搜索中的 “Any of these words”。
# 设置或更新本行涉及的变量值。
DEFAULT_ADVANCED_SEARCH_WORDS = (
    # 续写当前数据结构、参数列表或表达式。
    "Xinjiang", "维吾尔", "新疆", "Uyghur", "Uighur", "Uyghurs", "Uighurs",
    # 续写当前数据结构、参数列表或表达式。
    "Uiguren", "East Turkistan", "East Turkestan",
# 结束上一行开始的数据结构或表达式。
)
# 设置或更新本行涉及的变量值。
DEFAULT_ARCHIVE_SINCE = "2024-01-01"
# 设置或更新本行涉及的变量值。
DEFAULT_ARCHIVE_UNTIL = "2025-12-31"


# 设置或更新本行涉及的变量值。
XINJIANG_CONTEXT_KEYWORDS = [
    # 这些词单独出现不足以证明与新疆相关，只用于辅助分类/调试
    # 续写当前数据结构、参数列表或表达式。
    "genocide", "forced labor", "forced labour",
    # 续写当前数据结构、参数列表或表达式。
    "atrocity", "crimes against humanity",
    # 续写当前数据结构、参数列表或表达式。
    "concentration camp", "re-education camp",
    # 续写当前数据结构、参数列表或表达式。
    "persecution", "oppression", "repression",
    # 续写当前数据结构、参数列表或表达式。
    "deportation", "repatriation", "extradition",
    # 续写当前数据结构、参数列表或表达式。
    "inhumane detention",
    # 续写当前数据结构、参数列表或表达式。
    "Magnitsky", "CECC",
# 结束上一行开始的数据结构或表达式。
]


# ============================================================
#  工具函数
# ============================================================


# 定义可复用的处理函数。
def get_config(config_path="config.json"):
    # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
    """加载并解析配置文件，返回 dict。"""
    # 根据条件决定后续执行分支。
    if not os.path.isfile(config_path):
        # 输出运行提示、进度或错误信息。
        print(f"✗ 配置文件不存在: {config_path}")
        # 输出运行提示、进度或错误信息。
        print(f"  请先运行 'python3 x_scraper.py config' 生成模板配置文件")
        # 执行当前步骤的业务处理。
        sys.exit(1)


    # 开始可能抛出异常的受保护操作。
    try:
        # 使用上下文管理器并在结束时自动清理资源。
        with open(config_path, "r", encoding="utf-8") as f:
            # 解析或写入 JSON 配置与数据。
            config = json.load(f)
        # 使相对路径始终相对于 config.json，而不是当前工作目录。
        # 设置或更新本行涉及的变量值。
        config["_config_dir"] = os.path.dirname(os.path.realpath(config_path))
        # 将本函数的计算结果返回给调用处。
        return config
    # 捕获并处理指定的异常情况。
    except json.JSONDecodeError as e:
        # 输出运行提示、进度或错误信息。
        print(f"✗ 配置文件格式不正确: {e}")
        # 执行当前步骤的业务处理。
        sys.exit(1)




# 定义可复用的处理函数。
def print_banner():
    # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
    """打印程序横幅。"""
    # 输出运行提示、进度或错误信息。
    print("=" * 50)
    # 输出运行提示、进度或错误信息。
    print("  X (Twitter) 帖子爬虫工具")
    # 输出运行提示、进度或错误信息。
    print("  基于 Selenium + Chrome")
    # 输出运行提示、进度或错误信息。
    print("=" * 50)
    # 输出运行提示、进度或错误信息。
    print()




# 定义可复用的处理函数。
def print_summary(mode, query, requested, actual, output_path, skipped=0):
    # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
    """打印抓取结果摘要。"""
    # 输出运行提示、进度或错误信息。
    print()
    # 输出运行提示、进度或错误信息。
    print("-" * 50)
    # 输出运行提示、进度或错误信息。
    print(f"  抓取模式: {mode}")
    # 输出运行提示、进度或错误信息。
    print(f"  目标: {query}")
    # 输出运行提示、进度或错误信息。
    print(f"  请求数量: {requested}")
    # 输出运行提示、进度或错误信息。
    print(f"  实际获取: {actual}")
    # 根据条件决定后续执行分支。
    if skipped > 0:
        # 输出运行提示、进度或错误信息。
        print(f"  跳过: {skipped}")
    # 输出运行提示、进度或错误信息。
    print(f"  输出文件: {output_path}")
    # 输出运行提示、进度或错误信息。
    print("-" * 50)




# 定义可复用的处理函数。
def _contains_keyword(text, keyword):
    # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
    """匹配关键词。英文/数字词使用词边界，避免在更长单词中误命中。"""
    # 使用正则表达式完成匹配或提取。
    escaped = re.escape(unicodedata.normalize("NFKC", keyword).casefold())
    # 根据条件决定后续执行分支。
    if re.search(r"[a-z0-9]", keyword, flags=re.I):
        # 将本函数的计算结果返回给调用处。
        return re.search(rf"(?<![a-z0-9_]){escaped}(?![a-z0-9_])", text) is not None
    # 将本函数的计算结果返回给调用处。
    return escaped in text




# 定义可复用的处理函数。
def matches_xinjiang(text):
    # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
    """严格审核涉疆相关性。

    新疆地名/地区别称直接通过；仅出现维吾尔族群名称时，必须同时出现
    中国语境和具体事件语境，避免把饮食、音乐、语言等一般内容误收录。
    """
    # 根据条件决定后续执行分支。
    if matches_any_words(text, XINJIANG_DIRECT_KEYWORDS):
        # 将本函数的计算结果返回给调用处。
        return True
    # 将本函数的计算结果返回给调用处。
    return (
        # 执行当前步骤的业务处理。
        matches_any_words(text, UYGHUR_IDENTITY_KEYWORDS)
        # 执行当前步骤的业务处理。
        and matches_any_words(text, CHINA_CONTEXT_KEYWORDS)
        # 执行当前步骤的业务处理。
        and matches_any_words(text, UYGHUR_EVENT_KEYWORDS)
    # 结束上一行开始的数据结构或表达式。
    )




# 定义可复用的处理函数。
def matches_any_words(text, words):
    # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
    """检查文本是否命中给定列表中的任意关键词。"""
    # 根据条件决定后续执行分支。
    if not text:
        # 将本函数的计算结果返回给调用处。
        return False
    # 设置或更新本行涉及的变量值。
    normalized = unicodedata.normalize("NFKC", str(text)).casefold()
    # 将本函数的计算结果返回给调用处。
    return any(_contains_keyword(normalized, kw) for kw in words)




# 定义可复用的处理函数。
def sanitize_csv_value(value):
    # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
    """防止外部文本被 Excel/LibreOffice 解释为公式。"""
    # 根据条件决定后续执行分支。
    if not isinstance(value, str):
        # 将本函数的计算结果返回给调用处。
        return value
    # 设置或更新本行涉及的变量值。
    value = value.replace("\x00", "")
    # 根据条件决定后续执行分支。
    if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        # 将本函数的计算结果返回给调用处。
        return "'" + value
    # 将本函数的计算结果返回给调用处。
    return value




# ============================================================
#  RateLimiter 类 - 统一请求限流控制器
# ============================================================


# 定义封装相关状态和方法的类。
class RateLimiter:
    # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
    """统一请求限流器（同步版）

    三层节奏控制：
    1. 请求级 — 每次操作前强制等待固定间隔 + 随机抖动
    2. 批次级 — 连续请求达到阈值后触发长暂停，模拟人类行为
    3. 异常级 — 触发平台限流后进入冷却期，大幅降低请求频率
    """


    # 定义可复用的处理函数。
    def __init__(self, config):
        # 读取字典或配置中的对应值。
        cfg = config.get("rate_limit", {})
        # 读取字典或配置中的对应值。
        self.min_interval = cfg.get("min_interval_seconds", 3)
        # 读取字典或配置中的对应值。
        self.max_interval = cfg.get("max_interval_seconds", 6)
        # 读取字典或配置中的对应值。
        self.long_pause = cfg.get("long_pause_seconds", 60)
        # 读取字典或配置中的对应值。
        self.batch_size = cfg.get("pages_per_long_pause", 20)
        # 读取字典或配置中的对应值。
        self.cooldown_seconds = cfg.get("cooldown_seconds", 300)
        # 读取字典或配置中的对应值。
        self.max_retries = cfg.get("max_retries", 3)


        # 设置或更新本行涉及的变量值。
        self._last_request = 0.0
        # 设置或更新本行涉及的变量值。
        self._request_count = 0


    # 应用装饰器以调整后续定义的行为。
    @property
    # 定义可复用的处理函数。
    def request_count(self):
        # 将本函数的计算结果返回给调用处。
        return self._request_count


    # 定义可复用的处理函数。
    def wait(self, label="操作"):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """每次操作前调用，自动计算并等待合适间隔。"""
        # 根据条件决定后续执行分支。
        if self._last_request > 0:
            # 设置或更新本行涉及的变量值。
            elapsed = time.time() - self._last_request
            # 设置或更新本行涉及的变量值。
            jitter = random.uniform(0, self.max_interval - self.min_interval)
            # 设置或更新本行涉及的变量值。
            required = self.min_interval + jitter


            # 根据条件决定后续执行分支。
            if elapsed < required:
                # 设置或更新本行涉及的变量值。
                delay = required - elapsed
                # 输出运行提示、进度或错误信息。
                print(f"  ⏳ [{label}] 等待 {delay:.1f}s "
                      # 执行当前步骤的业务处理。
                      f"(固定间隔={self.min_interval}s + 随机={jitter:.1f}s)")
                # 执行当前步骤的业务处理。
                time.sleep(delay)


        # 设置或更新本行涉及的变量值。
        self._last_request = time.time()
        # 设置或更新本行涉及的变量值。
        self._request_count += 1


    # 定义可复用的处理函数。
    def batch_pause(self):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """每批次请求后长暂停，模拟人类休息。"""
        # 根据条件决定后续执行分支。
        if self._request_count > 0 and self._request_count % self.batch_size == 0:
            # 输出运行提示、进度或错误信息。
            print(f"  🛑 已完成 {self._request_count} 次操作，"
                  # 执行当前步骤的业务处理。
                  f"长暂停 {self.long_pause}s 模拟人类行为...")
            # 执行当前步骤的业务处理。
            time.sleep(self.long_pause)


    # 定义可复用的处理函数。
    def cooldown(self):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """触发平台限流后的强制冷却。"""
        # 输出运行提示、进度或错误信息。
        print(f"  🚫 触发限流保护，强制冷却 {self.cooldown_seconds}s...")
        # 执行当前步骤的业务处理。
        time.sleep(self.cooldown_seconds)
        # 设置或更新本行涉及的变量值。
        self._request_count = 0




# ============================================================
#  SeleniumScraper 类
# ============================================================


# 定义封装相关状态和方法的类。
class SeleniumScraper:
    # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
    """X (Twitter) 帖子爬虫

    使用 Selenium WebDriver 控制 Chrome 浏览器，
    模拟真实用户操作，通过 JS 原子提取页面数据避免 stale element。
    """


    # 设置或更新本行涉及的变量值。
    TWEET_SELECTOR = 'article[data-testid="tweet"]'
    # 设置或更新本行涉及的变量值。
    TWEET_TEXT_SHOW_MORE_SELECTOR = (
        # 执行当前步骤的业务处理。
        'article[data-testid="tweet"] '
        # 执行当前步骤的业务处理。
        'button[data-testid="tweet-text-show-more-link"], '
        # 执行当前步骤的业务处理。
        'article[data-testid="tweet"] '
        # 设置或更新本行涉及的变量值。
        '[role="button"][data-testid="tweet-text-show-more-link"]'
    # 结束上一行开始的数据结构或表达式。
    )


    # ---- JS 脚本：在浏览器端原子提取所有可见推文的结构化数据 ----
    # 以下说明按脚本执行顺序逐项对应 JavaScript 语句；实际脚本保持原样，避免注释改变浏览器端字符串。
    # 创建结果数组，集中保存本次页面扫描得到的帖子。
    # 定义正文提取函数，接收帖文正文的根节点。
    # 根节点不存在时返回空文本。
    # 创建文本片段数组，按 DOM 顺序累积正文。
    # 定义文本追加函数，仅把非空值转换为字符串后写入片段数组。
    # 定义换行追加函数，仅在末尾不是换行符时补充换行。
    # 定义递归 DOM 遍历函数；节点不存在时结束当前分支。
    # 文本节点读取 nodeValue 后结束当前分支。
    # 非元素节点不参与样式和标签判断。
    # 跳过 hidden、display:none、visibility:hidden 的不可见元素。
    # 将标签名转为大写，统一后续标签比较。
    # BR 标签转换为正文换行。
    # IMG 标签优先读取 alt、其次读取 aria-label，以保留图片表情。
    # 跳过 aria-hidden=true 的辅助或装饰元素。
    # 将 DIV、P、LI 识别为块级内容，并在内容前后补充必要换行。
    # 按 DOM 顺序递归遍历全部子节点，避免遗漏嵌套文本。
    # 从正文根节点启动遍历并合并文本片段。
    # 统一回车换行、不换行空格和换行两侧空白。
    # 将三个及以上连续换行压缩为两个并清理首尾空白。
    # 定义互动量缩写解析函数；空值或无法匹配的值返回零。
    # 删除千位逗号后拆分数值与 K、M、B、万、亿单位。
    # 按单位倍数还原数值，并以四舍五入整数返回。
    # 建立中英文推荐区标题的识别规则。
    # 查询页面全部帖子节点，并按 DOM 顺序逐条处理。
    # 使用 try 隔离单条帖子异常，避免中断整批提取。
    # 读取社交语境区域；命中中英文置顶标记时跳过该帖子。
    # 初始化帖子 ID 与链接，并遍历 /status/ 链接提取稳定 ID。
    # 将首个有效状态链接规范化为不含查询参数的 x.com 链接。
    # 无法取得帖子 ID 时跳过该节点，防止生成不可去重记录。
    # 查询正文节点并调用完整 DOM 遍历函数提取正文。
    # 查询 time 元素并读取标准 ISO datetime。
    # 初始化作者显示名和账号名。
    # 从头像容器 data-testid 中去除固定前缀，得到账号名。
    # 遍历账号主页链接，从内部 span 提取长度合理的显示名。
    # 头像容器未提供账号名时，用主页链接中的 handle 补充。
    # 主要路径未取得显示名时，从第一个有效用户链接执行备用提取。
    # 仍无显示名但已有账号名时，用账号名作为显示名。
    # 初始化点赞、转发、回复和浏览量。
    # 从互动按钮组的 aria-label 中分别匹配中英文互动量。
    # 调用缩写解析函数还原 K、M、B、万、亿计数。
    # 从正文提取 Unicode 话题标签并去除井号。
    # 遍历帖子内 HTTP 链接，排除 X 和 Twitter 站内链接。
    # 统计图片容器、视频播放器和 video 元素数量。
    # 遍历帖文图片，保存非空且未重复的 src 或 currentSrc。
    # 遍历帖文视频，保存非空且未重复的 poster 链接。
    # 读取社交语境和帖子完整文本，定位正文之前的头部区域。
    # 仅在头部区域匹配中英文回复标签，避免正文中的 @造成误判。
    # 提取回复对象账号，并据此设置回复标记和回复说明。
    # 定位帖子所属虚拟列表单元格，从前序同级节点回溯推荐区标题。
    # 命中推荐标题后标记推荐区并停止回溯。
    # 从社交语境文本识别中英文推广标记。
    # 初始化对话深度，并遍历祖先节点为嵌套线程规则保留入口。
    # 将本条帖子组装为结构化对象并写入结果数组。
    # 保存稳定 ID、DOM 序号、单行正文、时间和作者字段。
    # 保存点赞、转发、回复、引用、浏览量和话题标签。
    # 最多保留五个外部链接及四个媒体证据链接。
    # 保存回复对象、规范化链接、推荐区标记和推广标记。
    # 单条帖子解析失败时跳过该条，继续处理其余节点。
    # 全部节点处理完成后，将结果数组序列化为 JSON 返回 Python。
    _EXTRACT_TWEETS_JS = r"""
    const results = [];
    const extractTweetText = (root) => {
      if (!root) return '';

      const chunks = [];
      const appendText = (value) => {
        if (value) chunks.push(String(value));
      };
      const appendNewline = () => {
        if (chunks.length && !String(chunks[chunks.length - 1]).endsWith('\n')) {
          chunks.push('\n');
        }
      };
      const walk = (node) => {
        if (!node) return;
        if (node.nodeType === Node.TEXT_NODE) {
          appendText(node.nodeValue || '');
          return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return;

        const element = node;
        if (element.hidden) return;

        const style = window.getComputedStyle(element);
        if (style.display === 'none' || style.visibility === 'hidden') return;

        const tagName = element.tagName.toUpperCase();
        if (tagName === 'BR') {
          appendNewline();
          return;
        }
        if (tagName === 'IMG') {
          // X may render emoji as images. innerText/textContent do not reliably
          // include their visible character, so preserve the accessible label.
          appendText(
            element.getAttribute('alt') ||
            element.getAttribute('aria-label') ||
            ''
          );
          return;
        }
        if (element.getAttribute('aria-hidden') === 'true') return;

        const isBlock = ['DIV', 'P', 'LI'].includes(tagName);
        if (isBlock) appendNewline();
        Array.from(element.childNodes || []).forEach(walk);
        if (isBlock) appendNewline();
      };

      walk(root);
      return chunks.join('')
        .replace(/\r\n?/g, '\n')
        .replace(/\u00a0/g, ' ')
        .replace(/[ \t]+\n/g, '\n')
        .replace(/\n[ \t]+/g, '\n')
        .replace(/\n{3,}/g, '\n\n')
        .trim();
    };
    const parseCompactNumber = (raw) => {
      if (!raw) return 0;
      const cleaned = String(raw).replace(/,/g, '').trim();
      const m = cleaned.match(/([\d.]+)\s*([KMB万亿]?)/i);
      if (!m) return 0;
      let value = Number(m[1]);
      const unit = (m[2] || '').toUpperCase();
      const factors = {K: 1e3, M: 1e6, B: 1e9, '万': 1e4, '亿': 1e8};
      if (factors[unit]) value *= factors[unit];
      return Number.isFinite(value) ? Math.round(value) : 0;
    };
    const recommendationPattern = /Discover more|More Tweets|Explore more|更多推文|探索更多|你可能喜欢|推荐内容/i;
    const articles = document.querySelectorAll('article[data-testid="tweet"]');
    articles.forEach((article, idx) => {
      try {
        // --- 跳过置顶推文（Pinned Tweet 固定显示在时间线顶部，会破坏按时间倒序的假设，
        //     导致 since_date 早停逻辑误判为"已翻到最早"而提前终止）---
        const pinContext = article.querySelector('[data-testid="socialContext"]');
        if (pinContext && /pinned|置顶/i.test(pinContext.innerText || '')) {
          return;
        }

        // --- 推文链接 & ID ---
        let tweetId = '', tweetUrl = '';
        const statusLinks = article.querySelectorAll('a[href*="/status/"]');
        for (const link of statusLinks) {
          const href = link.getAttribute('href') || '';
          const match = href.match(/\/status\/(\d+)/);
          if (match) { tweetId = match[1]; tweetUrl = 'https://x.com' + href.split('?')[0]; break; }
        }
        if (!tweetId) return;

        // --- 文本（遍历完整 DOM，保留分段、换行和图片表情）---
        const textEl = article.querySelector('[data-testid="tweetText"]');
        const text = extractTweetText(textEl);

        // --- 时间 ---
        const timeEl = article.querySelector('time');
        const createdAt = timeEl ? (timeEl.getAttribute('datetime') || '') : '';

        // --- 作者信息 ---
        let authorName = '', authorHandle = '';

        // 从 UserAvatar-Container 提取 handle
        const avatarEls = article.querySelectorAll('[data-testid^="UserAvatar-Container-"]');
        if (avatarEls.length > 0) {
          const testid = avatarEls[0].getAttribute('data-testid') || '';
          authorHandle = testid.replace('UserAvatar-Container-', '');
        }

        // 从用户链接提取显示名称
        const userLinks = article.querySelectorAll('a[role="link"]');
        for (const link of userLinks) {
          const href = link.getAttribute('href') || '';
          // 匹配 href="/handle" 格式
          const handleMatch = href.match(/^\/(\w+)$/);
          if (handleMatch) {
            const innerSpan = link.querySelector('span span');
            if (innerSpan) {
              const name = innerSpan.innerText.trim();
              if (name && name.length < 80) {
                authorName = name;
                if (!authorHandle) authorHandle = handleMatch[1];
                break;
              }
            }
          }
        }

        // Fallback：从第一个指向用户的链接提取
        if (!authorName) {
          for (const link of userLinks) {
            const href = link.getAttribute('href') || '';
            const hrefMatch = href.match(/^\/(\w+)$/);
            if (hrefMatch) {
              const linkText = link.innerText.trim();
              if (linkText && !linkText.startsWith('@') && linkText.length < 80) {
                authorName = linkText;
                if (!authorHandle) authorHandle = hrefMatch[1];
                break;
              }
            }
          }
        }

        if (!authorName && authorHandle) authorName = authorHandle;

        // --- 互动数据（兼容英文/中文 aria-label 和 K/M/万缩写）---
        let likeCount = 0, retweetCount = 0, replyCount = 0, viewCount = 0;
        const groupEl = article.querySelector('div[role="group"]');
        if (groupEl) {
          const aria = groupEl.getAttribute('aria-label') || '';
          let m;
          m = aria.match(/([\d,.]+\s*[KMB万亿]?)\s*(?:条\s*)?(?:repl|回复)/i); if (m) replyCount = parseCompactNumber(m[1]);
          m = aria.match(/([\d,.]+\s*[KMB万亿]?)\s*(?:次\s*)?(?:repo|retweet|转发)/i); if (m) retweetCount = parseCompactNumber(m[1]);
          m = aria.match(/([\d,.]+\s*[KMB万亿]?)\s*(?:个\s*)?(?:lik|喜欢|赞)/i); if (m) likeCount = parseCompactNumber(m[1]);
          m = aria.match(/([\d,.]+\s*[KMB万亿]?)\s*(?:次\s*)?(?:vie|查看|浏览)/i); if (m) viewCount = parseCompactNumber(m[1]);
        }

        // --- 话题标签 ---
        const hashtags = (text.match(/#[\p{L}\p{N}_]+/gu) || []).map(h => h.replace('#', ''));

        // --- 外部链接 ---
        const urlElements = article.querySelectorAll('a[href*="http"]');
        const urls = [];
        for (const a of urlElements) {
          const href = a.getAttribute('href') || '';
          if (!href.includes('x.com') && !href.includes('twitter.com')) {
            urls.push(href);
          }
        }

        // --- 媒体 ---
        const mediaCount = article.querySelectorAll(
          '[data-testid="tweetPhoto"], [data-testid="videoPlayer"], video'
        ).length;
        // Keep direct media references for downstream evidence review.  Profile
        // avatars are excluded by scoping to the post's own media containers.
        const mediaUrls = [];
        for (const img of article.querySelectorAll('[data-testid="tweetPhoto"] img')) {
          const src = img.getAttribute('src') || img.currentSrc || '';
          if (src && !mediaUrls.includes(src)) mediaUrls.push(src);
        }
        for (const video of article.querySelectorAll('[data-testid="videoPlayer"] video')) {
          const poster = video.getAttribute('poster') || '';
          if (poster && !mediaUrls.includes(poster)) mediaUrls.push(poster);
        }

        // --- 是否回复 / 回复对象 ---
        const socialContext = article.querySelector('[data-testid="socialContext"]');
        const fullText = article.innerText || '';
        const textPosition = text ? fullText.indexOf(text) : -1;
        const headerText = textPosition >= 0 ? fullText.slice(0, textPosition) : fullText.slice(0, 300);
        const replyLabel = /(Replying to|正在回复|回复)[\s\S]{0,160}/i.exec(headerText);
        const replyToHandles = replyLabel ? (replyLabel[0].match(/@[A-Za-z0-9_]{1,15}/g) || []) : [];
        const isReply = replyToHandles.length > 0;
        let replyTo = '';
        if (replyLabel) replyTo = replyLabel[0].trim().split('\n').slice(0, 4).join(' ');

        // --- 对话区边界 ---
        // X 会在帖子详情页尾部插入“Discover more / 更多推文”。
        // 只要当前 article 之前的同级 cell 出现该标题，就标记为推荐区内容。
        let isRecommendation = false;
        const cell = article.closest('[data-testid="cellInnerDiv"]');
        if (cell && cell.parentElement) {
          let sibling = cell.previousElementSibling;
          while (sibling) {
            const headings = sibling.querySelectorAll('[role="heading"], h1, h2, h3');
            for (const heading of headings) {
              if (recommendationPattern.test(heading.innerText || '')) {
                isRecommendation = true;
                break;
              }
            }
            if (isRecommendation) break;
            sibling = sibling.previousElementSibling;
          }
        }
        const socialText = socialContext ? (socialContext.innerText || '') : '';
        const isPromoted = /Promoted|推广/i.test(socialText);

        // --- 推文深度（0=主帖, 1=一级评论, 2=二级评论...）---
        let depth = 0;
        // 通过检查是否在嵌套的线程容器中判断深度
        let parent = article.parentElement;
        while (parent) {
          if (parent.getAttribute('data-testid') === 'cellInnerDiv') {
            // 检查父级链中是否有多个嵌套的线程
          }
          parent = parent.parentElement;
        }
        // 简单判断：如果 socialContext 包含 @ 回复，可能是深度>0
        if (socialContext) {
          const ctxText = socialContext.innerText || '';
          // "Replying to @someone and @others" -> 一级评论
          // 如果是一级评论的回复，通常会显示 "Replying to @commenter"
        }

        results.push({
          id: tweetId,
          dom_index: idx,
          text: text.replace(/\n/g, ' '),
          created_at: createdAt,
          author_name: authorName,
          author_handle: authorHandle,
          favorite_count: likeCount,
          retweet_count: retweetCount,
          reply_count: replyCount,
          quote_count: 0,
          view_count: viewCount,
          hashtags: hashtags.join(','),
          urls: urls.slice(0, 5).join('|'),
          media_count: mediaCount,
          media_urls: mediaUrls.slice(0, 4).join('|'),
          is_reply: isReply,
          reply_to: replyTo,
          reply_to_handles: replyToHandles.map(h => h.slice(1)).join(','),
          tweet_url: tweetUrl,
          is_recommendation: isRecommendation,
          is_promoted: isPromoted,
        });
      } catch(e) {}
    });
    return JSON.stringify(results);
    """


    # 定义可复用的处理函数。
    def __init__(self, config):
        # 设置或更新本行涉及的变量值。
        self.config = config
        # 执行当前步骤的业务处理。
        self.validate_config(config)


        # 输出目录
        # 读取字典或配置中的对应值。
        self.output_dir = config.get("output", {}).get("directory", "x_output")
        # 根据条件决定后续执行分支。
        if not os.path.isabs(self.output_dir):
            # 设置或更新本行涉及的变量值。
            script_dir = os.path.dirname(os.path.realpath(__file__))
            # 设置或更新本行涉及的变量值。
            self.output_dir = os.path.join(script_dir, self.output_dir)
        # 执行当前步骤的业务处理。
        os.makedirs(self.output_dir, exist_ok=True)


        # 限流器
        # 设置或更新本行涉及的变量值。
        self.rate_limiter = RateLimiter(config)


        # Selenium 配置
        # 读取字典或配置中的对应值。
        self.selenium_cfg = config.get("selenium", {})
        # 读取字典或配置中的对应值。
        self.headless = self.selenium_cfg.get("headless", False)
        # 读取字典或配置中的对应值。
        self.page_timeout = self.selenium_cfg.get("page_load_timeout", 60)
        # 读取字典或配置中的对应值。
        self.scroll_pause = self.selenium_cfg.get("scroll_pause_seconds", 3)
        # 设置或更新本行涉及的变量值。
        self.scroll_pause = max(0.3, min(float(self.scroll_pause), 5.0))


        # Xinjiang 关键词过滤
        # 读取字典或配置中的对应值。
        filter_cfg = config.get("filter", {})
        # 读取字典或配置中的对应值。
        self.filter_xinjiang = filter_cfg.get("xinjiang_only", True)
        # 读取字典或配置中的对应值。
        self.strict_xinjiang_audit = filter_cfg.get("strict_china_context", True)
        # 读取字典或配置中的对应值。
        advanced_cfg = config.get("advanced_search", {})
        # 读取字典或配置中的对应值。
        self.advanced_search_enabled = advanced_cfg.get("enabled", True)
        # 读取字典或配置中的对应值。
        self.advanced_search_words = advanced_cfg.get(
            # 执行当前步骤的业务处理。
            "any_words", list(DEFAULT_ADVANCED_SEARCH_WORDS)
        # 结束上一行开始的数据结构或表达式。
        )
        # 读取字典或配置中的对应值。
        self.advanced_search_since = advanced_cfg.get("since", DEFAULT_ARCHIVE_SINCE)
        # 读取字典或配置中的对应值。
        self.advanced_search_until = advanced_cfg.get("until", DEFAULT_ARCHIVE_UNTIL)


        # 评论抓取：仅对页面显示有回复的帖子进入详情页，实际可见评论另存目录。
        # 读取字典或配置中的对应值。
        comments_cfg = config.get("comments", {})
        # 读取字典或配置中的对应值。
        self.auto_fetch_comments = comments_cfg.get("enabled", True)
        # 设置或更新本行涉及的变量值。
        self.max_comments_per_post = max(
            # 读取字典或配置中的对应值。
            1, min(int(comments_cfg.get("max_per_post", 1000)), 1000)
        # 结束上一行开始的数据结构或表达式。
        )
        # 设置或更新本行涉及的变量值。
        self.max_comment_depth = max(
            # 读取字典或配置中的对应值。
            0, min(int(comments_cfg.get("max_depth", 2)), 3)
        # 结束上一行开始的数据结构或表达式。
        )
        # 读取字典或配置中的对应值。
        comments_directory = str(comments_cfg.get("directory", "comments")).strip()
        # 根据条件决定后续执行分支。
        if not comments_directory:
            # 设置或更新本行涉及的变量值。
            comments_directory = "comments"
        # 根据条件决定后续执行分支。
        if os.path.isabs(comments_directory):
            # 设置或更新本行涉及的变量值。
            self.comments_dir = comments_directory
        # 处理前述条件不成立的情况。
        else:
            # 设置或更新本行涉及的变量值。
            self.comments_dir = os.path.join(self.output_dir, comments_directory)
        # 执行当前步骤的业务处理。
        os.makedirs(self.comments_dir, exist_ok=True)


        # 去重 & 计数
        # 设置或更新本行涉及的变量值。
        self.got_count = 0
        # 设置或更新本行涉及的变量值。
        self.skipped_count = 0
        # 设置或更新本行涉及的变量值。
        self.tweet_ids = set()


        # Driver 延迟初始化
        # 调用浏览器驱动完成当前操作。
        self.driver = None


    # ----- 配置校验 -----


    # 定义可复用的处理函数。
    def validate_config(self, config):
        # 根据条件决定后续执行分支。
        if "auth" not in config:
            # 输出运行提示、进度或错误信息。
            print("✗ 配置文件缺少 'auth' 字段")
            # 执行当前步骤的业务处理。
            sys.exit(1)


        # 读取字典或配置中的对应值。
        rate_cfg = config.get("rate_limit", {})
        # 读取字典或配置中的对应值。
        min_interval = rate_cfg.get("min_interval_seconds", 2)
        # 读取字典或配置中的对应值。
        max_interval = rate_cfg.get("max_interval_seconds", 5)
        # 根据条件决定后续执行分支。
        if min_interval < 0 or max_interval < min_interval:
            # 主动抛出异常以中止无效流程。
            raise ValueError("rate_limit 配置无效：需要 0 <= min_interval <= max_interval")


    # 应用装饰器以调整后续定义的行为。
    @staticmethod
    # 定义可复用的处理函数。
    def _validate_tweet_id(tweet_id):
        # 设置或更新本行涉及的变量值。
        value = str(tweet_id).strip()
        # 根据条件决定后续执行分支。
        if not re.fullmatch(r"\d{5,25}", value):
            # 主动抛出异常以中止无效流程。
            raise ValueError(f"无效的推文 ID: {tweet_id!r}")
        # 将本函数的计算结果返回给调用处。
        return value


    # 应用装饰器以调整后续定义的行为。
    @staticmethod
    # 定义可复用的处理函数。
    def _validate_screen_name(screen_name):
        # 设置或更新本行涉及的变量值。
        value = str(screen_name).strip().lstrip("@")
        # 根据条件决定后续执行分支。
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", value):
            # 主动抛出异常以中止无效流程。
            raise ValueError(f"无效的 X 用户名: {screen_name!r}")
        # 将本函数的计算结果返回给调用处。
        return value


    # 应用装饰器以调整后续定义的行为。
    @staticmethod
    # 定义可复用的处理函数。
    def _validate_date(value, name):
        # 根据条件决定后续执行分支。
        if not value:
            # 将本函数的计算结果返回给调用处。
            return None
        # 开始可能抛出异常的受保护操作。
        try:
            # 执行当前步骤的业务处理。
            datetime.strptime(value, "%Y-%m-%d")
        # 捕获并处理指定的异常情况。
        except (TypeError, ValueError) as exc:
            # 主动抛出异常以中止无效流程。
            raise ValueError(f"{name} 必须是 YYYY-MM-DD 格式") from exc
        # 将本函数的计算结果返回给调用处。
        return value


    # 应用装饰器以调整后续定义的行为。
    @staticmethod
    # 定义可复用的处理函数。
    def _normalize_any_words(any_words):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """校验并规范化高级搜索的 “Any of these words” 列表。"""
        # 根据条件决定后续执行分支。
        if any_words is None:
            # 设置或更新本行涉及的变量值。
            any_words = DEFAULT_ADVANCED_SEARCH_WORDS
        # 根据条件决定后续执行分支。
        if isinstance(any_words, str):
            # 设置或更新本行涉及的变量值。
            any_words = any_words.split()


        # 设置或更新本行涉及的变量值。
        normalized = []
        # 设置或更新本行涉及的变量值。
        seen = set()
        # 遍历集合中的元素并逐项处理。
        for raw_word in any_words:
            # 设置或更新本行涉及的变量值。
            word = unicodedata.normalize("NFKC", str(raw_word)).strip()
            # 根据条件决定后续执行分支。
            if not word:
                # 控制当前循环或占位分支的执行。
                continue
            # 根据条件决定后续执行分支。
            if len(word) > 80 or any(ch in word for ch in ('"', "\n", "\r")):
                # 主动抛出异常以中止无效流程。
                raise ValueError(f"高级搜索关键词无效: {raw_word!r}")
            # 设置或更新本行涉及的变量值。
            key = word.casefold()
            # 根据条件决定后续执行分支。
            if key not in seen:
                # 将当前结果追加到列表或集合。
                normalized.append(word)
                # 执行当前步骤的业务处理。
                seen.add(key)


        # 根据条件决定后续执行分支。
        if not normalized:
            # 主动抛出异常以中止无效流程。
            raise ValueError("高级搜索至少需要一个关键词")
        # 根据条件决定后续执行分支。
        if len(normalized) > 20:
            # 主动抛出异常以中止无效流程。
            raise ValueError("高级搜索关键词不能超过 20 个")
        # 将本函数的计算结果返回给调用处。
        return normalized


    # 应用装饰器以调整后续定义的行为。
    @classmethod
    # 定义可复用的处理函数。
    def build_account_advanced_query(cls, screen_name, any_words=None,
                                     # 设置或更新本行涉及的变量值。
                                     since_date=DEFAULT_ARCHIVE_SINCE,
                                     # 设置或更新本行涉及的变量值。
                                     until_date=DEFAULT_ARCHIVE_UNTIL):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """构造 X 高级搜索查询；until 输入按用户习惯视为包含当日。"""
        # 设置或更新本行涉及的变量值。
        screen_name = cls._validate_screen_name(screen_name)
        # 设置或更新本行涉及的变量值。
        since_date = cls._validate_date(since_date, "--since")
        # 设置或更新本行涉及的变量值。
        until_date = cls._validate_date(until_date, "--until")
        # 根据条件决定后续执行分支。
        if not since_date or not until_date:
            # 主动抛出异常以中止无效流程。
            raise ValueError("账号高级搜索必须同时指定 --since 和 --until")
        # 根据条件决定后续执行分支。
        if since_date > until_date:
            # 主动抛出异常以中止无效流程。
            raise ValueError("--since 不能晚于 --until")


        # 设置或更新本行涉及的变量值。
        words = cls._normalize_any_words(any_words)
        # 设置或更新本行涉及的变量值。
        quoted_words = " OR ".join(f'"{word}"' for word in words)
        # X 的 until: 操作符按次日零点截断。对用户暴露的 --until 保持包含当日语义。
        # 设置或更新本行涉及的变量值。
        until_exclusive = (
            # 执行当前步骤的业务处理。
            datetime.strptime(until_date, "%Y-%m-%d").date() + timedelta(days=1)
        # 结束上一行开始的数据结构或表达式。
        ).isoformat()
        # 将本函数的计算结果返回给调用处。
        return (
            # 执行当前步骤的业务处理。
            f"({quoted_words}) from:{screen_name} "
            # 执行当前步骤的业务处理。
            f"since:{since_date} until:{until_exclusive}"
        # 结束上一行开始的数据结构或表达式。
        )


    # 应用装饰器以调整后续定义的行为。
    @staticmethod
    # 定义可复用的处理函数。
    def _cst_date_from_iso(iso_value):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """将 X 的 UTC ISO 8601 时间转为中国标准时间日期。"""
        # 根据条件决定后续执行分支。
        if not iso_value:
            # 将本函数的计算结果返回给调用处。
            return ""
        # 开始可能抛出异常的受保护操作。
        try:
            # 设置或更新本行涉及的变量值。
            dt = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
            # 根据条件决定后续执行分支。
            if dt.tzinfo is None:
                # 设置或更新本行涉及的变量值。
                dt = dt.replace(tzinfo=timezone.utc)
            # 将本函数的计算结果返回给调用处。
            return dt.astimezone(timezone(timedelta(hours=8))).date().isoformat()
        # 捕获并处理指定的异常情况。
        except (TypeError, ValueError):
            # 将本函数的计算结果返回给调用处。
            return ""


    # ----- WebDriver 初始化 -----


    # 定义可复用的处理函数。
    def _init_driver(self):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """创建并配置 Chrome WebDriver。优先使用 undetected-chromedriver。"""
        # 设置或更新本行涉及的变量值。
        options = Options()


        # 读取字典或配置中的对应值。
        selenium_cfg = self.config.get("selenium", {})
        # 读取字典或配置中的对应值。
        profile_dir = selenium_cfg.get("profile_dir", "")
        # 读取字典或配置中的对应值。
        use_profile = selenium_cfg.get("use_existing_profile", False)
        # 读取字典或配置中的对应值。
        use_uc = selenium_cfg.get("use_undetected", False)


        # 根据条件决定后续执行分支。
        if use_profile and profile_dir and os.path.isdir(profile_dir):
            # 执行当前步骤的业务处理。
            options.add_argument(f"--user-data-dir={profile_dir}")
            # 输出运行提示、进度或错误信息。
            print(f"✓ 使用已有 Chrome Profile: {profile_dir}")
        # 处理前述条件不成立的情况。
        else:
            # 使用真实 Chrome UA；伪装 iPhone Safari 会造成 UA/渲染引擎特征矛盾，
            # 并且移动窄屏每屏加载的推文更少。
            # 执行当前步骤的业务处理。
            options.add_argument("--window-size=1280,1000")


        # 根据条件决定后续执行分支。
        if self.headless:
            # 执行当前步骤的业务处理。
            options.add_argument("--headless=new")


        # 执行当前步骤的业务处理。
        options.add_argument("--disable-gpu")
        # 执行当前步骤的业务处理。
        options.add_argument("--disable-dev-shm-usage")
        # 执行当前步骤的业务处理。
        options.add_argument("--disable-notifications")
        # 续写当前数据结构、参数列表或表达式。
        options.add_experimental_option("prefs", {
            # 续写当前数据结构、参数列表或表达式。
            "profile.default_content_setting_values.notifications": 2,
            # 续写当前数据结构、参数列表或表达式。
            "credentials_enable_service": False,
        # 结束上一行开始的数据结构或表达式。
        })


        # 如果用户明确开启，才使用 undetected-chromedriver。
        # 根据条件决定后续执行分支。
        if use_uc and HAS_UC and not use_profile:
            # 输出运行提示、进度或错误信息。
            print("✓ 使用 undetected-chromedriver（反检测模式）")
            # 调用浏览器驱动完成当前操作。
            self.driver = uc.Chrome(options=options)
        # 处理前述条件不成立的情况。
        else:
            # Selenium 4 自带的 Selenium Manager 会复用本地驱动，避免每次调用
            # webdriver-manager 检查/下载驱动。
            # 调用浏览器驱动完成当前操作。
            self.driver = webdriver.Chrome(options=options)


        # 调用浏览器驱动完成当前操作。
        self.driver.set_page_load_timeout(self.page_timeout)
        # 只使用显式等待，避免隐式等待与 WebDriverWait 叠加。
        # 调用浏览器驱动完成当前操作。
        self.driver.implicitly_wait(0)


    # 定义可复用的处理函数。
    def _wait_for_page_ready(self, timeout=12):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """等待 DOM 可交互，替代固定时长 sleep。"""
        # 调用浏览器驱动完成当前操作。
        WebDriverWait(self.driver, timeout).until(
            # 在浏览器页面中执行 JavaScript。
            lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
        # 结束上一行开始的数据结构或表达式。
        )


    # ----- 认证 -----


    # 定义可复用的处理函数。
    def login(self):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """导航到 x.com 并完成认证。"""
        # 执行当前步骤的业务处理。
        self._init_driver()


        # 读取字典或配置中的对应值。
        selenium_cfg = self.config.get("selenium", {})
        # 读取字典或配置中的对应值。
        use_profile = selenium_cfg.get("use_existing_profile", False)


        # 根据条件决定后续执行分支。
        if use_profile:
            # 使用已有 Chrome Profile，直接访问 x.com 验证登录态
            # 输出运行提示、进度或错误信息。
            print("正在访问 x.com (使用已有 Profile)...")
            # 遍历集合中的元素并逐项处理。
            for attempt in range(3):
                # 开始可能抛出异常的受保护操作。
                try:
                    # 调用浏览器驱动完成当前操作。
                    self.driver.get("https://x.com")
                    # 控制当前循环或占位分支的执行。
                    break
                # 捕获并处理指定的异常情况。
                except Exception:
                    # 根据条件决定后续执行分支。
                    if attempt < 2:
                        # 输出运行提示、进度或错误信息。
                        print(f"  ⚠ 页面加载超时，重试 ({attempt+1}/3)...")
                        # 执行当前步骤的业务处理。
                        time.sleep(5)
            # 执行当前步骤的业务处理。
            self._wait_for_page_ready()


            # 调用浏览器驱动完成当前操作。
            page_source = self.driver.page_source
            # 根据条件决定后续执行分支。
            if "Something went wrong" in page_source:
                # 输出运行提示、进度或错误信息。
                print("⚠ X 返回错误页面，可能需要等待限流解除")
            # 根据条件决定后续执行分支。
            elif "Sign in" in page_source or "login" in self.driver.current_url.lower():
                # 输出运行提示、进度或错误信息。
                print("⚠ Profile 未登录 X，请在 Chrome 中先登录 x.com 后再试")
            # 处理前述条件不成立的情况。
            else:
                # 输出运行提示、进度或错误信息。
                print("✓ Profile 登录态有效")
            # 将本函数的计算结果返回给调用处。
            return


        # 否则使用 Cookie 注入方式
        # 读取字典或配置中的对应值。
        auth = self.config.get("auth", {})
        # 读取字典或配置中的对应值。
        cookies_file = auth.get("cookies_file", "")
        # 根据条件决定后续执行分支。
        if cookies_file and not os.path.isabs(cookies_file):
            # 读取字典或配置中的对应值。
            cookies_file = os.path.join(self.config.get("_config_dir", os.getcwd()), cookies_file)
        # 根据条件决定后续执行分支。
        if not cookies_file or not os.path.isfile(cookies_file):
            # 输出运行提示、进度或错误信息。
            print("✗ Cookie 文件不存在或未配置")
            # 输出运行提示、进度或错误信息。
            print(f"  请在 config.json 的 auth.cookies_file 中指定 Cookie 文件路径")
            # 调用浏览器驱动完成当前操作。
            self.driver.quit()
            # 执行当前步骤的业务处理。
            sys.exit(1)


        # Cookie 等同于登录凭据，POSIX 系统上自动收紧为仅当前用户可读写。
        # 开始可能抛出异常的受保护操作。
        try:
            # 根据条件决定后续执行分支。
            if os.name == "posix" and (os.stat(cookies_file).st_mode & 0o077):
                # 执行当前步骤的业务处理。
                os.chmod(cookies_file, 0o600)
                # 输出运行提示、进度或错误信息。
                print("  ✓ 已将 Cookie 文件权限收紧为 600")
        # 捕获并处理指定的异常情况。
        except OSError as e:
            # 输出运行提示、进度或错误信息。
            print(f"  ⚠ 无法收紧 Cookie 文件权限: {e}")


        # 输出运行提示、进度或错误信息。
        print(f"正在加载 Cookie: {cookies_file}")
        # 使用上下文管理器并在结束时自动清理资源。
        with open(cookies_file, "r", encoding="utf-8") as f:
            # 解析或写入 JSON 配置与数据。
            cookies = json.load(f)


        # 先访问 x.com 建立域名上下文
        # 输出运行提示、进度或错误信息。
        print("正在访问 x.com ...")
        # 遍历集合中的元素并逐项处理。
        for attempt in range(3):
            # 开始可能抛出异常的受保护操作。
            try:
                # 调用浏览器驱动完成当前操作。
                self.driver.get("https://x.com")
                # 控制当前循环或占位分支的执行。
                break
            # 捕获并处理指定的异常情况。
            except Exception:
                # 根据条件决定后续执行分支。
                if attempt < 2:
                    # 输出运行提示、进度或错误信息。
                    print(f"  ⚠ 页面加载超时，重试 ({attempt+1}/3)...")
                    # 执行当前步骤的业务处理。
                    time.sleep(5)
                # 处理前述条件不成立的情况。
                else:
                    # 主动抛出异常以中止无效流程。
                    raise
        # 执行当前步骤的业务处理。
        self._wait_for_page_ready()


        # 注入 Cookie
        # 根据条件决定后续执行分支。
        if isinstance(cookies, dict):
            # 遍历集合中的元素并逐项处理。
            for name, value in cookies.items():
                # 开始可能抛出异常的受保护操作。
                try:
                    # 调用浏览器驱动完成当前操作。
                    self.driver.add_cookie({"name": name, "value": value})
                # 捕获并处理指定的异常情况。
                except Exception as e:
                    # 输出运行提示、进度或错误信息。
                    print(f"  ⚠ 添加 Cookie '{name}' 失败: {e}")
        # 根据条件决定后续执行分支。
        elif isinstance(cookies, list):
            # 遍历集合中的元素并逐项处理。
            for cookie in cookies:
                # 开始可能抛出异常的受保护操作。
                try:
                    # 调用浏览器驱动完成当前操作。
                    self.driver.add_cookie(cookie)
                # 捕获并处理指定的异常情况。
                except Exception as e:
                    # 输出运行提示、进度或错误信息。
                    print(f"  ⚠ 添加 Cookie 失败: {e}")


        # 刷新页面使 Cookie 生效
        # 输出运行提示、进度或错误信息。
        print("正在刷新验证登录状态...")
        # 遍历集合中的元素并逐项处理。
        for attempt in range(3):
            # 开始可能抛出异常的受保护操作。
            try:
                # 调用浏览器驱动完成当前操作。
                self.driver.get("https://x.com")
                # 控制当前循环或占位分支的执行。
                break
            # 捕获并处理指定的异常情况。
            except Exception:
                # 根据条件决定后续执行分支。
                if attempt < 2:
                    # 输出运行提示、进度或错误信息。
                    print(f"  ⚠ 页面加载超时，重试 ({attempt+1}/3)...")
                    # 执行当前步骤的业务处理。
                    time.sleep(5)
                # 处理前述条件不成立的情况。
                else:
                    # 输出运行提示、进度或错误信息。
                    print("  ⚠ 页面加载较慢，继续尝试...")
        # 执行当前步骤的业务处理。
        self._wait_for_page_ready()


        # 调用浏览器驱动完成当前操作。
        page_source = self.driver.page_source
        # 根据条件决定后续执行分支。
        if "Something went wrong" in page_source:
            # 输出运行提示、进度或错误信息。
            print("⚠ X 返回错误页面，可能需要等待限流解除后重试")
        # 根据条件决定后续执行分支。
        elif "Sign in" in page_source or "login" in self.driver.current_url.lower():
            # 输出运行提示、进度或错误信息。
            print("⚠ 可能未成功登录，请检查 Cookie 是否有效")
        # 处理前述条件不成立的情况。
        else:
            # 输出运行提示、进度或错误信息。
            print("✓ Cookie 登录成功")


    # ----- JS 批量提取 -----


    # 定义可复用的处理函数。
    def _extract_tweets_batch(self):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """通过 JS 在浏览器端原子提取所有可见推文数据，返回 dict 列表。"""
        # 开始可能抛出异常的受保护操作。
        try:
            # 在浏览器页面中执行 JavaScript。
            json_str = self.driver.execute_script(self._EXTRACT_TWEETS_JS)
            # 根据条件决定后续执行分支。
            if json_str and len(json_str) > 2:  # 不是空数组 "[]"
                # 将本函数的计算结果返回给调用处。
                return json.loads(json_str)
            # 将本函数的计算结果返回给调用处。
            return []
        # 捕获并处理指定的异常情况。
        except Exception as e:
            # 输出运行提示、进度或错误信息。
            print(f"  ⚠ JS 批量提取推文失败: {e}")
            # 将本函数的计算结果返回给调用处。
            return []


    # 定义可复用的处理函数。
    def _expand_visible_tweet_texts(self, max_expansions=100):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """在提取前展开当前可见帖文中被折叠的正文。

        只点击 X 专用于帖文正文的 data-testid 控件。每次点击后重新查询 DOM，
        避免继续使用 X 虚拟列表中已经失效的元素引用；页面其他“更多”按钮不处理。
        """
        # 设置或更新本行涉及的变量值。
        expanded = 0
        # 设置或更新本行涉及的变量值。
        attempted = set()


        # 遍历集合中的元素并逐项处理。
        for _ in range(max(0, int(max_expansions))):
            # 开始可能抛出异常的受保护操作。
            try:
                # 在页面 DOM 中定位目标元素。
                controls = self.driver.find_elements(
                    # 执行当前步骤的业务处理。
                    By.CSS_SELECTOR, self.TWEET_TEXT_SHOW_MORE_SELECTOR
                # 结束上一行开始的数据结构或表达式。
                )
            # 捕获并处理指定的异常情况。
            except Exception:
                # 将本函数的计算结果返回给调用处。
                return expanded


            # 设置或更新本行涉及的变量值。
            control = None
            # 遍历集合中的元素并逐项处理。
            for candidate in controls:
                # 设置或更新本行涉及的变量值。
                key = getattr(candidate, "id", None) or f"object-{id(candidate)}"
                # 根据条件决定后续执行分支。
                if key in attempted:
                    # 控制当前循环或占位分支的执行。
                    continue
                # 执行当前步骤的业务处理。
                attempted.add(key)
                # 开始可能抛出异常的受保护操作。
                try:
                    # 根据条件决定后续执行分支。
                    if not candidate.is_displayed():
                        # 控制当前循环或占位分支的执行。
                        continue
                # 捕获并处理指定的异常情况。
                except Exception:
                    # 控制当前循环或占位分支的执行。
                    continue
                # 设置或更新本行涉及的变量值。
                control = candidate
                # 控制当前循环或占位分支的执行。
                break


            # 根据条件决定后续执行分支。
            if control is None:
                # 控制当前循环或占位分支的执行。
                break


            # 开始可能抛出异常的受保护操作。
            try:
                # 在浏览器页面中执行 JavaScript。
                self.driver.execute_script("arguments[0].click();", control)
                # 设置或更新本行涉及的变量值。
                expanded += 1
                # 设置或更新本行涉及的变量值。
                pause = max(0.0, float(getattr(self, "scroll_pause", 0.3)))
                # 执行当前步骤的业务处理。
                time.sleep(min(pause, 0.5))
            # 捕获并处理指定的异常情况。
            except Exception:
                # 点击可能立即替换整个帖文节点；下一轮重新查询，不复用旧元素。
                # 控制当前循环或占位分支的执行。
                continue


        # 根据条件决定后续执行分支。
        if expanded:
            # 输出运行提示、进度或错误信息。
            print(f"  已展开 {expanded} 条折叠帖文正文")
        # 将本函数的计算结果返回给调用处。
        return expanded


    # ----- 滚动加载 -----


    # 定义可复用的处理函数。
    def _wait_for_initial_tweets_or_empty(self, timeout=12):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """等待 X 异步渲染首屏结果，避免把加载中的空 DOM 当作零结果。

        X 的 ``document.readyState`` 先于搜索结果到达；若随即以短间隔
        滚动，旧逻辑会在数秒内触发“无新推文”早停。这里同时接受明确的
        空结果提示，因而真实零结果不会被无谓地等待到超时。
        """
        # 设置或更新本行涉及的变量值。
        empty_markers = ("no results", "没有结果", "未找到结果", "无结果")


        # 定义可复用的处理函数。
        def ready(driver):
            # 开始可能抛出异常的受保护操作。
            try:
                # 根据条件决定后续执行分支。
                if driver.find_elements(By.CSS_SELECTOR, self.TWEET_SELECTOR):
                    # 将本函数的计算结果返回给调用处。
                    return True
                # 设置或更新本行涉及的变量值。
                source = (driver.page_source or "").casefold()
                # 将本函数的计算结果返回给调用处。
                return any(marker in source for marker in empty_markers)
            # 捕获并处理指定的异常情况。
            except Exception:
                # 将本函数的计算结果返回给调用处。
                return False


        # 开始可能抛出异常的受保护操作。
        try:
            # 调用浏览器驱动完成当前操作。
            WebDriverWait(self.driver, timeout).until(ready)
            # 将本函数的计算结果返回给调用处。
            return True
        # 捕获并处理指定的异常情况。
        except Exception:
            # 输出运行提示、进度或错误信息。
            print("  ⚠ 首屏结果未在等待时间内出现；继续以滚动方式复核")
            # 将本函数的计算结果返回给调用处。
            return False


    # 定义可复用的处理函数。
    def _scroll_to_load(self, target_count, label="推文", max_scrolls=200,
                        # 设置或更新本行涉及的变量值。
                        since_date=None, until_date=None, keyword_filter=False,
                        # 设置或更新本行涉及的变量值。
                        expected_author=None, any_words_filter=None,
                        # 设置或更新本行涉及的变量值。
                        relevance_audit=False):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """滚动页面加载更多推文。

        Args:
            target_count: 目标推文数量
            label: 日志标签
            max_scrolls: 最大滚动次数
            since_date: 起始日期 'YYYY-MM-DD'
            until_date: 截止日期 'YYYY-MM-DD'
            keyword_filter: 是否启用新疆关键词过滤

        Returns:
            推文数据 dict 列表（已去重）
        """
        # 根据条件决定后续执行分支。
        if target_count <= 0:
            # 将本函数的计算结果返回给调用处。
            return []


        # 设置或更新本行涉及的变量值。
        since_date = self._validate_date(since_date, "since_date")
        # 设置或更新本行涉及的变量值。
        until_date = self._validate_date(until_date, "until_date")
        # 根据条件决定后续执行分支。
        if since_date and until_date and since_date > until_date:
            # 主动抛出异常以中止无效流程。
            raise ValueError("since_date 不能晚于 until_date")


        # 执行当前步骤的业务处理。
        self._wait_for_initial_tweets_or_empty()
        # 设置或更新本行涉及的变量值。
        collected = []
        # 设置或更新本行涉及的变量值。
        local_seen_ids = set()
        # 设置或更新本行涉及的变量值。
        stale_count = 0
        # 时间线最上方可能混有置顶推文（顺序与实际发布时间无关），且置顶推文
        # 前面还可能夹着不匹配关键词而被跳过的正常推文，因此置顶徽章检测不完全
        # 可靠时，仅保护"第一条"不够。这里保守地保护前 N_PINNED_GUARD 条新推文，
        # 即使日期早于 since_date 也只跳过、不据此触发提前停止滚动。
        # 设置或更新本行涉及的变量值。
        N_PINNED_GUARD = 3
        # 设置或更新本行涉及的变量值。
        new_tweet_index = 0
        # 设置或更新本行涉及的变量值。
        old_date_streak = 0


        # 遍历集合中的元素并逐项处理。
        for scroll_num in range(max_scrolls):
            # 执行当前步骤的业务处理。
            self._expand_visible_tweet_texts()
            # 设置或更新本行涉及的变量值。
            batch = sorted(
                # 续写当前数据结构、参数列表或表达式。
                self._extract_tweets_batch(),
                # 读取字典或配置中的对应值。
                key=lambda item: item.get("dom_index", 0) if item else 0,
            # 结束上一行开始的数据结构或表达式。
            )
            # 设置或更新本行涉及的变量值。
            new_seen_this_round = 0


            # 遍历集合中的元素并逐项处理。
            for data in batch:
                # 根据条件决定后续执行分支。
                if len(collected) >= target_count:
                    # 控制当前循环或占位分支的执行。
                    break
                # 根据条件决定后续执行分支。
                if not data or not data.get("id"):
                    # 控制当前循环或占位分支的执行。
                    continue
                # 根据条件决定后续执行分支。
                if data["id"] in local_seen_ids:
                    # 控制当前循环或占位分支的执行。
                    continue


                # 标记为已扫描（无论是否匹配关键词），避免同一条推文
                # 在后续每次滚动中被反复重新扫描，导致"是否有新内容"的
                # 判断失真、提前误判为停滞而中断滚动
                # 执行当前步骤的业务处理。
                local_seen_ids.add(data["id"])
                # 设置或更新本行涉及的变量值。
                new_seen_this_round += 1
                # 设置或更新本行涉及的变量值。
                is_guarded = new_tweet_index < N_PINNED_GUARD
                # 设置或更新本行涉及的变量值。
                new_tweet_index += 1


                # 先做时间过滤。否则旧的不相关推文会在关键词处 continue，
                # 程序就无法及时感知已经翻过 since_date。
                # 读取字典或配置中的对应值。
                created = data.get("created_at", "")
                # 设置或更新本行涉及的变量值。
                created_date = self._cst_date_from_iso(created)
                # 根据条件决定后续执行分支。
                if (since_date or until_date) and not created_date:
                    # 设置或更新本行涉及的变量值。
                    self.skipped_count += 1
                    # 控制当前循环或占位分支的执行。
                    continue
                # 根据条件决定后续执行分支。
                if since_date and created_date < since_date:
                    # 根据条件决定后续执行分支。
                    if is_guarded:
                        # 疑似置顶推文导致的时间乱序，跳过但不中断滚动
                        # 控制当前循环或占位分支的执行。
                        continue
                    # 设置或更新本行涉及的变量值。
                    old_date_streak += 1
                    # 两条连续旧推文才早停，容忍一条算法插入/时间乱序。
                    # 根据条件决定后续执行分支。
                    if old_date_streak >= 2:
                        # 输出运行提示、进度或错误信息。
                        print(f"  连续推文时间早于 {since_date}，停止滚动")
                        # 设置或更新本行涉及的变量值。
                        self._stop_early = True
                        # 控制当前循环或占位分支的执行。
                        break
                    # 控制当前循环或占位分支的执行。
                    continue
                # 设置或更新本行涉及的变量值。
                old_date_streak = 0
                # 根据条件决定后续执行分支。
                if until_date and created_date > until_date:
                    # 控制当前循环或占位分支的执行。
                    continue


                # 根据条件决定后续执行分支。
                if expected_author:
                    # 读取字典或配置中的对应值。
                    handle = data.get("author_handle", "")
                    # 根据条件决定后续执行分支。
                    if handle.casefold() != expected_author.casefold():
                        # 设置或更新本行涉及的变量值。
                        self.skipped_count += 1
                        # 控制当前循环或占位分支的执行。
                        continue


                # 根据条件决定后续执行分支。
                if any_words_filter and not matches_any_words(
                    # 读取字典或配置中的对应值。
                    data.get("text", ""), any_words_filter
                # 结束上一行开始的数据结构或表达式。
                ):
                    # 设置或更新本行涉及的变量值。
                    self.skipped_count += 1
                    # 控制当前循环或占位分支的执行。
                    continue


                # X 搜索只负责召回候选项；最终仍在本地执行严格相关性审核。
                # 根据条件决定后续执行分支。
                if relevance_audit and not matches_xinjiang(data.get("text", "")):
                    # 设置或更新本行涉及的变量值。
                    self.skipped_count += 1
                    # 控制当前循环或占位分支的执行。
                    continue


                # 关键词在时间判断之后处理。
                # 根据条件决定后续执行分支。
                if keyword_filter and not matches_xinjiang(data.get("text", "")):
                    # 设置或更新本行涉及的变量值。
                    self.skipped_count += 1
                    # 控制当前循环或占位分支的执行。
                    continue


                # 将当前结果追加到列表或集合。
                collected.append(data)
                # 执行当前步骤的业务处理。
                self.tweet_ids.add(data["id"])


            # 设置或更新本行涉及的变量值。
            current_unique = len(collected)


            # 根据条件决定后续执行分支。
            if current_unique >= target_count:
                # 输出运行提示、进度或错误信息。
                print(f"  已收集 {current_unique} 条推文 (目标 {target_count})")
                # 控制当前循环或占位分支的执行。
                break


            # 根据条件决定后续执行分支。
            if getattr(self, '_stop_early', False):
                # 设置或更新本行涉及的变量值。
                self._stop_early = False
                # 控制当前循环或占位分支的执行。
                break


            # 停滞判断依据"本轮是否扫描到任何新推文"（无论匹配与否），
            # 而不是只看匹配到的数量，避免因连续出现不相关推文而提前停止
            # 根据条件决定后续执行分支。
            if new_seen_this_round == 0:
                # 设置或更新本行涉及的变量值。
                stale_count += 1
                # 根据条件决定后续执行分支。
                if stale_count >= 5:
                    # 输出运行提示、进度或错误信息。
                    print(f"  连续 {stale_count} 次无新推文，停止滚动")
                    # 控制当前循环或占位分支的执行。
                    break
            # 处理前述条件不成立的情况。
            else:
                # 设置或更新本行涉及的变量值。
                stale_count = 0
                # 输出运行提示、进度或错误信息。
                print(f"  已收集 {current_unique} 条推文 (目标 {target_count}，"
                      # 执行当前步骤的业务处理。
                      f"本轮新扫描 {new_seen_this_round} 条)")


            # 滚动本身不是新的 HTTP 导航，不再套用 8~15 秒的导航限流。
            # 按视口小步滚动，避免直接跳到 document.body.scrollHeight
            # 跳过 X 虚拟列表中尚未进入 DOM 的推文。
            # 设置或更新本行涉及的变量值。
            multiplier = 1.5 if stale_count >= 2 else 0.85
            # 在浏览器页面中执行 JavaScript。
            self.driver.execute_script(
                # 续写当前数据结构、参数列表或表达式。
                "window.scrollBy(0, Math.max(600, window.innerHeight * arguments[0]));",
                # 续写当前数据结构、参数列表或表达式。
                multiplier,
            # 结束上一行开始的数据结构或表达式。
            )
            # 执行当前步骤的业务处理。
            time.sleep(self.scroll_pause)


        # 将本函数的计算结果返回给调用处。
        return collected


    # ----- 页面导航（带重试） -----


    # 定义可复用的处理函数。
    def _navigate(self, url, label="页面", max_retries=None):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """安全导航到指定 URL，带超时重试。"""
        # 根据条件决定后续执行分支。
        if max_retries is None:
            # 设置或更新本行涉及的变量值。
            max_retries = max(1, int(self.rate_limiter.max_retries))
        # 遍历集合中的元素并逐项处理。
        for attempt in range(max_retries):
            # 开始可能抛出异常的受保护操作。
            try:
                # 调用浏览器驱动完成当前操作。
                self.driver.get(url)
                # 调用浏览器驱动完成当前操作。
                source = (self.driver.page_source or "").casefold()
                # 设置或更新本行涉及的变量值。
                limited = any(marker in source for marker in (
                    # 续写当前数据结构、参数列表或表达式。
                    "rate limit exceeded", "too many requests", "请求过于频繁",
                # 结束上一行开始的数据结构或表达式。
                ))
                # 根据条件决定后续执行分支。
                if limited:
                    # 根据条件决定后续执行分支。
                    if attempt < max_retries - 1:
                        # 设置或更新本行涉及的变量值。
                        delay = min(60, 10 * (2 ** attempt))
                        # 输出运行提示、进度或错误信息。
                        print(f"  ⚠ [{label}] 检测到限流，{delay}s 后重试...")
                        # 执行当前步骤的业务处理。
                        time.sleep(delay)
                        # 控制当前循环或占位分支的执行。
                        continue
                    # 输出运行提示、进度或错误信息。
                    print(f"  ✗ [{label}] 平台仍在限流，放弃当前页面")
                    # 将本函数的计算结果返回给调用处。
                    return False
                # 执行当前步骤的业务处理。
                self.rate_limiter.batch_pause()
                # 将本函数的计算结果返回给调用处。
                return True
            # 捕获并处理指定的异常情况。
            except Exception as e:
                # 根据条件决定后续执行分支。
                if attempt < max_retries - 1:
                    # 输出运行提示、进度或错误信息。
                    print(f"  ⚠ [{label}] 加载超时，重试 ({attempt+1}/{max_retries})...")
                    # 执行当前步骤的业务处理。
                    time.sleep(5)
                # 处理前述条件不成立的情况。
                else:
                    # 输出运行提示、进度或错误信息。
                    print(f"  ✗ [{label}] 加载失败: {e}")
                    # 将本函数的计算结果返回给调用处。
                    return False
        # 将本函数的计算结果返回给调用处。
        return False


    # ----- 抓取方法 -----


    # 定义可复用的处理函数。
    def fetch_tweet(self, tweet_id):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """获取单条推文详情。"""
        # 设置或更新本行涉及的变量值。
        tweet_id = self._validate_tweet_id(tweet_id)
        # 设置或更新本行涉及的变量值。
        url = f"https://x.com/i/status/{tweet_id}"
        # 输出运行提示、进度或错误信息。
        print(f"正在访问: {url}")


        # 执行当前步骤的业务处理。
        self.rate_limiter.wait(label="获取推文")
        # 根据条件决定后续执行分支。
        if not self._navigate(url, label="推文"):
            # 将本函数的计算结果返回给调用处。
            return []
        # 执行当前步骤的业务处理。
        self._wait_for_page_ready()


        # 开始可能抛出异常的受保护操作。
        try:
            # 调用浏览器驱动完成当前操作。
            WebDriverWait(self.driver, 10).until(
                # 执行当前步骤的业务处理。
                EC.presence_of_element_located((By.CSS_SELECTOR, self.TWEET_SELECTOR))
            # 结束上一行开始的数据结构或表达式。
            )
        # 捕获并处理指定的异常情况。
        except Exception:
            # 输出运行提示、进度或错误信息。
            print(f"  ⚠ 推文加载超时，可能不存在或无权限访问")
            # 将本函数的计算结果返回给调用处。
            return []


        # 执行当前步骤的业务处理。
        self._expand_visible_tweet_texts()
        # 设置或更新本行涉及的变量值。
        batch = self._extract_tweets_batch()
        # 根据条件决定后续执行分支。
        if not batch:
            # 输出运行提示、进度或错误信息。
            print(f"  ✗ 未找到推文元素")
            # 将本函数的计算结果返回给调用处。
            return []


        # 读取字典或配置中的对应值。
        tweet_data = next((item for item in batch if item.get("id") == tweet_id), None)
        # 根据条件决定后续执行分支。
        if not tweet_data:
            # 输出运行提示、进度或错误信息。
            print(f"  ✗ 页面中未找到目标推文 ID {tweet_id}")
            # 将本函数的计算结果返回给调用处。
            return []
        # 根据条件决定后续执行分支。
        if tweet_data:
            # 执行当前步骤的业务处理。
            self.tweet_ids.add(tweet_data["id"])
            # 设置或更新本行涉及的变量值。
            self.got_count += 1
            # 输出运行提示、进度或错误信息。
            print(f"  ✓ 获取成功: @{tweet_data['author_handle']}")
            # 设置或更新本行涉及的变量值。
            txt = tweet_data['text']
            # 输出运行提示、进度或错误信息。
            print(f"    内容: {txt[:80]}..." if len(txt) > 80 else f"    内容: {txt}")
            # 将本函数的计算结果返回给调用处。
            return [tweet_data]
        # 将本函数的计算结果返回给调用处。
        return []


    # 定义可复用的处理函数。
    def fetch_user_timeline(self, screen_name, count=20, since_date=None, until_date=None,
                            # 设置或更新本行涉及的变量值。
                            keyword_filter=False):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """获取指定用户的最新推文。"""
        # 设置或更新本行涉及的变量值。
        screen_name = self._validate_screen_name(screen_name)
        # 设置或更新本行涉及的变量值。
        since_date = self._validate_date(since_date, "--since")
        # 设置或更新本行涉及的变量值。
        until_date = self._validate_date(until_date, "--until")
        # 根据条件决定后续执行分支。
        if since_date and until_date and since_date > until_date:
            # 主动抛出异常以中止无效流程。
            raise ValueError("--since 不能晚于 --until")
        # 根据条件决定后续执行分支。
        if count <= 0:
            # 主动抛出异常以中止无效流程。
            raise ValueError("--count 必须大于 0")
        # 输出运行提示、进度或错误信息。
        print(f"正在访问用户主页: @{screen_name}")
        # 根据条件决定后续执行分支。
        if since_date or until_date:
            # 输出运行提示、进度或错误信息。
            print(f"时间段: {since_date or '不限'} ~ {until_date or '不限'}")
        # 根据条件决定后续执行分支。
        if keyword_filter:
            # 输出运行提示、进度或错误信息。
            print(f"关键词过滤: 新疆/Uyghur/Xinjiang")
        # 输出运行提示、进度或错误信息。
        print(f"目标: {count} 条推文")


        # 根据条件决定后续执行分支。
        if not self._load_profile_stats(screen_name):
            # 将本函数的计算结果返回给调用处。
            return []


        # 设置或更新本行涉及的变量值。
        tweets = self._scroll_to_load(
            # 续写当前数据结构、参数列表或表达式。
            count, label=f"@{screen_name}",
            # 设置或更新本行涉及的变量值。
            since_date=since_date, until_date=until_date,
            # 设置或更新本行涉及的变量值。
            keyword_filter=keyword_filter,
            # 设置或更新本行涉及的变量值。
            expected_author=screen_name,
        # 结束上一行开始的数据结构或表达式。
        )


        # 设置或更新本行涉及的变量值。
        self.got_count += len(tweets)
        # 输出运行提示、进度或错误信息。
        print(f"  ✓ 实际获取 {len(tweets)} 条 @{screen_name} 的推文")
        # 根据条件决定后续执行分支。
        if keyword_filter and self.skipped_count > 0:
            # 输出运行提示、进度或错误信息。
            print(f"     (跳过 {self.skipped_count} 条不相关推文)")
        # 将本函数的计算结果返回给调用处。
        return tweets


    # 定义可复用的处理函数。
    def _load_profile_stats(self, screen_name):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """访问账号主页并在滚动前保存 Profile 统计。"""
        # 设置或更新本行涉及的变量值。
        screen_name = self._validate_screen_name(screen_name)
        # 设置或更新本行涉及的变量值。
        url = f"https://x.com/{screen_name}"
        # 执行当前步骤的业务处理。
        self.rate_limiter.wait(label="访问主页")
        # 根据条件决定后续执行分支。
        if not self._navigate(url, label="用户主页"):
            # 将本函数的计算结果返回给调用处。
            return False
        # 执行当前步骤的业务处理。
        self._wait_for_page_ready()
        # Profile 统计位于页面顶部，滚动后会被 X 的虚拟 DOM 移除。
        # 设置或更新本行涉及的变量值。
        self._last_profile_stats = self._get_profile_stats(screen_name)
        # 将本函数的计算结果返回给调用处。
        return True


    # 定义可复用的处理函数。
    def fetch_account_advanced_search(
        # 续写当前数据结构、参数列表或表达式。
        self,
        # 续写当前数据结构、参数列表或表达式。
        screen_name,
        # 设置或更新本行涉及的变量值。
        count=9999,
        # 设置或更新本行涉及的变量值。
        since_date=DEFAULT_ARCHIVE_SINCE,
        # 设置或更新本行涉及的变量值。
        until_date=DEFAULT_ARCHIVE_UNTIL,
        # 设置或更新本行涉及的变量值。
        any_words=None,
        # 设置或更新本行涉及的变量值。
        load_profile=True,
    # 结束上一行开始的数据结构或表达式。
    ):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """用 X 高级搜索抓取指定账号、日期范围和任一关键词命中的帖子。"""
        # 设置或更新本行涉及的变量值。
        screen_name = self._validate_screen_name(screen_name)
        # 设置或更新本行涉及的变量值。
        since_date = self._validate_date(since_date, "--since")
        # 设置或更新本行涉及的变量值。
        until_date = self._validate_date(until_date, "--until")
        # 根据条件决定后续执行分支。
        if count <= 0:
            # 主动抛出异常以中止无效流程。
            raise ValueError("--count 必须大于 0")
        # 设置或更新本行涉及的变量值。
        source_words = self.advanced_search_words if any_words is None else any_words
        # 设置或更新本行涉及的变量值。
        words = self._normalize_any_words(source_words)
        # 设置或更新本行涉及的变量值。
        query = self.build_account_advanced_query(
            # 续写当前数据结构、参数列表或表达式。
            screen_name,
            # 设置或更新本行涉及的变量值。
            any_words=words,
            # 设置或更新本行涉及的变量值。
            since_date=since_date,
            # 设置或更新本行涉及的变量值。
            until_date=until_date,
        # 结束上一行开始的数据结构或表达式。
        )


        # 输出运行提示、进度或错误信息。
        print(f"正在使用 X 高级搜索抓取 @{screen_name}")
        # 输出运行提示、进度或错误信息。
        print(f"Any of these words: {' / '.join(words)}")
        # 输出运行提示、进度或错误信息。
        print(f"时间段（含首尾）: {since_date} ~ {until_date}")
        # 输出运行提示、进度或错误信息。
        print(f"高级搜索查询: {query}")
        # 输出运行提示、进度或错误信息。
        print(f"目标: {count} 条推文")


        # 根据条件决定后续执行分支。
        if load_profile and not self._load_profile_stats(screen_name):
            # 设置或更新本行涉及的变量值。
            self._last_profile_stats = ("", "")
            # 输出运行提示、进度或错误信息。
            print("  ⚠ Profile 统计读取失败，继续执行高级搜索")


        # 设置或更新本行涉及的变量值。
        encoded_query = quote_plus(query)
        # 设置或更新本行涉及的变量值。
        url = f"https://x.com/search?q={encoded_query}&src=typed_query&f=live"
        # 执行当前步骤的业务处理。
        self.rate_limiter.wait(label="账号高级搜索")
        # 根据条件决定后续执行分支。
        if not self._navigate(url, label="账号高级搜索"):
            # 将本函数的计算结果返回给调用处。
            return []
        # 执行当前步骤的业务处理。
        self._wait_for_page_ready()


        # 设置或更新本行涉及的变量值。
        tweets = self._scroll_to_load(
            # 续写当前数据结构、参数列表或表达式。
            count,
            # 设置或更新本行涉及的变量值。
            label=f"高级搜索@{screen_name}",
            # 设置或更新本行涉及的变量值。
            since_date=since_date,
            # 设置或更新本行涉及的变量值。
            until_date=until_date,
            # 设置或更新本行涉及的变量值。
            expected_author=screen_name,
            # 设置或更新本行涉及的变量值。
            any_words_filter=words,
            # 设置或更新本行涉及的变量值。
            relevance_audit=getattr(self, "strict_xinjiang_audit", True),
        # 结束上一行开始的数据结构或表达式。
        )
        # 设置或更新本行涉及的变量值。
        self.got_count += len(tweets)
        # 输出运行提示、进度或错误信息。
        print(f"  ✓ 高级搜索实际获取 {len(tweets)} 条 @{screen_name} 的相关推文")
        # 将本函数的计算结果返回给调用处。
        return tweets


    # 定义可复用的处理函数。
    def fetch_search_tweets(self, query, count=20, product="Latest"):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """根据关键词搜索推文。"""
        # 根据条件决定后续执行分支。
        if count <= 0:
            # 主动抛出异常以中止无效流程。
            raise ValueError("--count 必须大于 0")
        # 设置或更新本行涉及的变量值。
        encoded_query = quote_plus(query)
        # 设置或更新本行涉及的变量值。
        url = f"https://x.com/search?q={encoded_query}&f={'live' if product == 'Latest' else 'top'}"
        # 输出运行提示、进度或错误信息。
        print(f"正在搜索: \"{query}\" (类型: {product}, 目标: {count} 条)")


        # 执行当前步骤的业务处理。
        self.rate_limiter.wait(label="搜索")
        # 根据条件决定后续执行分支。
        if not self._navigate(url, label="搜索"):
            # 将本函数的计算结果返回给调用处。
            return []
        # 执行当前步骤的业务处理。
        self._wait_for_page_ready()


        # 设置或更新本行涉及的变量值。
        tweets = self._scroll_to_load(count, label="搜索")
        # 设置或更新本行涉及的变量值。
        self.got_count += len(tweets)
        # 输出运行提示、进度或错误信息。
        print(f"  ✓ 实际获取 {len(tweets)} 条搜索结果")
        # 将本函数的计算结果返回给调用处。
        return tweets


    # ----- 评论 & 子评论抓取 -----


    # 应用装饰器以调整后续定义的行为。
    @staticmethod
    # 定义可复用的处理函数。
    def _is_direct_reply(candidate, parent_author):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """只在页面明确标注候选帖回复了目标作者时认定归属。"""
        # 设置或更新本行涉及的变量值。
        expected = str(parent_author or "").strip().lstrip("@").casefold()
        # 根据条件决定后续执行分支。
        if not expected:
            # 将本函数的计算结果返回给调用处。
            return False
        # 设置或更新本行涉及的变量值。
        reply_handles = {
            # 执行当前步骤的业务处理。
            handle.strip().lstrip("@").casefold()
            # 遍历集合中的元素并逐项处理。
            for handle in candidate.get("reply_to_handles", "").split(",")
            # 根据条件决定后续执行分支。
            if handle.strip()
        # 结束上一行开始的数据结构或表达式。
        }
        # 将本函数的计算结果返回给调用处。
        return expected in reply_handles


    # 应用装饰器以调整后续定义的行为。
    @staticmethod
    # 定义可复用的处理函数。
    def _select_conversation_items(candidates, target_id, target_author, max_items=1000):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """从帖子详情页中保留对话链前后文、直接回复和子回复。

        X 详情页中目标帖之前的帖子是对话前文，目标帖之后、
        “Discover more / 更多推文”边界之前的内容视为回复区。
        """
        # 设置或更新本行涉及的变量值。
        target_id = str(target_id or "")
        # 读取字典或配置中的对应值。
        ordered = [item for item in candidates if item and item.get("id")]
        # 设置或更新本行涉及的变量值。
        target_index = next(
            # 读取字典或配置中的对应值。
            (index for index, item in enumerate(ordered) if str(item.get("id")) == target_id),
            # 续写当前数据结构、参数列表或表达式。
            None,
        # 结束上一行开始的数据结构或表达式。
        )
        # 根据条件决定后续执行分支。
        if target_index is None:
            # 将本函数的计算结果返回给调用处。
            return []


        # 设置或更新本行涉及的变量值。
        expected = str(target_author or "").strip().lstrip("@").casefold()
        # 设置或更新本行涉及的变量值。
        selected = []
        # 遍历集合中的元素并逐项处理。
        for index, item in enumerate(ordered):
            # 根据条件决定后续执行分支。
            if str(item.get("id")) == target_id or item.get("is_promoted"):
                # 控制当前循环或占位分支的执行。
                continue
            # 根据条件决定后续执行分支。
            if index > target_index and item.get("is_recommendation"):
                # 控制当前循环或占位分支的执行。
                break
            # 根据条件决定后续执行分支。
            if index < target_index and item.get("is_recommendation"):
                # 控制当前循环或占位分支的执行。
                continue


            # 设置或更新本行涉及的变量值。
            copy = dict(item)
            # 设置或更新本行涉及的变量值。
            reply_handles = {
                # 执行当前步骤的业务处理。
                handle.strip().lstrip("@").casefold()
                # 遍历集合中的元素并逐项处理。
                for handle in copy.get("reply_to_handles", "").split(",")
                # 根据条件决定后续执行分支。
                if handle.strip()
            # 结束上一行开始的数据结构或表达式。
            }
            # 根据条件决定后续执行分支。
            if index < target_index:
                # 设置或更新本行涉及的变量值。
                copy["thread_relation"] = "context"
            # 根据条件决定后续执行分支。
            elif expected and expected in reply_handles:
                # 设置或更新本行涉及的变量值。
                copy["thread_relation"] = "direct_reply"
            # 根据条件决定后续执行分支。
            elif reply_handles:
                # 设置或更新本行涉及的变量值。
                copy["thread_relation"] = "nested_reply"
            # 处理前述条件不成立的情况。
            else:
                # 设置或更新本行涉及的变量值。
                copy["thread_relation"] = "thread_item"
            # 将当前结果追加到列表或集合。
            selected.append(copy)
            # 根据条件决定后续执行分支。
            if len(selected) >= max_items:
                # 控制当前循环或占位分支的执行。
                break
        # 将本函数的计算结果返回给调用处。
        return selected


    # 定义可复用的处理函数。
    def _fetch_comments_for_tweet(self, tweet_url, max_comments=20, max_depth=1,
                                  # 设置或更新本行涉及的变量值。
                                  current_depth=0, _visited=None):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """获取指定推文的所有评论及子评论（递归）。

        Args:
            tweet_url: 推文链接
            max_comments: 最多获取多少条一级评论
            max_depth: 子评论递归深度（0=仅一级评论, 1=含子评论, 默认1）

        Returns:
            list[dict]: 所有评论（含子评论），每条包含 parent_tweet_id, parent_author, depth 字段
        """
        # 根据条件决定后续执行分支。
        if max_comments <= 0:
            # 将本函数的计算结果返回给调用处。
            return []
        # 根据条件决定后续执行分支。
        if max_depth < 0:
            # 主动抛出异常以中止无效流程。
            raise ValueError("max_depth 不能小于 0")


        # 设置或更新本行涉及的变量值。
        parsed = urlparse(tweet_url)
        # 根据条件决定后续执行分支。
        if parsed.hostname not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
            # 主动抛出异常以中止无效流程。
            raise ValueError(f"拒绝访问非 X 域名: {tweet_url!r}")
        # 使用正则表达式完成匹配或提取。
        id_match = re.search(r"/status/(\d{5,25})", parsed.path)
        # 根据条件决定后续执行分支。
        if not id_match:
            # 主动抛出异常以中止无效流程。
            raise ValueError(f"无效的推文链接: {tweet_url!r}")
        # 设置或更新本行涉及的变量值。
        target_id = id_match.group(1)


        # 根据条件决定后续执行分支。
        if _visited is None:
            # 设置或更新本行涉及的变量值。
            _visited = set()
        # 根据条件决定后续执行分支。
        if target_id in _visited:
            # 将本函数的计算结果返回给调用处。
            return []
        # 执行当前步骤的业务处理。
        _visited.add(target_id)


        # 设置或更新本行涉及的变量值。
        all_comments = []
        # 开始可能抛出异常的受保护操作。
        try:
            # 执行当前步骤的业务处理。
            self.rate_limiter.wait(label="获取评论")
            # 根据条件决定后续执行分支。
            if not self._navigate(tweet_url, label="推文详情"):
                # 将本函数的计算结果返回给调用处。
                return all_comments
            # 执行当前步骤的业务处理。
            self._wait_for_page_ready()


            # 等待评论加载
            # 开始可能抛出异常的受保护操作。
            try:
                # 调用浏览器驱动完成当前操作。
                WebDriverWait(self.driver, 10).until(
                    # 执行当前步骤的业务处理。
                    EC.presence_of_element_located((By.CSS_SELECTOR, self.TWEET_SELECTOR))
                # 结束上一行开始的数据结构或表达式。
                )
            # 捕获并处理指定的异常情况。
            except Exception:
                # 将本函数的计算结果返回给调用处。
                return all_comments


            # 设置或更新本行涉及的变量值。
            initial_batch = self._extract_tweets_batch()
            # 读取字典或配置中的对应值。
            target_tweet = next((t for t in initial_batch if t.get("id") == target_id), None)
            # 根据条件决定后续执行分支。
            if not target_tweet:
                # 输出运行提示、进度或错误信息。
                print(f"  ⚠ 未找到目标推文 {target_id}，放弃评论归属")
                # 将本函数的计算结果返回给调用处。
                return all_comments
            # 读取字典或配置中的对应值。
            parent_author = target_tweet.get("author_handle", "").casefold()
            # 根据条件决定后续执行分支。
            if not parent_author:
                # 输出运行提示、进度或错误信息。
                print(f"  ⚠ 无法确定目标推文作者，放弃评论归属")
                # 将本函数的计算结果返回给调用处。
                return all_comments


            # 多扫描一些候选项，保留目标帖的对话链前后文、
            # 直接回复及二、三级回复，并在推荐区标题处停止。
            # 设置或更新本行涉及的变量值。
            candidate_target = max(max_comments * 3, max_comments + 5)
            # 设置或更新本行涉及的变量值。
            candidates = self._scroll_to_load(
                # 续写当前数据结构、参数列表或表达式。
                candidate_target,
                # 设置或更新本行涉及的变量值。
                label="评论",
                # 设置或更新本行涉及的变量值。
                max_scrolls=min(80, max(20, max_comments * 2)),
            # 结束上一行开始的数据结构或表达式。
            )


            # 设置或更新本行涉及的变量值。
            conversation_items = self._select_conversation_items(
                # 执行当前步骤的业务处理。
                candidates, target_id, parent_author, max_items=max_comments
            # 结束上一行开始的数据结构或表达式。
            )
            # 遍历集合中的元素并逐项处理。
            for c in conversation_items:
                # 设置或更新本行涉及的变量值。
                c["depth"] = current_depth
                # 设置或更新本行涉及的变量值。
                c["parent_comment_id"] = target_id if current_depth > 0 else ""
                # 将当前结果追加到列表或集合。
                all_comments.append(c)


            # 输出运行提示、进度或错误信息。
            print(f"    对话链过滤：保留 {len(conversation_items)} 条前后文/回复，排除推广和推荐区")


            # 递归获取子评论
            # 根据条件决定后续执行分支。
            if current_depth < max_depth:
                # 设置或更新本行涉及的变量值。
                direct_comments = [
                    # 执行当前步骤的业务处理。
                    item for item in all_comments
                    # 根据条件决定后续执行分支。
                    if item.get("thread_relation") != "context"
                # 结束上一行开始的数据结构或表达式。
                ]
                # 遍历集合中的元素并逐项处理。
                for i, comment in enumerate(direct_comments):
                    # 根据条件决定后续执行分支。
                    if comment.get("reply_count", 0) > 0:
                        # 读取字典或配置中的对应值。
                        sub_url = comment.get("tweet_url", "")
                        # 根据条件决定后续执行分支。
                        if not sub_url:
                            # 控制当前循环或占位分支的执行。
                            continue
                        # 输出运行提示、进度或错误信息。
                        print(f"    [{i+1}/{len(direct_comments)}] 抓取子评论: "
                            # 执行当前步骤的业务处理。
                            f"@{comment['author_handle']} 的评论 (已有{comment['reply_count']}条回复)...")
                        # 设置或更新本行涉及的变量值。
                        sub_comments = self._fetch_comments_for_tweet(
                            # 续写当前数据结构、参数列表或表达式。
                            sub_url,
                            # 设置或更新本行涉及的变量值。
                            max_comments=min(20, max_comments),
                            # 设置或更新本行涉及的变量值。
                            max_depth=max_depth,
                            # 设置或更新本行涉及的变量值。
                            current_depth=current_depth + 1,
                            # 设置或更新本行涉及的变量值。
                            _visited=_visited,
                        # 结束上一行开始的数据结构或表达式。
                        )
                        # 执行当前步骤的业务处理。
                        all_comments.extend(sub_comments)
                        # 输出运行提示、进度或错误信息。
                        print(f"      → 获取 {len(sub_comments)} 条子评论")


        # 捕获并处理指定的异常情况。
        except Exception as e:
            # 输出运行提示、进度或错误信息。
            print(f"  ⚠ 获取评论时出错: {e}")


        # 将本函数的计算结果返回给调用处。
        return all_comments


    # 定义可复用的处理函数。
    def fetch_comments_for_posts(self, posts, max_comments=None, max_depth=None):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """进入有回复的帖子详情页，抓取实际可见评论并回填实际数量。"""
        # 根据条件决定后续执行分支。
        if max_comments is None:
            # 设置或更新本行涉及的变量值。
            max_comments = self.max_comments_per_post
        # 根据条件决定后续执行分支。
        if max_depth is None:
            # 设置或更新本行涉及的变量值。
            max_depth = self.max_comment_depth
        # 设置或更新本行涉及的变量值。
        max_comments = max(1, min(int(max_comments), 1000))
        # 设置或更新本行涉及的变量值。
        max_depth = max(0, min(int(max_depth), 3))


        # 设置或更新本行涉及的变量值。
        all_comments = []
        # 设置或更新本行涉及的变量值。
        seen_comment_ids = set()
        # 读取字典或配置中的对应值。
        candidates = [post for post in posts if int(post.get("reply_count", 0) or 0) > 0]
        # 输出运行提示、进度或错误信息。
        print(
            # 执行当前步骤的业务处理。
            f"\n评论检查：{len(posts)} 条帖子中有 {len(candidates)} 条显示存在回复，"
            # 执行当前步骤的业务处理。
            "将进入详情页核对实际可见评论"
        # 结束上一行开始的数据结构或表达式。
        )


        # 遍历集合中的元素并逐项处理。
        for index, post in enumerate(posts, start=1):
            # 读取字典或配置中的对应值。
            reported_count = int(post.get("reply_count", 0) or 0)
            # 设置或更新本行涉及的变量值。
            post["actual_comment_count"] = 0
            # 根据条件决定后续执行分支。
            if reported_count <= 0:
                # 控制当前循环或占位分支的执行。
                continue


            # 读取字典或配置中的对应值。
            tweet_url = post.get("tweet_url", "")
            # 根据条件决定后续执行分支。
            if not tweet_url:
                # 输出运行提示、进度或错误信息。
                print(f"  ⚠ [{index}/{len(posts)}] 帖子缺少详情链接，无法核对评论")
                # 控制当前循环或占位分支的执行。
                continue


            # 输出运行提示、进度或错误信息。
            print(
                # 执行当前步骤的业务处理。
                f"  [{index}/{len(posts)}] 页面显示 {reported_count} 条回复，"
                # 读取字典或配置中的对应值。
                f"核对帖子 {post.get('id', '')}"
            # 结束上一行开始的数据结构或表达式。
            )
            # 设置或更新本行涉及的变量值。
            comments = self._fetch_comments_for_tweet(
                # 续写当前数据结构、参数列表或表达式。
                tweet_url,
                # 设置或更新本行涉及的变量值。
                max_comments=max_comments,
                # 设置或更新本行涉及的变量值。
                max_depth=max_depth,
            # 结束上一行开始的数据结构或表达式。
            )


            # 设置或更新本行涉及的变量值。
            actual_for_post = []
            # 遍历集合中的元素并逐项处理。
            for comment in comments:
                # 读取字典或配置中的对应值。
                comment_id = comment.get("id", "")
                # 根据条件决定后续执行分支。
                if (not comment_id or comment_id == post.get("id", "")
                        # 执行当前步骤的业务处理。
                        or comment_id in seen_comment_ids):
                    # 控制当前循环或占位分支的执行。
                    continue
                # 执行当前步骤的业务处理。
                seen_comment_ids.add(comment_id)
                # 读取字典或配置中的对应值。
                comment["parent_tweet_id"] = post.get("id", "")
                # 读取字典或配置中的对应值。
                comment["parent_tweet_author"] = post.get("author_handle", "")
                # 设置或更新本行涉及的变量值。
                reply_targets = [
                    # 执行当前步骤的业务处理。
                    handle.strip().lstrip("@")
                    # 遍历集合中的元素并逐项处理。
                    for handle in comment.get("reply_to_handles", "").split(",")
                    # 根据条件决定后续执行分支。
                    if handle.strip()
                # 结束上一行开始的数据结构或表达式。
                ]
                # 设置或更新本行涉及的变量值。
                comment["reply_target_handle"] = (
                    # 读取字典或配置中的对应值。
                    reply_targets[0] if reply_targets else post.get("author_handle", "")
                # 结束上一行开始的数据结构或表达式。
                )
                # 将当前结果追加到列表或集合。
                actual_for_post.append(comment)


            # 设置或更新本行涉及的变量值。
            post["actual_comment_count"] = len(actual_for_post)
            # 执行当前步骤的业务处理。
            all_comments.extend(actual_for_post)
            # 输出运行提示、进度或错误信息。
            print(
                # 执行当前步骤的业务处理。
                f"    → 页面标示 {reported_count} 条，实际保留 "
                # 执行当前步骤的业务处理。
                f"{len(actual_for_post)} 条对话链前后文/回复"
            # 结束上一行开始的数据结构或表达式。
            )


        # 输出运行提示、进度或错误信息。
        print(f"✓ 评论核对完成：共抓取 {len(all_comments)} 条唯一评论")
        # 将本函数的计算结果返回给调用处。
        return all_comments


    # 定义可复用的处理函数。
    def fetch_report(self, screen_name, since_date, until_date=None,
                     # 设置或更新本行涉及的变量值。
                     replies_per_tweet=20, max_comment_depth=1,
                     # 设置或更新本行涉及的变量值。
                     use_advanced_search=True, any_words=None):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """一站式报告。返回 (posts, comments, following, followers)。"""
        # 第一步：优先使用服务器端高级搜索缩小账号、关键词和日期范围。
        # 输出运行提示、进度或错误信息。
        print(f"\n{'='*40}")
        # 根据条件决定后续执行分支。
        if use_advanced_search:
            # 输出运行提示、进度或错误信息。
            print(f"  第一步：高级搜索 @{screen_name} 的相关帖子")
        # 处理前述条件不成立的情况。
        else:
            # 输出运行提示、进度或错误信息。
            print(f"  第一步：扫描 @{screen_name} 的时间线（兼容模式）")
        # 输出运行提示、进度或错误信息。
        print(f"{'='*40}")
        # 根据条件决定后续执行分支。
        if use_advanced_search:
            # 设置或更新本行涉及的变量值。
            posts = self.fetch_account_advanced_search(
                # 续写当前数据结构、参数列表或表达式。
                screen_name,
                # 设置或更新本行涉及的变量值。
                count=9999,
                # 设置或更新本行涉及的变量值。
                since_date=since_date,
                # 设置或更新本行涉及的变量值。
                until_date=until_date,
                # 设置或更新本行涉及的变量值。
                any_words=any_words,
            # 结束上一行开始的数据结构或表达式。
            )
        # 处理前述条件不成立的情况。
        else:
            # 设置或更新本行涉及的变量值。
            posts = self.fetch_user_timeline(
                # 续写当前数据结构、参数列表或表达式。
                screen_name, count=9999,
                # 设置或更新本行涉及的变量值。
                since_date=since_date,
                # 设置或更新本行涉及的变量值。
                until_date=until_date,
                # 设置或更新本行涉及的变量值。
                keyword_filter=True,
            # 结束上一行开始的数据结构或表达式。
            )


        # 提取 Profile 统计数据
        # 执行当前步骤的业务处理。
        following, followers = getattr(self, "_last_profile_stats", ("", ""))
        # 输出运行提示、进度或错误信息。
        print(f"  Profile: Following={following}, Followers={followers}")


        # 根据条件决定后续执行分支。
        if not posts:
            # 输出运行提示、进度或错误信息。
            print("✗ 该时间段内无新疆相关推文")
            # 将本函数的计算结果返回给调用处。
            return [], [], following, followers


        # 输出运行提示、进度或错误信息。
        print(f"\n✓ 第一步完成：获取 {len(posts)} 条新疆相关推文")


        # 第二步：仅对有回复的帖子进入详情页，抓取实际可见评论。
        # 输出运行提示、进度或错误信息。
        print(f"\n{'='*40}")
        # 输出运行提示、进度或错误信息。
        print(f"  第二步：抓取每条推文的评论 (一级{replies_per_tweet}条 + 子评论深度{max_comment_depth})")
        # 输出运行提示、进度或错误信息。
        print(f"{'='*40}")


        # 设置或更新本行涉及的变量值。
        all_comments = self.fetch_comments_for_posts(
            # 续写当前数据结构、参数列表或表达式。
            posts,
            # 设置或更新本行涉及的变量值。
            max_comments=replies_per_tweet,
            # 设置或更新本行涉及的变量值。
            max_depth=max_comment_depth,
        # 结束上一行开始的数据结构或表达式。
        )


        # 输出运行提示、进度或错误信息。
        print(f"\n✓ 第二步完成：共获取 {len(all_comments)} 条评论")
        # 将本函数的计算结果返回给调用处。
        return posts, all_comments, following, followers


    # ----- 数据输出 -----


    # 应用装饰器以调整后续定义的行为。
    @staticmethod
    # 定义可复用的处理函数。
    def _fmt_time_posts(iso_str):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """ISO 8601 UTC → Posts 格式: YYYY.M.DD (CST)"""
        # 根据条件决定后续执行分支。
        if not iso_str:
            # 将本函数的计算结果返回给调用处。
            return ""
        # 开始可能抛出异常的受保护操作。
        try:
            # Parse ISO 8601
            # 设置或更新本行涉及的变量值。
            dt_str = iso_str.replace("Z", "+00:00")
            # 导入本行所需模块或对象。
            from datetime import timezone as tz
            # 设置或更新本行涉及的变量值。
            dt = datetime.fromisoformat(dt_str)
            # Convert to CST (UTC+8)
            # 设置或更新本行涉及的变量值。
            cst = tz(timedelta(hours=8))
            # 设置或更新本行涉及的变量值。
            dt_cst = dt.astimezone(cst)
            # 将本函数的计算结果返回给调用处。
            return f"{dt_cst.year}.{dt_cst.month}.{dt_cst.day}"
        # 捕获并处理指定的异常情况。
        except Exception:
            # 将本函数的计算结果返回给调用处。
            return iso_str[:10].replace("-", ".") if len(iso_str) >= 10 else iso_str


    # 应用装饰器以调整后续定义的行为。
    @staticmethod
    # 定义可复用的处理函数。
    def _fmt_time_comments(iso_str):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """ISO 8601 UTC → 评论格式: YYYY.M.DD HH:MM (CST)"""
        # 根据条件决定后续执行分支。
        if not iso_str:
            # 将本函数的计算结果返回给调用处。
            return ""
        # 开始可能抛出异常的受保护操作。
        try:
            # 设置或更新本行涉及的变量值。
            dt_str = iso_str.replace("Z", "+00:00")
            # 导入本行所需模块或对象。
            from datetime import timezone as tz
            # 设置或更新本行涉及的变量值。
            dt = datetime.fromisoformat(dt_str)
            # 设置或更新本行涉及的变量值。
            cst = tz(timedelta(hours=8))
            # 设置或更新本行涉及的变量值。
            dt_cst = dt.astimezone(cst)
            # 将本函数的计算结果返回给调用处。
            return f"{dt_cst.year}.{dt_cst.month}.{dt_cst.day} {dt_cst.hour:02d}:{dt_cst.minute:02d}"
        # 捕获并处理指定的异常情况。
        except Exception:
            # 将本函数的计算结果返回给调用处。
            return iso_str[:16].replace("-", ".").replace("T", " ") if len(iso_str) >= 16 else iso_str


    # 应用装饰器以调整后续定义的行为。
    @staticmethod
    # 定义可复用的处理函数。
    def _ensure_at(text):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """确保字符串以 @ 开头"""
        # 根据条件决定后续执行分支。
        if not text:
            # 将本函数的计算结果返回给调用处。
            return ""
        # 将本函数的计算结果返回给调用处。
        return f"@{text.lstrip('@')}"


    # 定义可复用的处理函数。
    def _get_profile_stats(self, screen_name):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """从用户主页提取 Following / Followers 数。"""
        # 开始可能抛出异常的受保护操作。
        try:
            # 以下说明按脚本执行顺序对应主页统计 JavaScript；实际脚本保持原样。
            # 创建关注数和粉丝数结果对象。
            # 查询关注、粉丝及认证粉丝入口链接。
            # 遍历统计链接并读取 href 与可见文本。
            # 从可见文本提取带千位符或缩写单位的数值。
            # 普通 following 链接写入关注数。
            # verified_followers 或 followers 链接写入粉丝数。
            # 任一统计值缺失时启用页面全文备用匹配。
            # 从页面正文分别匹配中英文关注数和粉丝数。
            # 命中备用结果时回填对应字段。
            # 将统计对象序列化为 JSON 返回 Python。
            js = r"""
            var stats = {following: '', followers: ''};
            var links = document.querySelectorAll(
              'a[href$="/following"], a[href$="/followers"], a[href*="/verified_followers"]'
            );
            links.forEach(function(a) {
              var href = a.getAttribute('href') || '';
              var text = (a.innerText || '').trim();
              var numMatch = text.match(/([\d,.]+\s*[KMB万亿]?)/i);
              var num = numMatch ? numMatch[1] : '';
              if (href.includes('/following') && !href.includes('verified')) {
                stats.following = num;
              } else if (href.includes('/verified_followers') || href.endsWith('/followers')) {
                stats.followers = num;
              }
            });
            // fallback: look for spans with these numbers next to text
            if (!stats.following || !stats.followers) {
              var allText = document.body ? document.body.innerText : '';
              var followingMatch = allText.match(/([\d,.]+\s*[KMB万亿]?)\s*(?:Following|正在关注)/i);
              var followersMatch = allText.match(/([\d,.]+\s*[KMB万亿]?)\s*(?:Followers|关注者|粉丝)/i);
              if (followingMatch) stats.following = followingMatch[1];
              if (followersMatch) stats.followers = followersMatch[1];
            }
            return JSON.stringify(stats);
            """
            # 在浏览器页面中执行 JavaScript。
            raw = self.driver.execute_script(js)
            # 解析或写入 JSON 配置与数据。
            stats = json.loads(raw) if raw else {}
            # 读取字典或配置中的对应值。
            following = stats.get("following", "")
            # 读取字典或配置中的对应值。
            followers = stats.get("followers", "")
            # 将本函数的计算结果返回给调用处。
            return following, followers
        # 捕获并处理指定的异常情况。
        except Exception:
            # 将本函数的计算结果返回给调用处。
            return "", ""


    # 定义可复用的处理函数。
    def export_posts_csv(self, data, output_path, profile_following="", profile_followers=""):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """导出帖子 CSV，列格式与 24-25年知情代理人涉疆数据.xlsx 一致。

        列: ID, name, Following, Followers, time, text, translation,
            tag, reply, repost, likes, views, vedios/photos, 评论条数, 原始链接
        """
        # 设置或更新本行涉及的变量值。
        fieldnames = [
            # 续写当前数据结构、参数列表或表达式。
            "ID", "name", "Following", "Followers", "time", "text",
            # 续写当前数据结构、参数列表或表达式。
            "translation", "tag", "reply", "repost", "likes", "views",
            # 续写当前数据结构、参数列表或表达式。
            "vedios/photos", "评论条数", "原始链接",
        # 结束上一行开始的数据结构或表达式。
        ]


        # 设置或更新本行涉及的变量值。
        rows = []
        # 遍历集合中的元素并逐项处理。
        for d in data:
            # 读取字典或配置中的对应值。
            handle = d.get("author_handle", "")
            # 读取字典或配置中的对应值。
            name = d.get("author_name", "")


            # 只有目标用户本人的帖子才填 Following/Followers
            # 设置或更新本行涉及的变量值。
            following = ""
            # 设置或更新本行涉及的变量值。
            followers = ""
            # 根据条件决定后续执行分支。
            if profile_following and handle:
                # 设置或更新本行涉及的变量值。
                following = profile_following
                # 设置或更新本行涉及的变量值。
                followers = profile_followers


            # 媒体列
            # 读取字典或配置中的对应值。
            media_count = d.get("media_count", 0)
            # 设置或更新本行涉及的变量值。
            media_str = "/" if media_count == 0 else str(media_count)


            # tag 列：第一个外部链接 或 /
            # 读取字典或配置中的对应值。
            urls_str = d.get("urls", "")
            # 根据条件决定后续执行分支。
            if urls_str:
                # 设置或更新本行涉及的变量值。
                first_url = urls_str.split("|")[0]
                # 设置或更新本行涉及的变量值。
                tag = first_url if first_url else "/"
            # 处理前述条件不成立的情况。
            else:
                # 设置或更新本行涉及的变量值。
                tag = "/"


            # 将当前结果追加到列表或集合。
            rows.append({
                # 续写当前数据结构、参数列表或表达式。
                "ID": self._ensure_at(handle),
                # 续写当前数据结构、参数列表或表达式。
                "name": name,
                # 续写当前数据结构、参数列表或表达式。
                "Following": following,
                # 续写当前数据结构、参数列表或表达式。
                "Followers": followers,
                # 读取字典或配置中的对应值。
                "time": self._fmt_time_posts(d.get("created_at", "")),
                # 读取字典或配置中的对应值。
                "text": d.get("text", ""),
                # 读取字典或配置中的对应值。
                "translation": d.get("translation", ""),
                # 续写当前数据结构、参数列表或表达式。
                "tag": tag,
                # 读取字典或配置中的对应值。
                "reply": d.get("reply_count", 0),
                # 读取字典或配置中的对应值。
                "repost": d.get("retweet_count", 0),
                # 读取字典或配置中的对应值。
                "likes": d.get("favorite_count", 0),
                # 读取字典或配置中的对应值。
                "views": d.get("view_count", 0),
                # 续写当前数据结构、参数列表或表达式。
                "vedios/photos": media_str,
                # 读取字典或配置中的对应值。
                "评论条数": d.get(
                    # 读取字典或配置中的对应值。
                    "actual_comment_count", d.get("reply_count", 0)
                # 续写当前数据结构、参数列表或表达式。
                ),
                # 读取字典或配置中的对应值。
                "原始链接": d.get("tweet_url", ""),
            # 结束上一行开始的数据结构或表达式。
            })


        # 使用上下文管理器并在结束时自动清理资源。
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            # 按既定字段顺序写出 CSV 数据。
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            # 执行当前步骤的业务处理。
            writer.writeheader()
            # 按既定字段顺序写出 CSV 数据。
            writer.writerows([
                # 续写当前数据结构、参数列表或表达式。
                {key: sanitize_csv_value(value) for key, value in row.items()}
                # 遍历集合中的元素并逐项处理。
                for row in rows
            # 结束上一行开始的数据结构或表达式。
            ])


        # 输出运行提示、进度或错误信息。
        print(f"\n✓ 帖子结果已保存到: {output_path}（{len(rows)} 条）")


    # 定义可复用的处理函数。
    def export_comments_csv(self, data, output_path):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """按研究表格的固定顺序导出对话链内容。"""
        # 设置或更新本行涉及的变量值。
        fieldnames = ["序号", "account", "tweet_id", "link", "time", "text", "贴主ID"]


        # 设置或更新本行涉及的变量值。
        rows = []
        # 遍历集合中的元素并逐项处理。
        for index, d in enumerate(data, start=1):
            # 读取字典或配置中的对应值。
            post_owner = d.get("parent_tweet_author", "")
            # 将当前结果追加到列表或集合。
            rows.append({
                # 续写当前数据结构、参数列表或表达式。
                "序号": index,
                # 读取字典或配置中的对应值。
                "account": d.get("author_name", ""),
                # 读取字典或配置中的对应值。
                "tweet_id": self._ensure_at(d.get("author_handle", "")),
                # 读取字典或配置中的对应值。
                "link": d.get("tweet_url", ""),
                # 读取字典或配置中的对应值。
                "time": self._fmt_time_comments(d.get("created_at", "")),
                # 读取字典或配置中的对应值。
                "text": d.get("text", ""),
                # 续写当前数据结构、参数列表或表达式。
                "贴主ID": self._ensure_at(post_owner),
            # 结束上一行开始的数据结构或表达式。
            })


        # 使用上下文管理器并在结束时自动清理资源。
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            # 按既定字段顺序写出 CSV 数据。
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            # 执行当前步骤的业务处理。
            writer.writeheader()
            # 按既定字段顺序写出 CSV 数据。
            writer.writerows([
                # 续写当前数据结构、参数列表或表达式。
                {key: sanitize_csv_value(value) for key, value in row.items()}
                # 遍历集合中的元素并逐项处理。
                for row in rows
            # 结束上一行开始的数据结构或表达式。
            ])


        # 输出运行提示、进度或错误信息。
        print(f"\n✓ 评论结果已保存到: {output_path}（{len(rows)} 条）")


    # 定义可复用的处理函数。
    def _make_output_path(self, query, suffix=""):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """生成输出文件路径。"""
        # 设置或更新本行涉及的变量值。
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 设置或更新本行涉及的变量值。
        safe_query = "".join(
            # 执行当前步骤的业务处理。
            c for c in str(query) if c.isalnum() or c in "_- "
        # 结束上一行开始的数据结构或表达式。
        )[:50].strip().replace(" ", "_")
        # 根据条件决定后续执行分支。
        if suffix:
            # 设置或更新本行涉及的变量值。
            safe_query = f"{safe_query}_{suffix}"
        # 设置或更新本行涉及的变量值。
        filename = f"{safe_query}_{ts}.csv"
        # 将本函数的计算结果返回给调用处。
        return os.path.join(self.output_dir, filename)


    # 定义可复用的处理函数。
    def _make_comments_output_path(self, query):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """在独立 comments 目录生成评论文件路径。"""
        # 设置或更新本行涉及的变量值。
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 设置或更新本行涉及的变量值。
        safe_query = "".join(
            # 执行当前步骤的业务处理。
            c for c in str(query) if c.isalnum() or c in "_- "
        # 结束上一行开始的数据结构或表达式。
        )[:50].strip().replace(" ", "_") or "comments"
        # 将本函数的计算结果返回给调用处。
        return os.path.join(self.comments_dir, f"{safe_query}_comments_{ts}.csv")


    # ----- 调度入口 -----


    # 定义可复用的处理函数。
    def start(self, cli_args):
        # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
        """根据 CLI 参数调度抓取任务。"""
        # 执行当前步骤的业务处理。
        self.login()


        # 设置或更新本行涉及的变量值。
        mode = cli_args.mode
        # 设置或更新本行涉及的变量值。
        data = []
        # 设置或更新本行涉及的变量值。
        comments = []
        # 设置或更新本行涉及的变量值。
        comment_output_path = None
        # 设置或更新本行涉及的变量值。
        query = ""


        # 开始可能抛出异常的受保护操作。
        try:
            # 根据条件决定后续执行分支。
            if mode == "tweet":
                # 设置或更新本行涉及的变量值。
                tweet_id = cli_args.tweet_id
                # 设置或更新本行涉及的变量值。
                query = tweet_id
                # 设置或更新本行涉及的变量值。
                data = self.fetch_tweet(tweet_id)


            # 根据条件决定后续执行分支。
            elif mode == "timeline":
                # 设置或更新本行涉及的变量值。
                screen_name = cli_args.screen_name
                # 设置或更新本行涉及的变量值。
                count = cli_args.count
                # 设置或更新本行涉及的变量值。
                since = getattr(cli_args, "since", None)
                # 设置或更新本行涉及的变量值。
                until = getattr(cli_args, "until", None)
                # 设置或更新本行涉及的变量值。
                query = screen_name
                # 设置或更新本行涉及的变量值。
                data = self.fetch_user_timeline(
                    # 续写当前数据结构、参数列表或表达式。
                    screen_name, count, since, until,
                    # 设置或更新本行涉及的变量值。
                    keyword_filter=self.filter_xinjiang,
                # 结束上一行开始的数据结构或表达式。
                )


            # 根据条件决定后续执行分支。
            elif mode == "search":
                # 设置或更新本行涉及的变量值。
                query = cli_args.query
                # 设置或更新本行涉及的变量值。
                count = cli_args.count
                # 设置或更新本行涉及的变量值。
                product = cli_args.product
                # 设置或更新本行涉及的变量值。
                data = self.fetch_search_tweets(query, count, product)


            # 根据条件决定后续执行分支。
            elif mode == "account-search":
                # 设置或更新本行涉及的变量值。
                screen_name = cli_args.screen_name
                # 设置或更新本行涉及的变量值。
                count = cli_args.count
                # 设置或更新本行涉及的变量值。
                since = cli_args.since or self.advanced_search_since
                # 设置或更新本行涉及的变量值。
                until = cli_args.until or self.advanced_search_until
                # 设置或更新本行涉及的变量值。
                words = cli_args.any_words or self.advanced_search_words
                # 设置或更新本行涉及的变量值。
                query = screen_name
                # 设置或更新本行涉及的变量值。
                data = self.fetch_account_advanced_search(
                    # 续写当前数据结构、参数列表或表达式。
                    screen_name,
                    # 设置或更新本行涉及的变量值。
                    count=count,
                    # 设置或更新本行涉及的变量值。
                    since_date=since,
                    # 设置或更新本行涉及的变量值。
                    until_date=until,
                    # 设置或更新本行涉及的变量值。
                    any_words=words,
                # 结束上一行开始的数据结构或表达式。
                )


            # 根据条件决定后续执行分支。
            elif mode == "replies":
                # 设置或更新本行涉及的变量值。
                tweet_id = self._validate_tweet_id(cli_args.tweet_id)
                # 设置或更新本行涉及的变量值。
                count = cli_args.count
                # 设置或更新本行涉及的变量值。
                query = tweet_id
                # 设置或更新本行涉及的变量值。
                url = f"https://x.com/i/status/{tweet_id}"
                # 设置或更新本行涉及的变量值。
                original = self.fetch_tweet(tweet_id)
                # 设置或更新本行涉及的变量值。
                replies = self._fetch_comments_for_tweet(
                    # 执行当前步骤的业务处理。
                    url, max_comments=count, max_depth=0
                # 结束上一行开始的数据结构或表达式。
                )
                # 根据条件决定后续执行分支。
                if original:
                    # 设置或更新本行涉及的变量值。
                    original[0]["is_original"] = True
                # 设置或更新本行涉及的变量值。
                data = original + replies


            # 根据条件决定后续执行分支。
            elif mode == "report":
                # 设置或更新本行涉及的变量值。
                screen_name = cli_args.screen_name
                # 设置或更新本行涉及的变量值。
                since_date = cli_args.since or self.advanced_search_since
                # 设置或更新本行涉及的变量值。
                until_date = cli_args.until or self.advanced_search_until
                # 设置或更新本行涉及的变量值。
                reply_count = cli_args.replies
                # 设置或更新本行涉及的变量值。
                max_depth = getattr(cli_args, "depth", 1)
                # 设置或更新本行涉及的变量值。
                requested_search_mode = getattr(cli_args, "advanced_search", None)
                # 设置或更新本行涉及的变量值。
                use_advanced_search = (
                    # 执行当前步骤的业务处理。
                    self.advanced_search_enabled
                    # 根据条件决定后续执行分支。
                    if requested_search_mode is None
                    # 执行当前步骤的业务处理。
                    else requested_search_mode
                # 结束上一行开始的数据结构或表达式。
                )
                # 设置或更新本行涉及的变量值。
                words = cli_args.any_words or self.advanced_search_words
                # 设置或更新本行涉及的变量值。
                query = screen_name


                # 续写当前数据结构、参数列表或表达式。
                posts, comments, following, followers = self.fetch_report(
                    # 续写当前数据结构、参数列表或表达式。
                    screen_name,
                    # 续写当前数据结构、参数列表或表达式。
                    since_date,
                    # 续写当前数据结构、参数列表或表达式。
                    until_date,
                    # 续写当前数据结构、参数列表或表达式。
                    reply_count,
                    # 续写当前数据结构、参数列表或表达式。
                    max_depth,
                    # 设置或更新本行涉及的变量值。
                    use_advanced_search=use_advanced_search,
                    # 设置或更新本行涉及的变量值。
                    any_words=words,
                # 结束上一行开始的数据结构或表达式。
                )


                # 输出帖子 CSV（列对齐 24-25年知情代理人涉疆数据.xlsx）
                # 设置或更新本行涉及的变量值。
                post_path = getattr(cli_args, "output", None)
                # 根据条件决定后续执行分支。
                if not post_path:
                    # 设置或更新本行涉及的变量值。
                    post_path = self._make_output_path(query, "posts")
                # 根据条件决定后续执行分支。
                if posts:
                    # 执行当前步骤的业务处理。
                    self.export_posts_csv(posts, post_path, following, followers)


                # 评论始终放在独立 comments 目录；即使为 0 条也保留表头。
                # 设置或更新本行涉及的变量值。
                comment_path = self._make_comments_output_path(query)
                # 执行当前步骤的业务处理。
                self.export_comments_csv(comments, comment_path)


                # 续写当前数据结构、参数列表或表达式。
                print_summary(
                    # 设置或更新本行涉及的变量值。
                    mode=mode,
                    # 设置或更新本行涉及的变量值。
                    query=query,
                    # 设置或更新本行涉及的变量值。
                    requested=reply_count,
                    # 设置或更新本行涉及的变量值。
                    actual=len(posts),
                    # 设置或更新本行涉及的变量值。
                    output_path=f"{post_path}\n{' '*12}+ {comment_path}",
                    # 设置或更新本行涉及的变量值。
                    skipped=self.skipped_count,
                # 结束上一行开始的数据结构或表达式。
                )
                # 将本函数的计算结果返回给调用处。
                return


            # timeline/account-search 默认自动核对有回复帖子的实际评论。
            # 根据条件决定后续执行分支。
            if mode in {"timeline", "account-search"} and data:
                # 设置或更新本行涉及的变量值。
                requested_comments = getattr(cli_args, "comments", None)
                # 设置或更新本行涉及的变量值。
                comments_enabled = (
                    # 执行当前步骤的业务处理。
                    self.auto_fetch_comments
                    # 根据条件决定后续执行分支。
                    if requested_comments is None
                    # 执行当前步骤的业务处理。
                    else requested_comments
                # 结束上一行开始的数据结构或表达式。
                )
                # 根据条件决定后续执行分支。
                if comments_enabled:
                    # 设置或更新本行涉及的变量值。
                    max_comments = (
                        # 执行当前步骤的业务处理。
                        getattr(cli_args, "max_comments", None)
                        # 执行当前步骤的业务处理。
                        or self.max_comments_per_post
                    # 结束上一行开始的数据结构或表达式。
                    )
                    # 设置或更新本行涉及的变量值。
                    comment_depth = (
                        # 执行当前步骤的业务处理。
                        getattr(cli_args, "comment_depth", None)
                        # 根据条件决定后续执行分支。
                        if getattr(cli_args, "comment_depth", None) is not None
                        # 执行当前步骤的业务处理。
                        else self.max_comment_depth
                    # 结束上一行开始的数据结构或表达式。
                    )
                    # 设置或更新本行涉及的变量值。
                    comments = self.fetch_comments_for_posts(
                        # 续写当前数据结构、参数列表或表达式。
                        data,
                        # 设置或更新本行涉及的变量值。
                        max_comments=max_comments,
                        # 设置或更新本行涉及的变量值。
                        max_depth=comment_depth,
                    # 结束上一行开始的数据结构或表达式。
                    )
                    # 设置或更新本行涉及的变量值。
                    comment_output_path = self._make_comments_output_path(query)


        # 捕获并处理指定的异常情况。
        except KeyboardInterrupt:
            # 输出运行提示、进度或错误信息。
            print("\n⚠ 用户中断操作")
            # 根据条件决定后续执行分支。
            if data:
                # 输出运行提示、进度或错误信息。
                print(f"  已获取 {len(data)} 条数据，正在保存...")
            # 处理前述条件不成立的情况。
            else:
                # 调用浏览器驱动完成当前操作。
                self.driver.quit()
                # 执行当前步骤的业务处理。
                sys.exit(0)
        # 捕获并处理指定的异常情况。
        except Exception as e:
            # 输出运行提示、进度或错误信息。
            print(f"\n✗ 抓取异常: {e}")
            # 执行当前步骤的业务处理。
            traceback.print_exc()
        # 无论是否异常都执行收尾操作。
        finally:
            # 根据条件决定后续执行分支。
            if self.driver:
                # 调用浏览器驱动完成当前操作。
                self.driver.quit()
                # 输出运行提示、进度或错误信息。
                print("浏览器已关闭")


        # 输出
        # 设置或更新本行涉及的变量值。
        output_path = getattr(cli_args, "output", None)
        # 根据条件决定后续执行分支。
        if not output_path:
            # 设置或更新本行涉及的变量值。
            output_path = self._make_output_path(query, mode)


        # 根据条件决定后续执行分支。
        if data:
            # 根据条件决定后续执行分支。
            if mode in {"timeline", "account-search"}:
                # 执行当前步骤的业务处理。
                following, followers = getattr(self, "_last_profile_stats", ("", ""))
                # 执行当前步骤的业务处理。
                self.export_posts_csv(data, output_path, following, followers)
            # 处理前述条件不成立的情况。
            else:
                # 执行当前步骤的业务处理。
                self.export_posts_csv(data, output_path)


        # 根据条件决定后续执行分支。
        if comment_output_path:
            # 执行当前步骤的业务处理。
            self.export_comments_csv(comments, comment_output_path)


        # 设置或更新本行涉及的变量值。
        displayed_output = output_path
        # 根据条件决定后续执行分支。
        if comment_output_path:
            # 设置或更新本行涉及的变量值。
            displayed_output = f"{output_path}\n{' '*12}+ {comment_output_path}"


        # 续写当前数据结构、参数列表或表达式。
        print_summary(
            # 设置或更新本行涉及的变量值。
            mode=mode,
            # 设置或更新本行涉及的变量值。
            query=query,
            # 设置或更新本行涉及的变量值。
            requested=getattr(cli_args, "count", 1),
            # 设置或更新本行涉及的变量值。
            actual=len(data),
            # 设置或更新本行涉及的变量值。
            output_path=displayed_output,
            # 设置或更新本行涉及的变量值。
            skipped=self.skipped_count,
        # 结束上一行开始的数据结构或表达式。
        )




# ============================================================
#  CLI 入口
# ============================================================


# 定义可复用的处理函数。
def generate_config(output_path="config.json"):
    # 下方文档字符串说明当前类或函数的用途、参数和返回结果。
    """生成模板配置文件。"""
    # 设置或更新本行涉及的变量值。
    template = {
        # 续写当前数据结构、参数列表或表达式。
        "auth": {
            # 续写当前数据结构、参数列表或表达式。
            "cookies_file": "x_cookies.json",
        # 续写当前数据结构、参数列表或表达式。
        },
        # 续写当前数据结构、参数列表或表达式。
        "output": {
            # 续写当前数据结构、参数列表或表达式。
            "directory": "x_output",
        # 续写当前数据结构、参数列表或表达式。
        },
        # 续写当前数据结构、参数列表或表达式。
        "rate_limit": {
            # 续写当前数据结构、参数列表或表达式。
            "min_interval_seconds": 3,
            # 续写当前数据结构、参数列表或表达式。
            "max_interval_seconds": 6,
            # 续写当前数据结构、参数列表或表达式。
            "long_pause_seconds": 60,
            # 续写当前数据结构、参数列表或表达式。
            "pages_per_long_pause": 20,
            # 续写当前数据结构、参数列表或表达式。
            "cooldown_seconds": 300,
            # 续写当前数据结构、参数列表或表达式。
            "max_retries": 3,
        # 续写当前数据结构、参数列表或表达式。
        },
        # 续写当前数据结构、参数列表或表达式。
        "selenium": {
            # 续写当前数据结构、参数列表或表达式。
            "headless": False,
            # 续写当前数据结构、参数列表或表达式。
            "page_load_timeout": 30,
            # 续写当前数据结构、参数列表或表达式。
            "scroll_pause_seconds": 1.2,
            # 续写当前数据结构、参数列表或表达式。
            "use_undetected": False,
        # 续写当前数据结构、参数列表或表达式。
        },
        # 续写当前数据结构、参数列表或表达式。
        "filter": {
            # 续写当前数据结构、参数列表或表达式。
            "xinjiang_only": True,
            # 续写当前数据结构、参数列表或表达式。
            "strict_china_context": True,
        # 续写当前数据结构、参数列表或表达式。
        },
        # 续写当前数据结构、参数列表或表达式。
        "advanced_search": {
            # 续写当前数据结构、参数列表或表达式。
            "enabled": True,
            # 续写当前数据结构、参数列表或表达式。
            "any_words": list(DEFAULT_ADVANCED_SEARCH_WORDS),
            # 续写当前数据结构、参数列表或表达式。
            "since": DEFAULT_ARCHIVE_SINCE,
            # 续写当前数据结构、参数列表或表达式。
            "until": DEFAULT_ARCHIVE_UNTIL,
        # 续写当前数据结构、参数列表或表达式。
        },
        # 续写当前数据结构、参数列表或表达式。
        "comments": {
            # 续写当前数据结构、参数列表或表达式。
            "enabled": True,
            # 续写当前数据结构、参数列表或表达式。
            "directory": "comments",
            # 续写当前数据结构、参数列表或表达式。
            "max_per_post": 1000,
            # 续写当前数据结构、参数列表或表达式。
            "max_depth": 2,
        # 续写当前数据结构、参数列表或表达式。
        },
    # 结束上一行开始的数据结构或表达式。
    }


    # 根据条件决定后续执行分支。
    if os.path.exists(output_path):
        # 输出运行提示、进度或错误信息。
        print(f"⚠ 配置文件已存在: {output_path}")
        # 设置或更新本行涉及的变量值。
        resp = input("  是否覆盖? (y/N): ").strip().lower()
        # 根据条件决定后续执行分支。
        if resp != "y":
            # 输出运行提示、进度或错误信息。
            print("  已取消")
            # 将本函数的计算结果返回给调用处。
            return


    # 使用上下文管理器并在结束时自动清理资源。
    with open(output_path, "w", encoding="utf-8") as f:
        # 解析或写入 JSON 配置与数据。
        json.dump(template, f, ensure_ascii=False, indent=2)


    # 输出运行提示、进度或错误信息。
    print(f"✓ 配置文件模板已生成: {output_path}")
    # 输出运行提示、进度或错误信息。
    print()
    # 输出运行提示、进度或错误信息。
    print("下一步：")
    # 输出运行提示、进度或错误信息。
    print("  1. 编辑 config.json，将 cookies_file 指向 Cookie 文件")
    # 输出运行提示、进度或错误信息。
    print("  2. Cookie 文件获取方式：")
    # 输出运行提示、进度或错误信息。
    print("     - 在浏览器中登录 x.com")
    # 输出运行提示、进度或错误信息。
    print("     - 打开开发者工具 → Application → Cookies")
    # 输出运行提示、进度或错误信息。
    print("     - 导出 Cookie 保存为 x_cookies.json")
    # 输出运行提示、进度或错误信息。
    print("  3. 确保 Chrome 浏览器已安装")
    # 输出运行提示、进度或错误信息。
    print()
    # 输出运行提示、进度或错误信息。
    print("然后运行: python3 x_scraper.py tweet <推文ID>")




# 定义可复用的处理函数。
def main():
    # 设置或更新本行涉及的变量值。
    parser = argparse.ArgumentParser(
        # 设置或更新本行涉及的变量值。
        description="X (Twitter) 帖子爬虫工具 - 基于 Selenium + Chrome",
        # 设置或更新本行涉及的变量值。
        formatter_class=argparse.RawDescriptionHelpFormatter,
        # 设置或更新本行涉及的变量值。
        epilog="""
使用示例:
  python3 x_scraper.py config                                 生成配置文件
  python3 x_scraper.py tweet 1234567890                       获取单条推文
  python3 x_scraper.py timeline elonmusk --count 50           获取用户时间线
  python3 x_scraper.py timeline elonmusk --since 2025-01-01   时间段过滤
  python3 x_scraper.py search "python" --count 20             搜索推文
  python3 x_scraper.py account-search elonmusk                高级搜索账号的 2024-2025 涉疆帖子
  python3 x_scraper.py replies 1234567890 --count 30          获取推文回复
  python3 x_scraper.py report elonmusk --replies 20 --depth 1 高级搜索 + 评论报告
        """,
    # 结束上一行开始的数据结构或表达式。
    )


    # 续写当前数据结构、参数列表或表达式。
    parser.add_argument(
        # 续写当前数据结构、参数列表或表达式。
        "-c", "--config",
        # 设置或更新本行涉及的变量值。
        default="config.json",
        # 设置或更新本行涉及的变量值。
        help="配置文件路径 (默认: config.json)",
    # 结束上一行开始的数据结构或表达式。
    )
    # 续写当前数据结构、参数列表或表达式。
    parser.add_argument(
        # 续写当前数据结构、参数列表或表达式。
        "-v", "--verbose",
        # 设置或更新本行涉及的变量值。
        action="store_true",
        # 设置或更新本行涉及的变量值。
        help="输出详细调试信息",
    # 结束上一行开始的数据结构或表达式。
    )


    # 设置或更新本行涉及的变量值。
    subparsers = parser.add_subparsers(
        # 设置或更新本行涉及的变量值。
        dest="mode",
        # 设置或更新本行涉及的变量值。
        title="子命令",
        # 设置或更新本行涉及的变量值。
        description="选择要执行的抓取模式",
        # 设置或更新本行涉及的变量值。
        help="可用的抓取模式",
    # 结束上一行开始的数据结构或表达式。
    )


    # ---- tweet ----
    # 设置或更新本行涉及的变量值。
    tweet_parser = subparsers.add_parser("tweet", help="根据推文 ID 获取单条推文详情")
    # 执行当前步骤的业务处理。
    tweet_parser.add_argument("tweet_id", help="推文 ID")
    # 执行当前步骤的业务处理。
    tweet_parser.add_argument("-o", "--output", help="输出文件路径")


    # ---- timeline ----
    # 设置或更新本行涉及的变量值。
    timeline_parser = subparsers.add_parser("timeline", help="获取指定用户的最新推文")
    # 执行当前步骤的业务处理。
    timeline_parser.add_argument("screen_name", help="用户 screen name")
    # 执行当前步骤的业务处理。
    timeline_parser.add_argument("--count", type=int, default=20, help="获取推文数量 (默认: 20)")
    # 执行当前步骤的业务处理。
    timeline_parser.add_argument("--since", help="起始日期 YYYY-MM-DD")
    # 执行当前步骤的业务处理。
    timeline_parser.add_argument("--until", help="截止日期 YYYY-MM-DD")
    # 续写当前数据结构、参数列表或表达式。
    timeline_parser.add_argument(
        # 续写当前数据结构、参数列表或表达式。
        "--comments", action=argparse.BooleanOptionalAction, default=None,
        # 设置或更新本行涉及的变量值。
        help="是否自动进入有回复的帖子并抓取实际评论（默认由配置决定）",
    # 结束上一行开始的数据结构或表达式。
    )
    # 续写当前数据结构、参数列表或表达式。
    timeline_parser.add_argument(
        # 执行当前步骤的业务处理。
        "--max-comments", type=int, help="每条帖子最多抓取多少条可见评论"
    # 结束上一行开始的数据结构或表达式。
    )
    # 续写当前数据结构、参数列表或表达式。
    timeline_parser.add_argument(
        # 续写当前数据结构、参数列表或表达式。
        "--comment-depth", type=int, choices=range(0, 4),
        # 设置或更新本行涉及的变量值。
        help="评论递归深度：0=仅直接评论，1-3=包含子评论",
    # 结束上一行开始的数据结构或表达式。
    )
    # 执行当前步骤的业务处理。
    timeline_parser.add_argument("-o", "--output", help="输出文件路径")


    # ---- search ----
    # 设置或更新本行涉及的变量值。
    search_parser = subparsers.add_parser("search", help="根据关键词搜索推文")
    # 执行当前步骤的业务处理。
    search_parser.add_argument("query", help="搜索关键词")
    # 执行当前步骤的业务处理。
    search_parser.add_argument("--count", type=int, default=20, help="获取推文数量 (默认: 20)")
    # 续写当前数据结构、参数列表或表达式。
    search_parser.add_argument(
        # 续写当前数据结构、参数列表或表达式。
        "--product", choices=["Top", "Latest"], default="Latest",
        # 设置或更新本行涉及的变量值。
        help="搜索类型 (默认: Latest)",
    # 结束上一行开始的数据结构或表达式。
    )
    # 执行当前步骤的业务处理。
    search_parser.add_argument("-o", "--output", help="输出文件路径")


    # ---- account-search ----
    # 设置或更新本行涉及的变量值。
    account_search_parser = subparsers.add_parser(
        # 续写当前数据结构、参数列表或表达式。
        "account-search",
        # 设置或更新本行涉及的变量值。
        help="使用 X 高级搜索抓取指定账号和日期范围内的任一关键词帖子",
    # 结束上一行开始的数据结构或表达式。
    )
    # 执行当前步骤的业务处理。
    account_search_parser.add_argument("screen_name", help="用户 screen name")
    # 续写当前数据结构、参数列表或表达式。
    account_search_parser.add_argument(
        # 执行当前步骤的业务处理。
        "--count", type=int, default=9999, help="最多获取多少条帖子 (默认: 9999)"
    # 结束上一行开始的数据结构或表达式。
    )
    # 续写当前数据结构、参数列表或表达式。
    account_search_parser.add_argument(
        # 执行当前步骤的业务处理。
        "--since", help=f"起始日期 YYYY-MM-DD (默认: {DEFAULT_ARCHIVE_SINCE})"
    # 结束上一行开始的数据结构或表达式。
    )
    # 续写当前数据结构、参数列表或表达式。
    account_search_parser.add_argument(
        # 执行当前步骤的业务处理。
        "--until", help=f"截止日期 YYYY-MM-DD，包含当日 (默认: {DEFAULT_ARCHIVE_UNTIL})"
    # 结束上一行开始的数据结构或表达式。
    )
    # 续写当前数据结构、参数列表或表达式。
    account_search_parser.add_argument(
        # 续写当前数据结构、参数列表或表达式。
        "--any-words",
        # 设置或更新本行涉及的变量值。
        nargs="+",
        # 设置或更新本行涉及的变量值。
        metavar="WORD",
        # 设置或更新本行涉及的变量值。
        help='“Any of these words” 关键词列表（默认含 Uyghur/Uighur 与 East Turkistan 等变体）',
    # 结束上一行开始的数据结构或表达式。
    )
    # 续写当前数据结构、参数列表或表达式。
    account_search_parser.add_argument(
        # 续写当前数据结构、参数列表或表达式。
        "--comments", action=argparse.BooleanOptionalAction, default=None,
        # 设置或更新本行涉及的变量值。
        help="是否自动进入有回复的帖子并抓取实际评论（默认由配置决定）",
    # 结束上一行开始的数据结构或表达式。
    )
    # 续写当前数据结构、参数列表或表达式。
    account_search_parser.add_argument(
        # 执行当前步骤的业务处理。
        "--max-comments", type=int, help="每条帖子最多抓取多少条可见评论"
    # 结束上一行开始的数据结构或表达式。
    )
    # 续写当前数据结构、参数列表或表达式。
    account_search_parser.add_argument(
        # 续写当前数据结构、参数列表或表达式。
        "--comment-depth", type=int, choices=range(0, 4),
        # 设置或更新本行涉及的变量值。
        help="评论递归深度：0=仅直接评论，1-3=包含子评论",
    # 结束上一行开始的数据结构或表达式。
    )
    # 执行当前步骤的业务处理。
    account_search_parser.add_argument("-o", "--output", help="输出文件路径")


    # ---- replies ----
    # 设置或更新本行涉及的变量值。
    replies_parser = subparsers.add_parser("replies", help="获取指定推文的回复列表（含原帖）")
    # 执行当前步骤的业务处理。
    replies_parser.add_argument("tweet_id", help="推文 ID")
    # 执行当前步骤的业务处理。
    replies_parser.add_argument("--count", type=int, default=20, help="获取回复数量 (默认: 20)")
    # 执行当前步骤的业务处理。
    replies_parser.add_argument("-o", "--output", help="输出文件路径")


    # ---- config ----
    # 设置或更新本行涉及的变量值。
    config_parser = subparsers.add_parser("config", help="生成模板配置文件")
    # 续写当前数据结构、参数列表或表达式。
    config_parser.add_argument(
        # 续写当前数据结构、参数列表或表达式。
        "-o", "--output", default="config.json",
        # 设置或更新本行涉及的变量值。
        help="配置文件输出路径 (默认: config.json)",
    # 结束上一行开始的数据结构或表达式。
    )


    # ---- report ----
    # 设置或更新本行涉及的变量值。
    report_parser = subparsers.add_parser(
        # 执行当前步骤的业务处理。
        "report", help="一站式报告：账号高级搜索 + 评论 + 子评论"
    # 结束上一行开始的数据结构或表达式。
    )
    # 执行当前步骤的业务处理。
    report_parser.add_argument("screen_name", help="用户 screen name（@后面部分）")
    # 续写当前数据结构、参数列表或表达式。
    report_parser.add_argument(
        # 执行当前步骤的业务处理。
        "--since", help=f"起始日期 YYYY-MM-DD (默认: {DEFAULT_ARCHIVE_SINCE})"
    # 结束上一行开始的数据结构或表达式。
    )
    # 续写当前数据结构、参数列表或表达式。
    report_parser.add_argument(
        # 执行当前步骤的业务处理。
        "--until", help=f"截止日期 YYYY-MM-DD，包含当日 (默认: {DEFAULT_ARCHIVE_UNTIL})"
    # 结束上一行开始的数据结构或表达式。
    )
    # 续写当前数据结构、参数列表或表达式。
    report_parser.add_argument(
        # 续写当前数据结构、参数列表或表达式。
        "--any-words",
        # 设置或更新本行涉及的变量值。
        nargs="+",
        # 设置或更新本行涉及的变量值。
        metavar="WORD",
        # 设置或更新本行涉及的变量值。
        help='高级搜索“Any of these words” (默认: Xinjiang 维吾尔 新疆 Uyghur)',
    # 结束上一行开始的数据结构或表达式。
    )
    # 设置或更新本行涉及的变量值。
    search_mode_group = report_parser.add_mutually_exclusive_group()
    # 续写当前数据结构、参数列表或表达式。
    search_mode_group.add_argument(
        # 续写当前数据结构、参数列表或表达式。
        "--advanced-search",
        # 设置或更新本行涉及的变量值。
        dest="advanced_search",
        # 设置或更新本行涉及的变量值。
        action="store_true",
        # 设置或更新本行涉及的变量值。
        default=None,
        # 设置或更新本行涉及的变量值。
        help="强制使用 X 高级搜索（默认由配置决定）",
    # 结束上一行开始的数据结构或表达式。
    )
    # 续写当前数据结构、参数列表或表达式。
    search_mode_group.add_argument(
        # 续写当前数据结构、参数列表或表达式。
        "--timeline-scan",
        # 设置或更新本行涉及的变量值。
        dest="advanced_search",
        # 设置或更新本行涉及的变量值。
        action="store_false",
        # 设置或更新本行涉及的变量值。
        help="禁用高级搜索，回退到主页时间线扫描",
    # 结束上一行开始的数据结构或表达式。
    )
    # 执行当前步骤的业务处理。
    report_parser.add_argument("--replies", type=int, default=20, help="每条推文取多少一级评论 (默认: 20)")
    # 续写当前数据结构、参数列表或表达式。
    report_parser.add_argument("--depth", type=int, default=1,
                               # 设置或更新本行涉及的变量值。
                               help="子评论递归深度: 0=仅一级评论, 1=含一级子评论 (默认: 1)")
    # 执行当前步骤的业务处理。
    report_parser.add_argument("-o", "--output", help="推文输出文件路径")


    # 设置或更新本行涉及的变量值。
    args = parser.parse_args()


    # 根据条件决定后续执行分支。
    if not args.mode:
        # 执行当前步骤的业务处理。
        parser.print_help()
        # 输出运行提示、进度或错误信息。
        print("\n✗ 请指定一个子命令")
        # 执行当前步骤的业务处理。
        sys.exit(1)


    # 根据条件决定后续执行分支。
    if args.mode == "config":
        # 执行当前步骤的业务处理。
        print_banner()
        # 执行当前步骤的业务处理。
        generate_config(args.output)
        # 将本函数的计算结果返回给调用处。
        return


    # 执行当前步骤的业务处理。
    print_banner()


    # 设置或更新本行涉及的变量值。
    config = get_config(args.config)
    # 设置或更新本行涉及的变量值。
    scraper = SeleniumScraper(config)
    # 执行当前步骤的业务处理。
    scraper.start(args)




# 根据条件决定后续执行分支。
if __name__ == "__main__":
    # 执行当前步骤的业务处理。
    main()
