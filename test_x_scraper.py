import unittest
import csv
import tempfile
from pathlib import Path

import x_scraper


class FakeDriver:
    def __init__(self):
        self.scroll_calls = []

    def execute_script(self, script, *args):
        self.scroll_calls.append((script, args))


class FakeShowMoreElement:
    def __init__(self, element_id, displayed=True):
        self.id = element_id
        self._displayed = displayed

    def is_displayed(self):
        return self._displayed


class FakeShowMoreDriver:
    def __init__(self, element_batches):
        self.element_batches = iter(element_batches)
        self.find_calls = []
        self.clicked_ids = []

    def find_elements(self, by, selector):
        self.find_calls.append((by, selector))
        return next(self.element_batches, [])

    def execute_script(self, script, element):
        self.clicked_ids.append(element.id)


class FilterTests(unittest.TestCase):
    def test_direct_xinjiang_keywords_match_without_more_context(self):
        self.assertTrue(x_scraper.matches_xinjiang("这是一则新疆相关消息"))
        self.assertTrue(x_scraper.matches_xinjiang("A short Xinjiang update"))
        self.assertTrue(x_scraper.matches_xinjiang("News from East Turkestan"))
        self.assertTrue(x_scraper.matches_xinjiang("UFLPA enforcement update"))

    def test_uyghur_mention_alone_is_not_enough(self):
        self.assertFalse(x_scraper.matches_xinjiang("Support for Uyghur families"))
        self.assertFalse(x_scraper.matches_xinjiang("Uyghur food and music festival"))

    def test_uyghur_requires_china_and_event_context(self):
        self.assertTrue(
            x_scraper.matches_xinjiang(
                "Chinese authorities detained a Uyghur activist and sent him to prison"
            )
        )
        self.assertFalse(x_scraper.matches_xinjiang("A Uyghur visitor travelled to China"))
        self.assertFalse(x_scraper.matches_xinjiang("A detained Uyghur activist spoke today"))

    def test_generic_context_words_do_not_match_alone(self):
        self.assertFalse(x_scraper.matches_xinjiang("oppression and deportation elsewhere"))
        self.assertFalse(x_scraper.matches_xinjiang("a generic Magnitsky sanctions update"))

    def test_english_keyword_uses_word_boundaries(self):
        self.assertFalse(x_scraper.matches_xinjiang("prefixuhrpsuffix"))

    def test_custom_any_words_filter(self):
        words = ["Xinjiang", "维吾尔", "新疆", "Uyghur"]
        self.assertTrue(x_scraper.matches_any_words("News about 新疆", words))
        self.assertFalse(x_scraper.matches_any_words("Unrelated regional news", words))


class AdvancedSearchTests(unittest.TestCase):
    def test_builds_account_date_and_any_words_query(self):
        query = x_scraper.SeleniumScraper.build_account_advanced_query(
            "@example",
            ["Xinjiang", "维吾尔", "新疆", "Uyghur"],
            "2024-01-01",
            "2025-12-31",
        )
        self.assertEqual(
            query,
            '("Xinjiang" OR "维吾尔" OR "新疆" OR "Uyghur") '
            "from:example since:2024-01-01 until:2026-01-01",
        )

    def test_until_date_is_inclusive(self):
        query = x_scraper.SeleniumScraper.build_account_advanced_query(
            "example", ["新疆"], "2025-01-01", "2025-01-01"
        )
        self.assertIn("until:2025-01-02", query)

    def test_normalizes_and_deduplicates_words(self):
        words = x_scraper.SeleniumScraper._normalize_any_words(
            [" Xinjiang ", "xinjiang", "新疆", ""]
        )
        self.assertEqual(words, ["Xinjiang", "新疆"])

    def test_rejects_empty_word_list(self):
        with self.assertRaises(ValueError):
            x_scraper.SeleniumScraper._normalize_any_words([])

    def test_account_search_navigates_to_latest_advanced_results(self):
        scraper = x_scraper.SeleniumScraper.__new__(x_scraper.SeleniumScraper)
        scraper.advanced_search_words = list(x_scraper.DEFAULT_ADVANCED_SEARCH_WORDS)
        scraper.got_count = 0
        scraper.rate_limiter = type("Limiter", (), {"wait": lambda self, label="": None})()
        visited = {}
        scraper._navigate = lambda url, label="": visited.update(url=url, label=label) or True
        scraper._wait_for_page_ready = lambda: None
        scraper._scroll_to_load = lambda count, **kwargs: visited.update(
            scroll_count=count, scroll_kwargs=kwargs
        ) or []

        result = scraper.fetch_account_advanced_search(
            "example",
            count=25,
            since_date="2024-01-01",
            until_date="2025-12-31",
            load_profile=False,
        )

        self.assertEqual(result, [])
        self.assertIn("https://x.com/search?q=", visited["url"])
        self.assertIn("from%3Aexample", visited["url"])
        self.assertIn("since%3A2024-01-01", visited["url"])
        self.assertIn("until%3A2026-01-01", visited["url"])
        self.assertTrue(visited["url"].endswith("&src=typed_query&f=live"))
        self.assertEqual(visited["scroll_count"], 25)
        self.assertEqual(
            visited["scroll_kwargs"]["any_words_filter"],
            list(x_scraper.DEFAULT_ADVANCED_SEARCH_WORDS),
        )
        self.assertTrue(visited["scroll_kwargs"]["relevance_audit"])


