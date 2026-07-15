import unittest

import x_scraper


class FakeDriver:
    def __init__(self):
        self.scroll_calls = []

    def execute_script(self, script, *args):
        self.scroll_calls.append((script, args))


class FilterTests(unittest.TestCase):
    def test_anchor_keywords_match(self):
        self.assertTrue(x_scraper.matches_xinjiang("这是一则新疆相关消息"))
        self.assertTrue(x_scraper.matches_xinjiang("UFLPA enforcement update"))
        self.assertTrue(x_scraper.matches_xinjiang("Support for Uyghur families"))

    def test_generic_context_words_do_not_match_alone(self):
        self.assertFalse(x_scraper.matches_xinjiang("oppression and deportation elsewhere"))
        self.assertFalse(x_scraper.matches_xinjiang("a generic Magnitsky sanctions update"))

    def test_english_keyword_uses_word_boundaries(self):
        self.assertFalse(x_scraper.matches_xinjiang("prefixuhrpsuffix"))


class CsvSafetyTests(unittest.TestCase):
    def test_formula_prefixes_are_escaped(self):
        for value in ("=1+1", "+cmd", "-2+3", "@SUM(A1:A2)", "\tformula"):
            with self.subTest(value=value):
                self.assertTrue(x_scraper.sanitize_csv_value(value).startswith("'"))

    def test_normal_text_is_unchanged(self):
        self.assertEqual(x_scraper.sanitize_csv_value("普通推文"), "普通推文")


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


if __name__ == "__main__":
    unittest.main()
