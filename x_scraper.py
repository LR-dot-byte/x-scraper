#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

import argparse
import csv
import json
import os
import random
import re
import sys
import time
import traceback
from datetime import datetime, timezone

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


# ============================================================
#  工具函数
# ============================================================

def get_config(config_path="config.json"):
    """加载并解析配置文件，返回 dict。"""
    if not os.path.isfile(config_path):
        print(f"✗ 配置文件不存在: {config_path}")
        print(f"  请先运行 'python3 x_scraper.py config' 生成模板配置文件")
        sys.exit(1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config
    except json.JSONDecodeError as e:
        print(f"✗ 配置文件格式不正确: {e}")
        sys.exit(1)


def print_banner():
    """打印程序横幅。"""
    print("=" * 50)
    print("  X (Twitter) 帖子爬虫工具")
    print("  基于 Selenium + Chrome")
    print("=" * 50)
    print()


def print_summary(mode, query, requested, actual, output_path, skipped=0):
    """打印抓取结果摘要。"""
    print()
    print("-" * 50)
    print(f"  抓取模式: {mode}")
    print(f"  目标: {query}")
    print(f"  请求数量: {requested}")
    print(f"  实际获取: {actual}")
    if skipped > 0:
        print(f"  跳过: {skipped}")
    print(f"  输出文件: {output_path}")
    print("-" * 50)


def safe_get(obj, attr, default=None):
    """安全获取对象属性，不存在时返回默认值。"""
    try:
        val = getattr(obj, attr, default)
        return val if val is not None else default
    except Exception:
        return default


def safe_find(element, selector, by=By.CSS_SELECTOR, default=None):
    """安全查找子元素，不存在时返回默认值。"""
    try:
        return element.find_element(by, selector)
    except Exception:
        return default


def safe_text(element, selector=None, default=""):
    """安全获取元素文本。"""
    try:
        if selector:
            el = element.find_element(By.CSS_SELECTOR, selector)
        else:
            el = element
        return el.text.strip() if el else default
    except Exception:
        return default


def parse_count(text):
    """将 '1.2K' / '3.4M' / '123' 等文本解析为整数。"""
    if not text:
        return 0
    text = text.strip().lower().replace(",", "")
    try:
        if "k" in text:
            return int(float(text.replace("k", "")) * 1000)
        elif "m" in text:
            return int(float(text.replace("m", "")) * 1000000)
        elif "b" in text:
            return int(float(text.replace("b", "")) * 1000000000)
        else:
            return int(float(text))
    except (ValueError, TypeError):
        return 0


def parse_datetime(time_element):
    """从 <time datetime='...'> 元素提取 ISO 时间字符串。"""
    if time_element is None:
        return ""
    dt_attr = time_element.get_attribute("datetime")
    return dt_attr if dt_attr else ""


# ============================================================
#  RateLimiter 类 - 统一请求限流控制器
# ============================================================

class RateLimiter:
    """统一请求限流器（同步版）

    三层节奏控制：
    1. 请求级 — 每次操作前强制等待固定间隔 + 随机抖动
    2. 批次级 — 连续请求达到阈值后触发长暂停，模拟人类行为
    3. 异常级 — 触发平台限流后进入冷却期，大幅降低请求频率
    """

    def __init__(self, config):
        cfg = config.get("rate_limit", {})
        self.min_interval = cfg.get("min_interval_seconds", 8)
        self.max_interval = cfg.get("max_interval_seconds", 15)
        self.long_pause = cfg.get("long_pause_seconds", 90)
        self.batch_size = cfg.get("pages_per_long_pause", 10)
        self.cooldown_seconds = cfg.get("cooldown_seconds", 300)
        self.max_retries = cfg.get("max_retries", 3)

        self._last_request = 0.0
        self._request_count = 0

    @property
    def request_count(self):
        return self._request_count

    def wait(self, label="操作"):
        """每次操作前调用，自动计算并等待合适间隔。"""
        if self._last_request > 0:
            elapsed = time.time() - self._last_request
            jitter = random.uniform(0, self.max_interval - self.min_interval)
            required = self.min_interval + jitter

            if elapsed < required:
                delay = required - elapsed
                print(f"  ⏳ [{label}] 等待 {delay:.1f}s "
                      f"(固定间隔={self.min_interval}s + 随机={jitter:.1f}s)")
                time.sleep(delay)

        self._last_request = time.time()
        self._request_count += 1

    def batch_pause(self):
        """每批次请求后长暂停，模拟人类休息。"""
        if self._request_count > 0 and self._request_count % self.batch_size == 0:
            print(f"  🛑 已完成 {self._request_count} 次操作，"
                  f"长暂停 {self.long_pause}s 模拟人类行为...")
            time.sleep(self.long_pause)

    def cooldown(self):
        """触发平台限流后的强制冷却。"""
        print(f"  🚫 触发限流保护，强制冷却 {self.cooldown_seconds}s...")
        time.sleep(self.cooldown_seconds)
        self._request_count = 0


# ============================================================
#  SeleniumScraper 类
# ============================================================

class SeleniumScraper:
    """X (Twitter) 帖子爬虫

    使用 Selenium WebDriver 控制 Chrome 浏览器，
    模拟真实用户操作，从页面 DOM 中提取推文数据。
    """

    # ---- X.com DOM 选择器 ----
    TWEET_SELECTOR = 'article[data-testid="tweet"]'
    TEXT_SELECTOR = '[data-testid="tweetText"]'
    USER_LINK_SELECTOR = 'a[role="link"]'
    TIME_SELECTOR = "time"
    PHOTO_SELECTOR = '[data-testid="tweetPhoto"]'
    LIKE_SELECTOR = '[data-testid="like"]'
    RETWEET_SELECTOR = '[data-testid="retweet"]'
    REPLY_SELECTOR = '[data-testid="reply"]'
    QUOTE_SELECTOR = '[data-testid="quote"]'

    def __init__(self, config):
        self.config = config
        self.validate_config(config)

        # 输出目录
        self.output_dir = config.get("output", {}).get("directory", "x_output")
        if not os.path.isabs(self.output_dir):
            script_dir = os.path.dirname(os.path.realpath(__file__))
            self.output_dir = os.path.join(script_dir, self.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        # 限流器
        self.rate_limiter = RateLimiter(config)

        # Selenium 配置
        self.selenium_cfg = config.get("selenium", {})
        self.headless = self.selenium_cfg.get("headless", False)
        self.page_timeout = self.selenium_cfg.get("page_load_timeout", 60)
        self.scroll_pause = self.selenium_cfg.get("scroll_pause_seconds", 3)

        # 去重 & 计数
        self.got_count = 0
        self.skipped_count = 0
        self.tweet_ids = set()

        # Driver 延迟初始化
        self.driver = None

    # ----- 配置校验 -----

    def validate_config(self, config):
        if "auth" not in config:
            print("✗ 配置文件缺少 'auth' 字段")
            sys.exit(1)

    # ----- WebDriver 初始化 -----

    def _init_driver(self):
        """创建并配置 Chrome WebDriver。"""
        options = Options()

        # 反自动化检测
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # 移动端 User-Agent（社交平台对移动端限制更宽松）
        options.add_argument(
            "--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        )

        # 窗口尺寸（模拟手机屏幕）
        options.add_argument("--window-size=390,844")

        if self.headless:
            options.add_argument("--headless=new")

        # 其他优化
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-logging")
        options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
        })

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.set_page_load_timeout(self.page_timeout)
        self.driver.implicitly_wait(5)

    # ----- 认证 -----

    def login(self):
        """导航到 x.com 并注入 Cookie 完成认证。"""
        self._init_driver()
        auth = self.config.get("auth", {})

        cookies_file = auth.get("cookies_file", "")
        if not cookies_file or not os.path.isfile(cookies_file):
            print("✗ Cookie 文件不存在或未配置")
            print(f"  请在 config.json 的 auth.cookies_file 中指定 Cookie 文件路径")
            self.driver.quit()
            sys.exit(1)

        print(f"正在加载 Cookie: {cookies_file}")
        with open(cookies_file, "r", encoding="utf-8") as f:
            cookies = json.load(f)

        # 先访问 x.com 建立域名上下文（带重试）
        print("正在访问 x.com ...")
        for attempt in range(3):
            try:
                self.driver.get("https://x.com")
                break
            except Exception as e:
                if attempt < 2:
                    print(f"  ⚠ 页面加载超时，重试 ({attempt+1}/3)...")
                    time.sleep(5)
                else:
                    raise
        time.sleep(3)

        # 注入 Cookie
        if isinstance(cookies, dict):
            for name, value in cookies.items():
                try:
                    self.driver.add_cookie({"name": name, "value": value})
                except Exception as e:
                    print(f"  ⚠ 添加 Cookie '{name}' 失败: {e}")
        elif isinstance(cookies, list):
            for cookie in cookies:
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    print(f"  ⚠ 添加 Cookie 失败: {e}")

        # 刷新页面使 Cookie 生效
        print("正在刷新验证登录状态...")
        for attempt in range(3):
            try:
                self.driver.get("https://x.com")
                break
            except Exception:
                if attempt < 2:
                    print(f"  ⚠ 页面加载超时，重试 ({attempt+1}/3)...")
                    time.sleep(5)
                else:
                    print("  ⚠ 页面加载较慢，继续尝试...")
        time.sleep(3)

        # 简单校验
        page_source = self.driver.page_source
        if "Sign in" in page_source or "login" in self.driver.current_url.lower():
            print("⚠ 可能未成功登录，请检查 Cookie 是否有效")
        else:
            print("✓ Cookie 登录成功")

    # ----- 滚动加载 -----

    def _scroll_to_load(self, target_count, label="推文", max_scrolls=50):
        """滚动页面加载更多推文，直到达到目标数量或无法加载更多。"""
        tweet_elements = []
        last_count = 0
        stale_count = 0

        for scroll_num in range(max_scrolls):
            # 获取当前所有推文元素
            tweet_elements = self.driver.find_elements(By.CSS_SELECTOR, self.TWEET_SELECTOR)
            current_count = len(tweet_elements)

            if current_count >= target_count:
                print(f"  已加载 {current_count} 个推文元素 (目标 {target_count})")
                break

            if current_count == last_count:
                stale_count += 1
                if stale_count >= 3:
                    print(f"  连续 {stale_count} 次无新内容，停止滚动")
                    break
            else:
                stale_count = 0
                print(f"  已加载 {current_count} 个推文元素 (目标 {target_count})")

            last_count = current_count

            # 限流等待
            self.rate_limiter.wait(label=f"{label}滚动{scroll_num+1}")

            # 滚动到底部
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(self.scroll_pause)

            # 批次长暂停
            self.rate_limiter.batch_pause()

        return tweet_elements[:target_count]

    # ----- 推文数据提取 -----

    def _extract_tweet(self, article_el):
        """从 article DOM 元素中提取推文数据字典。

        Args:
            article_el: Selenium WebElement (<article>)

        Returns:
            dict 或 None（无法解析时）
        """
        try:
            # --- 推文链接 & ID ---
            links = article_el.find_elements(By.CSS_SELECTOR, 'a[href*="/status/"]')
            tweet_url = ""
            tweet_id = ""
            for link in links:
                href = link.get_attribute("href") or ""
                match = re.search(r"/status/(\d+)", href)
                if match:
                    tweet_id = match.group(1)
                    tweet_url = href
                    break

            if not tweet_id:
                return None  # 无法提取 ID 的推文跳过

            # --- 文本 ---
            text_el = safe_find(article_el, self.TEXT_SELECTOR)
            text = text_el.text.strip() if text_el else ""

            # --- 时间 ---
            time_el = safe_find(article_el, self.TIME_SELECTOR)
            created_at = parse_datetime(time_el)

            # --- 作者信息 ---
            author_name = ""
            author_handle = ""
            # 从 UserAvatar 容器提取 screen_name
            avatar_containers = article_el.find_elements(
                By.CSS_SELECTOR, '[data-testid^="UserAvatar-Container-"]'
            )
            if avatar_containers:
                testid = avatar_containers[0].get_attribute("data-testid") or ""
                author_handle = testid.replace("UserAvatar-Container-", "")

            # 从用户链接提取显示名称
            if author_handle:
                user_links = article_el.find_elements(By.CSS_SELECTOR, f'a[href="/{author_handle}"]')
                for ulink in user_links:
                    aria_label = ulink.get_attribute("aria-label") or ""
                    if aria_label and not aria_label.startswith("@"):
                        author_name = aria_label
                        break
                    link_text = ulink.text.strip()
                    if link_text and not link_text.startswith("@"):
                        author_name = link_text
                        break

            if not author_name and author_handle:
                for link in article_el.find_elements(By.CSS_SELECTOR, 'a[role="link"]'):
                    href = link.get_attribute("href") or ""
                    if f"/{author_handle}" in href:
                        inner_text = link.text.strip()
                        if inner_text and not inner_text.startswith("@") and len(inner_text) < 100:
                            author_name = inner_text
                            break

            if not author_name:
                author_name = author_handle

            # --- 互动数据 ---
            metrics = self._extract_metrics(article_el)

            # --- 话题标签 ---
            hashtags = []
            if text:
                hashtags = re.findall(r"#(\w+)", text)

            # --- 链接 ---
            urls = []
            url_links = article_el.find_elements(By.CSS_SELECTOR, 'a[href*="http"]')
            for ul in url_links:
                href = ul.get_attribute("href") or ""
                if "x.com" not in href and "twitter.com" not in href:
                    urls.append(href)

            # --- 媒体 ---
            photos = article_el.find_elements(By.CSS_SELECTOR, self.PHOTO_SELECTOR)
            media_count = len(photos)

            # --- 是否回复 ---
            is_reply = "Replying to" in text or bool(
                safe_find(article_el, '[data-testid="socialContext"]')
            )

            return {
                "id": tweet_id,
                "text": text.replace("\n", " "),
                "created_at": created_at,
                "author_name": author_name,
                "author_handle": author_handle,
                "favorite_count": metrics.get("like", 0),
                "retweet_count": metrics.get("retweet", 0),
                "reply_count": metrics.get("reply", 0),
                "quote_count": metrics.get("quote", 0),
                "view_count": metrics.get("view", 0),
                "hashtags": ",".join(hashtags),
                "urls": "|".join(urls[:5]),
                "media_count": media_count,
                "is_reply": is_reply,
                "tweet_url": tweet_url,
            }

        except Exception as e:
            print(f"  ⚠ 提取推文数据时出错: {e}")
            return None

    def _extract_metrics(self, article_el):
        """提取推文的互动数据（点赞/转发/回复/引用/查看）。"""
        metrics = {}

        # 主方案：从 role="group" 的 aria-label 解析
        # 格式："392 replies, 122 reposts, 767 likes, 30 bookmarks, 442408 views"
        group_el = safe_find(article_el, 'div[role="group"]')
        aria_label = group_el.get_attribute("aria-label") if group_el else ""

        if aria_label:
            reply_match = re.search(r"(\d[\d,]*)\s*repl", aria_label)
            repost_match = re.search(r"(\d[\d,]*)\s*repo", aria_label)
            like_match = re.search(r"(\d[\d,]*)\s*lik", aria_label)
            view_match = re.search(r"(\d[\d,]*)\s*vie", aria_label)

            if reply_match:
                metrics["reply"] = int(reply_match.group(1).replace(",", ""))
            if repost_match:
                metrics["retweet"] = int(repost_match.group(1).replace(",", ""))
            if like_match:
                metrics["like"] = int(like_match.group(1).replace(",", ""))
            if view_match:
                metrics["view"] = int(view_match.group(1).replace(",", ""))

        # Fallback: 从独立按钮 aria-label 解析
        if not metrics:
            for sel, keyword in [
                ('button[data-testid="reply"]', "repl"),
                ('button[data-testid="retweet"]', "repo"),
                ('button[data-testid="like"]', "lik"),
            ]:
                btn = safe_find(article_el, sel)
                if btn:
                    label = btn.get_attribute("aria-label") or ""
                    match = re.search(r"(\d[\d,]*)", label)
                    if not match:
                        continue
                    val = int(match.group(1).replace(",", ""))
                    if "reply" in keyword:
                        metrics["reply"] = val
                    elif "repo" in keyword:
                        metrics["retweet"] = val
                    elif "lik" in keyword:
                        metrics["like"] = val

        return metrics

    # ----- 页面导航（带重试） -----

    def _navigate(self, url, label="页面", max_retries=3):
        """安全导航到指定 URL，带超时重试。"""
        for attempt in range(max_retries):
            try:
                self.driver.get(url)
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"  ⚠ [{label}] 加载超时，重试 ({attempt+1}/{max_retries})...")
                    time.sleep(5)
                else:
                    print(f"  ✗ [{label}] 加载失败: {e}")
                    return False
        return False

    # ----- 抓取方法 -----

    def fetch_tweet(self, tweet_id):
        """获取单条推文详情。"""
        url = f"https://x.com/i/status/{tweet_id}"
        print(f"正在访问: {url}")

        self.rate_limiter.wait(label="获取推文")
        self._navigate(url, label="推文")
        time.sleep(3)

        # 等待推文元素加载
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, self.TWEET_SELECTOR))
            )
        except Exception:
            print(f"  ⚠ 推文加载超时，可能不存在或无权限访问")
            return []

        # 提取第一条推文（原帖）
        articles = self.driver.find_elements(By.CSS_SELECTOR, self.TWEET_SELECTOR)
        if not articles:
            print(f"  ✗ 未找到推文元素")
            return []

        tweet_data = self._extract_tweet(articles[0])
        if tweet_data:
            self.tweet_ids.add(tweet_data["id"])
            self.got_count += 1
            print(f"  ✓ 获取成功: @{tweet_data['author_handle']}")
            print(f"    内容: {tweet_data['text'][:80]}..."
                  if len(tweet_data['text']) > 80
                  else f"    内容: {tweet_data['text']}")
            print(f"    点赞: {tweet_data['favorite_count']}  "
                  f"转发: {tweet_data['retweet_count']}  "
                  f"回复: {tweet_data['reply_count']}")
            return [tweet_data]
        return []

    def fetch_user_timeline(self, screen_name, count=20):
        """获取指定用户的最新推文。"""
        screen_name = screen_name.lstrip("@")
        url = f"https://x.com/{screen_name}"
        print(f"正在访问用户主页: @{screen_name}")
        print(f"目标: {count} 条推文")

        self.rate_limiter.wait(label="访问主页")
        self._navigate(url, label="用户主页")
        time.sleep(3)

        # 滚动加载
        tweet_elements = self._scroll_to_load(count, label="@{screen_name}")

        # 提取数据
        tweets = []
        for article in tweet_elements:
            if len(tweets) >= count:
                break
            data = self._extract_tweet(article)
            if data and data["id"] not in self.tweet_ids:
                self.tweet_ids.add(data["id"])
                tweets.append(data)

        self.got_count += len(tweets)
        print(f"  ✓ 实际获取 {len(tweets)} 条 @{screen_name} 的推文")
        return tweets

    def fetch_search_tweets(self, query, count=20, product="Latest"):
        """根据关键词搜索推文。"""
        from urllib.parse import quote_plus

        encoded_query = quote_plus(query)
        url = f"https://x.com/search?q={encoded_query}&f={'live' if product == 'Latest' else 'top'}"
        print(f"正在搜索: \"{query}\" (类型: {product}, 目标: {count} 条)")

        self.rate_limiter.wait(label="搜索")
        self._navigate(url, label="搜索")
        time.sleep(3)

        # 滚动加载
        tweet_elements = self._scroll_to_load(count, label="搜索")

        # 提取数据
        tweets = []
        for article in tweet_elements:
            if len(tweets) >= count:
                break
            data = self._extract_tweet(article)
            if data and data["id"] not in self.tweet_ids:
                self.tweet_ids.add(data["id"])
                tweets.append(data)

        self.got_count += len(tweets)
        print(f"  ✓ 实际获取 {len(tweets)} 条搜索结果")
        return tweets

    def fetch_tweet_replies(self, tweet_id, count=20):
        """获取指定推文的回复列表（含原帖）。"""
        url = f"https://x.com/i/status/{tweet_id}"
        print(f"正在获取推文 {tweet_id} 及其回复 (目标 {count} 条)...")

        self.rate_limiter.wait(label="获取推文及回复")
        self._navigate(url, label="推文及回复")
        time.sleep(3)

        # 等待加载
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, self.TWEET_SELECTOR))
            )
        except Exception:
            print(f"  ⚠ 页面加载超时")
            return []

        # 滚动加载更多（含原帖所以 target+1）
        tweet_elements = self._scroll_to_load(count + 1, label="回复")

        # 提取数据
        all_tweets = []
        for article in tweet_elements:
            if len(all_tweets) >= count + 1:
                break
            data = self._extract_tweet(article)
            if data and data["id"] not in self.tweet_ids:
                self.tweet_ids.add(data["id"])
                all_tweets.append(data)

        # 第一条是原帖
        if all_tweets:
            all_tweets[0]["is_original"] = True
            for t in all_tweets[1:]:
                t["is_original"] = False

        self.got_count += len(all_tweets)
        print(f"  ✓ 实际获取原帖 + {max(0, len(all_tweets)-1)} 条回复")
        return all_tweets

    # ----- 数据输出 -----

    def export_csv(self, data, output_path, meta=None):
        """将推文数据导出为 CSV 文件（UTF-8 编码）。"""
        if not data:
            print("⚠ 无数据可输出")
            return

        fieldnames = [
            "id", "text", "created_at", "author_name", "author_handle",
            "favorite_count", "retweet_count", "reply_count", "quote_count",
            "view_count", "hashtags", "urls", "media_count",
            "is_reply", "tweet_url",
        ]

        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)

        print(f"\n✓ 结果已保存到: {output_path}")

    def _make_output_path(self, query, suffix=""):
        """生成输出文件路径。"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = "".join(
            c for c in str(query) if c.isalnum() or c in "_- "
        )[:50].strip().replace(" ", "_")
        if suffix:
            safe_query = f"{safe_query}_{suffix}"
        filename = f"{safe_query}_{ts}.csv"
        return os.path.join(self.output_dir, filename)

    # ----- 调度入口 -----

    def start(self, cli_args):
        """根据 CLI 参数调度抓取任务。"""
        self.login()

        mode = cli_args.mode
        data = []
        query = ""

        try:
            if mode == "tweet":
                tweet_id = cli_args.tweet_id
                query = tweet_id
                data = self.fetch_tweet(tweet_id)

            elif mode == "timeline":
                screen_name = cli_args.screen_name
                count = cli_args.count
                query = screen_name
                data = self.fetch_user_timeline(screen_name, count)

            elif mode == "search":
                query = cli_args.query
                count = cli_args.count
                product = cli_args.product
                data = self.fetch_search_tweets(query, count, product)

            elif mode == "replies":
                tweet_id = cli_args.tweet_id
                count = cli_args.count
                query = tweet_id
                data = self.fetch_tweet_replies(tweet_id, count)

        except KeyboardInterrupt:
            print("\n⚠ 用户中断操作")
            if data:
                print(f"  已获取 {len(data)} 条数据，正在保存...")
            else:
                self.driver.quit()
                sys.exit(0)
        except Exception as e:
            print(f"\n✗ 抓取异常: {e}")
            traceback.print_exc()
        finally:
            # 确保浏览器关闭
            if self.driver:
                self.driver.quit()
                print("浏览器已关闭")

        # 输出
        output_path = getattr(cli_args, "output", None)
        if not output_path:
            output_path = self._make_output_path(query, mode)

        if data:
            self.export_csv(data, output_path)

        print_summary(
            mode=mode,
            query=query,
            requested=getattr(cli_args, "count", 1),
            actual=len(data),
            output_path=output_path,
            skipped=self.skipped_count,
        )


# ============================================================
#  CLI 入口
# ============================================================

def generate_config(output_path="config.json"):
    """生成模板配置文件。"""
    template = {
        "auth": {
            "cookies_file": "x_cookies.json",
        },
        "output": {
            "directory": "x_output",
        },
        "rate_limit": {
            "min_interval_seconds": 8,
            "max_interval_seconds": 15,
            "long_pause_seconds": 90,
            "pages_per_long_pause": 10,
            "cooldown_seconds": 300,
            "max_retries": 3,
        },
        "selenium": {
            "headless": False,
            "page_load_timeout": 30,
            "scroll_pause_seconds": 3,
        },
    }

    if os.path.exists(output_path):
        print(f"⚠ 配置文件已存在: {output_path}")
        resp = input("  是否覆盖? (y/N): ").strip().lower()
        if resp != "y":
            print("  已取消")
            return

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)

    print(f"✓ 配置文件模板已生成: {output_path}")
    print()
    print("下一步：")
    print("  1. 编辑 config.json，将 cookies_file 指向 Cookie 文件")
    print("  2. Cookie 文件获取方式：")
    print("     - 在浏览器中登录 x.com")
    print("     - 打开开发者工具 → Application → Cookies")
    print("     - 导出 Cookie 保存为 x_cookies.json")
    print("  3. 确保 Chrome 浏览器已安装")
    print()
    print("然后运行: python3 x_scraper.py tweet <推文ID>")


def main():
    parser = argparse.ArgumentParser(
        description="X (Twitter) 帖子爬虫工具 - 基于 Selenium + Chrome",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python3 x_scraper.py config                       生成配置文件
  python3 x_scraper.py tweet 1234567890             获取单条推文
  python3 x_scraper.py timeline elonmusk --count 50 获取用户时间线
  python3 x_scraper.py search "python" --count 20   搜索推文
  python3 x_scraper.py replies 1234567890 --count 30 获取推文回复
        """,
    )

    # 全局参数
    parser.add_argument(
        "-c", "--config",
        default="config.json",
        help="配置文件路径 (默认: config.json)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="输出详细调试信息",
    )

    # 子命令
    subparsers = parser.add_subparsers(
        dest="mode",
        title="子命令",
        description="选择要执行的抓取模式",
        help="可用的抓取模式",
    )

    # ---- tweet 子命令 ----
    tweet_parser = subparsers.add_parser("tweet", help="根据推文 ID 获取单条推文详情")
    tweet_parser.add_argument("tweet_id", help="推文 ID（数字字符串，从 URL 中获取）")
    tweet_parser.add_argument("-o", "--output", help="输出文件路径（默认自动生成）")

    # ---- timeline 子命令 ----
    timeline_parser = subparsers.add_parser("timeline", help="获取指定用户的最新推文")
    timeline_parser.add_argument("screen_name", help="用户 screen name（@后面的部分，如 elonmusk）")
    timeline_parser.add_argument("--count", type=int, default=20, help="获取推文数量 (默认: 20)")
    timeline_parser.add_argument("-o", "--output", help="输出文件路径（默认自动生成）")

    # ---- search 子命令 ----
    search_parser = subparsers.add_parser("search", help="根据关键词搜索推文")
    search_parser.add_argument("query", help="搜索关键词")
    search_parser.add_argument("--count", type=int, default=20, help="获取推文数量 (默认: 20)")
    search_parser.add_argument(
        "--product", choices=["Top", "Latest"], default="Latest",
        help="搜索类型 (默认: Latest)",
    )
    search_parser.add_argument("-o", "--output", help="输出文件路径（默认自动生成）")

    # ---- replies 子命令 ----
    replies_parser = subparsers.add_parser("replies", help="获取指定推文的回复列表（含原帖）")
    replies_parser.add_argument("tweet_id", help="推文 ID")
    replies_parser.add_argument("--count", type=int, default=20, help="获取回复数量 (默认: 20)")
    replies_parser.add_argument("-o", "--output", help="输出文件路径（默认自动生成）")

    # ---- config 子命令 ----
    config_parser = subparsers.add_parser("config", help="生成模板配置文件")
    config_parser.add_argument(
        "-o", "--output", default="config.json",
        help="配置文件输出路径 (默认: config.json)",
    )

    # 解析
    args = parser.parse_args()

    if not args.mode:
        parser.print_help()
        print("\n✗ 请指定一个子命令")
        sys.exit(1)

    if args.mode == "config":
        print_banner()
        generate_config(args.output)
        return

    print_banner()

    # 加载配置
    config = get_config(args.config)

    # 创建爬虫实例并执行
    scraper = SeleniumScraper(config)
    scraper.start(args)


if __name__ == "__main__":
    main()