class CsvSafetyTests(unittest.TestCase):
    def test_formula_prefixes_are_escaped(self):
        for value in ("=1+1", "+cmd", "-2+3", "@SUM(A1:A2)", "\tformula"):
            with self.subTest(value=value):
                self.assertTrue(x_scraper.sanitize_csv_value(value).startswith("'"))

    def test_normal_text_is_unchanged(self):
        self.assertEqual(x_scraper.sanitize_csv_value("普通推文"), "普通推文")


class TweetTextExtractionTests(unittest.TestCase):
    def test_extractor_walks_all_text_nodes_and_preserves_structure(self):
        script = x_scraper.SeleniumScraper._EXTRACT_TWEETS_JS

        self.assertIn("node.nodeType === Node.TEXT_NODE", script)
        self.assertIn("element.childNodes || []", script)
        self.assertIn("tagName === 'BR'", script)
        self.assertIn("['DIV', 'P', 'LI'].includes(tagName)", script)
        self.assertNotIn("textEl.innerText.trim()", script)

    def test_extractor_preserves_image_emoji_and_text_after_it(self):
        script = x_scraper.SeleniumScraper._EXTRACT_TWEETS_JS

        self.assertIn("tagName === 'IMG'", script)
        self.assertIn("element.getAttribute('alt')", script)
        self.assertIn("element.getAttribute('aria-label')", script)
        self.assertIn("Array.from(element.childNodes || []).forEach(walk)", script)


