from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app import (  # noqa: E402
    AuditAppHandler,
    AuditRequestError,
    WEB_DIR,
    parse_audit_request,
)


class AppRequestTests(unittest.TestCase):
    def test_adds_https_when_scheme_is_omitted(self) -> None:
        url, max_pages = parse_audit_request({"url": "example.com", "max_pages": "25"})
        self.assertEqual("https://example.com", url)
        self.assertEqual(25, max_pages)

    def test_rejects_url_with_credentials(self) -> None:
        with self.assertRaises(AuditRequestError):
            parse_audit_request({"url": "https://name:secret@example.com"})

    def test_rejects_page_limit_outside_web_boundary(self) -> None:
        with self.assertRaises(AuditRequestError):
            parse_audit_request({"url": "https://example.com", "max_pages": 101})

    def test_web_entrypoint_exists(self) -> None:
        self.assertTrue((WEB_DIR / "index.html").is_file())

    def test_web_entrypoint_links_supported_agents(self) -> None:
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        for website in (
            "https://openai.com/codex/",
            "https://openclaw.ai/",
            "https://hermes-agent.nousresearch.com/",
            "https://claude.com/product/claude-code",
        ):
            self.assertIn(website, html)

    def test_health_and_private_target_boundary(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), AuditAppHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            connection.request("GET", "/api/health")
            health = connection.getresponse()
            self.assertEqual(200, health.status)
            self.assertTrue(json.loads(health.read())["ok"])

            request_body = json.dumps({"url": "http://127.0.0.1", "max_pages": 10})
            connection.request(
                "POST",
                "/api/audit",
                body=request_body.encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            audit = connection.getresponse()
            self.assertEqual(400, audit.status)
            self.assertIn("Private or non-public address blocked", json.loads(audit.read())["error"])
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
