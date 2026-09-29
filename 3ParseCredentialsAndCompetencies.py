"""
Step 3: Parse the downloaded program pages into two bulk-upload drafts:

  - kutztown_credentials4.csv   one credential row per Student Learning
                                Outcomes framework found on a page, linked to
                                its framework via a Required Competency
                                Framework condition profile
  - kutztown_competencies4.csv  CTDL-ASN competency frameworks: a framework
                                row followed by one row per outcome

Columns to the right of the standard BU headers (FileName, FrameworkTitle,
PageTitle, ProgramName, DownloadedDate, rawHTML) are review aids only; step 6
drops them.
"""

import csv
import os

from bs4 import BeautifulSoup, Comment

from ku_common import (
    LANGUAGE,
    PARSED_COMPETENCIES_CSV,
    PARSED_CREDENTIALS_CSV,
    PROGRAM_HTML_DIR,
    PUBLISHED_STATUS,
    generate_ctid,
    infer_credential_type,
)


# ---------- HELPERS ----------

def parse_top_comment_metadata(soup):
    """
    Look for the top HTML comment that contains:
      Full URL: ...
      Program Name: ...
      Downloaded: ...
    (written by 2DownloadProgramHTML.py)
    """
    full_url = None
    program_name = None
    downloaded = None

    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        text = str(comment)
        if "Full URL:" in text:
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("Full URL:"):
                    full_url = line.split("Full URL:", 1)[1].strip()
                elif line.startswith("Program Name:"):
                    program_name = line.split("Program Name:", 1)[1].strip()
                elif line.startswith("Downloaded:"):
                    downloaded = line.split("Downloaded:", 1)[1].strip()
            break  # Use the first matching comment

    return {
        "FullURL": full_url or "",
        "ProgramName": program_name or "",
        "DownloadedDate": downloaded or "",
    }

def get_page_title(soup):
    """Get page-level title if present (e.g., <h1 class='headline'>...)."""
    h1 = soup.find("h1", class_="headline")
    return h1.get_text(strip=True) if h1 else ""

def _is_single_column_table(table):
    """
    Return True if the table effectively has a single column:
    - Either only a header row, or
    - All data rows have exactly one cell.
    """
    rows = table.find_all("tr")
    if not rows:
        return False

    for row in rows:
        cells = row.find_all(["th", "td"], recursive=False)
        if cells:
            return len(cells) == 1
    return False


def _table_to_sentence(table):
    """
    Convert a 1-column table into:
    "<header>: item1, item2, ..., and itemN."
    Returns None if it can't build a good sentence.
    """
    rows = table.find_all("tr")
    if not rows:
        return None

    # Header from first <th>, if present
    header_text = ""
    header_cells = rows[0].find_all("th")
    if header_cells:
        header_text = header_cells[0].get_text(" ", strip=True)

    # Items from <td> cells in remaining rows
    items = []
    for row in rows[1:]:
        for td in row.find_all("td"):
            text = td.get_text(" ", strip=True)
            if text:
                items.append(text.rstrip("."))

    if not header_text or not items:
        return None

    if len(items) == 1:
        return f"{header_text}: {items[0]}."

    *others, last = items
    return f"{header_text}: {', '.join(others)}, and {last}."


def _get_column_count(table):
    """
    Determine how many columns a table has by inspecting the first row
    that contains th/td cells.
    """
    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all(["th", "td"], recursive=False)
        if cells:
            return len(cells)
    return 0


STOP_PHRASES = {
    "student learning outcomes",
    "admissions requirements and deadlines",
}