class ScrollFilteringTests(unittest.TestCase):
    def make_scraper(self, batches):
        scraper = x_scraper.SeleniumScraper.__new__(x_scraper.SeleniumScraper)
        scraper.driver = FakeDriver()
        scraper.scroll_pause = 0
        scraper.skipped_count = 0
        scraper.tweet_ids = set()
        scraper._stop_early = False
        scraper._batches = iter(batches)
        scraper._extract_tweets_batch = lambda: next(scraper._batches, [])
        return scraper

    def test_expands_tweet_text_before_extracting_batch(self):
        scraper = self.make_scraper([[
            {"id": "10001", "dom_index": 0,
             "created_at": "2025-01-01T00:00:00Z",
             "text": "Xinjiang full text", "author_handle": "target"},
        ]])
        events = []
        original_extract = scraper._extract_tweets_batch
        scraper._expand_visible_tweet_texts = lambda: events.append("expand") or 1
        scraper._extract_tweets_batch = lambda: events.append("extract") or original_extract()

        result = scraper._scroll_to_load(1, expected_author="target")

        self.assertEqual([item["id"] for item in result], ["10001"])
        self.assertEqual(events[:2], ["expand", "extract"])

    def test_show_more_expansion_requeries_dom_after_each_click(self):
        first = FakeShowMoreElement("first")
        second = FakeShowMoreElement("second")
        driver = FakeShowMoreDriver([
            [first, second],
            [second],
            [],
        ])
        scraper = x_scraper.SeleniumScraper.__new__(x_scraper.SeleniumScraper)
        scraper.driver = driver
        scraper.scroll_pause = 0

        expanded = scraper._expand_visible_tweet_texts(max_expansions=10)

        self.assertEqual(expanded, 2)
        self.assertEqual(driver.clicked_ids, ["first", "second"])
        self.assertEqual(len(driver.find_calls), 3)
        self.assertTrue(all(
            "tweet-text-show-more-link" in selector
            for _, selector in driver.find_calls
        ))

    def test_old_irrelevant_tweets_still_trigger_date_stop(self):
        old_items = [
            {
                "id": str(10000 + i),
                "dom_index": i,
                "created_at": "2023-01-01T00:00:00Z",
                "text": "completely unrelated",
                "author_handle": "target",
            }
            for i in range(6)
        ]
        scraper = self.make_scraper([old_items])
        result = scraper._scroll_to_load(
            50,
            since_date="2024-01-01",
            keyword_filter=True,
            expected_author="target",
        )
        self.assertEqual(result, [])
        self.assertEqual(scraper.driver.scroll_calls, [])

    def test_expected_author_filters_reposts_and_recommendations(self):
        items = [
            {"id": "10001", "dom_index": 0, "created_at": "2025-01-01T00:00:00Z",
             "text": "Xinjiang", "author_handle": "target"},
            {"id": "10002", "dom_index": 1, "created_at": "2025-01-01T00:00:00Z",
             "text": "Xinjiang", "author_handle": "someone_else"},
        ]
        scraper = self.make_scraper([items])
        result = scraper._scroll_to_load(1, expected_author="target")
        self.assertEqual([item["id"] for item in result], ["10001"])

    def test_advanced_search_results_are_verified_locally(self):
        items = [
            {"id": "10001", "dom_index": 0, "created_at": "2025-01-01T00:00:00Z",
             "text": "Unrelated recommendation", "author_handle": "target"},
            {"id": "10002", "dom_index": 1, "created_at": "2025-01-01T00:00:00Z",
             "text": "Xinjiang update", "author_handle": "target"},
        ]
        scraper = self.make_scraper([items])
        result = scraper._scroll_to_load(
            2,
            max_scrolls=1,
            expected_author="target",
            any_words_filter=["Xinjiang", "维吾尔", "新疆", "Uyghur"],
        )
        self.assertEqual([item["id"] for item in result], ["10002"])


class InputValidationTests(unittest.TestCase):
    def test_screen_name_validation(self):
        self.assertEqual(x_scraper.SeleniumScraper._validate_screen_name("@valid_name"), "valid_name")
        with self.assertRaises(ValueError):
            x_scraper.SeleniumScraper._validate_screen_name("bad/name")

    def test_tweet_id_validation(self):
        self.assertEqual(x_scraper.SeleniumScraper._validate_tweet_id("1234567890"), "1234567890")
        with self.assertRaises(ValueError):
            x_scraper.SeleniumScraper._validate_tweet_id("1?redirect=1")

    def test_utc_timestamp_is_filtered_by_cst_calendar_date(self):
        self.assertEqual(
            x_scraper.SeleniumScraper._cst_date_from_iso("2024-12-31T18:00:00Z"),
            "2025-01-01",
        )


