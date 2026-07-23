#!/usr/bin/env python3
"""Bounded, read-only SEO/GEO crawler using only the Python standard library."""

from __future__ import annotations

import argparse
from collections import Counter, deque
from datetime import datetime, timezone
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET


DEFAULT_USER_AGENT = "IndependentSiteSeoGeoAudit/1.0 (+read-only)"
AI_BOTS = (
    "GPTBot",
    "ChatGPT-User",
    "PerplexityBot",
    "ClaudeBot",
    "anthropic-ai",
    "Google-Extended",
    "Bingbot",
)
MACHINE_ASSETS = ("/llms.txt", "/pricing.md", "/okf/index.md")
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class AuditHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.h1_parts: list[list[str]] = []
        self.h2_count = 0
        self.meta: dict[str, str] = {}
        self.links: list[dict[str, str]] = []
        self.anchors: list[str] = []
        self.images_missing_alt = 0
        self.html_lang = ""
        self.json_ld_blocks: list[str] = []
        self.visible_text: list[str] = []
        self._capture_title = False
        self._capture_h1: list[str] | None = None
        self._capture_json: list[str] | None = None
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "html":
            self.html_lang = values.get("lang", "").strip()
        elif tag == "title":
            self._capture_title = True
        elif tag == "h1":
            self._capture_h1 = []
            self.h1_parts.append(self._capture_h1)
        elif tag == "h2":
            self.h2_count += 1
        elif tag == "meta":
            key = (values.get("name") or values.get("property")).strip().lower()
            if key:
                self.meta[key] = values.get("content", "").strip()
        elif tag == "link":
            self.links.append(
                {
                    "rel": values.get("rel", "").strip().lower(),
                    "href": values.get("href", "").strip(),
                    "hreflang": values.get("hreflang", "").strip(),
                }
            )
        elif tag == "a" and values.get("href"):
            self.anchors.append(values["href"].strip())
        elif tag == "img" and "alt" not in values:
            self.images_missing_alt += 1
        if tag == "script":
            self._ignored_depth += 1
            if values.get("type", "").lower() == "application/ld+json":
                self._capture_json = []
        elif tag in {"style", "noscript"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._capture_title = False
        elif tag == "h1":
            self._capture_h1 = None
        if tag == "script":
            if self._capture_json is not None:
                self.json_ld_blocks.append("".join(self._capture_json).strip())
                self._capture_json = None
            self._ignored_depth = max(0, self._ignored_depth - 1)
        elif tag in {"style", "noscript"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self.title_parts.append(data)
        if self._capture_h1 is not None:
            self._capture_h1.append(data)
        if self._capture_json is not None:
            self._capture_json.append(data)
        if not self._ignored_depth:
            text = " ".join(data.split())
            if text:
                self.visible_text.append(text)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalized_url(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def origin_for(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), "", "", ""))


def same_origin(left: str, right: str) -> bool:
    return origin_for(left) == origin_for(right)


def validate_url(url: str, allow_private: bool) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Only absolute http/https URLs are allowed: {url}")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not allowed")
    if allow_private:
        return
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for {parsed.hostname}: {exc}") from exc
    for item in addresses:
        address = ipaddress.ip_address(item[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            raise ValueError(f"Private or non-public address blocked for {parsed.hostname}")


def fetch_url(
    url: str,
    *,
    timeout: float,
    max_bytes: int,
    user_agent: str,
    allow_private: bool,
    max_redirects: int = 5,
) -> tuple[dict[str, Any], str]:
    current = normalized_url(url)
    history: list[dict[str, Any]] = []
    context = ssl.create_default_context()
    opener = build_opener(NoRedirect(), HTTPSHandler(context=context))

    for _ in range(max_redirects + 1):
        validate_url(current, allow_private)
        request = Request(
            current,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml,text/plain;q=0.9,*/*;q=0.1",
                "Accept-Encoding": "identity",
            },
        )
        started = time.perf_counter()
        try:
            response = opener.open(request, timeout=timeout)
            try:
                status = int(response.status)
                headers = response.headers
                body = response.read(max_bytes + 1)
            finally:
                response.close()
        except HTTPError as exc:
            try:
                status = int(exc.code)
                headers = exc.headers
                body = exc.read(max_bytes + 1) if status not in REDIRECT_STATUSES else b""
            finally:
                exc.close()
        except (URLError, TimeoutError, OSError) as exc:
            return (
                {
                    "requested_url": url,
                    "final_url": current,
                    "status": None,
                    "error": str(exc),
                    "redirects": history,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000),
                },
                "",
            )

        elapsed_ms = round((time.perf_counter() - started) * 1000)
        if status in REDIRECT_STATUSES and headers.get("Location"):
            next_url = normalized_url(urljoin(current, headers["Location"]))
            history.append({"status": status, "from": current, "to": next_url})
            current = next_url
            continue

        truncated = len(body) > max_bytes
        body = body[:max_bytes]
        content_type = headers.get_content_type() if hasattr(headers, "get_content_type") else ""
        charset = headers.get_content_charset() if hasattr(headers, "get_content_charset") else None
        try:
            text = body.decode(charset or "utf-8", errors="replace")
        except LookupError:
            text = body.decode("utf-8", errors="replace")
        return (
            {
                "requested_url": url,
                "final_url": current,
                "status": status,
                "content_type": content_type,
                "bytes_read": len(body),
                "truncated": truncated,
                "redirects": history,
                "elapsed_ms": elapsed_ms,
                "error": None,
            },
            text,
        )

    return (
        {
            "requested_url": url,
            "final_url": current,
            "status": None,
            "error": f"More than {max_redirects} redirects",
            "redirects": history,
        },
        "",
    )


def parse_html(url: str, text: str) -> tuple[dict[str, Any], list[str]]:
    parser = AuditHTMLParser()
    try:
        parser.feed(text)
    except Exception as exc:  # HTMLParser should be tolerant; retain partial evidence.
        parse_error = str(exc)
    else:
        parse_error = None

    canonical_links = [link for link in parser.links if "canonical" in link["rel"].split()]
    canonical = urljoin(url, canonical_links[0]["href"]) if canonical_links and canonical_links[0]["href"] else ""
    hreflang = [
        {"lang": link["hreflang"], "url": normalized_url(urljoin(url, link["href"]))}
        for link in parser.links
        if "alternate" in link["rel"].split() and link["hreflang"] and link["href"]
    ]
    json_ld_valid = 0
    json_ld_errors: list[str] = []
    for block in parser.json_ld_blocks:
        try:
            json.loads(block)
            json_ld_valid += 1
        except (json.JSONDecodeError, TypeError) as exc:
            json_ld_errors.append(str(exc))

    internal_links: list[str] = []
    external_links = 0
    for href in parser.anchors:
        absolute = normalized_url(urljoin(url, href))
        parsed = urlsplit(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if same_origin(url, absolute):
            internal_links.append(absolute)
        else:
            external_links += 1

    title = " ".join(" ".join(parser.title_parts).split())
    h1_values = [" ".join(" ".join(parts).split()) for parts in parser.h1_parts]
    description = parser.meta.get("description", "")
    robots_directive = ",".join(
        value for key, value in parser.meta.items() if key in {"robots", "googlebot", "bingbot"} and value
    ).lower()
    visible_text = " ".join(parser.visible_text)
    word_count = len(re.findall(r"[\w\u3400-\u9fff]+", visible_text, flags=re.UNICODE))
    has_author_signal = bool(
        parser.meta.get("author")
        or parser.meta.get("article:author")
        or re.search(r"\b(author|byline)\b|作者|撰稿", text, flags=re.IGNORECASE)
    )

    return (
        {
            "title": title,
            "title_length": len(title),
            "meta_description": description,
            "meta_description_length": len(description),
            "canonical": normalized_url(canonical) if canonical else "",
            "html_lang": parser.html_lang,
            "robots_directive": robots_directive,
            "noindex": "noindex" in robots_directive,
            "h1_count": len(h1_values),
            "h1": h1_values,
            "h2_count": parser.h2_count,
            "images_missing_alt_attribute": parser.images_missing_alt,
            "internal_link_count": len(set(internal_links)),
            "external_link_count": external_links,
            "hreflang": hreflang,
            "json_ld_static_count": len(parser.json_ld_blocks),
            "json_ld_static_valid_count": json_ld_valid,
            "json_ld_static_errors": json_ld_errors,
            "word_count": word_count,
            "author_signal": has_author_signal,
            "parse_error": parse_error,
        },
        list(dict.fromkeys(internal_links)),
    )


def parse_sitemap(text: str) -> tuple[str, list[str]]:
    root = ET.fromstring(text)
    kind = root.tag.split("}")[-1].lower()
    locations = [
        (element.text or "").strip()
        for element in root.iter()
        if element.tag.split("}")[-1].lower() == "loc" and (element.text or "").strip()
    ]
    return kind, locations


def add_finding(
    findings: list[dict[str, Any]],
    *,
    code: str,
    category: str,
    severity: str,
    status: str,
    issue: str,
    evidence: Any,
    action: str,
    verification: str,
) -> None:
    findings.append(
        {
            "id": f"F{len(findings) + 1:03d}",
            "code": code,
            "category": category,
            "severity": severity,
            "status": status,
            "issue": issue,
            "evidence": evidence,
            "action": action,
            "verification": verification,
        }
    )


def build_findings(audit: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    pages = audit["pages"]
    html_pages = [page for page in pages if page.get("is_html")]
    sitemap_urls = set(audit["discovery"]["sitemap_urls"])

    if audit["discovery"]["sitemap_duplicate_url_count"]:
        add_finding(
            findings,
            code="sitemap_duplicate_urls",
            category="technical_seo",
            severity="medium",
            status="verified",
            issue="Sitemap 含重复 URL",
            evidence=audit["discovery"]["sitemap_duplicate_urls"],
            action="去重 sitemap 的 loc，并保留唯一规范 URL。",
            verification="重新解析 sitemap，确认总 loc 数与唯一 loc 数相同。",
        )

    failed = [page for page in pages if page.get("status") is None or int(page["status"]) >= 400]
    if failed:
        add_finding(
            findings,
            code="failed_pages",
            category="crawlability",
            severity="high",
            status="verified",
            issue="已发现失败或错误响应页面",
            evidence=[{"url": p["url"], "status": p.get("status"), "error": p.get("error")} for p in failed[:20]],
            action="优先修复 sitemap 和核心导航中的失败 URL；有替代页时设置单跳 301。",
            verification="逐个请求受影响 URL，并确认最终状态、跳转链与 canonical。",
        )

    sitemap_noindex = [page["url"] for page in html_pages if page.get("noindex") and page["url"] in sitemap_urls]
    if sitemap_noindex:
        add_finding(
            findings,
            code="sitemap_noindex_conflict",
            category="indexation",
            severity="high",
            status="verified",
            issue="Sitemap URL 同时声明 noindex",
            evidence=sitemap_noindex[:20],
            action="根据页面意图移除 noindex 或从 sitemap 删除该 URL。",
            verification="确认页面索引指令与 sitemap 收录策略一致。",
        )

    missing_title = [page["url"] for page in html_pages if not page.get("title")]
    if missing_title:
        add_finding(
            findings,
            code="missing_title",
            category="on_page",
            severity="high",
            status="verified",
            issue="HTML 页面缺少 title",
            evidence=missing_title[:20],
            action="为每个可索引页面生成唯一且符合页面意图的 title。",
            verification="抓取页面并确认渲染前后 title 存在且唯一。",
        )

    missing_canonical = [page["url"] for page in html_pages if not page.get("canonical")]
    if missing_canonical:
        add_finding(
            findings,
            code="missing_canonical",
            category="canonicalization",
            severity="medium",
            status="verified",
            issue="部分 HTML 页面缺少 canonical",
            evidence=missing_canonical[:20],
            action="为唯一、可索引页面设置与最终规范 URL 一致的自引用 canonical。",
            verification="检查原始 HTML 和渲染 DOM 中的 canonical。",
        )

    external_canonical = [
        {"url": page["url"], "canonical": page["canonical"]}
        for page in html_pages
        if page.get("canonical") and not same_origin(page["url"], page["canonical"])
    ]
    if external_canonical:
        add_finding(
            findings,
            code="external_canonical",
            category="canonicalization",
            severity="high",
            status="verified",
            issue="页面 canonical 指向其他域名",
            evidence=external_canonical[:20],
            action="确认跨域规范化是否有意；若无，改为本域规范 URL。",
            verification="重新抓取并确认 canonical、sitemap 与最终 URL 对齐。",
        )

    h1_issues = [{"url": page["url"], "h1_count": page.get("h1_count", 0)} for page in html_pages if page.get("h1_count") != 1]
    if h1_issues:
        add_finding(
            findings,
            code="h1_structure",
            category="on_page",
            severity="medium",
            status="verified",
            issue="部分页面没有清晰的单一 H1",
            evidence=h1_issues[:20],
            action="让页面主标题使用一个与搜索意图一致的 H1；其他层级使用 H2/H3。",
            verification="检查渲染 DOM 的标题层级。",
        )

    for field, code, label in (("title", "duplicate_title", "title"), ("meta_description", "duplicate_description", "description")):
        groups: dict[str, list[str]] = {}
        for page in html_pages:
            value = page.get(field, "").strip()
            if value:
                groups.setdefault(value, []).append(page["url"])
        duplicates = [{label: value, "urls": urls[:10]} for value, urls in groups.items() if len(urls) > 1]
        if duplicates:
            add_finding(
                findings,
                code=code,
                category="on_page",
                severity="medium",
                status="verified",
                issue=f"站内存在重复 {label}",
                evidence=duplicates[:10],
                action=f"按页面搜索意图重写唯一 {label}，不要只替换品牌后缀。",
                verification=f"重新抓取并按规范化后的 {label} 分组，确认无非预期重复。",
            )

    invalid_json_ld = [
        {"url": page["url"], "errors": page.get("json_ld_static_errors")}
        for page in html_pages
        if page.get("json_ld_static_errors")
    ]
    if invalid_json_ld:
        add_finding(
            findings,
            code="invalid_static_json_ld",
            category="structured_data",
            severity="medium",
            status="verified",
            issue="静态 HTML 中存在无法解析的 JSON-LD",
            evidence=invalid_json_ld[:20],
            action="修复 JSON 语法，并确保字段与页面可见内容一致。",
            verification="通过 JSON 解析器和 Rich Results Test 复核。",
        )

    no_static_json_ld = [page["url"] for page in html_pages if page.get("json_ld_static_count", 0) == 0]
    if no_static_json_ld:
        add_finding(
            findings,
            code="schema_render_check",
            category="structured_data",
            severity="info",
            status="render_required",
            issue="部分页面的静态 HTML 未发现 JSON-LD，需渲染复核",
            evidence=no_static_json_ld[:20],
            action="使用浏览器读取渲染后的 application/ld+json；仅在仍为空时评估是否缺失。",
            verification="保存渲染 DOM 或 Rich Results Test 结果。",
        )

    pages_by_url = {normalized_url(page["url"]): page for page in html_pages}
    self_missing: list[str] = []
    reciprocal_missing: list[dict[str, str]] = []
    for page in html_pages:
        alternates = page.get("hreflang", [])
        if not alternates:
            continue
        source = normalized_url(page["url"])
        if source not in {item["url"] for item in alternates}:
            self_missing.append(page["url"])
        for alternate in alternates:
            target = pages_by_url.get(alternate["url"])
            if target and source not in {item["url"] for item in target.get("hreflang", [])}:
                reciprocal_missing.append({"from": source, "to": alternate["url"], "lang": alternate["lang"]})
    if self_missing or reciprocal_missing:
        add_finding(
            findings,
            code="hreflang_consistency",
            category="international_seo",
            severity="high" if reciprocal_missing else "medium",
            status="verified",
            issue="Hreflang 自引用或互惠关系不完整",
            evidence={"self_missing": self_missing[:20], "reciprocal_missing": reciprocal_missing[:20]},
            action="按完整语言集补齐自引用与返回链接，并确保目标 200、可索引、canonical 一致。",
            verification="按 pathname 和规范 URL 重新构建 hreflang 图并检查双向边。",
        )

    blocked_bots = [name for name, allowed in audit["discovery"]["robots_ai_bot_access"].items() if allowed is False]
    if blocked_bots:
        add_finding(
            findings,
            code="ai_bot_policy",
            category="geo",
            severity="low",
            status="verified",
            issue="部分 AI/搜索爬虫被 robots.txt 阻止",
            evidence=blocked_bots,
            action="结合隐私、训练和引用策略确认是否有意；只有希望被相应服务访问时才调整。",
            verification="使用各 User-Agent 重新解析 robots.txt，并记录策略决定。",
        )

    missing_assets = [path for path, item in audit["discovery"]["machine_assets"].items() if item.get("status") != 200]
    if missing_assets:
        add_finding(
            findings,
            code="optional_machine_assets",
            category="geo",
            severity="info",
            status="verified",
            issue="部分可选机器可读资源不可用",
            evidence=missing_assets,
            action="仅在能持续维护准确内容时补充；不要把这些文件当作 Google 排名必要条件。",
            verification="请求资源并确认 200、内容准确、可公开访问。",
        )

    add_finding(
        findings,
        code="core_web_vitals_data",
        category="performance",
        severity="info",
        status="external_data_required",
        issue="Core Web Vitals 未由本次 HTTP 抓取验证",
        evidence="需要 CrUX、PageSpeed 字段数据或 GSC Core Web Vitals。",
        action="获取 LCP、INP、CLS 字段数据并按页面类型和设备分析。",
        verification="保存数据源、时间窗、样本量和通过率。",
    )
    add_finding(
        findings,
        code="answer_engine_visibility_data",
        category="geo",
        severity="info",
        status="external_data_required",
        issue="真实答案引擎品牌提及与域名引用未验证",
        evidence="本脚本不调用 ChatGPT、Perplexity、Claude、Gemini 或 Copilot。",
        action="在用户授权后，对优先查询执行带时间、语言和地区的真实探测。",
        verification="保存逐查询结果、引用 URL、竞争来源和复测日期。",
    )
    return findings


def audit_site(
    url: str,
    *,
    max_pages: int = 100,
    timeout: float = 10,
    delay: float = 0.1,
    max_bytes: int = 5_000_000,
    max_sitemaps: int = 10,
    user_agent: str = DEFAULT_USER_AGENT,
    allow_private: bool = False,
) -> dict[str, Any]:
    started_at = utc_now()
    validate_url(url, allow_private)
    start_url = normalized_url(url)
    site_origin = origin_for(start_url)
    fetch_options = {
        "timeout": timeout,
        "max_bytes": max_bytes,
        "user_agent": user_agent,
        "allow_private": allow_private,
    }

    robots_url = f"{site_origin}/robots.txt"
    robots_meta, robots_text = fetch_url(robots_url, **fetch_options)
    robots_parser: RobotFileParser | None = None
    if robots_meta.get("status") == 200:
        robots_parser = RobotFileParser()
        robots_parser.set_url(robots_url)
        robots_parser.parse(robots_text.splitlines())
    sitemap_candidates = re.findall(r"(?im)^\s*Sitemap:\s*(\S+)", robots_text)
    if not sitemap_candidates:
        sitemap_candidates = [f"{site_origin}/sitemap.xml"]

    sitemap_records: list[dict[str, Any]] = []
    sitemap_urls_raw: list[str] = []
    pending_sitemaps = deque(normalized_url(urljoin(site_origin, item)) for item in sitemap_candidates)
    seen_sitemaps: set[str] = set()
    while pending_sitemaps and len(seen_sitemaps) < max_sitemaps:
        sitemap_url = pending_sitemaps.popleft()
        if sitemap_url in seen_sitemaps or not same_origin(start_url, sitemap_url):
            continue
        seen_sitemaps.add(sitemap_url)
        meta, text = fetch_url(sitemap_url, **fetch_options)
        record = {"url": sitemap_url, "status": meta.get("status"), "error": meta.get("error"), "kind": None, "url_count": 0}
        if meta.get("status") == 200:
            try:
                kind, locations = parse_sitemap(text)
                record["kind"] = kind
                record["url_count"] = len(locations)
                if kind == "sitemapindex":
                    pending_sitemaps.extend(normalized_url(urljoin(sitemap_url, item)) for item in locations)
                else:
                    sitemap_urls_raw.extend(normalized_url(urljoin(sitemap_url, item)) for item in locations)
            except ET.ParseError as exc:
                record["error"] = f"XML parse error: {exc}"
        sitemap_records.append(record)

    sitemap_counter = Counter(sitemap_urls_raw)
    sitemap_duplicate_urls = [url for url, count in sitemap_counter.items() if count > 1]
    sitemap_urls = list(dict.fromkeys(item for item in sitemap_urls_raw if same_origin(start_url, item)))

    machine_assets: dict[str, dict[str, Any]] = {}
    for path in MACHINE_ASSETS:
        meta, _ = fetch_url(f"{site_origin}{path}", **fetch_options)
        machine_assets[path] = {
            "status": meta.get("status"),
            "content_type": meta.get("content_type"),
            "error": meta.get("error"),
        }

    queue = deque([start_url, *sitemap_urls])
    queued = set(queue)
    visited: set[str] = set()
    pages: list[dict[str, Any]] = []
    while queue and len(pages) < max_pages:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        if robots_parser and not robots_parser.can_fetch(user_agent, current):
            pages.append({"url": current, "status": None, "error": "Blocked by robots.txt", "blocked_by_robots": True, "is_html": False})
            continue
        meta, text = fetch_url(current, **fetch_options)
        page: dict[str, Any] = {
            "url": current,
            "final_url": meta.get("final_url"),
            "status": meta.get("status"),
            "content_type": meta.get("content_type"),
            "elapsed_ms": meta.get("elapsed_ms"),
            "redirects": meta.get("redirects", []),
            "error": meta.get("error"),
            "truncated": meta.get("truncated", False),
            "in_sitemap": current in sitemap_counter,
        }
        content_type = (meta.get("content_type") or "").lower()
        page["is_html"] = meta.get("status") == 200 and content_type in {"text/html", "application/xhtml+xml"}
        if page["is_html"]:
            html_data, links = parse_html(meta.get("final_url") or current, text)
            page.update(html_data)
            for link in links:
                if link not in queued and link not in visited and same_origin(start_url, link):
                    queued.add(link)
                    queue.append(link)
        pages.append(page)
        if delay:
            time.sleep(delay)

    robots_ai_bot_access = {
        bot: robots_parser.can_fetch(bot, start_url) if robots_parser else None for bot in AI_BOTS
    }
    audit: dict[str, Any] = {
        "meta": {
            "target": start_url,
            "started_at": started_at,
            "finished_at": utc_now(),
            "user_agent": user_agent,
            "max_pages": max_pages,
            "allow_private": allow_private,
            "limitations": [
                "Static HTML only; client-rendered metadata and JSON-LD require browser verification.",
                "HTTP timing is not Core Web Vitals.",
                "No Search Console, analytics, backlink, ranking, or answer-engine data is collected.",
            ],
        },
        "discovery": {
            "robots": {**robots_meta, "body": None},
            "robots_ai_bot_access": robots_ai_bot_access,
            "sitemaps": sitemap_records,
            "sitemap_urls": sitemap_urls,
            "sitemap_url_count": len(sitemap_urls_raw),
            "sitemap_unique_url_count": len(set(sitemap_urls_raw)),
            "sitemap_duplicate_url_count": len(sitemap_duplicate_urls),
            "sitemap_duplicate_urls": sitemap_duplicate_urls,
            "machine_assets": machine_assets,
        },
        "pages": pages,
    }
    audit["summary"] = {
        "pages_crawled": len(pages),
        "html_pages": sum(1 for page in pages if page.get("is_html")),
        "failed_pages": sum(1 for page in pages if page.get("status") is None or int(page["status"]) >= 400),
        "robots_blocked_pages": sum(1 for page in pages if page.get("blocked_by_robots")),
        "crawl_limit_reached": len(pages) >= max_pages and bool(queue),
    }
    audit["findings"] = build_findings(audit)
    severity_counts = Counter(item["severity"] for item in audit["findings"])
    audit["summary"]["finding_counts"] = dict(severity_counts)
    return audit


def markdown_report(audit: dict[str, Any]) -> str:
    summary = audit["summary"]
    lines = [
        "# SEO/GEO 巡检报告",
        "",
        f"- 目标站点：{audit['meta']['target']}",
        f"- 开始时间：{audit['meta']['started_at']}",
        f"- 完成时间：{audit['meta']['finished_at']}",
        f"- 抓取页面：{summary['pages_crawled']}（HTML {summary['html_pages']}）",
        f"- 失败页面：{summary['failed_pages']}",
        f"- 达到抓取上限：{'是' if summary['crawl_limit_reached'] else '否'}",
        "",
        "## 问题清单",
        "",
    ]
    for item in audit["findings"]:
        evidence = json.dumps(item["evidence"], ensure_ascii=False, indent=2)
        lines.extend(
            [
                f"### {item['id']} [{item['severity'].upper()}] {item['issue']}",
                "",
                f"- 类别：{item['category']}",
                f"- 状态：{item['status']}",
                f"- 修复：{item['action']}",
                f"- 验收：{item['verification']}",
                "- 证据：",
                "",
                "```json",
                evidence,
                "```",
                "",
            ]
        )
    lines.extend(["## 限制", ""])
    lines.extend(f"- {item}" for item in audit["meta"]["limitations"])
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Public site URL, including http:// or https://")
    parser.add_argument("--max-pages", type=int, default=100, help="Maximum same-origin pages to crawl (default: 100)")
    parser.add_argument("--timeout", type=float, default=10, help="Per-request timeout in seconds")
    parser.add_argument("--delay", type=float, default=0.1, help="Delay between page requests in seconds")
    parser.add_argument("--max-bytes", type=int, default=5_000_000, help="Maximum response bytes read per URL")
    parser.add_argument("--max-sitemaps", type=int, default=10, help="Maximum sitemap files to inspect")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--allow-private", action="store_true", help="Allow private/loopback targets for explicitly authorized local testing")
    parser.add_argument("--json-out", type=Path, help="Write complete audit JSON to this path")
    parser.add_argument("--markdown-out", type=Path, help="Write Markdown findings to this path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.max_pages < 1 or args.max_pages > 5000:
        print("--max-pages must be between 1 and 5000", file=sys.stderr)
        return 2
    try:
        audit = audit_site(
            args.url,
            max_pages=args.max_pages,
            timeout=args.timeout,
            delay=max(0, args.delay),
            max_bytes=args.max_bytes,
            max_sitemaps=args.max_sitemaps,
            user_agent=args.user_agent,
            allow_private=args.allow_private,
        )
    except (ValueError, OSError) as exc:
        print(f"Audit failed: {exc}", file=sys.stderr)
        return 2

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(markdown_report(audit), encoding="utf-8")

    print(
        json.dumps(
            {
                "target": audit["meta"]["target"],
                "summary": audit["summary"],
                "json_out": str(args.json_out) if args.json_out else None,
                "markdown_out": str(args.markdown_out) if args.markdown_out else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