def get_description(soup):
    """
    Extract description text from all htmlArea blocks, stopping when
    'Student Learning Outcomes' appears.

    Also:
    - 1-column tables -> "Header: item1, item2, ..., and itemN."
    - Tables with 3+ columns are skipped entirely.
    - If no description is captured, fall back to meta description tags
      or the first featureText paragraph.
    """

    description_parts = []
    stop_reached = False

    html_areas = soup.find_all("div", class_="htmlArea")
    for area in html_areas:
        if stop_reached:
            break

        # --- Handle tables in this htmlArea ---
        tables = area.find_all("table")
        handled_table_ps = set()

        for table in tables:
            col_count = _get_column_count(table)

            # Skip any table with 3 or more columns
            if col_count >= 3:
                for p in table.find_all("p"):
                    handled_table_ps.add(p)
                continue

            # Single-column table -> special sentence format
            if col_count == 1 and _is_single_column_table(table):
                sentence = _table_to_sentence(table)
                if sentence:
                    description_parts.append(sentence)

                for p in table.find_all("p"):
                    handled_table_ps.add(p)

            else:
                # 2-column tables: ignore for now
                for p in table.find_all("p"):
                    handled_table_ps.add(p)
                continue

        # --- Handle normal paragraphs and bullet lists ---
        for p in area.find_all("p"):
            if p in handled_table_ps:
                continue

            text = p.get_text(" ", strip=True)
            if not text:
                continue

            # STOP condition: Student Learning Outcomes (check BEFORE skipping featureText)
            text_lower = text.lower()
            if any(phrase in text_lower for phrase in STOP_PHRASES):
                stop_reached = True
                break

            # Skip special unwanted sections
            classes = p.get("class") or []
            if "Sample Career Options" in text:
                continue
            if "Degree Information" in text:
                continue
            if "The Department of Music also offers several minors:" in text:
                continue
            if "View Counseling and Student Affairs Admission Requirements" in text:
                continue
            if "View Counseling Admission Requirements" in text:
                continue
            if "exactly what future employers are looking for" in text:
                continue

            # Skip featureText *except* when used as stop phrase (already handled)
            if "featureText" in classes:
                continue

            # Bullet-list pattern: paragraph ending with ":" or "Keep reading."
            if text.endswith(":") or text.endswith("Keep reading."):
                next_list = p.find_next_sibling(["ul", "ol"])
                if next_list:
                    items = [
                        li.get_text(" ", strip=True)
                        for li in next_list.find_all("li")
                        if li.get_text(" ", strip=True)
                    ]

                    if items:
                        header = text.rstrip(":").strip()
                        if len(items) == 1:
                            combined = f"{header}: {items[0]}"
                        else:
                            *others, last = items
                            combined = f"{header}: {', '.join(others)}, and {last}"
                        description_parts.append(combined)
                        continue

            # Default: just include the paragraph text
            description_parts.append(text)

    # If we captured any description, return it
    if description_parts:
        return "\n".join(description_parts).strip()

    # ---------- Fallback logic when description is blank ----------

    # 1) <meta name="description">
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()

    # 2) <meta property="og:description"> or <meta name="og:description">
    og_meta = (
        soup.find("meta", attrs={"property": "og:description"})
        or soup.find("meta", attrs={"name": "og:description"})
    )
    if og_meta and og_meta.get("content"):
        return og_meta["content"].strip()

    # 3) First featureText paragraph as last resort
    feature = soup.find("p", class_="featureText")
    if feature:
        return feature.get_text(" ", strip=True)

    # Nothing found
    return ""

