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
from datetime import datetime, timezone, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

try:
    import undetected_chromedriver as uc
    HAS_UC = True
except ImportError:
    HAS_UC = False


# ============================================================
#  新疆相关关键词（用于过滤帖子）
# ============================================================
XINJIANG_KEYWORDS = [
    # 中文
    "新疆", "维吾尔", "东突", "东突厥",
    # 英文
    "Xinjiang", "Uyghur", "Uighur", "Uygur", "Uigur",
    "East Turkestan", "East Turkistan",
    # 其他
    "ウイグル", "อุยกูร์",
]

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


def matches_xinjiang(text):
    """检查文本是否匹配新疆相关关键词（大小写不敏感）。"""
    if not text:
        return False
    text_lower = text.lower()
    for kw in XINJIANG_KEYWORDS:
        if kw.lower() in text_lower:
            return True
    return False


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
    模拟真实用户操作，通过 JS 原子提取页面数据避免 stale element。
    """

    TWEET_SELECTOR = 'article[data-testid="tweet"]'

    # ---- JS 脚本：在浏览器端原子提取所有可见推文的结构化数据 ----
    _EXTRACT_TWEETS_JS = r"""
    const results = [];
    const articles = document.querySelectorAll('article[data-testid="tweet"]');
    articles.forEach((article, idx) => {
      try {
        // --- 推文链接 & ID ---
        let tweetId = '', tweetUrl = '';
        const statusLinks = article.querySelectorAll('a[href*="/status/"]');
        for (const link of statusLinks) {
          const href = link.getAttribute('href') || '';
          const match = href.match(/\/status\/(\d+)/);
          if (match) { tweetId = match[1]; tweetUrl = 'https://x.com' + href.split('?')[0]; break; }
        }
        if (!tweetId) return;

        // --- 文本（使用 innerText 获取完整文本，保留换行）---
        const textEl = article.querySelector('[data-testid="tweetText"]');
        const text = textEl ? textEl.innerText.trim() : '';

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

        // --- 互动数据（从 role="group" aria-label 解析）---
        let likeCount = 0, retweetCount = 0, replyCount = 0, viewCount = 0;
        const groupEl = article.querySelector('div[role="group"]');
        if (groupEl) {
          const aria = groupEl.getAttribute('aria-label') || '';
          let m;
          m = aria.match(/([\d,]+)\s*repl/i); if (m) replyCount = parseInt(m[1].replace(/,/g, ''));
          m = aria.match(/([\d,]+)\s*repo/i); if (m) retweetCount = parseInt(m[1].replace(/,/g, ''));
          m = aria.match(/([\d,]+)\s*lik/i); if (m) likeCount = parseInt(m[1].replace(/,/g, ''));
          m = aria.match(/([\d,]+)\s*vie/i); if (m) viewCount = parseInt(m[1].replace(/,/g, ''));
        }

        // --- 话题标签 ---
        const hashtags = (text.match(/#(\w+)/g) || []).map(h => h.replace('#', ''));

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
        const mediaCount = article.querySelectorAll('[data-testid="tweetPhoto"]').length;

        // --- 是否回复 / 回复对象 ---
        const socialContext = article.querySelector('[data-testid="socialContext"]');
        const isReply = text.includes('Replying to') || !!socialContext;
        let replyTo = '';
        if (socialContext) {
          replyTo = socialContext.innerText.trim();
        }

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
          is_reply: isReply,
          reply_to: replyTo,
          tweet_url: tweetUrl,
        });
      } catch(e) {}
    });
    return JSON.stringify(results);
    """

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

        # Xinjiang 关键词过滤
        self.filter_xinjiang = config.get("filter", {}).get("xinjiang_only", True)

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
        """创建并配置 Chrome WebDriver。优先使用 undetected-chromedriver。"""
        options = Options()

        selenium_cfg = self.config.get("selenium", {})
        profile_dir = selenium_cfg.get("profile_dir", "")
        use_profile = selenium_cfg.get("use_existing_profile", False)
        use_uc = selenium_cfg.get("use_undetected", True)

        if use_profile and profile_dir and os.path.isdir(profile_dir):
            options.add_argument(f"--user-data-dir={profile_dir}")
            print(f"✓ 使用已有 Chrome Profile: {profile_dir}")
        else:
            options.add_argument(
                "--user-agent=Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            )
            options.add_argument("--window-size=390,844")

        if self.headless:
            options.add_argument("--headless=new")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-notifications")
        options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
        })

        # 使用 undetected-chromedriver（绕过 X 反爬检测）
        if use_uc and HAS_UC and not use_profile:
            print("✓ 使用 undetected-chromedriver（反检测模式）")
            self.driver = uc.Chrome(options=options)
        else:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)

        self.driver.set_page_load_timeout(self.page_timeout)
        self.driver.implicitly_wait(5)

    # ----- 认证 -----

    def login(self):
        """导航到 x.com 并完成认证。"""
        self._init_driver()

        selenium_cfg = self.config.get("selenium", {})
        use_profile = selenium_cfg.get("use_existing_profile", False)

        if use_profile:
            # 使用已有 Chrome Profile，直接访问 x.com 验证登录态
            print("正在访问 x.com (使用已有 Profile)...")
            for attempt in range(3):
                try:
                    self.driver.get("https://x.com")
                    break
                except Exception:
                    if attempt < 2:
                        print(f"  ⚠ 页面加载超时，重试 ({attempt+1}/3)...")
                        time.sleep(5)
            time.sleep(4)

            page_source = self.driver.page_source
            if "Something went wrong" in page_source:
                print("⚠ X 返回错误页面，可能需要等待限流解除")
            elif "Sign in" in page_source or "login" in self.driver.current_url.lower():
                print("⚠ Profile 未登录 X，请在 Chrome 中先登录 x.com 后再试")
            else:
                print("✓ Profile 登录态有效")
            return

        # 否则使用 Cookie 注入方式
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

        # 先访问 x.com 建立域名上下文
        print("正在访问 x.com ...")
        for attempt in range(3):
            try:
                self.driver.get("https://x.com")
                break
            except Exception:
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

        page_source = self.driver.page_source
        if "Something went wrong" in page_source:
            print("⚠ X 返回错误页面，可能需要等待限流解除后重试")
        elif "Sign in" in page_source or "login" in self.driver.current_url.lower():
            print("⚠ 可能未成功登录，请检查 Cookie 是否有效")
        else:
            print("✓ Cookie 登录成功")

    # ----- JS 批量提取 -----

    def _extract_tweets_batch(self):
        """通过 JS 在浏览器端原子提取所有可见推文数据，返回 dict 列表。"""
        try:
            json_str = self.driver.execute_script(self._EXTRACT_TWEETS_JS)
            if json_str and len(json_str) > 2:  # 不是空数组 "[]"
                return json.loads(json_str)
            return []
        except Exception as e:
            print(f"  ⚠ JS 批量提取推文失败: {e}")
            return []

    # ----- 滚动加载 -----

    def _scroll_to_load(self, target_count, label="推文", max_scrolls=200,
                        since_date=None, until_date=None, keyword_filter=False):
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
        collected = []
        last_unique = 0
        stale_count = 0

        for scroll_num in range(max_scrolls):
            batch = self._extract_tweets_batch()

            for data in batch:
                if len(collected) >= target_count:
                    break
                if not data or not data.get("id"):
                    continue
                if data["id"] in self.tweet_ids:
                    continue

                # 关键词过滤
                if keyword_filter:
                    text = data.get("text", "")
                    if not matches_xinjiang(text):
                        self.skipped_count += 1
                        continue

                # 时间过滤
                created = data.get("created_at", "")
                if since_date and created and created[:10] < since_date:
                    print(f"  推文时间 {created[:10]} 早于 {since_date}，停止滚动")
                    self._stop_early = True
                    break
                if until_date and created and created[:10] > until_date:
                    continue

                self.tweet_ids.add(data["id"])
                collected.append(data)

            current_unique = len(collected)

            if current_unique >= target_count:
                print(f"  已收集 {current_unique} 条推文 (目标 {target_count})")
                break

            if getattr(self, '_stop_early', False):
                self._stop_early = False
                break

            if current_unique == last_unique:
                stale_count += 1
                if stale_count >= 5:
                    print(f"  连续 {stale_count} 次无新推文，停止滚动")
                    break
            else:
                stale_count = 0
                print(f"  已收集 {current_unique} 条推文 (目标 {target_count})")

            last_unique = current_unique

            self.rate_limiter.wait(label=f"{label}滚动{scroll_num+1}")
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(self.scroll_pause)
            self.rate_limiter.batch_pause()

        return collected

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

        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, self.TWEET_SELECTOR))
            )
        except Exception:
            print(f"  ⚠ 推文加载超时，可能不存在或无权限访问")
            return []

        batch = self._extract_tweets_batch()
        if not batch:
            print(f"  ✗ 未找到推文元素")
            return []

        tweet_data = batch[0]
        if tweet_data:
            self.tweet_ids.add(tweet_data["id"])
            self.got_count += 1
            print(f"  ✓ 获取成功: @{tweet_data['author_handle']}")
            txt = tweet_data['text']
            print(f"    内容: {txt[:80]}..." if len(txt) > 80 else f"    内容: {txt}")
            return [tweet_data]
        return []

    def fetch_user_timeline(self, screen_name, count=20, since_date=None, until_date=None,
                            keyword_filter=False):
        """获取指定用户的最新推文。"""
        screen_name = screen_name.lstrip("@")
        url = f"https://x.com/{screen_name}"
        print(f"正在访问用户主页: @{screen_name}")
        if since_date or until_date:
            print(f"时间段: {since_date or '不限'} ~ {until_date or '不限'}")
        if keyword_filter:
            print(f"关键词过滤: 新疆/Uyghur/Xinjiang")
        print(f"目标: {count} 条推文")

        self.rate_limiter.wait(label="访问主页")
        self._navigate(url, label="用户主页")
        time.sleep(3)

        tweets = self._scroll_to_load(
            count, label=f"@{screen_name}",
            since_date=since_date, until_date=until_date,
            keyword_filter=keyword_filter,
        )

        self.got_count += len(tweets)
        print(f"  ✓ 实际获取 {len(tweets)} 条 @{screen_name} 的推文")
        if keyword_filter and self.skipped_count > 0:
            print(f"     (跳过 {self.skipped_count} 条不相关推文)")
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

        tweets = self._scroll_to_load(count, label="搜索")
        self.got_count += len(tweets)
        print(f"  ✓ 实际获取 {len(tweets)} 条搜索结果")
        return tweets

    # ----- 评论 & 子评论抓取 -----

    def _fetch_comments_for_tweet(self, tweet_url, max_comments=20, max_depth=1):
        """获取指定推文的所有评论及子评论（递归）。

        Args:
            tweet_url: 推文链接
            max_comments: 最多获取多少条一级评论
            max_depth: 子评论递归深度（0=仅一级评论, 1=含子评论, 默认1）

        Returns:
            list[dict]: 所有评论（含子评论），每条包含 parent_tweet_id, parent_author, depth 字段
        """
        all_comments = []
        try:
            self.rate_limiter.wait(label="获取评论")
            self._navigate(tweet_url, label="推文详情")
            time.sleep(4)

            # 等待评论加载
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, self.TWEET_SELECTOR))
                )
            except Exception:
                return all_comments

            # 滚动加载更多评论
            original_ids = self.tweet_ids.copy()
            comments = self._scroll_to_load(
                max_comments + 1,  # +1 因为第一条是原帖
                label="评论",
                max_scrolls=100,
            )

            # 过滤掉原帖和已处理的
            for c in comments:
                if c["id"] in original_ids:
                    continue
                c["depth"] = 0  # 一级评论
                all_comments.append(c)

            # 递归获取子评论
            if max_depth > 0:
                top_level = [c for c in all_comments if c.get("depth", 0) == 0]
                for i, comment in enumerate(top_level):
                    if comment.get("reply_count", 0) > 0:
                        sub_url = comment.get("tweet_url", "")
                        if not sub_url:
                            continue
                        print(f"    [{i+1}/{len(top_level)}] 抓取子评论: "
                              f"@{comment['author_handle']} 的评论 (已有{comment['reply_count']}条回复)...")
                        sub_comments = self._fetch_comments_for_tweet(
                            sub_url, max_comments=20, max_depth=max_depth - 1
                        )
                        for sc in sub_comments:
                            sc["depth"] = 1
                            sc["parent_comment_id"] = comment["id"]
                        all_comments.extend(sub_comments)
                        print(f"      → 获取 {len(sub_comments)} 条子评论")

        except Exception as e:
            print(f"  ⚠ 获取评论时出错: {e}")

        return all_comments

    def fetch_report(self, screen_name, since_date, until_date=None,
                     replies_per_tweet=20, max_comment_depth=1):
        """一站式报告。返回 (posts, comments, following, followers)。"""
        # 第一步：获取用户时间线
        print(f"\n{'='*40}")
        print(f"  第一步：抓取 @{screen_name} 的时间线")
        print(f"  关键词: 新疆 / Xinjiang / Uyghur")
        print(f"{'='*40}")
        posts = self.fetch_user_timeline(
            screen_name, count=9999,
            since_date=since_date,
            until_date=until_date,
            keyword_filter=True,
        )

        # 提取 Profile 统计数据
        following, followers = self._get_profile_stats(screen_name)
        print(f"  Profile: Following={following}, Followers={followers}")

        if not posts:
            print("✗ 该时间段内无新疆相关推文")
            return [], [], following, followers

        print(f"\n✓ 第一步完成：获取 {len(posts)} 条新疆相关推文")

        # 第二步：对每条推文抓取评论（含子评论）
        print(f"\n{'='*40}")
        print(f"  第二步：抓取每条推文的评论 (一级{replies_per_tweet}条 + 子评论深度{max_comment_depth})")
        print(f"{'='*40}")

        all_comments = []
        for i, post in enumerate(posts):
            tweet_url = post.get("tweet_url", "")
            if not tweet_url:
                continue

            txt_preview = post['text'][:60].replace('\n', ' ')
            print(f"\n[{i+1}/{len(posts)}] {txt_preview}...")
            print(f"    作者: @{post['author_handle']} | {post['created_at'][:16] if post.get('created_at') else '?'}")

            comments = self._fetch_comments_for_tweet(
                tweet_url,
                max_comments=replies_per_tweet,
                max_depth=max_comment_depth,
            )

            # 给每条评论打上所属推文信息
            for c in comments:
                c["parent_tweet_id"] = post["id"]
                c["parent_tweet_author"] = post["author_handle"]
                if "parent_comment_id" not in c:
                    c["parent_comment_id"] = ""

            all_comments.extend(comments)
            depth0 = sum(1 for c in comments if c.get("depth", 0) == 0)
            depth1 = sum(1 for c in comments if c.get("depth", 0) >= 1)
            print(f"  → 一级评论 {depth0} 条 + 子评论 {depth1} 条 = 共 {len(comments)} 条")

        print(f"\n✓ 第二步完成：共获取 {len(all_comments)} 条评论")
        return posts, all_comments, following, followers

    # ----- 数据输出 -----

    @staticmethod
    def _fmt_time_posts(iso_str):
        """ISO 8601 UTC → Posts 格式: YYYY.M.DD (CST)"""
        if not iso_str:
            return ""
        try:
            # Parse ISO 8601
            dt_str = iso_str.replace("Z", "+00:00")
            from datetime import timezone as tz
            dt = datetime.fromisoformat(dt_str)
            # Convert to CST (UTC+8)
            cst = tz(timedelta(hours=8))
            dt_cst = dt.astimezone(cst)
            return f"{dt_cst.year}.{dt_cst.month}.{dt_cst.day}"
        except Exception:
            return iso_str[:10].replace("-", ".") if len(iso_str) >= 10 else iso_str

    @staticmethod
    def _fmt_time_comments(iso_str):
        """ISO 8601 UTC → 评论格式: YYYY.M.DD HH:MM (CST)"""
        if not iso_str:
            return ""
        try:
            dt_str = iso_str.replace("Z", "+00:00")
            from datetime import timezone as tz
            dt = datetime.fromisoformat(dt_str)
            cst = tz(timedelta(hours=8))
            dt_cst = dt.astimezone(cst)
            return f"{dt_cst.year}.{dt_cst.month}.{dt_cst.day} {dt_cst.hour:02d}:{dt_cst.minute:02d}"
        except Exception:
            return iso_str[:16].replace("-", ".").replace("T", " ") if len(iso_str) >= 16 else iso_str

    @staticmethod
    def _ensure_at(text):
        """确保字符串以 @ 开头"""
        if not text:
            return ""
        return f"@{text.lstrip('@')}"

    def _get_profile_stats(self, screen_name):
        """从用户主页提取 Following / Followers 数。"""
        try:
            js = r"""
            var stats = {following: '', followers: ''};
            var links = document.querySelectorAll('a[href*="/following"], a[href*="/verified_followers"]');
            links.forEach(function(a) {
              var href = a.getAttribute('href') || '';
              var text = (a.innerText || '').trim();
              var numMatch = text.match(/([\d,.]+)/);
              var num = numMatch ? numMatch[1] : '';
              if (href.includes('/following') && !href.includes('verified')) {
                stats.following = num;
              } else if (href.includes('/verified_followers')) {
                stats.followers = num;
              }
            });
            // fallback: look for spans with these numbers next to text
            if (!stats.following || !stats.followers) {
              var allText = document.body ? document.body.innerText : '';
              var followingMatch = allText.match(/([\d,.]+)\s*Following/);
              var followersMatch = allText.match(/([\d,.]+)\s*Followers/);
              if (followingMatch) stats.following = followingMatch[1];
              if (followersMatch) stats.followers = followersMatch[1];
            }
            return JSON.stringify(stats);
            """
            raw = self.driver.execute_script(js)
            stats = json.loads(raw) if raw else {}
            following = stats.get("following", "")
            followers = stats.get("followers", "")
            return following, followers
        except Exception:
            return "", ""

    def export_posts_csv(self, data, output_path, profile_following="", profile_followers=""):
        """导出帖子 CSV，列格式与 24-25年知情代理人涉疆数据.xlsx 一致。

        列: ID, name, Following, Followers, time, text, translation,
            tag, reply, repost, likes, views, vedios/photos, 评论条数
        """
        if not data:
            print("⚠ 无帖子数据可输出")
            return

        fieldnames = [
            "ID", "name", "Following", "Followers", "time", "text",
            "translation", "tag", "reply", "repost", "likes", "views",
            "vedios/photos", "评论条数",
        ]

        rows = []
        for d in data:
            handle = d.get("author_handle", "")
            name = d.get("author_name", "")

            # 只有目标用户本人的帖子才填 Following/Followers
            following = ""
            followers = ""
            if profile_following and handle:
                following = profile_following
                followers = profile_followers

            # 媒体列
            media_count = d.get("media_count", 0)
            media_str = "/" if media_count == 0 else str(media_count)

            # tag 列：第一个外部链接 或 /
            urls_str = d.get("urls", "")
            if urls_str:
                first_url = urls_str.split("|")[0]
                tag = first_url if first_url else "/"
            else:
                tag = "/"

            rows.append({
                "ID": self._ensure_at(handle),
                "name": name,
                "Following": following,
                "Followers": followers,
                "time": self._fmt_time_posts(d.get("created_at", "")),
                "text": d.get("text", ""),
                "translation": d.get("translation", ""),
                "tag": tag,
                "reply": d.get("reply_count", 0),
                "repost": d.get("retweet_count", 0),
                "likes": d.get("favorite_count", 0),
                "views": d.get("view_count", 0),
                "vedios/photos": media_str,
                "评论条数": d.get("reply_count", 0),
            })

        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"\n✓ 帖子结果已保存到: {output_path}")

    def export_comments_csv(self, data, output_path):
        """导出评论 CSV，列格式与 评论.xlsx 一致。

        列: (序号), account, tweet_id, link, time, text, 贴主ID
        """
        if not data:
            print("⚠ 无评论数据可输出")
            return

        fieldnames = [
            "序号", "account", "tweet_id", "link", "time", "text", "贴主ID",
        ]

        rows = []
        for i, d in enumerate(data):
            rows.append({
                "序号": i,
                "account": d.get("author_name", ""),
                "tweet_id": self._ensure_at(d.get("author_handle", "")),
                "link": d.get("tweet_url", ""),
                "time": self._fmt_time_comments(d.get("created_at", "")),
                "text": d.get("text", ""),
                "贴主ID": self._ensure_at(d.get("parent_tweet_author", "")),
            })

        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"\n✓ 评论结果已保存到: {output_path}")

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
                since = getattr(cli_args, "since", None)
                until = getattr(cli_args, "until", None)
                query = screen_name
                data = self.fetch_user_timeline(screen_name, count, since, until)

            elif mode == "search":
                query = cli_args.query
                count = cli_args.count
                product = cli_args.product
                data = self.fetch_search_tweets(query, count, product)

            elif mode == "replies":
                tweet_id = cli_args.tweet_id
                count = cli_args.count
                query = tweet_id
                # 使用新的评论抓取方法
                url = f"https://x.com/i/status/{tweet_id}"
                self.rate_limiter.wait(label="获取推文")
                self._navigate(url, label="推文详情")
                time.sleep(3)
                data = self._scroll_to_load(count + 1, label="回复")
                if data:
                    for t in data[1:]:
                        t["depth"] = 0
                    data[0]["is_original"] = True

            elif mode == "report":
                screen_name = cli_args.screen_name
                since_date = cli_args.since
                until_date = getattr(cli_args, "until", None)
                reply_count = cli_args.replies
                max_depth = getattr(cli_args, "depth", 1)
                query = screen_name

                posts, comments, following, followers = self.fetch_report(
                    screen_name, since_date, until_date, reply_count, max_depth
                )

                # 输出帖子 CSV（列对齐 24-25年知情代理人涉疆数据.xlsx）
                post_path = getattr(cli_args, "output", None)
                if not post_path:
                    post_path = self._make_output_path(query, "posts")
                if posts:
                    self.export_posts_csv(posts, post_path, following, followers)

                # 输出评论 CSV（列对齐 评论.xlsx）
                comment_path = None
                if comments:
                    comment_path = self._make_output_path(query, "comments")
                    self.export_comments_csv(comments, comment_path)

                print_summary(
                    mode=mode,
                    query=query,
                    requested=reply_count,
                    actual=len(posts),
                    output_path=f"{post_path}\n{' '*12}+ {comment_path}",
                    skipped=self.skipped_count,
                )
                return

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
            if self.driver:
                self.driver.quit()
                print("浏览器已关闭")

        # 输出
        output_path = getattr(cli_args, "output", None)
        if not output_path:
            output_path = self._make_output_path(query, mode)

        if data:
            self.export_posts_csv(data, output_path)

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
        "filter": {
            "xinjiang_only": True,
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
  python3 x_scraper.py config                                 生成配置文件
  python3 x_scraper.py tweet 1234567890                       获取单条推文
  python3 x_scraper.py timeline elonmusk --count 50           获取用户时间线
  python3 x_scraper.py timeline elonmusk --since 2025-01-01   时间段过滤
  python3 x_scraper.py search "python" --count 20             搜索推文
  python3 x_scraper.py replies 1234567890 --count 30          获取推文回复
  python3 x_scraper.py report elonmusk --since 2025-01-01 --replies 20 --depth 1  一站式报告
        """,
    )

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

    subparsers = parser.add_subparsers(
        dest="mode",
        title="子命令",
        description="选择要执行的抓取模式",
        help="可用的抓取模式",
    )

    # ---- tweet ----
    tweet_parser = subparsers.add_parser("tweet", help="根据推文 ID 获取单条推文详情")
    tweet_parser.add_argument("tweet_id", help="推文 ID")
    tweet_parser.add_argument("-o", "--output", help="输出文件路径")

    # ---- timeline ----
    timeline_parser = subparsers.add_parser("timeline", help="获取指定用户的最新推文")
    timeline_parser.add_argument("screen_name", help="用户 screen name")
    timeline_parser.add_argument("--count", type=int, default=20, help="获取推文数量 (默认: 20)")
    timeline_parser.add_argument("--since", help="起始日期 YYYY-MM-DD")
    timeline_parser.add_argument("--until", help="截止日期 YYYY-MM-DD")
    timeline_parser.add_argument("-o", "--output", help="输出文件路径")

    # ---- search ----
    search_parser = subparsers.add_parser("search", help="根据关键词搜索推文")
    search_parser.add_argument("query", help="搜索关键词")
    search_parser.add_argument("--count", type=int, default=20, help="获取推文数量 (默认: 20)")
    search_parser.add_argument(
        "--product", choices=["Top", "Latest"], default="Latest",
        help="搜索类型 (默认: Latest)",
    )
    search_parser.add_argument("-o", "--output", help="输出文件路径")

    # ---- replies ----
    replies_parser = subparsers.add_parser("replies", help="获取指定推文的回复列表（含原帖）")
    replies_parser.add_argument("tweet_id", help="推文 ID")
    replies_parser.add_argument("--count", type=int, default=20, help="获取回复数量 (默认: 20)")
    replies_parser.add_argument("-o", "--output", help="输出文件路径")

    # ---- config ----
    config_parser = subparsers.add_parser("config", help="生成模板配置文件")
    config_parser.add_argument(
        "-o", "--output", default="config.json",
        help="配置文件输出路径 (默认: config.json)",
    )

    # ---- report ----
    report_parser = subparsers.add_parser("report", help="一站式报告：用户时间线 + 评论 + 子评论")
    report_parser.add_argument("screen_name", help="用户 screen name（@后面部分）")
    report_parser.add_argument("--since", required=True, help="起始日期 YYYY-MM-DD（必填）")
    report_parser.add_argument("--until", help="截止日期 YYYY-MM-DD（可选）")
    report_parser.add_argument("--replies", type=int, default=20, help="每条推文取多少一级评论 (默认: 20)")
    report_parser.add_argument("--depth", type=int, default=1,
                               help="子评论递归深度: 0=仅一级评论, 1=含一级子评论 (默认: 1)")
    report_parser.add_argument("-o", "--output", help="推文输出文件路径")

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

    config = get_config(args.config)
    scraper = SeleniumScraper(config)
    scraper.start(args)


if __name__ == "__main__":
    main()
