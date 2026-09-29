"""
Step 1: Pull program names and URLs out of the saved Kutztown A-Z Programs
page (https://www.kutztown.edu/academics/a-z-programs.html).

Output: kutztown_programs.csv (name, url)
"""

import csv

from bs4 import BeautifulSoup

from ku_common import AZ_PROGRAMS_HTML, PROGRAMS_CSV


def extract_program_links(html_file, output_csv):
    with open(html_file, "r", encoding="utf-8-sig") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    rows = []
    seen_urls = set()

    # Each program is an <li class="azProgram"> with an <a class="azProgramLink">
    for li in soup.find_all("li", class_="azProgram"):
        a_tag = li.find("a", class_="azProgramLink")
        if not a_tag or not a_tag.get("href"):
            continue

        url = a_tag["href"].strip()
        if url in seen_urls:
            continue
        seen_urls.add(url)

        rows.append({"name": a_tag.get_text(strip=True), "url": url})

    with open(output_csv, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=["name", "url"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(rows)} records to {output_csv}")


if __name__ == "__main__":
    extract_program_links(AZ_PROGRAMS_HTML, PROGRAMS_CSV)