def extract_frameworks_from_file(filepath):
    """
    From one HTML file:
      - Find 'Student Learning Outcomes'
      - For most files, find the following <ul class="accordion">
      - For the special Computer Science page, use the previous <ul class="accordion">
      - Each <li class="accordion-item"> is a framework

    Returns: (soup, list_of_framework_dicts)
    where each framework dict has:
      framework_title, raw_html, competencies (list of texts)
    """
    with open(filepath, "r", encoding="utf-8-sig") as f:
        soup = BeautifulSoup(f, "html.parser")

    frameworks = []

    # Special-case flag for the Computer Science BS page
    filename_only = os.path.basename(filepath)
    is_cs_special = filename_only.lower() == "bachelor-of-science-in-computer-science_html.html"

    # Find all p.featureText and locate "Student Learning Outcomes"
    seen_accordions = set()
    feature_texts = soup.find_all("p", class_="featureText")
    for p in feature_texts:
        if "Student Learning Outcomes" not in p.get_text(strip=True):
            continue

        # NORMAL CASE: accordion comes after the label
        # SPECIAL CASE (CS page): accordion comes before the label
        if is_cs_special:
            accordion = p.find_previous("ul", class_="accordion")
        else:
            accordion = p.find_next("ul", class_="accordion")

        # Skip if missing, or already read via an earlier label on this page
        if not accordion or id(accordion) in seen_accordions:
            continue
        seen_accordions.add(id(accordion))

        # Each accordion-item is a framework
        for item in accordion.find_all("li", class_="accordion-item"):
            title_tag = item.find("a", class_="accordion-title")
            framework_title = title_tag.get_text(strip=True) if title_tag else ""

            content_div = item.find("div", class_="accordion-content")
            if not content_div:
                continue

            # Inner HTML of this framework
            raw_html = "".join(str(child) for child in content_div.contents).strip()

            # Competencies: all <li> inside this accordion-content
            competencies = []
            for li in content_div.find_all("li"):
                text = li.get_text(" ", strip=True)
                if text:
                    competencies.append(text)

            # Fallback: use <p> if no <li> found
            if not competencies:
                for p_tag in content_div.find_all("p"):
                    text = p_tag.get_text(" ", strip=True)
                    if text:
                        competencies.append(text)

            if competencies:
                frameworks.append(
                    {
                        "framework_title": framework_title,
                        "raw_html": raw_html,
                        "competencies": competencies,
                    }
                )

    return soup, frameworks

def get_keywords_pipes(soup):
    """
    Extracts keywords from:
        <meta name="keywords" content="...">
    Splits them by comma, trims whitespace, and returns a pipe-separated string.

    If no keywords meta tag exists, returns an empty string.
    """
    meta = soup.find("meta", attrs={"name": "keywords"})
    if not meta or not meta.get("content"):
        return ""

    raw = meta["content"]

    # Split on commas and strip spaces
    parts = [p.strip() for p in raw.split(",") if p.strip()]

    # Join using pipes
    return "|".join(parts)


# ---------- MAIN PROCESSING ----------

