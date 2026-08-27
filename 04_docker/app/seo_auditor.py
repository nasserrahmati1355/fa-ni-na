from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from ipaddress import ip_address
import os
import re
import socket
import time
from typing import Iterable
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
import requests


ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
SKIPPED_EXTENSIONS = {
    ".7z", ".avi", ".bmp", ".css", ".csv", ".doc", ".docx", ".eot",
    ".exe", ".gif", ".gz", ".ico", ".jpeg", ".jpg", ".js", ".json",
    ".m4a", ".m4v", ".mov", ".mp3", ".mp4", ".mpeg", ".ogg", ".pdf",
    ".png", ".ppt", ".pptx", ".rar", ".rss", ".svg", ".tar", ".tgz",
    ".tif", ".tiff", ".ttf", ".txt", ".wav", ".webm", ".webp", ".woff",
    ".woff2", ".xls", ".xlsx", ".xml", ".zip",
}

USER_AGENT = os.getenv(
    "SEO_AUDITOR_USER_AGENT",
    "DevOpsSeoAuditor/1.0 (+https://myapp.test)",
)
REQUEST_TIMEOUT_SECONDS = float(os.getenv("SEO_REQUEST_TIMEOUT_SECONDS", "5"))
MAX_RESPONSE_BYTES = int(os.getenv("SEO_MAX_RESPONSE_BYTES", "2000000"))
MAX_REDIRECTS = int(os.getenv("SEO_MAX_REDIRECTS", "5"))
MAX_ALLOWED_PAGES = int(os.getenv("SEO_MAX_PAGES", "25"))
CRAWL_DELAY_SECONDS = float(os.getenv("SEO_CRAWL_DELAY_SECONDS", "0.15"))


class AuditError(ValueError):
    """Raised when an audit target is invalid or cannot be fetched safely."""


@dataclass(slots=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    text: str
    response_time_ms: int
    body_truncated: bool


@dataclass(slots=True)
class PageAudit:
    requested_url: str
    url: str
    status_code: int | None
    response_time_ms: int | None
    title: str
    h1_count: int
    meta_description: str
    canonical: str
    noindex: bool
    issues: list[str]
    sources: list[str]
    error: str | None = None


@dataclass(slots=True)
class AuditReport:
    target_url: str
    root_url: str
    checked_at: str
    elapsed_ms: int
    pages: list[PageAudit]
    summary: dict[str, int]
    truncated: bool
    max_pages: int


def normalize_start_url(raw_url: str) -> str:
    value = (raw_url or "").strip()
    if not value:
        raise AuditError("آدرس سایت را وارد کنید.")

    if "://" not in value:
        value = f"https://{value}"

    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise AuditError("ساختار URL معتبر نیست.") from exc

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise AuditError("فقط آدرس‌های HTTP و HTTPS مجاز هستند.")

    if parts.username or parts.password:
        raise AuditError("URL دارای نام کاربری یا رمز عبور قابل بررسی نیست.")

    hostname = parts.hostname
    if not hostname:
        raise AuditError("URL باید دارای نام دامنه باشد.")

    if port is not None and port not in ALLOWED_PORTS:
        raise AuditError("برای جلوگیری از Port Scanning فقط پورت‌های 80 و 443 مجازند.")

    try:
        ip_address(hostname.split("%", maxsplit=1)[0])
    except ValueError:
        pass
    else:
        raise AuditError("برای کاهش ریسک SSRF، URL باید نام دامنه داشته باشد و IP مستقیم مجاز نیست.")

    hostname_ascii = hostname.encode("idna").decode("ascii").lower()
    if hostname_ascii in {"localhost", "localhost.localdomain"}:
        raise AuditError("بررسی localhost یا آدرس‌های داخلی مجاز نیست.")

    netloc = hostname_ascii
    if port is not None:
        netloc = f"{hostname_ascii}:{port}"

    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def _site_host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _validate_public_destination(url: str) -> None:
    parts = urlsplit(url)
    hostname = parts.hostname
    if not hostname:
        raise AuditError("نام دامنه URL مشخص نیست.")

    port = parts.port or (443 if parts.scheme == "https" else 80)

    try:
        addresses = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise AuditError(f"نام دامنه Resolve نشد: {hostname}") from exc

    if not addresses:
        raise AuditError(f"هیچ IPای برای دامنه {hostname} پیدا نشد.")

    resolved_ips: set[str] = set()
    for address in addresses:
        raw_ip = address[4][0].split("%", maxsplit=1)[0]
        resolved_ips.add(raw_ip)

    for raw_ip in resolved_ips:
        parsed_ip = ip_address(raw_ip)
        if not parsed_ip.is_global:
            raise AuditError(
                "برای جلوگیری از SSRF، دامنه‌هایی که به IP خصوصی، Loopback، "
                f"Link-local یا Reserved Resolve می‌شوند مجاز نیستند: {raw_ip}"
            )


def _read_limited_html(response: requests.Response) -> tuple[str, bool]:
    content_length = response.headers.get("Content-Length")
    declared_too_large = False
    if content_length:
        try:
            declared_too_large = int(content_length) > MAX_RESPONSE_BYTES
        except ValueError:
            declared_too_large = False

    chunks: list[bytes] = []
    total = 0
    truncated = declared_too_large

    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        remaining = MAX_RESPONSE_BYTES - total
        if remaining <= 0:
            truncated = True
            break
        if len(chunk) > remaining:
            chunks.append(chunk[:remaining])
            total += remaining
            truncated = True
            break
        chunks.append(chunk)
        total += len(chunk)

    raw_body = b"".join(chunks)
    encoding = response.encoding or "utf-8"
    return raw_body.decode(encoding, errors="replace"), truncated


def safe_fetch(session: requests.Session, requested_url: str) -> FetchResult:
    current_url = normalize_start_url(requested_url)
    started_at = time.monotonic()

    for _ in range(MAX_REDIRECTS + 1):
        _validate_public_destination(current_url)

        try:
            response = session.get(
                current_url,
                allow_redirects=False,
                timeout=(3, REQUEST_TIMEOUT_SECONDS),
                stream=True,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                },
            )
        except requests.RequestException as exc:
            raise AuditError(f"دریافت URL ناموفق بود: {exc}") from exc

        with response:
            if response.status_code in REDIRECT_STATUS_CODES:
                location = response.headers.get("Location")
                if not location:
                    raise AuditError("پاسخ Redirect فاقد Header مربوط به Location است.")
                current_url = normalize_start_url(urljoin(current_url, location))
                continue

            content_type = response.headers.get("Content-Type", "").lower()
            text = ""
            body_truncated = False
            if "text/html" in content_type or "application/xhtml+xml" in content_type:
                text, body_truncated = _read_limited_html(response)

            return FetchResult(
                requested_url=requested_url,
                final_url=current_url,
                status_code=response.status_code,
                content_type=content_type,
                text=text,
                response_time_ms=int((time.monotonic() - started_at) * 1000),
                body_truncated=body_truncated,
            )

    raise AuditError(f"تعداد Redirectها بیشتر از حد مجاز {MAX_REDIRECTS} است.")


