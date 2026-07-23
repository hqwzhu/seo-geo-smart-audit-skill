#!/usr/bin/env python3

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_audit import AuditHTMLParser, audit_site  # noqa: E402


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        port = self.server.server_address[1]
        routes = {
            "/robots.txt": ("text/plain", "User-agent: *\nAllow: /\nSitemap: /sitemap.xml\n"),
            "/sitemap.xml": (
                "application/xml",
                f"<?xml version='1.0'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                f"<url><loc>http://127.0.0.1:{port}/</loc></url>"
                f"<url><loc>http://127.0.0.1:{port}/about</loc></url>"
                f"<url><loc>http://127.0.0.1:{port}/about</loc></url></urlset>",
            ),
            "/llms.txt": ("text/plain", "# Fixture Site\n"),
            "/": (
                "text/html",
                f"<html lang='zh-CN'><head><title>首页</title>"
                f"<meta name='description' content='测试首页'>"
                f"<link rel='canonical' href='http://127.0.0.1:{port}/'>"
                f"<script type='application/ld+json'>{{\"@type\":\"WebSite\"}}</script>"
                f"</head><body><h1>首页</h1><a href='/about'>关于</a></body></html>",
            ),
            "/about": (
                "text/html",
                f"<html lang='zh-CN'><head><title>关于</title>"
                f"<meta name='description' content='关于我们'>"
                f"<link rel='canonical' href='http://127.0.0.1:{port}/about'>"
                f"</head><body><h1>关于</h1><p>公开测试内容。</p></body></html>",
            ),
        }
        if self.path not in routes:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"not found")
            return
        content_type, body = routes[self.path]
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


class SiteAuditTests(unittest.TestCase):
    def test_html_parser_extracts_core_fields(self) -> None:
        parser = AuditHTMLParser()
        parser.feed(
            "<html lang='en'><head><title>Example</title>"
            "<meta name='description' content='Description'>"
            "<script type='application/ld+json'>{\"@type\":\"Article\"}</script>"
            "</head><body><h1>Heading</h1><img src='x.png'></body></html>"
        )
        self.assertEqual("Example", "".join(parser.title_parts))
        self.assertEqual("en", parser.html_lang)
        self.assertEqual(1, parser.images_missing_alt)
        self.assertEqual(1, len(parser.json_ld_blocks))

    def test_bounded_local_audit(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            target = f"http://127.0.0.1:{server.server_address[1]}/"
            result = audit_site(
                target,
                max_pages=5,
                timeout=2,
                delay=0,
                max_sitemaps=2,
                allow_private=True,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(2, result["summary"]["html_pages"])
        self.assertEqual(1, result["discovery"]["sitemap_duplicate_url_count"])
        self.assertEqual(200, result["discovery"]["machine_assets"]["/llms.txt"]["status"])
        self.assertIn("sitemap_duplicate_urls", {item["code"] for item in result["findings"]})


if __name__ == "__main__":
    unittest.main()