def main():
    credentials_headers_base = [
        "External Identifier", "CTID", "Credential Name", "Credential Type",
        "Description", "Subject Webpage", "Credential Status", "Language", "Keywords",
        "ConditionProfile: External Identifier", "ConditionProfile: Condition Type",
        "Condition Profile: Required Competency Framework"
    ]

    competencies_headers_base = [
        "@id", "@type", "ceasn:description", "ceasn:inLanguage", "ceasn:name",
        "ceasn:publicationStatusType", "ceasn:source", "ceasn:codedNotation",
        "ceasn:competencyCategory", "ceasn:competencyText", "ceasn:isTopChildOf",
        "ceasn:listID"
    ]

    # Extra columns appended on the far right
    credentials_extra_headers = [
        "FileName", "FrameworkTitle", "PageTitle", "ProgramName", "DownloadedDate"
    ]

    competencies_extra_headers = [
        "FileName", "FrameworkTitle", "PageTitle", "ProgramName", "DownloadedDate", "rawHTML"
    ]

    credentials_headers = credentials_headers_base + credentials_extra_headers
    competencies_headers = competencies_headers_base + competencies_extra_headers

    with open(PARSED_CREDENTIALS_CSV, "w", newline="", encoding="utf-8-sig") as cred_file, \
         open(PARSED_COMPETENCIES_CSV, "w", newline="", encoding="utf-8-sig") as comp_file:

        cred_writer = csv.DictWriter(cred_file, fieldnames=credentials_headers)
        comp_writer = csv.DictWriter(comp_file, fieldnames=competencies_headers)

        cred_writer.writeheader()
        comp_writer.writeheader()

        for filename in sorted(os.listdir(PROGRAM_HTML_DIR)):
            if not filename.lower().endswith(".html"):
                continue

            filepath = os.path.join(PROGRAM_HTML_DIR, filename)
            print(f"Processing {filepath}...")

            soup, frameworks = extract_frameworks_from_file(filepath)

            # Page-level & comment metadata
            meta = parse_top_comment_metadata(soup)
            page_title = get_page_title(soup)
            
            description = get_description(soup)
            keywords = get_keywords_pipes(soup)

            for framework_index, fw in enumerate(frameworks, start=1):
                framework_title = fw["framework_title"]
                raw_html = fw["raw_html"]
                competencies = fw["competencies"]

                # Name the credential after the framework (accordion) title,
                # falling back to the page title, then the filename.
                credential_name = (
                    framework_title
                    or page_title
                    or filename
                )

                # Infer credential type using parentheses, prefix, and keyword strategies
                credential_type = infer_credential_type(credential_name)

                # Framework CTID (used both as required CF and as framework @id)
                framework_ctid = generate_ctid()

                # ---------- CREDENTIALS ROW ----------
                credential_ctid = generate_ctid()

                cred_row = {
                    "External Identifier": credential_ctid,
                    "CTID": credential_ctid,
                    "Credential Name": credential_name,
                    "Credential Type": credential_type,
                    "Description": description,
                    "Subject Webpage": meta["FullURL"],
                    "Credential Status": "Active",
                    "Language": LANGUAGE,
                    "Keywords": keywords,
                    "ConditionProfile: External Identifier": generate_ctid(),
                    "ConditionProfile: Condition Type": "requires",
                    "Condition Profile: Required Competency Framework": framework_ctid,
                    # Extra columns on the right:
                    "FileName": filename,
                    "FrameworkTitle": framework_title,
                    "PageTitle": page_title,
                    "ProgramName": meta["ProgramName"],
                    "DownloadedDate": meta["DownloadedDate"],
                }
                cred_writer.writerow(cred_row)

                # ---------- COMPETENCY FRAMEWORK ROW ----------
                framework_row = {
                    "@id": framework_ctid,
                    "@type": "ceasn:CompetencyFramework",
                    "ceasn:description": (
                        "Upon completion, students will be able to demonstrate the following student learning outcomes."
                    ),
                    "ceasn:inLanguage": LANGUAGE,
                    "ceasn:name": f"{credential_name} Student Learning Outcomes",
                    "ceasn:publicationStatusType": PUBLISHED_STATUS,
                    "ceasn:source": meta["FullURL"],
                    "ceasn:codedNotation": "",
                    "ceasn:competencyCategory": "",
                    "ceasn:competencyText": "",
                    "ceasn:isTopChildOf": "",
                    "ceasn:listID": "",
                    # Extra columns:
                    "FileName": filename,
                    "FrameworkTitle": framework_title,
                    "PageTitle": page_title,
                    "ProgramName": meta["ProgramName"],
                    "DownloadedDate": meta["DownloadedDate"],
                    "rawHTML": raw_html,
                }
                comp_writer.writerow(framework_row)

                # ---------- INDIVIDUAL COMPETENCIES ROWS ----------
                for i, outcome_text in enumerate(competencies, start=1):
                    comp_row = {
                        "@id": generate_ctid(),
                        "@type": "ceasn:Competency",
                        "ceasn:description": "",
                        "ceasn:inLanguage": LANGUAGE,
                        "ceasn:name": "",
                        "ceasn:publicationStatusType": "",
                        "ceasn:source": meta["FullURL"],
                        "ceasn:codedNotation": "",
                        "ceasn:competencyCategory": "Student Learning Outcome",
                        "ceasn:competencyText": outcome_text.strip(),
                        "ceasn:isTopChildOf": framework_ctid,
                        "ceasn:listID": str(i),
                        # Extra columns:
                        "FileName": filename,
                        "FrameworkTitle": framework_title,
                        "PageTitle": page_title,
                        "ProgramName": meta["ProgramName"],
                        "DownloadedDate": meta["DownloadedDate"],
                        "rawHTML": raw_html,
                    }
                    comp_writer.writerow(comp_row)

    print("Done.")
    print(f"Credentials written to: {PARSED_CREDENTIALS_CSV}")
    print(f"Competencies written to: {PARSED_COMPETENCIES_CSV}")


if __name__ == "__main__":
    main()