class CommentAttributionTests(unittest.TestCase):
    def test_only_explicit_reply_handle_matches(self):
        direct = {"reply_to_handles": "Target,another_user"}
        recommendation = {"reply_to_handles": "someone_else"}
        missing = {"reply_to_handles": ""}
        self.assertTrue(x_scraper.SeleniumScraper._is_direct_reply(direct, "@target"))
        self.assertFalse(x_scraper.SeleniumScraper._is_direct_reply(recommendation, "target"))
        self.assertFalse(x_scraper.SeleniumScraper._is_direct_reply(missing, "target"))

    def test_selects_thread_context_and_replies_until_recommendations(self):
        candidates = [
            {"id": "10000", "author_handle": "context_owner"},
            {"id": "10001", "author_handle": "owner"},
            {"id": "10002", "author_handle": "reply_one", "reply_to_handles": "owner"},
            {"id": "10003", "author_handle": "reply_two", "reply_to_handles": "reply_one"},
            {"id": "10004", "author_handle": "visible_in_thread", "reply_to_handles": ""},
            {"id": "10005", "author_handle": "suggested", "is_recommendation": True},
            {"id": "10006", "author_handle": "suggested_two"},
        ]
        selected = x_scraper.SeleniumScraper._select_conversation_items(
            candidates, "10001", "owner", max_items=20
        )
        self.assertEqual(
            [item["id"] for item in selected],
            ["10000", "10002", "10003", "10004"],
        )
        self.assertEqual(selected[0]["thread_relation"], "context")
        self.assertEqual(selected[1]["thread_relation"], "direct_reply")
        self.assertEqual(selected[2]["thread_relation"], "nested_reply")
        self.assertEqual(selected[3]["thread_relation"], "thread_item")

    def test_comment_csv_has_requested_columns_in_order(self):
        scraper = x_scraper.SeleniumScraper.__new__(x_scraper.SeleniumScraper)
        data = [{
            "author_name": "Reply User",
            "author_handle": "reply_user",
            "created_at": "2025-01-02T03:04:00Z",
            "text": "comment text",
            "id": "90001",
            "tweet_url": "https://x.com/reply_user/status/90001",
            "reply_to_handles": "post_owner",
            "parent_tweet_author": "post_owner",
        }]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "comments.csv"
            scraper.export_comments_csv(data, str(output))
            with output.open(encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            self.assertEqual(
                reader.fieldnames,
                ["序号", "account", "tweet_id", "link", "time", "text", "贴主ID"],
            )
            self.assertEqual(rows[0]["序号"], "1")
            self.assertEqual(rows[0]["account"], "Reply User")
            # @ 开头的外部文本会加单引号，防止 Excel 公式注入。
            self.assertEqual(rows[0]["tweet_id"], "'@reply_user")
            self.assertEqual(rows[0]["link"], "https://x.com/reply_user/status/90001")
            self.assertEqual(rows[0]["time"], "2025.1.2 11:04")
            self.assertEqual(rows[0]["text"], "comment text")
            self.assertEqual(rows[0]["贴主ID"], "'@post_owner")

    def test_actual_comment_count_is_written_to_post_csv(self):
        scraper = x_scraper.SeleniumScraper.__new__(x_scraper.SeleniumScraper)
        data = [{
            "author_name": "Owner",
            "author_handle": "owner",
            "created_at": "2025-01-02T03:04:00Z",
            "text": "Xinjiang update",
            "tweet_url": "https://x.com/owner/status/90002",
            "reply_count": 12,
            "actual_comment_count": 3,
        }]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "posts.csv"
            scraper.export_posts_csv(data, str(output))
            with output.open(encoding="utf-8-sig", newline="") as f:
                row = next(csv.DictReader(f))
            self.assertEqual(row["reply"], "12")
            self.assertEqual(row["评论条数"], "3")
            self.assertEqual(
                row["原始链接"], "https://x.com/owner/status/90002"
            )

    def test_empty_post_csv_keeps_fixed_header(self):
        scraper = x_scraper.SeleniumScraper.__new__(x_scraper.SeleniumScraper)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "empty_posts.csv"
            scraper.export_posts_csv([], str(output))
            with output.open(encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            self.assertEqual(
                reader.fieldnames,
                [
                    "ID", "name", "Following", "Followers", "time", "text",
                    "translation", "tag", "reply", "repost", "likes", "views",
                    "vedios/photos", "评论条数", "原始链接",
                ],
            )
            self.assertEqual(rows, [])

    def test_only_posts_with_reported_replies_open_details(self):
        scraper = x_scraper.SeleniumScraper.__new__(x_scraper.SeleniumScraper)
        scraper.max_comments_per_post = 20
        scraper.max_comment_depth = 0
        visited = []
        scraper._fetch_comments_for_tweet = lambda url, **kwargs: (
            visited.append(url)
            or [{
                "id": "90001",
                "author_handle": "reply_user",
                "reply_to_handles": "owner",
            }]
        )
        posts = [
            {"id": "10001", "reply_count": 0, "tweet_url": "https://x.com/owner/status/10001",
             "author_handle": "owner"},
            {"id": "10002", "reply_count": 2, "tweet_url": "https://x.com/owner/status/10002",
             "author_handle": "owner"},
        ]
        comments = scraper.fetch_comments_for_posts(posts)
        self.assertEqual(visited, ["https://x.com/owner/status/10002"])
        self.assertEqual(posts[0]["actual_comment_count"], 0)
        self.assertEqual(posts[1]["actual_comment_count"], 1)
        self.assertEqual(comments[0]["reply_target_handle"], "owner")


if __name__ == "__main__":
    unittest.main()
