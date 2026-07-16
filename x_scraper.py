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
import unicodedata
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus, urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    import undetected_chromedriver as uc
    HAS_UC = True
except ImportError:
    HAS_UC = False


# ============================================================
#  新疆相关关键词（用于过滤帖子）
# ============================================================
XINJIANG_DIRECT_KEYWORDS = [
    # 地名、地区别称和新疆专属法案：命中即可直接保留。
    "新疆", "东突", "东突厥", "Xinjiang", "XUAR",
    "East Turkestan", "East Turkistan", "UFLPA",
]

UYGHUR_IDENTITY_KEYWORDS = [
    # 仅出现族群名称还不够，必须同时具备中国语境和事件语境。
    "维吾尔", "Uyghur", "Uyghurs", "Uighur", "Uighurs",
    "Uygur", "Uygurs", "Uigur", "Uiguren", "ウイグル", "อุยกูร์",
]

CHINA_CONTEXT_KEYWORDS = [
    "中国", "中國", "中共", "北京", "China", "Chinese", "CCP", "PRC",
    "Beijing", "Chinese government", "Chinese authorities",
    "Chinese Communist Party",
]

UYGHUR_EVENT_KEYWORDS = [
    "拘留", "关押", "监禁", "逮捕", "判刑", "失踪", "集中营", "再教育营",
    "强迫劳动", "人权", "镇压", "迫害", "遣返", "引渡", "制裁", "释放",
    "detain", "detained", "detention", "interned", "internment",
    "imprison", "imprisoned", "prison", "arrest", "arrested", "sentence",
    "sentenced", "disappear", "disappeared", "camp", "re-education",
    "forced labor", "forced labour", "genocide", "human rights",
    "persecution", "repression", "surveillance", "deport", "deported",
    "deportation", "repatriation", "extradition", "sanction", "sanctions",
    "release", "released", "asylum", "activist", "political prisoner",
]

# 对应 X 高级搜索中的 “Any of these words”。
DEFAULT_ADVANCED_SEARCH_WORDS = (
    "Xinjiang", "维吾尔", "新疆", "Uyghur", "Uighur", "Uyghurs", "Uighurs",
    "Uiguren", "East Turkistan", "East Turkestan",
)
DEFAULT_ARCHIVE_SINCE = "2024-01-01"
DEFAULT_ARCHIVE_UNTIL = "2025-12-31"