def _first_meta_content(soup: BeautifulSoup, name: str) -> str:
    tag = soup.find("meta", attrs={"name": re.compile(rf"^{re.escape(name)}$", re.I)})
    if not tag:
        return ""
    return str(tag.get("content") or "").strip()


def _canonical_url(soup: BeautifulSoup, page_url: str) -> str:
    for tag in soup.find_all("link"):
        rel = tag.get("rel") or []
        rel_values = [str(item).lower() for item in rel]
        if "canonical" in rel_values:
            href = str(tag.get("href") or "").strip()
            return urljoin(page_url, href) if href else ""
    return ""


def _extract_internal_links(
    soup: BeautifulSoup,
    page_url: str,
    root_host: str,
) -> list[str]:
    links: set[str] = set()

    for tag in soup.find_all("a", href=True):
        href = str(tag.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue

        absolute_url, _ = urldefrag(urljoin(page_url, href))
        try:
            normalized = normalize_start_url(absolute_url)
        except AuditError:
            continue

        if _site_host(normalized) != root_host:
            continue

        path = urlsplit(normalized).path.lower()
        if any(path.endswith(extension) for extension in SKIPPED_EXTENSIONS):
            continue

        links.add(normalized)

    return sorted(links)


def analyze_html_document(
    page_url: str,
    html: str,
    root_host: str,
) -> tuple[dict[str, object], list[str]]:
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1_count = len(soup.find_all("h1"))
    meta_description = _first_meta_content(soup, "description")
    robots_content = _first_meta_content(soup, "robots").lower()
    canonical = _canonical_url(soup, page_url)
    noindex = "noindex" in {item.strip() for item in robots_content.split(",") if item.strip()}

    issues: list[str] = []
    if not title:
        issues.append("Title ندارد")
    elif len(title) < 30:
        issues.append("Title کوتاه‌تر از معیار داخلی 30 کاراکتر است")
    elif len(title) > 60:
        issues.append("Title بلندتر از معیار داخلی 60 کاراکتر است")

    if h1_count == 0:
        issues.append("H1 ندارد")
    elif h1_count > 1:
        issues.append("بیش از یک H1 دارد")

    if not meta_description:
        issues.append("Meta Description ندارد")
    elif len(meta_description) < 70:
        issues.append("Meta Description کوتاه‌تر از معیار داخلی 70 کاراکتر است")
    elif len(meta_description) > 160:
        issues.append("Meta Description بلندتر از معیار داخلی 160 کاراکتر است")

    if not canonical:
        issues.append("Canonical ندارد")
    if noindex:
        issues.append("صفحه دارای noindex است")

    details: dict[str, object] = {
        "title": title,
        "h1_count": h1_count,
        "meta_description": meta_description,
        "canonical": canonical,
        "noindex": noindex,
        "issues": issues,
    }
    return details, _extract_internal_links(soup, page_url, root_host)


def _unique_sources(values: Iterable[str]) -> list[str]:
    return sorted(set(values))


def audit_site(raw_url: str, max_pages: int = 10) -> AuditReport:
    started_at = time.monotonic()
    start_url = normalize_start_url(raw_url)
    _validate_public_destination(start_url)

    page_limit = max(1, min(int(max_pages), MAX_ALLOWED_PAGES))
    queue: deque[str] = deque([start_url])
    queued = {start_url}
    visited: set[str] = set()
    sources: defaultdict[str, set[str]] = defaultdict(set)
    pages: list[PageAudit] = []
    root_host: str | None = None
    root_url = start_url

    session = requests.Session()
    session.trust_env = False

    try:
        while queue and len(pages) < page_limit:
            requested_url = queue.popleft()
            if requested_url in visited:
                continue
            visited.add(requested_url)

            if len(visited) > 1 and CRAWL_DELAY_SECONDS > 0:
                time.sleep(CRAWL_DELAY_SECONDS)

            try:
                fetched = safe_fetch(session, requested_url)
            except AuditError as exc:
                pages.append(
                    PageAudit(
                        requested_url=requested_url,
                        url=requested_url,
                        status_code=None,
                        response_time_ms=None,
                        title="",
                        h1_count=0,
                        meta_description="",
                        canonical="",
                        noindex=False,
                        issues=["خطای دریافت URL"],
                        sources=_unique_sources(sources[requested_url]),
                        error=str(exc),
                    )
                )
                continue

            if root_host is None:
                root_host = _site_host(fetched.final_url)
                root_url = fetched.final_url

            issues: list[str] = []
            title = ""
            h1_count = 0
            meta_description = ""
            canonical = ""
            noindex = False

            if fetched.status_code == 404:
                issues.append("لینک 404")
            elif fetched.status_code >= 400:
                issues.append(f"خطای HTTP {fetched.status_code}")

            if fetched.final_url != requested_url:
                issues.append("Redirect شده است")

            if root_host is not None and _site_host(fetched.final_url) != root_host:
                issues.append("به دامنه‌ای خارج از سایت Redirect شده است")
            elif fetched.text and fetched.status_code < 400:
                details, discovered_links = analyze_html_document(
                    fetched.final_url,
                    fetched.text,
                    root_host,
                )
                title = str(details["title"])
                h1_count = int(details["h1_count"])
                meta_description = str(details["meta_description"])
                canonical = str(details["canonical"])
                noindex = bool(details["noindex"])
                issues.extend(details["issues"])  # type: ignore[arg-type]

                if fetched.body_truncated:
                    issues.append("بدنه HTML به دلیل محدودیت حجم ناقص خوانده شد")

                for link in discovered_links:
                    sources[link].add(fetched.final_url)
                    if link not in visited and link not in queued:
                        queue.append(link)
                        queued.add(link)
            elif fetched.status_code < 400:
                issues.append("محتوا HTML نیست")

            pages.append(
                PageAudit(
                    requested_url=requested_url,
                    url=fetched.final_url,
                    status_code=fetched.status_code,
                    response_time_ms=fetched.response_time_ms,
                    title=title,
                    h1_count=h1_count,
                    meta_description=meta_description,
                    canonical=canonical,
                    noindex=noindex,
                    issues=issues,
                    sources=_unique_sources(sources[requested_url]),
                )
            )

    finally:
        session.close()

    summary = {
        "pages_checked": len(pages),
        "not_found_links": sum(page.status_code == 404 for page in pages),
        "http_errors": sum(
            page.status_code is not None and page.status_code >= 400
            for page in pages
        ),
        "fetch_errors": sum(page.error is not None for page in pages),
        "pages_without_h1": sum(
            page.status_code is not None
            and page.status_code < 400
            and page.h1_count == 0
            and "محتوا HTML نیست" not in page.issues
            for page in pages
        ),
        "pages_with_multiple_h1": sum(page.h1_count > 1 for page in pages),
        "pages_without_title": sum(
            page.status_code is not None
            and page.status_code < 400
            and not page.title
            and "محتوا HTML نیست" not in page.issues
            for page in pages
        ),
        "pages_without_meta": sum(
            page.status_code is not None
            and page.status_code < 400
            and not page.meta_description
            and "محتوا HTML نیست" not in page.issues
            for page in pages
        ),
        "noindex_pages": sum(page.noindex for page in pages),
        "total_issues": sum(len(page.issues) for page in pages),
    }

    return AuditReport(
        target_url=start_url,
        root_url=root_url,
        checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        elapsed_ms=int((time.monotonic() - started_at) * 1000),
        pages=pages,
        summary=summary,
        truncated=bool(queue),
        max_pages=page_limit,
    )
