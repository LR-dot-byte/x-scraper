#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X (Twitter) 帖子爬虫工具
基于 twikit 库，支持获取推文详情、用户时间线、关键词搜索、评论回复。
输出 JSON 格式，包含原帖内容、评论、点赞数、转发数和引用数。

使用示例:
  python3 x_scraper.py tweet 1234567890
  python3 x_scraper.py timeline elonmusk --count 50
  python3 x_scraper.py search "python" --count 20
  python3 x_scraper.py replies 1234567890 --count 30
  python3 x_scraper.py config
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
import traceback
from collections import OrderedDict
from datetime import datetime, timezone


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


def format_datetime(dt):
    """将 twikit 返回的时间对象转换为 ISO 8601 字符串。"""
    if dt is None:
        return None
    try:
        if isinstance(dt, str):
            return dt
        return dt.isoformat()
    except Exception:
        return str(dt)


def print_banner():
    """打印程序横幅。"""
    print("=" * 50)
    print("  X (Twitter) 帖子爬虫工具")
    print("  基于 twikit 库")
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


# ============================================================
#  RateLimiter 类 - 统一请求限流控制器
# ============================================================

class RateLimiter:
    """统一请求限流器

    三层节奏控制：
    1. 请求级 — 每次 API 调用前强制等待固定间隔 + 随机抖动
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
        self._in_cooldown = False

    @property
    def request_count(self):
        return self._request_count

    async def wait(self, label="请求"):
        """每次网络请求前调用，自动计算并等待合适间隔"""
        if self._last_request > 0:
            elapsed = time.time() - self._last_request
            jitter = random.uniform(0, self.max_interval - self.min_interval)
            required = self.min_interval + jitter

            if elapsed < required:
                delay = required - elapsed
                print(f"  ⏳ [{label}] 等待 {delay:.1f}s "
                      f"(固定间隔={self.min_interval}s + 随机={jitter:.1f}s)")
                await asyncio.sleep(delay)

        self._last_request = time.time()
        self._request_count += 1

    async def batch_pause(self):
        """每批次请求后长暂停，模拟人类休息"""
        if self._request_count > 0 and self._request_count % self.batch_size == 0:
            print(f"  🛑 已完成 {self._request_count} 次请求，"
                  f"长暂停 {self.long_pause}s 模拟人类行为...")
            await asyncio.sleep(self.long_pause)

    async def cooldown(self):
        """触发平台限流后的强制冷却"""
        self._in_cooldown = True
        print(f"  🚫 触发限流保护，强制冷却 {self.cooldown_seconds}s...")
        await asyncio.sleep(self.cooldown_seconds)
        self._in_cooldown = False
        self._request_count = 0

    async def retry_with_backoff(self, coro_func, label="操作"):
        """带指数退避的重试执行，检测到限流自动冷却"""
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return await coro_func()
            except Exception as e:
                last_error = e
                msg = str(e).lower()

                if any(kw in msg for kw in ["rate limit", "too many", "429"]):
                    print(f"  ⚠ [{label}] 触发平台限流")
                    await self.cooldown()
                elif attempt < self.max_retries:
                    delay = 2 ** attempt  # 2, 4, 8
                    print(f"  ⚠ [{label}] 失败，{delay}s 后重试 "
                          f"({attempt}/{self.max_retries})")
                    await asyncio.sleep(delay)
                else:
                    raise

        raise last_error


# ============================================================
#  XScraper 类
# ============================================================

class XScraper:
    """X (Twitter) 帖子爬虫

    负责登录认证、数据抓取、格式转换和结果输出。
    """

    def __init__(self, config):
        self.config = config
        self.validate_config(config)

        # 输出目录
        self.output_dir = config.get("output", {}).get("directory", "x_output")
        if not os.path.isabs(self.output_dir):
            # 相对于脚本所在目录
            script_dir = os.path.dirname(os.path.realpath(__file__))
            self.output_dir = os.path.join(script_dir, self.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

        # 统一限流器
        self.rate_limiter = RateLimiter(config)

        # 收集追踪
        self.got_count = 0
        self.skipped_count = 0
        self.tweet_ids = set()  # 去重

        # twikit Client 延迟初始化
        self.client = None

    # ----- 配置校验 -----

    def validate_config(self, config):
        """校验配置文件必填字段，不合法则退出。"""
        if "auth" not in config:
            print("✗ 配置文件缺少 'auth' 字段")
            sys.exit(1)

    # ----- 认证 -----

    async def login(self):
        """登录 X 平台。优先使用 Cookie 文件，其次使用账号密码。"""
        from twikit import Client

        self.client = Client(language="en-US")
        auth = self.config.get("auth", {})

        # 优先尝试 Cookie 文件
        cookies_file = auth.get("cookies_file", "")
        if cookies_file and os.path.isfile(cookies_file):
            try:
                print(f"正在从 Cookie 文件加载: {cookies_file}")
                self.client.load_cookies(cookies_file)
                print("✓ Cookie 登录成功")
                # 测试登录是否有效
                await self.client.user_id()
                return
            except Exception as e:
                print(f"⚠ Cookie 登录失败: {e}")
                print("  尝试使用账号密码登录...")

        # 回退到账号密码登录
        username = auth.get("username", "")
        email = auth.get("email", "")
        password = auth.get("password", "")

        if not username or not password:
            print("✗ 认证信息不足，请配置以下任一方式：")
            print("  1) cookies_file: 浏览器导出的 Cookie JSON 文件（推荐）")
            print("  2) username + email + password: X 账号密码")
            print()
            print("  获取 Cookie 的方法：")
            print("  - 在浏览器中登录 x.com")
            print("  - 打开开发者工具 → Application → Cookies")
            print("  - 导出为 JSON 格式，保存为 x_cookies.json")
            sys.exit(1)

        try:
            print(f"正在登录账号: {username}")
            await self.client.login(
                auth_info_1=username,
                auth_info_2=email,
                password=password,
            )
            print("✓ 账号密码登录成功")

            # 登录成功后保存 Cookie 以便下次使用
            if cookies_file:
                self.client.save_cookies(cookies_file)
                print(f"✓ Cookie 已保存到: {cookies_file}")

        except Exception as e:
            print(f"✗ 登录失败: {e}")
            print("  请检查账号、邮箱和密码是否正确")
            traceback.print_exc()
            sys.exit(1)

    # ----- 数据转换 -----

    def _convert_user_to_dict(self, user):
        """将 twikit User 对象转换为有序字典。"""
        if user is None:
            return None

        return OrderedDict([
            ("id", safe_get(user, "id")),
            ("screen_name", safe_get(user, "screen_name")),
            ("name", safe_get(user, "name")),
            ("description", safe_get(user, "description")),
            ("followers_count", safe_get(user, "followers_count")),
            ("friends_count", safe_get(user, "friends_count")),
            ("statuses_count", safe_get(user, "statuses_count")),
            ("profile_image_url", safe_get(user, "profile_image_url")),
            ("verified", safe_get(user, "verified")),
            ("location", safe_get(user, "location")),
        ])

    def _convert_media_to_list(self, media_list):
        """将 twikit Media 对象列表转换为字典列表。"""
        if not media_list:
            return []

        result = []
        for m in media_list:
            media_type = type(m).__name__ if m else "Unknown"
            item = OrderedDict([
                ("type", media_type),
            ])
            # 尝试获取常见属性
            for attr in ("url", "media_url_https", "expanded_url",
                         "display_url", "preview_url"):
                val = safe_get(m, attr)
                if val:
                    item["url"] = val
                    break
            # 视频特有属性
            duration = safe_get(m, "duration")
            if duration:
                item["duration_ms"] = duration
            result.append(item)
        return result

    def _convert_tweet_to_dict(self, tweet, include_quoted=True):
        """将 twikit Tweet 对象转换为有序字典。

        Args:
            tweet: twikit Tweet 对象
            include_quoted: 是否递归转换引用/转发的推文
        """
        if tweet is None:
            return None

        tweet_id = str(safe_get(tweet, "id", ""))

        # 基础字段
        result = OrderedDict()
        result["id"] = tweet_id
        result["text"] = safe_get(tweet, "full_text") or safe_get(tweet, "text", "")
        result["created_at"] = format_datetime(safe_get(tweet, "created_at"))
        result["lang"] = safe_get(tweet, "lang", "")

        # 回复 / 引用标记
        in_reply_to = safe_get(tweet, "in_reply_to")
        result["is_reply"] = in_reply_to is not None and in_reply_to != ""
        result["in_reply_to"] = in_reply_to

        is_quote = safe_get(tweet, "is_quote_status")
        result["is_quote_status"] = is_quote if is_quote is not None else False

        # 作者信息
        user = safe_get(tweet, "user")
        result["author"] = self._convert_user_to_dict(user)

        # 互动数据
        result["metrics"] = OrderedDict([
            ("favorite_count", safe_get(tweet, "favorite_count", 0)),
            ("retweet_count", safe_get(tweet, "retweet_count", 0)),
            ("reply_count", safe_get(tweet, "reply_count", 0)),
            ("quote_count", safe_get(tweet, "quote_count", 0)),
            ("view_count", safe_get(tweet, "view_count", 0)),
            ("bookmark_count", safe_get(tweet, "bookmark_count", 0)),
        ])

        # 话题标签
        hashtags = safe_get(tweet, "hashtags", [])
        result["hashtags"] = [safe_get(h, "text", str(h)) for h in (hashtags or [])]

        # 链接
        urls = safe_get(tweet, "urls", [])
        result["urls"] = [safe_get(u, "expanded_url") or safe_get(u, "url", str(u))
                          for u in (urls or [])]

        # 媒体
        media = safe_get(tweet, "media", [])
        result["media"] = self._convert_media_to_list(media)

        # 引用推文（递归）
        if include_quoted:
            quoted = safe_get(tweet, "quote")
            if quoted:
                result["quoted_tweet"] = self._convert_tweet_to_dict(
                    quoted, include_quoted=False
                )

            retweeted = safe_get(tweet, "retweeted_tweet")
            if retweeted:
                result["retweeted_tweet"] = self._convert_tweet_to_dict(
                    retweeted, include_quoted=False
                )

        # 文章来源标识
        result["source"] = safe_get(tweet, "source", "")

        return result

    # ----- 数据抓取 -----

    async def fetch_tweet(self, tweet_id, include_replies=False):
        """获取单条推文详情。

        Args:
            tweet_id: 推文 ID
            include_replies: 是否同时获取回复列表

        Returns:
            推文字典（包含 replies 列表，如果 include_replies=True）
        """
        async def _get():
            return await self.client.get_tweet_by_id(tweet_id)

        print(f"正在获取推文 {tweet_id} ...")
        await self.rate_limiter.wait(label=f"获取推文 {tweet_id}")
        tweet = await self.rate_limiter.retry_with_backoff(
            _get, label=f"获取推文 {tweet_id}"
        )

        result = self._convert_tweet_to_dict(tweet)
        print(f"  ✓ 获取成功: @{result['author']['screen_name']}")
        print(f"    内容: {result['text'][:80]}..."
              if len(result['text']) > 80 else f"    内容: {result['text']}")
        print(f"    点赞: {result['metrics']['favorite_count']}  "
              f"转发: {result['metrics']['retweet_count']}  "
              f"回复: {result['metrics']['reply_count']}  "
              f"引用: {result['metrics']['quote_count']}")

        self.got_count += 1

        # 获取回复
        if include_replies:
            replies = await self._fetch_replies_for_tweet(tweet)
            result["replies"] = replies

        return result

    async def _fetch_replies_for_tweet(self, tweet):
        """获取某条推文的回复列表。"""
        replies = []
        try:
            reply_result = safe_get(tweet, "replies")
            if reply_result is None:
                return replies

            page_count = 0
            while reply_result is not None:
                page_count += 1
                for reply in (reply_result or []):
                    d = self._convert_tweet_to_dict(reply)
                    if d and d["id"] not in self.tweet_ids:
                        self.tweet_ids.add(d["id"])
                        replies.append(d)

                # 获取下一页
                try:
                    await self.rate_limiter.wait(label=f"回复翻页{page_count}")
                    reply_result = await reply_result.next()
                    await self.rate_limiter.batch_pause()
                except Exception:
                    break

        except Exception as e:
            print(f"  ⚠ 获取回复时出错: {e}")
            traceback.print_exc()

        if replies:
            print(f"  ✓ 获取到 {len(replies)} 条回复")
        return replies

    async def _paginate(self, result, count, label="推文"):
        """通用的游标分页逻辑。

        Args:
            result: twikit Result 对象
            count: 目标获取数量
            label: 显示标签

        Returns:
            推文字典列表
        """
        tweets = []
        page_count = 0

        while result is not None and len(tweets) < count:
            page_count += 1
            page_items = list(result) if result else []

            if not page_items:
                break

            for tweet in page_items:
                d = self._convert_tweet_to_dict(tweet)
                if d and d["id"] not in self.tweet_ids:
                    self.tweet_ids.add(d["id"])
                    tweets.append(d)
                    if len(tweets) >= count:
                        break

            if len(tweets) >= count:
                break

            print(f"  已获取 {len(tweets)}/{count} 条{label} (第 {page_count} 页)")

            # 获取下一页
            try:
                await self.rate_limiter.wait(label=f"{label}翻页{page_count}")
                result = await result.next()
                await self.rate_limiter.batch_pause()
            except Exception as e:
                print(f"  ⚠ 翻页时出错: {e}")
                break

        return tweets

    async def fetch_user_timeline(self, screen_name, count=20):
        """获取指定用户的最新推文。

        Args:
            screen_name: 用户 screen name（@后面的部分）
            count: 获取数量
        """
        # 先获取用户信息
        async def _get_user():
            return await self.client.get_user_by_screen_name(screen_name)

        print(f"正在查找用户 @{screen_name} ...")
        await self.rate_limiter.wait(label=f"查找用户")
        try:
            user = await self.rate_limiter.retry_with_backoff(
                _get_user, label=f"查找用户 @{screen_name}"
            )
        except Exception:
            print(f"✗ 用户 @{screen_name} 不存在或无法访问")
            return []

        user_dict = self._convert_user_to_dict(user)
        print(f"  ✓ 找到用户: {user_dict['name']} (@{user_dict['screen_name']})")
        print(f"    关注者: {user_dict['followers_count']}  "
              f"发帖数: {user_dict['statuses_count']}")

        # 获取推文
        async def _get_tweets():
            return await self.client.get_user_tweets(
                user.id, "Tweets", count=min(count, 40)
            )

        print(f"正在获取 @{screen_name} 的推文 (目标 {count} 条)...")
        await self.rate_limiter.wait(label=f"获取用户推文")
        try:
            result = await self.rate_limiter.retry_with_backoff(
                _get_tweets, label=f"获取 @{screen_name} 推文"
            )
        except Exception as e:
            print(f"✗ 获取推文失败: {e}")
            traceback.print_exc()
            return []

        tweets = await self._paginate(result, count, label="推文")

        self.got_count += len(tweets)
        return tweets

    async def fetch_search_tweets(self, query, count=20, product="Latest"):
        """根据关键词搜索推文。

        Args:
            query: 搜索关键词
            count: 获取数量
            product: 搜索类型 ("Latest" / "Top" / "Media")
        """
        async def _search():
            return await self.client.search_tweet(
                query, product, count=min(count, 20)
            )

        print(f"正在搜索: \"{query}\" (类型: {product}, 目标: {count} 条)...")
        await self.rate_limiter.wait(label=f"搜索")
        try:
            result = await self.rate_limiter.retry_with_backoff(
                _search, label=f"搜索 \"{query}\""
            )
        except Exception as e:
            print(f"✗ 搜索失败: {e}")
            traceback.print_exc()
            return []

        tweets = await self._paginate(result, count, label="推文")

        self.got_count += len(tweets)
        return tweets

    async def fetch_tweet_replies(self, tweet_id, count=20):
        """获取指定推文的回复列表。

        Args:
            tweet_id: 推文 ID
            count: 获取数量
        """
        async def _get():
            return await self.client.get_tweet_by_id(tweet_id)

        print(f"正在获取推文 {tweet_id} 及其回复...")
        await self.rate_limiter.wait(label=f"获取推文 {tweet_id}")
        tweet = await self.rate_limiter.retry_with_backoff(
            _get, label=f"获取推文 {tweet_id}"
        )

        # 先添加原推文
        original = self._convert_tweet_to_dict(tweet)
        self.tweet_ids.add(original["id"])
        original["is_original"] = True

        # 获取回复
        replies = []
        try:
            reply_result = safe_get(tweet, "replies")
            if reply_result is not None:
                replies = await self._paginate(
                    reply_result, count, label="回复"
                )
                for r in replies:
                    r["is_original"] = False
        except Exception as e:
            print(f"  ⚠ 获取回复时出错: {e}")
            traceback.print_exc()

        # 合并结果：原帖 + 回复
        all_tweets = [original] + replies
        self.got_count += len(all_tweets)

        print(f"  ✓ 原帖 + {len(replies)} 条回复")

        return all_tweets

    # ----- 输出 -----

    def export_json(self, data, output_path, meta=None):
        """将数据导出为 JSON 文件。

        Args:
            data: 推文列表或单个推文字典
            output_path: 输出文件路径
            meta: 元数据字典
        """
        if meta is None:
            meta = {}

        meta.update({
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "x_scraper",
            "total_count": len(data) if isinstance(data, list) else 1,
        })

        output = OrderedDict([
            ("meta", meta),
            ("tweets", data),
        ])

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"\n✓ 结果已保存到: {output_path}")

    def _make_output_path(self, query, suffix=""):
        """生成输出文件路径。"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 清理文件名中的非法字符
        safe_query = "".join(
            c for c in str(query) if c.isalnum() or c in "_- "
        )[:50].strip().replace(" ", "_")
        if suffix:
            safe_query = f"{safe_query}_{suffix}"
        filename = f"{safe_query}_{ts}.json"
        return os.path.join(self.output_dir, filename)

    # ----- 调度入口 -----

    async def start(self, cli_args):
        """根据 CLI 参数调度抓取任务。"""
        await self.login()

        mode = cli_args.mode
        data = []
        output_path = None
        query = ""

        try:
            if mode == "tweet":
                tweet_id = cli_args.tweet_id
                query = tweet_id
                include_replies = cli_args.replies
                result = await self.fetch_tweet(
                    tweet_id, include_replies=include_replies
                )
                data = [result]

            elif mode == "timeline":
                screen_name = cli_args.screen_name
                count = cli_args.count
                query = screen_name
                data = await self.fetch_user_timeline(screen_name, count)

            elif mode == "search":
                query = cli_args.query
                count = cli_args.count
                product = cli_args.product
                data = await self.fetch_search_tweets(query, count, product)

            elif mode == "replies":
                tweet_id = cli_args.tweet_id
                count = cli_args.count
                query = tweet_id
                data = await self.fetch_tweet_replies(tweet_id, count)

        except KeyboardInterrupt:
            print("\n⚠ 用户中断操作")
            if data:
                print(f"  已获取 {len(data)} 条数据，正在保存...")
            else:
                sys.exit(0)

        # 输出
        if output_path is None:
            output_path = cli_args.output
        if output_path is None:
            output_path = self._make_output_path(query, mode)

        self.export_json(data, output_path, meta={
            "mode": mode,
            "query": query,
            "count_requested": getattr(cli_args, "count", 1) if hasattr(cli_args, "count") else 1,
            "count_actual": len(data) if isinstance(data, list) else 1,
        })

        print_summary(
            mode=mode,
            query=query,
            requested=getattr(cli_args, "count", 1) if hasattr(cli_args, "count") else 1,
            actual=len(data) if isinstance(data, list) else 1,
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
            "username": "",
            "email": "",
            "password": "",
            "cookies_file": "x_cookies.json",
        },
        "output": {
            "directory": "x_output",
            "include_replies": True,
            "include_quoted_tweets": True,
        },
        "rate_limit": {
            "min_interval_seconds": 8,
            "max_interval_seconds": 15,
            "long_pause_seconds": 90,
            "pages_per_long_pause": 10,
            "cooldown_seconds": 300,
            "max_retries": 3,
        },
        "filter": 1,
        "since_date": "",
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
    print("  1. 编辑 config.json 配置认证信息")
    print("  2. 推荐方式（Cookie 认证，无需暴露密码）：")
    print("     - 在浏览器中登录 x.com")
    print("     - 打开开发者工具 → Application → Cookies")
    print("     - 导出所有 Cookies 保存为 x_cookies.json")
    print("  3. 或者在 config.json 中填写 username + email + password")
    print()
    print("然后运行: python3 x_scraper.py tweet <推文ID>")


