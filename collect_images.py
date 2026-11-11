#!/usr/bin/env python3
"""Discover image candidates with Edge/Bing, then download a reviewed URL list."""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
from io import BytesIO
import json
import math
from pathlib import Path
import socket
import tempfile
import time
from urllib.parse import urlencode, urljoin, urlsplit

from PIL import Image


def validate_url(url, resolve=False):
    if not isinstance(url, str):
        raise ValueError("URL must be a string")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Only HTTP(S) URLs without embedded credentials are allowed")
    if resolve:
        addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80),
                                       type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError("Local/private network image URLs are not allowed")
    return url


def parse_bing_results(attributes, query):
    records, seen = [], set()
    for raw in attributes:
        try:
            data = json.loads(raw)
            url = validate_url(data["murl"])
            page = data.get("purl", "")
            if page:
                validate_url(page)
        except (TypeError, ValueError, KeyError):
            continue
        if url not in seen:
            records.append({"image_url": url, "source_page": page, "query": query,
                            "license_status": "unreviewed"})
            seen.add(url)
    return records


def search_images(queries, limit):
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    options = webdriver.EdgeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Edge(options=options)
    records, seen = [], set()
    try:
        driver.set_page_load_timeout(30)
        for query in queries:
            driver.get("https://www.bing.com/images/search?" + urlencode({"q": query}))
            # shortcut: Bing's public HTML is unstable; update this selector if markup changes.
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.iusc[m]")))
            candidates = []
            for _ in range(5):
                elements = driver.find_elements(By.CSS_SELECTOR, "a.iusc[m]")
                candidates = parse_bing_results([element.get_attribute("m") for element in elements], query)
                if len(candidates) >= limit:
                    break
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)
            if not candidates:
                raise RuntimeError("No image candidates found; check access/markup or supply a URL list")
            for item in candidates[:limit]:
                if item["image_url"] not in seen:
                    records.append(item)
                    seen.add(item["image_url"])
    finally:
        driver.quit()
    return records


def fetch_image(session, url, max_bytes):
    for _ in range(6):
        validate_url(url, resolve=True)
        with session.get(url, stream=True, timeout=(5, 15), allow_redirects=False) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("Location")
                if not location:
                    raise ValueError("Redirect has no destination")
                url = urljoin(url, location)
                continue
            response.raise_for_status()
            if not response.headers.get("Content-Type", "").lower().startswith("image/"):
                raise ValueError("Response is not an image")
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise ValueError("Image exceeds download size limit")
            return bytes(content), url
    raise ValueError("Too many redirects")


def save_image(content, directory, min_width, min_height):
    formats = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "BMP": ".bmp"}
    with Image.open(BytesIO(content)) as image:
        width, height = image.size
        extension = formats.get(image.format)
        if not extension or getattr(image, "is_animated", False):
            raise ValueError("Expected a non-animated JPEG, PNG, WebP or BMP")
        if width < min_width or height < min_height or width * height > 25_000_000:
            raise ValueError("Image dimensions outside accepted limits")
        image.verify()
    with Image.open(BytesIO(content)) as image:
        image.load()
    digest = hashlib.sha256(content).hexdigest()
    path = Path(directory) / (digest + extension)
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Existing image has different content; refusing to overwrite")
        status = "duplicate"
    else:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(content)
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        status = "downloaded"
    return {"status": status, "file": path.name, "sha256": digest, "width": width, "height": height}


def read_candidates(path):
    records, seen = [], set()
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            url = validate_url(record["image_url"])
            if not all(isinstance(record.get(key, ""), str) for key in ("source_page", "query", "license_status")):
                raise ValueError("Candidate metadata must be text")
            if record.get("source_page"):
                validate_url(record["source_page"])
        except (TypeError, KeyError, ValueError) as exc:
            raise ValueError(f"Invalid candidate on line {number}: {exc}") from exc
        if url not in seen:
            records.append({"image_url": url, "source_page": record.get("source_page", ""),
                            "query": record.get("query", ""),
                            "license_status": record.get("license_status", "unreviewed")})
            seen.add(url)
    if not records:
        raise ValueError("Candidate list is empty")
    return records


def download_images(records, output, session, min_width=800, min_height=600, max_bytes=10 * 1024 * 1024, delay=1):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "manifest.jsonl"
    finished = set()
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("status") in ("downloaded", "duplicate"):
                filename = record["file"]
                if Path(filename).name != filename:
                    raise ValueError("Unsafe filename in manifest")
                path = output / filename
                if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]:
                    finished.add(record["image_url"])
    stats = {"downloaded": 0, "duplicate": 0, "skipped": 0, "failed": 0}
    import requests
    with manifest.open("a", encoding="utf-8") as log:
        for record in records:
            if record["image_url"] in finished:
                stats["skipped"] += 1
                continue
            result = {**record, "collected_at": datetime.now(timezone.utc).isoformat(), "label": None}
            try:
                content, final_url = fetch_image(session, record["image_url"], max_bytes)
                result.update(final_url=final_url, **save_image(content, output, min_width, min_height))
            except (requests.RequestException, OSError, ValueError, Image.DecompressionBombError) as exc:
                result.update(status="failed", error=str(exc))
            stats[result["status"]] += 1
            log.write(json.dumps(result, ensure_ascii=False) + "\n")
            log.flush()
            if result["status"] != "failed":
                finished.add(record["image_url"])
            time.sleep(delay)
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("search", help="Discover URLs only; no image downloads")
    search.add_argument("--query", action="append", required=True)
    search.add_argument("--limit", type=int, default=50)
    search.add_argument("--output", type=Path, default=Path("data/candidates.jsonl"))
    download = commands.add_parser("download", help="Download a reviewed JSONL list")
    download.add_argument("--input", type=Path, required=True)
    download.add_argument("--output", type=Path, default=Path("data/unreviewed"))
    download.add_argument("--min-width", type=int, default=800)
    download.add_argument("--min-height", type=int, default=600)
    download.add_argument("--max-mb", type=float, default=10)
    download.add_argument("--delay", type=float, default=1)
    args = parser.parse_args()
    if args.command == "search":
        if not 1 <= args.limit <= 1000 or any(not q.strip() for q in args.query):
            parser.error("Use nonempty queries and a limit in [1, 1000]")
        if args.output.exists():
            parser.error("Candidate output exists; choose a new path")
        records = search_images(args.query, args.limit)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"Saved {len(records)} candidates to {args.output}; review source pages before download")
    else:
        if args.min_width < 1 or args.min_height < 1 or not math.isfinite(args.max_mb) or args.max_mb <= 0:
            parser.error("Image dimension and size limits must be positive and finite")
        if not math.isfinite(args.delay) or args.delay < 0:
            parser.error("delay must be nonnegative and finite")
        records = read_candidates(args.input)
        import requests
        with requests.Session() as session:
            session.trust_env = False  # Do not send local .netrc credentials to discovered hosts.
            session.headers.update({"User-Agent": "F1VisorResearchCollector/1.0", "Accept": "image/*"})
            stats = download_images(records, args.output, session, args.min_width, args.min_height,
                                    int(args.max_mb * 1024 * 1024), args.delay)
        print(json.dumps(stats))
        if stats["failed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