XINJIANG_CONTEXT_KEYWORDS = [
    # 这些词单独出现不足以证明与新疆相关，只用于辅助分类/调试
    "genocide", "forced labor", "forced labour",
    "atrocity", "crimes against humanity",
    "concentration camp", "re-education camp",
    "persecution", "oppression", "repression",
    "deportation", "repatriation", "extradition",
    "inhumane detention",
    "Magnitsky", "CECC",
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
        # 使相对路径始终相对于 config.json，而不是当前工作目录。
        config["_config_dir"] = os.path.dirname(os.path.realpath(config_path))
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


def _contains_keyword(text, keyword):
    """匹配关键词。英文/数字词使用词边界，避免在更长单词中误命中。"""
    escaped = re.escape(unicodedata.normalize("NFKC", keyword).casefold())
    if re.search(r"[a-z0-9]", keyword, flags=re.I):
        return re.search(rf"(?<![a-z0-9_]){escaped}(?![a-z0-9_])", text) is not None
    return escaped in text


def matches_xinjiang(text):
    """严格审核涉疆相关性。

    新疆地名/地区别称直接通过；仅出现维吾尔族群名称时，必须同时出现
    中国语境和具体事件语境，避免把饮食、音乐、语言等一般内容误收录。
    """
    if matches_any_words(text, XINJIANG_DIRECT_KEYWORDS):
        return True
    return (
        matches_any_words(text, UYGHUR_IDENTITY_KEYWORDS)
        and matches_any_words(text, CHINA_CONTEXT_KEYWORDS)
        and matches_any_words(text, UYGHUR_EVENT_KEYWORDS)
    )


def matches_any_words(text, words):
    """检查文本是否命中给定列表中的任意关键词。"""
    if not text:
        return False
    normalized = unicodedata.normalize("NFKC", str(text)).casefold()
    return any(_contains_keyword(normalized, kw) for kw in words)


def sanitize_csv_value(value):
    """防止外部文本被 Excel/LibreOffice 解释为公式。"""
    if not isinstance(value, str):
        return value
    value = value.replace("\x00", "")
    if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + value
    return value


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
        self.min_interval = cfg.get("min_interval_seconds", 3)
        self.max_interval = cfg.get("max_interval_seconds", 6)
        self.long_pause = cfg.get("long_pause_seconds", 60)
        self.batch_size = cfg.get("pages_per_long_pause", 20)
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
        self.scroll_pause = max(0.3, min(float(self.scroll_pause), 5.0))

        # Xinjiang 关键词过滤
        filter_cfg = config.get("filter", {})
        self.filter_xinjiang = filter_cfg.get("xinjiang_only", True)
        self.strict_xinjiang_audit = filter_cfg.get("strict_china_context", True)
        advanced_cfg = config.get("advanced_search", {})
        self.advanced_search_enabled = advanced_cfg.get("enabled", True)
        self.advanced_search_words = advanced_cfg.get(
            "any_words", list(DEFAULT_ADVANCED_SEARCH_WORDS)
        )
        self.advanced_search_since = advanced_cfg.get("since", DEFAULT_ARCHIVE_SINCE)
        self.advanced_search_until = advanced_cfg.get("until", DEFAULT_ARCHIVE_UNTIL)

        # 评论抓取：仅对页面显示有回复的帖子进入详情页，实际可见评论另存目录。
        comments_cfg = config.get("comments", {})
        self.auto_fetch_comments = comments_cfg.get("enabled", True)
        self.max_comments_per_post = max(
            1, min(int(comments_cfg.get("max_per_post", 1000)), 1000)
        )
        self.max_comment_depth = max(
            0, min(int(comments_cfg.get("max_depth", 2)), 3)
        )
        comments_directory = str(comments_cfg.get("directory", "comments")).strip()
        if not comments_directory:
            comments_directory = "comments"
        if os.path.isabs(comments_directory):
            self.comments_dir = comments_directory
        else:
            self.comments_dir = os.path.join(self.output_dir, comments_directory)
        os.makedirs(self.comments_dir, exist_ok=True)

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

        rate_cfg = config.get("rate_limit", {})
        min_interval = rate_cfg.get("min_interval_seconds", 2)
        max_interval = rate_cfg.get("max_interval_seconds", 5)
        if min_interval < 0 or max_interval < min_interval:
            raise ValueError("rate_limit 配置无效：需要 0 <= min_interval <= max_interval")

    @staticmethod
    def _validate_tweet_id(tweet_id):
        value = str(tweet_id).strip()
        if not re.fullmatch(r"\d{5,25}", value):
            raise ValueError(f"无效的推文 ID: {tweet_id!r}")
        return value

    @staticmethod
    def _validate_screen_name(screen_name):
        value = str(screen_name).strip().lstrip("@")
        if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", value):
            raise ValueError(f"无效的 X 用户名: {screen_name!r}")
        return value

    @staticmethod
    def _validate_date(value, name):
        if not value:
            return None
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} 必须是 YYYY-MM-DD 格式") from exc
        return value

    @staticmethod
    def _normalize_any_words(any_words):
        """校验并规范化高级搜索的 “Any of these words” 列表。"""
        if any_words is None:
            any_words = DEFAULT_ADVANCED_SEARCH_WORDS
        if isinstance(any_words, str):
            any_words = any_words.split()

        normalized = []
        seen = set()
        for raw_word in any_words:
            word = unicodedata.normalize("NFKC", str(raw_word)).strip()
            if not word:
                continue
            if len(word) > 80 or any(ch in word for ch in ('"', "\n", "\r")):
                raise ValueError(f"高级搜索关键词无效: {raw_word!r}")
            key = word.casefold()
            if key not in seen:
                normalized.append(word)
                seen.add(key)

        if not normalized:
            raise ValueError("高级搜索至少需要一个关键词")
        if len(normalized) > 20:
            raise ValueError("高级搜索关键词不能超过 20 个")
        return normalized

    @classmethod
    def build_account_advanced_query(cls, screen_name, any_words=None,
                                     since_date=DEFAULT_ARCHIVE_SINCE,
                                     until_date=DEFAULT_ARCHIVE_UNTIL):
        """构造 X 高级搜索查询；until 输入按用户习惯视为包含当日。"""
        screen_name = cls._validate_screen_name(screen_name)
        since_date = cls._validate_date(since_date, "--since")
        until_date = cls._validate_date(until_date, "--until")
        if not since_date or not until_date:
            raise ValueError("账号高级搜索必须同时指定 --since 和 --until")
        if since_date > until_date:
            raise ValueError("--since 不能晚于 --until")

        words = cls._normalize_any_words(any_words)
        quoted_words = " OR ".join(f'"{word}"' for word in words)
        # X 的 until: 操作符按次日零点截断。对用户暴露的 --until 保持包含当日语义。
        until_exclusive = (
            datetime.strptime(until_date, "%Y-%m-%d").date() + timedelta(days=1)
        ).isoformat()
        return (
            f"({quoted_words}) from:{screen_name} "
            f"since:{since_date} until:{until_exclusive}"
        )

    @staticmethod
    def _cst_date_from_iso(iso_value):
        """将 X 的 UTC ISO 8601 时间转为中国标准时间日期。"""
        if not iso_value:
            return ""
        try:
            dt = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone(timedelta(hours=8))).date().isoformat()
        except (TypeError, ValueError):
            return ""

    # ----- WebDriver 初始化 -----

    def _init_driver(self):
        """创建并配置 Chrome WebDriver。优先使用 undetected-chromedriver。"""
        options = Options()

        selenium_cfg = self.config.get("selenium", {})
        profile_dir = selenium_cfg.get("profile_dir", "")
        use_profile = selenium_cfg.get("use_existing_profile", False)
        use_uc = selenium_cfg.get("use_undetected", False)

        if use_profile and profile_dir and os.path.isdir(profile_dir):
            options.add_argument(f"--user-data-dir={profile_dir}")
            print(f"✓ 使用已有 Chrome Profile: {profile_dir}")
        else:
            # 使用真实 Chrome UA；伪装 iPhone Safari 会造成 UA/渲染引擎特征矛盾，
            # 并且移动窄屏每屏加载的推文更少。
            options.add_argument("--window-size=1280,1000")

        if self.headless:
            options.add_argument("--headless=new")

        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-notifications")
        options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
        })

        # 如果用户明确开启，才使用 undetected-chromedriver。
        if use_uc and HAS_UC and not use_profile:
            print("✓ 使用 undetected-chromedriver（反检测模式）")
            self.driver = uc.Chrome(options=options)
        else:
            # Selenium 4 自带的 Selenium Manager 会复用本地驱动，避免每次调用
            # webdriver-manager 检查/下载驱动。
            self.driver = webdriver.Chrome(options=options)

        self.driver.set_page_load_timeout(self.page_timeout)
        # 只使用显式等待，避免隐式等待与 WebDriverWait 叠加。
        self.driver.implicitly_wait(0)

    def _wait_for_page_ready(self, timeout=12):
        """等待 DOM 可交互，替代固定时长 sleep。"""
        WebDriverWait(self.driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
        )

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
            self._wait_for_page_ready()

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
        if cookies_file and not os.path.isabs(cookies_file):
            cookies_file = os.path.join(self.config.get("_config_dir", os.getcwd()), cookies_file)
        if not cookies_file or not os.path.isfile(cookies_file):
            print("✗ Cookie 文件不存在或未配置")
            print(f"  请在 config.json 的 auth.cookies_file 中指定 Cookie 文件路径")
            self.driver.quit()
            sys.exit(1)

        # Cookie 等同于登录凭据，POSIX 系统上自动收紧为仅当前用户可读写。
        try:
            if os.name == "posix" and (os.stat(cookies_file).st_mode & 0o077):
                os.chmod(cookies_file, 0o600)
                print("  ✓ 已将 Cookie 文件权限收紧为 600")
        except OSError as e:
            print(f"  ⚠ 无法收紧 Cookie 文件权限: {e}")

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
        self._wait_for_page_ready()

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
        self._wait_for_page_ready()

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
                        since_date=None, until_date=None, keyword_filter=False,
                        expected_author=None, any_words_filter=None,
                        relevance_audit=False):
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
        if target_count <= 0:
            return []

        since_date = self._validate_date(since_date, "since_date")
        until_date = self._validate_date(until_date, "until_date")
        if since_date and until_date and since_date > until_date:
            raise ValueError("since_date 不能晚于 until_date")

        collected = []
        local_seen_ids = set()
        stale_count = 0
        # 时间线最上方可能混有置顶推文（顺序与实际发布时间无关），且置顶推文
        # 前面还可能夹着不匹配关键词而被跳过的正常推文，因此置顶徽章检测不完全
        # 可靠时，仅保护"第一条"不够。这里保守地保护前 N_PINNED_GUARD 条新推文，
        # 即使日期早于 since_date 也只跳过、不据此触发提前停止滚动。
        N_PINNED_GUARD = 3
        new_tweet_index = 0
        old_date_streak = 0

        for scroll_num in range(max_scrolls):
            batch = sorted(
                self._extract_tweets_batch(),
                key=lambda item: item.get("dom_index", 0) if item else 0,
            )
            new_seen_this_round = 0

            for data in batch:
                if len(collected) >= target_count:
                    break
                if not data or not data.get("id"):
                    continue
                if data["id"] in local_seen_ids:
                    continue

                # 标记为已扫描（无论是否匹配关键词），避免同一条推文
                # 在后续每次滚动中被反复重新扫描，导致"是否有新内容"的
                # 判断失真、提前误判为停滞而中断滚动
                local_seen_ids.add(data["id"])
                new_seen_this_round += 1
                is_guarded = new_tweet_index < N_PINNED_GUARD
                new_tweet_index += 1

                # 先做时间过滤。否则旧的不相关推文会在关键词处 continue，
                # 程序就无法及时感知已经翻过 since_date。
                created = data.get("created_at", "")
                created_date = self._cst_date_from_iso(created)
                if (since_date or until_date) and not created_date:
                    self.skipped_count += 1
                    continue
                if since_date and created_date < since_date:
                    if is_guarded:
                        # 疑似置顶推文导致的时间乱序，跳过但不中断滚动
                        continue
                    old_date_streak += 1
                    # 两条连续旧推文才早停，容忍一条算法插入/时间乱序。
                    if old_date_streak >= 2:
                        print(f"  连续推文时间早于 {since_date}，停止滚动")
                        self._stop_early = True
                        break
                    continue
                old_date_streak = 0
                if until_date and created_date > until_date:
                    continue

                if expected_author:
                    handle = data.get("author_handle", "")
                    if handle.casefold() != expected_author.casefold():
                        self.skipped_count += 1
                        continue

                if any_words_filter and not matches_any_words(
                    data.get("text", ""), any_words_filter
                ):
                    self.skipped_count += 1
                    continue

                # X 搜索只负责召回候选项；最终仍在本地执行严格相关性审核。
                if relevance_audit and not matches_xinjiang(data.get("text", "")):
                    self.skipped_count += 1
                    continue

                # 关键词在时间判断之后处理。
                if keyword_filter and not matches_xinjiang(data.get("text", "")):
                    self.skipped_count += 1
                    continue

                collected.append(data)
                self.tweet_ids.add(data["id"])

            current_unique = len(collected)

            if current_unique >= target_count:
                print(f"  已收集 {current_unique} 条推文 (目标 {target_count})")
                break

            if getattr(self, '_stop_early', False):
                self._stop_early = False
                break

            # 停滞判断依据"本轮是否扫描到任何新推文"（无论匹配与否），
            # 而不是只看匹配到的数量，避免因连续出现不相关推文而提前停止
            if new_seen_this_round == 0:
                stale_count += 1
                if stale_count >= 5:
                    print(f"  连续 {stale_count} 次无新推文，停止滚动")
                    break
            else:
                stale_count = 0
                print(f"  已收集 {current_unique} 条推文 (目标 {target_count}，"
                      f"本轮新扫描 {new_seen_this_round} 条)")

            # 滚动本身不是新的 HTTP 导航，不再套用 8~15 秒的导航限流。
            # 按视口小步滚动，避免直接跳到 document.body.scrollHeight
            # 跳过 X 虚拟列表中尚未进入 DOM 的推文。
            multiplier = 1.5 if stale_count >= 2 else 0.85
            self.driver.execute_script(
                "window.scrollBy(0, Math.max(600, window.innerHeight * arguments[0]));",
                multiplier,
            )
            time.sleep(self.scroll_pause)

        return collected

    # ----- 页面导航（带重试） -----

    def _navigate(self, url, label="页面", max_retries=None):
        """安全导航到指定 URL，带超时重试。"""
        if max_retries is None:
            max_retries = max(1, int(self.rate_limiter.max_retries))
        for attempt in range(max_retries):
            try:
                self.driver.get(url)
                source = (self.driver.page_source or "").casefold()
                limited = any(marker in source for marker in (
                    "rate limit exceeded", "too many requests", "请求过于频繁",
                ))
                if limited:
                    if attempt < max_retries - 1:
                        delay = min(60, 10 * (2 ** attempt))
                        print(f"  ⚠ [{label}] 检测到限流，{delay}s 后重试...")
                        time.sleep(delay)
                        continue
                    print(f"  ✗ [{label}] 平台仍在限流，放弃当前页面")
                    return False
                self.rate_limiter.batch_pause()
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
        tweet_id = self._validate_tweet_id(tweet_id)
        url = f"https://x.com/i/status/{tweet_id}"
        print(f"正在访问: {url}")

        self.rate_limiter.wait(label="获取推文")
        if not self._navigate(url, label="推文"):
            return []
        self._wait_for_page_ready()

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

        tweet_data = next((item for item in batch if item.get("id") == tweet_id), None)
        if not tweet_data:
            print(f"  ✗ 页面中未找到目标推文 ID {tweet_id}")
            return []
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
        screen_name = self._validate_screen_name(screen_name)
        since_date = self._validate_date(since_date, "--since")
        until_date = self._validate_date(until_date, "--until")
        if since_date and until_date and since_date > until_date:
            raise ValueError("--since 不能晚于 --until")
        if count <= 0:
            raise ValueError("--count 必须大于 0")
        print(f"正在访问用户主页: @{screen_name}")
        if since_date or until_date:
            print(f"时间段: {since_date or '不限'} ~ {until_date or '不限'}")
        if keyword_filter:
            print(f"关键词过滤: 新疆/Uyghur/Xinjiang")
        print(f"目标: {count} 条推文")

        if not self._load_profile_stats(screen_name):
            return []

        tweets = self._scroll_to_load(
            count, label=f"@{screen_name}",
            since_date=since_date, until_date=until_date,
            keyword_filter=keyword_filter,
            expected_author=screen_name,
        )

        self.got_count += len(tweets)
        print(f"  ✓ 实际获取 {len(tweets)} 条 @{screen_name} 的推文")
        if keyword_filter and self.skipped_count > 0:
            print(f"     (跳过 {self.skipped_count} 条不相关推文)")
        return tweets

    def _load_profile_stats(self, screen_name):
        """访问账号主页并在滚动前保存 Profile 统计。"""
        screen_name = self._validate_screen_name(screen_name)
        url = f"https://x.com/{screen_name}"
        self.rate_limiter.wait(label="访问主页")
        if not self._navigate(url, label="用户主页"):
            return False
        self._wait_for_page_ready()
        # Profile 统计位于页面顶部，滚动后会被 X 的虚拟 DOM 移除。
        self._last_profile_stats = self._get_profile_stats(screen_name)
        return True

    def fetch_account_advanced_search(
        self,
        screen_name,
        count=9999,
        since_date=DEFAULT_ARCHIVE_SINCE,
        until_date=DEFAULT_ARCHIVE_UNTIL,
        any_words=None,
        load_profile=True,
    ):
        """用 X 高级搜索抓取指定账号、日期范围和任一关键词命中的帖子。"""
        screen_name = self._validate_screen_name(screen_name)
        since_date = self._validate_date(since_date, "--since")
        until_date = self._validate_date(until_date, "--until")
        if count <= 0:
            raise ValueError("--count 必须大于 0")
        source_words = self.advanced_search_words if any_words is None else any_words
        words = self._normalize_any_words(source_words)
        query = self.build_account_advanced_query(
            screen_name,
            any_words=words,
            since_date=since_date,
            until_date=until_date,
        )

        print(f"正在使用 X 高级搜索抓取 @{screen_name}")
        print(f"Any of these words: {' / '.join(words)}")
        print(f"时间段（含首尾）: {since_date} ~ {until_date}")
        print(f"高级搜索查询: {query}")
        print(f"目标: {count} 条推文")

        if load_profile and not self._load_profile_stats(screen_name):
            self._last_profile_stats = ("", "")
            print("  ⚠ Profile 统计读取失败，继续执行高级搜索")

        encoded_query = quote_plus(query)
        url = f"https://x.com/search?q={encoded_query}&src=typed_query&f=live"
        self.rate_limiter.wait(label="账号高级搜索")
        if not self._navigate(url, label="账号高级搜索"):
            return []
        self._wait_for_page_ready()

        tweets = self._scroll_to_load(
            count,
            label=f"高级搜索@{screen_name}",
            since_date=since_date,
            until_date=until_date,
            expected_author=screen_name,
            any_words_filter=words,
            relevance_audit=getattr(self, "strict_xinjiang_audit", True),
        )
        self.got_count += len(tweets)
        print(f"  ✓ 高级搜索实际获取 {len(tweets)} 条 @{screen_name} 的相关推文")
        return tweets

    def fetch_search_tweets(self, query, count=20, product="Latest"):
        """根据关键词搜索推文。"""
        if count <= 0:
            raise ValueError("--count 必须大于 0")
        encoded_query = quote_plus(query)
        url = f"https://x.com/search?q={encoded_query}&f={'live' if product == 'Latest' else 'top'}"
        print(f"正在搜索: \"{query}\" (类型: {product}, 目标: {count} 条)")

        self.rate_limiter.wait(label="搜索")
        if not self._navigate(url, label="搜索"):
            return []
        self._wait_for_page_ready()

        tweets = self._scroll_to_load(count, label="搜索")
        self.got_count += len(tweets)
        print(f"  ✓ 实际获取 {len(tweets)} 条搜索结果")
        return tweets

    # ----- 评论 & 子评论抓取 -----

    @staticmethod
    def _is_direct_reply(candidate, parent_author):
        """只在页面明确标注候选帖回复了目标作者时认定归属。"""
        expected = str(parent_author or "").strip().lstrip("@").casefold()
        if not expected:
            return False
        reply_handles = {
            handle.strip().lstrip("@").casefold()
            for handle in candidate.get("reply_to_handles", "").split(",")
            if handle.strip()
        }
        return expected in reply_handles

    @staticmethod
    def _select_conversation_items(candidates, target_id, target_author, max_items=1000):
        """从帖子详情页中保留对话链前后文、直接回复和子回复。

        X 详情页中目标帖之前的帖子是对话前文，目标帖之后、
        “Discover more / 更多推文”边界之前的内容视为回复区。
        """
        target_id = str(target_id or "")
        ordered = [item for item in candidates if item and item.get("id")]
        target_index = next(
            (index for index, item in enumerate(ordered) if str(item.get("id")) == target_id),
            None,
        )
        if target_index is None:
            return []

        expected = str(target_author or "").strip().lstrip("@").casefold()
        selected = []
        for index, item in enumerate(ordered):
            if str(item.get("id")) == target_id or item.get("is_promoted"):
                continue
            if index > target_index and item.get("is_recommendation"):
                break
            if index < target_index and item.get("is_recommendation"):
                continue

            copy = dict(item)
            reply_handles = {
                handle.strip().lstrip("@").casefold()
                for handle in copy.get("reply_to_handles", "").split(",")
                if handle.strip()
            }
            if index < target_index:
                copy["thread_relation"] = "context"
            elif expected and expected in reply_handles:
                copy["thread_relation"] = "direct_reply"
            elif reply_handles:
                copy["thread_relation"] = "nested_reply"
            else:
                copy["thread_relation"] = "thread_item"
            selected.append(copy)
            if len(selected) >= max_items:
                break
        return selected

    def _fetch_comments_for_tweet(self, tweet_url, max_comments=20, max_depth=1,
                                  current_depth=0, _visited=None):
        """获取指定推文的所有评论及子评论（递归）。

        Args:
            tweet_url: 推文链接
            max_comments: 最多获取多少条一级评论
            max_depth: 子评论递归深度（0=仅一级评论, 1=含子评论, 默认1）

        Returns:
            list[dict]: 所有评论（含子评论），每条包含 parent_tweet_id, parent_author, depth 字段
        """
        if max_comments <= 0:
            return []
        if max_depth < 0:
            raise ValueError("max_depth 不能小于 0")

        parsed = urlparse(tweet_url)
        if parsed.hostname not in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
            raise ValueError(f"拒绝访问非 X 域名: {tweet_url!r}")
        id_match = re.search(r"/status/(\d{5,25})", parsed.path)
        if not id_match:
            raise ValueError(f"无效的推文链接: {tweet_url!r}")
        target_id = id_match.group(1)

        if _visited is None:
            _visited = set()
        if target_id in _visited:
            return []
        _visited.add(target_id)

        all_comments = []
        try:
            self.rate_limiter.wait(label="获取评论")
            if not self._navigate(tweet_url, label="推文详情"):
                return all_comments
            self._wait_for_page_ready()

            # 等待评论加载
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, self.TWEET_SELECTOR))
                )
            except Exception:
                return all_comments

            initial_batch = self._extract_tweets_batch()
            target_tweet = next((t for t in initial_batch if t.get("id") == target_id), None)
            if not target_tweet:
                print(f"  ⚠ 未找到目标推文 {target_id}，放弃评论归属")
                return all_comments
            parent_author = target_tweet.get("author_handle", "").casefold()
            if not parent_author:
                print(f"  ⚠ 无法确定目标推文作者，放弃评论归属")
                return all_comments

            # 多扫描一些候选项，保留目标帖的对话链前后文、
            # 直接回复及二、三级回复，并在推荐区标题处停止。
            candidate_target = max(max_comments * 3, max_comments + 5)
            candidates = self._scroll_to_load(
                candidate_target,
                label="评论",
                max_scrolls=min(80, max(20, max_comments * 2)),
            )

            conversation_items = self._select_conversation_items(
                candidates, target_id, parent_author, max_items=max_comments
            )
            for c in conversation_items:
                c["depth"] = current_depth
                c["parent_comment_id"] = target_id if current_depth > 0 else ""
                all_comments.append(c)

            print(f"    对话链过滤：保留 {len(conversation_items)} 条前后文/回复，排除推广和推荐区")

            # 递归获取子评论
            if current_depth < max_depth:
                direct_comments = [
                    item for item in all_comments
                    if item.get("thread_relation") != "context"
                ]
                for i, comment in enumerate(direct_comments):
                    if comment.get("reply_count", 0) > 0:
                        sub_url = comment.get("tweet_url", "")
                        if not sub_url:
                            continue
                        print(f"    [{i+1}/{len(direct_comments)}] 抓取子评论: "
                            f"@{comment['author_handle']} 的评论 (已有{comment['reply_count']}条回复)...")
                        sub_comments = self._fetch_comments_for_tweet(
                            sub_url,
                            max_comments=min(20, max_comments),
                            max_depth=max_depth,
                            current_depth=current_depth + 1,
                            _visited=_visited,
                        )
                        all_comments.extend(sub_comments)
                        print(f"      → 获取 {len(sub_comments)} 条子评论")

        except Exception as e:
            print(f"  ⚠ 获取评论时出错: {e}")

        return all_comments

    def fetch_comments_for_posts(self, posts, max_comments=None, max_depth=None):
        """进入有回复的帖子详情页，抓取实际可见评论并回填实际数量。"""
        if max_comments is None:
            max_comments = self.max_comments_per_post
        if max_depth is None:
            max_depth = self.max_comment_depth
        max_comments = max(1, min(int(max_comments), 1000))
        max_depth = max(0, min(int(max_depth), 3))

        all_comments = []
        seen_comment_ids = set()
        candidates = [post for post in posts if int(post.get("reply_count", 0) or 0) > 0]
        print(
            f"\n评论检查：{len(posts)} 条帖子中有 {len(candidates)} 条显示存在回复，"
            "将进入详情页核对实际可见评论"
        )

        for index, post in enumerate(posts, start=1):
            reported_count = int(post.get("reply_count", 0) or 0)
            post["actual_comment_count"] = 0
            if reported_count <= 0:
                continue

            tweet_url = post.get("tweet_url", "")
            if not tweet_url:
                print(f"  ⚠ [{index}/{len(posts)}] 帖子缺少详情链接，无法核对评论")
                continue

            print(
                f"  [{index}/{len(posts)}] 页面显示 {reported_count} 条回复，"
                f"核对帖子 {post.get('id', '')}"
            )
            comments = self._fetch_comments_for_tweet(
                tweet_url,
                max_comments=max_comments,
                max_depth=max_depth,
            )

            actual_for_post = []
            for comment in comments:
                comment_id = comment.get("id", "")
                if (not comment_id or comment_id == post.get("id", "")
                        or comment_id in seen_comment_ids):
                    continue
                seen_comment_ids.add(comment_id)
                comment["parent_tweet_id"] = post.get("id", "")
                comment["parent_tweet_author"] = post.get("author_handle", "")
                reply_targets = [
                    handle.strip().lstrip("@")
                    for handle in comment.get("reply_to_handles", "").split(",")
                    if handle.strip()
                ]
                comment["reply_target_handle"] = (
                    reply_targets[0] if reply_targets else post.get("author_handle", "")
                )
                actual_for_post.append(comment)

            post["actual_comment_count"] = len(actual_for_post)
            all_comments.extend(actual_for_post)
            print(
                f"    → 页面标示 {reported_count} 条，实际保留 "
                f"{len(actual_for_post)} 条对话链前后文/回复"
            )

        print(f"✓ 评论核对完成：共抓取 {len(all_comments)} 条唯一评论")
        return all_comments

    def fetch_report(self, screen_name, since_date, until_date=None,
                     replies_per_tweet=20, max_comment_depth=1,
                     use_advanced_search=True, any_words=None):
        """一站式报告。返回 (posts, comments, following, followers)。"""
        # 第一步：优先使用服务器端高级搜索缩小账号、关键词和日期范围。
        print(f"\n{'='*40}")
        if use_advanced_search:
            print(f"  第一步：高级搜索 @{screen_name} 的相关帖子")
        else:
            print(f"  第一步：扫描 @{screen_name} 的时间线（兼容模式）")
        print(f"{'='*40}")
        if use_advanced_search:
            posts = self.fetch_account_advanced_search(
                screen_name,
                count=9999,
                since_date=since_date,
                until_date=until_date,
                any_words=any_words,
            )
        else:
            posts = self.fetch_user_timeline(
                screen_name, count=9999,
                since_date=since_date,
                until_date=until_date,
                keyword_filter=True,
            )

        # 提取 Profile 统计数据
        following, followers = getattr(self, "_last_profile_stats", ("", ""))
        print(f"  Profile: Following={following}, Followers={followers}")

        if not posts:
            print("✗ 该时间段内无新疆相关推文")
            return [], [], following, followers

        print(f"\n✓ 第一步完成：获取 {len(posts)} 条新疆相关推文")

        # 第二步：仅对有回复的帖子进入详情页，抓取实际可见评论。
        print(f"\n{'='*40}")
        print(f"  第二步：抓取每条推文的评论 (一级{replies_per_tweet}条 + 子评论深度{max_comment_depth})")
        print(f"{'='*40}")

        all_comments = self.fetch_comments_for_posts(
            posts,
            max_comments=replies_per_tweet,
            max_depth=max_comment_depth,
        )

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
                "评论条数": d.get(
                    "actual_comment_count", d.get("reply_count", 0)
                ),
            })

        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows([
                {key: sanitize_csv_value(value) for key, value in row.items()}
                for row in rows
            ])

        print(f"\n✓ 帖子结果已保存到: {output_path}（{len(rows)} 条）")

    def export_comments_csv(self, data, output_path):
        """按研究表格的固定顺序导出对话链内容。"""
        fieldnames = ["序号", "account", "tweet_id", "link", "time", "text", "贴主ID"]

        rows = []
        for index, d in enumerate(data, start=1):
            post_owner = d.get("parent_tweet_author", "")
            rows.append({
                "序号": index,
                "account": d.get("author_name", ""),
                "tweet_id": self._ensure_at(d.get("author_handle", "")),
                "link": d.get("tweet_url", ""),
                "time": self._fmt_time_comments(d.get("created_at", "")),
                "text": d.get("text", ""),
                "贴主ID": self._ensure_at(post_owner),
            })

        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows([
                {key: sanitize_csv_value(value) for key, value in row.items()}
                for row in rows
            ])

        print(f"\n✓ 评论结果已保存到: {output_path}（{len(rows)} 条）")

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

    def _make_comments_output_path(self, query):
        """在独立 comments 目录生成评论文件路径。"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_query = "".join(
            c for c in str(query) if c.isalnum() or c in "_- "
        )[:50].strip().replace(" ", "_") or "comments"
        return os.path.join(self.comments_dir, f"{safe_query}_comments_{ts}.csv")

    # ----- 调度入口 -----

    def start(self, cli_args):
        """根据 CLI 参数调度抓取任务。"""
        self.login()

        mode = cli_args.mode
        data = []
        comments = []
        comment_output_path = None
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
                data = self.fetch_user_timeline(
                    screen_name, count, since, until,
                    keyword_filter=self.filter_xinjiang,
                )

            elif mode == "search":
                query = cli_args.query
                count = cli_args.count
                product = cli_args.product
                data = self.fetch_search_tweets(query, count, product)

            elif mode == "account-search":
                screen_name = cli_args.screen_name
                count = cli_args.count
                since = cli_args.since or self.advanced_search_since
                until = cli_args.until or self.advanced_search_until
                words = cli_args.any_words or self.advanced_search_words
                query = screen_name
                data = self.fetch_account_advanced_search(
                    screen_name,
                    count=count,
                    since_date=since,
                    until_date=until,
                    any_words=words,
                )

            elif mode == "replies":
                tweet_id = self._validate_tweet_id(cli_args.tweet_id)
                count = cli_args.count
                query = tweet_id
                url = f"https://x.com/i/status/{tweet_id}"
                original = self.fetch_tweet(tweet_id)
                replies = self._fetch_comments_for_tweet(
                    url, max_comments=count, max_depth=0
                )
                if original:
                    original[0]["is_original"] = True
                data = original + replies

            elif mode == "report":
                screen_name = cli_args.screen_name
                since_date = cli_args.since or self.advanced_search_since
                until_date = cli_args.until or self.advanced_search_until
                reply_count = cli_args.replies
                max_depth = getattr(cli_args, "depth", 1)
                requested_search_mode = getattr(cli_args, "advanced_search", None)
                use_advanced_search = (
                    self.advanced_search_enabled
                    if requested_search_mode is None
                    else requested_search_mode
                )
                words = cli_args.any_words or self.advanced_search_words
                query = screen_name

                posts, comments, following, followers = self.fetch_report(
                    screen_name,
                    since_date,
                    until_date,
                    reply_count,
                    max_depth,
                    use_advanced_search=use_advanced_search,
                    any_words=words,
                )

                # 输出帖子 CSV（列对齐 24-25年知情代理人涉疆数据.xlsx）
                post_path = getattr(cli_args, "output", None)
                if not post_path:
                    post_path = self._make_output_path(query, "posts")
                if posts:
                    self.export_posts_csv(posts, post_path, following, followers)

                # 评论始终放在独立 comments 目录；即使为 0 条也保留表头。
                comment_path = self._make_comments_output_path(query)
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

            # timeline/account-search 默认自动核对有回复帖子的实际评论。
            if mode in {"timeline", "account-search"} and data:
                requested_comments = getattr(cli_args, "comments", None)
                comments_enabled = (
                    self.auto_fetch_comments
                    if requested_comments is None
                    else requested_comments
                )
                if comments_enabled:
                    max_comments = (
                        getattr(cli_args, "max_comments", None)
                        or self.max_comments_per_post
                    )
                    comment_depth = (
                        getattr(cli_args, "comment_depth", None)
                        if getattr(cli_args, "comment_depth", None) is not None
                        else self.max_comment_depth
                    )
                    comments = self.fetch_comments_for_posts(
                        data,
                        max_comments=max_comments,
                        max_depth=comment_depth,
                    )
                    comment_output_path = self._make_comments_output_path(query)

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
            if mode in {"timeline", "account-search"}:
                following, followers = getattr(self, "_last_profile_stats", ("", ""))
                self.export_posts_csv(data, output_path, following, followers)
            else:
                self.export_posts_csv(data, output_path)

        if comment_output_path:
            self.export_comments_csv(comments, comment_output_path)

        displayed_output = output_path
        if comment_output_path:
            displayed_output = f"{output_path}\n{' '*12}+ {comment_output_path}"

        print_summary(
            mode=mode,
            query=query,
            requested=getattr(cli_args, "count", 1),
            actual=len(data),
            output_path=displayed_output,
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
            "min_interval_seconds": 3,
            "max_interval_seconds": 6,
            "long_pause_seconds": 60,
            "pages_per_long_pause": 20,
            "cooldown_seconds": 300,
            "max_retries": 3,
        },
        "selenium": {
            "headless": False,
            "page_load_timeout": 30,
            "scroll_pause_seconds": 1.2,
            "use_undetected": False,
        },
        "filter": {
            "xinjiang_only": True,
            "strict_china_context": True,
        },
        "advanced_search": {
            "enabled": True,
            "any_words": list(DEFAULT_ADVANCED_SEARCH_WORDS),
            "since": DEFAULT_ARCHIVE_SINCE,
            "until": DEFAULT_ARCHIVE_UNTIL,
        },
        "comments": {
            "enabled": True,
            "directory": "comments",
            "max_per_post": 1000,
            "max_depth": 2,
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
  python3 x_scraper.py account-search elonmusk                高级搜索账号的 2024-2025 涉疆帖子
  python3 x_scraper.py replies 1234567890 --count 30          获取推文回复
  python3 x_scraper.py report elonmusk --replies 20 --depth 1 高级搜索 + 评论报告
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
    timeline_parser.add_argument(
        "--comments", action=argparse.BooleanOptionalAction, default=None,
        help="是否自动进入有回复的帖子并抓取实际评论（默认由配置决定）",
    )
    timeline_parser.add_argument(
        "--max-comments", type=int, help="每条帖子最多抓取多少条可见评论"
    )
    timeline_parser.add_argument(
        "--comment-depth", type=int, choices=range(0, 4),
        help="评论递归深度：0=仅直接评论，1-3=包含子评论",
    )
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

    # ---- account-search ----
    account_search_parser = subparsers.add_parser(
        "account-search",
        help="使用 X 高级搜索抓取指定账号和日期范围内的任一关键词帖子",
    )
    account_search_parser.add_argument("screen_name", help="用户 screen name")
    account_search_parser.add_argument(
        "--count", type=int, default=9999, help="最多获取多少条帖子 (默认: 9999)"
    )
    account_search_parser.add_argument(
        "--since", help=f"起始日期 YYYY-MM-DD (默认: {DEFAULT_ARCHIVE_SINCE})"
    )
    account_search_parser.add_argument(
        "--until", help=f"截止日期 YYYY-MM-DD，包含当日 (默认: {DEFAULT_ARCHIVE_UNTIL})"
    )
    account_search_parser.add_argument(
        "--any-words",
        nargs="+",
        metavar="WORD",
        help='“Any of these words” 关键词列表（默认含 Uyghur/Uighur 与 East Turkistan 等变体）',
    )
    account_search_parser.add_argument(
        "--comments", action=argparse.BooleanOptionalAction, default=None,
        help="是否自动进入有回复的帖子并抓取实际评论（默认由配置决定）",
    )
    account_search_parser.add_argument(
        "--max-comments", type=int, help="每条帖子最多抓取多少条可见评论"
    )
    account_search_parser.add_argument(
        "--comment-depth", type=int, choices=range(0, 4),
        help="评论递归深度：0=仅直接评论，1-3=包含子评论",
    )
    account_search_parser.add_argument("-o", "--output", help="输出文件路径")

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
    report_parser = subparsers.add_parser(
        "report", help="一站式报告：账号高级搜索 + 评论 + 子评论"
    )
    report_parser.add_argument("screen_name", help="用户 screen name（@后面部分）")
    report_parser.add_argument(
        "--since", help=f"起始日期 YYYY-MM-DD (默认: {DEFAULT_ARCHIVE_SINCE})"
    )
    report_parser.add_argument(
        "--until", help=f"截止日期 YYYY-MM-DD，包含当日 (默认: {DEFAULT_ARCHIVE_UNTIL})"
    )
    report_parser.add_argument(
        "--any-words",
        nargs="+",
        metavar="WORD",
        help='高级搜索“Any of these words” (默认: Xinjiang 维吾尔 新疆 Uyghur)',
    )
    search_mode_group = report_parser.add_mutually_exclusive_group()
    search_mode_group.add_argument(
        "--advanced-search",
        dest="advanced_search",
        action="store_true",
        default=None,
        help="强制使用 X 高级搜索（默认由配置决定）",
    )
    search_mode_group.add_argument(
        "--timeline-scan",
        dest="advanced_search",
        action="store_false",
        help="禁用高级搜索，回退到主页时间线扫描",
    )
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
