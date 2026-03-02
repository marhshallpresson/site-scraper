import unittest

from site_scraper import is_telemetry_url, is_valid_resource_candidate


class UrlFilterTests(unittest.TestCase):
    def test_valid_resource_candidates(self):
        self.assertTrue(is_valid_resource_candidate("/assets/main.css"))
        self.assertTrue(is_valid_resource_candidate("https://example.com/a.js"))
        self.assertFalse(is_valid_resource_candidate(""))
        self.assertFalse(is_valid_resource_candidate(" "))
        self.assertFalse(is_valid_resource_candidate("|"))
        self.assertFalse(is_valid_resource_candidate("https://a.com://b.com"))
        self.assertFalse(is_valid_resource_candidate("bad value with space"))

    def test_telemetry_detection(self):
        self.assertTrue(is_telemetry_url("https://www.google-analytics.com/g/collect"))
        self.assertTrue(is_telemetry_url("https://example.com/telemetry/beacon"))
        self.assertFalse(is_telemetry_url("https://example.com/assets/app.js"))


if __name__ == "__main__":
    unittest.main()
