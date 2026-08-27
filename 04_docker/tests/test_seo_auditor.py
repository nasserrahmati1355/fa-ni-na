from __future__ import annotations

from pathlib import Path
import sys
import unittest


APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

from seo_auditor import AuditError, analyze_html_document, normalize_start_url  # noqa: E402


class SeoAuditorTests(unittest.TestCase):
    def test_normalizes_domain_without_scheme(self) -> None:
        self.assertEqual(
            normalize_start_url("Example.com/docs#part"),
            "https://example.com/docs",
        )

    def test_rejects_direct_ip_targets(self) -> None:
        with self.assertRaises(AuditError):
            normalize_start_url("http://127.0.0.1/")

    def test_detects_missing_h1_meta_and_canonical(self) -> None:
        html = """
        <!doctype html>
        <html>
          <head><title>Short title</title></head>
          <body>
            <a href="/missing">Broken candidate</a>
            <a href="http://example.com/other">HTTP page on same host</a>
            <a href="https://external.example/page">External</a>
          </body>
        </html>
        """

        details, links = analyze_html_document(
            "https://example.com/",
            html,
            "example.com",
        )

        self.assertEqual(details["h1_count"], 0)
        self.assertIn("H1 ندارد", details["issues"])
        self.assertIn("Meta Description ندارد", details["issues"])
        self.assertIn("Canonical ندارد", details["issues"])
        self.assertIn("https://example.com/missing", links)
        self.assertIn("http://example.com/other", links)
        self.assertNotIn("https://external.example/page", links)

    def test_detects_multiple_h1_and_noindex(self) -> None:
        html = """
        <html>
          <head>
            <title>This is a sufficiently descriptive test page title</title>
            <meta name="description" content="This description is long enough to pass the internal minimum length used by the test SEO auditor application.">
            <meta name="robots" content="noindex, follow">
            <link rel="canonical" href="/canonical">
          </head>
          <body><h1>One</h1><h1>Two</h1></body>
        </html>
        """

        details, _ = analyze_html_document(
            "https://example.com/page",
            html,
            "example.com",
        )

        self.assertEqual(details["h1_count"], 2)
        self.assertTrue(details["noindex"])
        self.assertIn("بیش از یک H1 دارد", details["issues"])
        self.assertIn("صفحه دارای noindex است", details["issues"])
        self.assertEqual(details["canonical"], "https://example.com/canonical")


if __name__ == "__main__":
    unittest.main()