def main():
    parser = argparse.ArgumentParser(
        description="X (Twitter) 帖子爬虫工具 - 基于 twikit 库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python3 x_scraper.py config                       生成配置文件
  python3 x_scraper.py tweet 1234567890             获取单条推文
  python3 x_scraper.py tweet 1234567890 --replies   获取推文及回复
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
    tweet_parser = subparsers.add_parser(
        "tweet",
        help="根据推文 ID 获取单条推文详情",
    )
    tweet_parser.add_argument(
        "tweet_id",
        help="推文 ID（数字字符串，从 URL 中获取）",
    )
    tweet_parser.add_argument(
        "--replies",
        action="store_true",
        help="同时获取该推文的回复/评论",
    )
    tweet_parser.add_argument(
        "-o", "--output",
        help="输出文件路径（默认自动生成）",
    )

    # ---- timeline 子命令 ----
    timeline_parser = subparsers.add_parser(
        "timeline",
        help="获取指定用户的最新推文",
    )
    timeline_parser.add_argument(
        "screen_name",
        help="用户 screen name（@后面的部分，如 elonmusk）",
    )
    timeline_parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="获取推文数量 (默认: 20)",
    )
    timeline_parser.add_argument(
        "-o", "--output",
        help="输出文件路径（默认自动生成）",
    )

    # ---- search 子命令 ----
    search_parser = subparsers.add_parser(
        "search",
        help="根据关键词搜索推文",
    )
    search_parser.add_argument(
        "query",
        help="搜索关键词",
    )
    search_parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="获取推文数量 (默认: 20)",
    )
    search_parser.add_argument(
        "--product",
        choices=["Top", "Latest", "Media"],
        default="Latest",
        help="搜索类型 (默认: Latest)",
    )
    search_parser.add_argument(
        "-o", "--output",
        help="输出文件路径（默认自动生成）",
    )

    # ---- replies 子命令 ----
    replies_parser = subparsers.add_parser(
        "replies",
        help="获取指定推文的回复列表（含原帖）",
    )
    replies_parser.add_argument(
        "tweet_id",
        help="推文 ID",
    )
    replies_parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="获取回复数量 (默认: 20)",
    )
    replies_parser.add_argument(
        "-o", "--output",
        help="输出文件路径（默认自动生成）",
    )

    # ---- config 子命令 ----
    config_parser = subparsers.add_parser(
        "config",
        help="生成模板配置文件",
    )
    config_parser.add_argument(
        "-o", "--output",
        default="config.json",
        help="配置文件输出路径 (默认: config.json)",
    )

    # 解析
    args = parser.parse_args()

    # 没有子命令时打印帮助
    if not args.mode:
        parser.print_help()
        print("\n✗ 请指定一个子命令")
        sys.exit(1)

    # config 子命令不需要加载配置和登录
    if args.mode == "config":
        print_banner()
        generate_config(args.output)
        return

    # 检查 twikit 是否已安装
    try:
        import twikit  # noqa: F401
    except ImportError:
        print("✗ 未安装 twikit 库")
        print("  请运行: pip install twikit")
        print("  或: pip install -r requirements.txt")
        sys.exit(1)

    print_banner()

    # 加载配置
    config = get_config(args.config)

    # 创建爬虫实例并执行
    scraper = XScraper(config)

    try:
        asyncio.run(scraper.start(args))
    except KeyboardInterrupt:
        print("\n⚠ 用户中断操作")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ 程序异常: {e}")
        if args.verbose:
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
