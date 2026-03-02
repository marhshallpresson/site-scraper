import unittest

from scripts.extract_pageant_content import build_media, build_sections, build_site_map


class ExtractSchemaTests(unittest.TestCase):
    def setUp(self):
        self.source_profiles = [
            {
                "domain": "missglobal.com",
                "html_files_scanned": 3,
                "nav_items": [
                    {
                        "label": "Apply",
                        "href": "/apply/",
                        "source_domain": "missglobal.com",
                        "source_page": "/index.html",
                    }
                ],
                "ctas": [],
                "headings": ["Miss Global"],
                "section_hits": {"events": 1, "news": 2},
                "media": [
                    {
                        "type": "image",
                        "url": "https://missglobal.com/image.jpg",
                        "alt": "sample",
                        "source_domain": "missglobal.com",
                        "source_page": "/index.html",
                    }
                ],
            }
        ]

    def test_site_map_schema(self):
        site_map = build_site_map(self.source_profiles)
        self.assertIn("routes", site_map)
        self.assertIn("nav_hierarchy", site_map)
        self.assertTrue(any(r["path"] == "/apply" for r in site_map["routes"]))

    def test_sections_schema(self):
        sections = build_sections(self.source_profiles)
        self.assertIn("home", sections)
        self.assertIn("faq", sections)
        self.assertIn("contact", sections)

    def test_media_schema(self):
        media = build_media(self.source_profiles)
        self.assertIn("items", media)
        self.assertEqual(media["items"][0]["id"], "media-0001")
        self.assertEqual(media["items"][0]["section_hint"], "gallery")


if __name__ == "__main__":
    unittest.main()
