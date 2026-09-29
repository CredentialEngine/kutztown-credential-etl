"""
Step 2: Download each program page listed in kutztown_programs.csv.

Each page is saved to programHTML/<last-url-segment>.html with an HTML
comment prepended recording the source URL, program name, and download
date. Step 3 reads that comment back.

Pages that already exist on disk are skipped, so the script can be re-run
to resume an interrupted download.
"""

import csv
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests

from ku_common import PROGRAM_HTML_DIR, PROGRAMS_CSV

BASE_URL = "https://www.kutztown.edu/"

# Browser-like headers
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


def sanitize_filename(name: str) -> str:
    """Keep letters, numbers, dashes, and underscores."""
    name = name.strip().replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_\-]", "_", name)
    return name or "program"


def get_last_folder_from_url(url: str, fallback: str) -> str:
    """
    Extract the last path segment from the URL.
      https://www.example.com/a/b/c/      -> c
      https://www.example.com/a/b/c.html  -> c_html (after sanitizing)
    """
    path = urlparse(url).path.rstrip("/")
    last_segment = path.split("/")[-1] if path else ""
    return last_segment or fallback


def download_program_pages(csv_file, output_folder):
    output_folder.mkdir(parents=True, exist_ok=True)

    # Step 1 writes utf-8-sig; reading it the same way keeps the BOM out of
    # the first header name
    with open(csv_file, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    session = requests.Session()
    session.headers.update(HEADERS)

    count = 0
    for idx, row in enumerate(rows, start=1):
        url = (row.get("url") or "").strip()
        program_name = (row.get("name") or "").strip() or f"program_{idx}"

        if not url:
            print(f"[{idx}] Skipping row (no URL).")
            continue
        url = urljoin(BASE_URL, url)

        base_name = sanitize_filename(get_last_folder_from_url(url, f"program_{idx}"))
        filepath = output_folder / f"{base_name}.html"

        if filepath.exists():
            print(f"[{idx}] Skipping (already exists): {filepath}")
            continue

        try:
            print(f"[{idx}] Downloading: {url}")
            response = session.get(url, timeout=20)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"[{idx}] ERROR downloading {url}: {e}")
            continue

        header_comment = (
            "<!--\n"
            f"Full URL: {url}\n"
            f"Program Name: {program_name}\n"
            f"Downloaded: {datetime.now():%Y-%m-%d}\n"
            "-->\n"
        )
        filepath.write_text(header_comment + response.text, encoding="utf-8")

        print(f"[{idx}] Saved to: {filepath}")
        count += 1

        # Be polite: small delay between requests
        time.sleep(1)

    print(f"Done. Downloaded {count} pages into {output_folder}")


if __name__ == "__main__":
    download_program_pages(PROGRAMS_CSV, PROGRAM_HTML_DIR)
