"""
Step 8: Download every learning opportunity (courses, learning programs, ...)
Kutztown already has in the Credential Registry, via the Credential Engine
Assistant Search API, so step 9 can reuse their CTIDs instead of publishing
duplicates.

Requires an API token in the environment (same as step 4):
    export CE_ASSISTANT_API_TOKEN=your-token-here

Output: KutztownCoursesPublished.csv
"""

import csv
import os
import sys

import requests

from ku_common import ORG_CTID, PUBLISHED_COURSES_CSV

SEARCH_URL = "https://apps.credentialengine.org/assistant/search/ctdl"
PAGE_SIZE = 100

HEADERS_OUT = [
    "ID", "Type", "CTID", "Name", "Coded Notation", "Subject Webpage",
    "Credit Value", "Credit Unit Type", "Life Cycle Status", "Description",
]


def fetch_page(session, skip, take=PAGE_SIZE):
    query_payload = {
        "Query": {
            "@type": {
                "search:value": "ceterms:LearningOpportunityProfile",
                "search:matchType": "search:subClassOf",
            },
            "ceterms:ownedBy": [{"ceterms:ctid": ORG_CTID}],
        },
        "Skip": skip,
        "Take": take,
    }
    response = session.post(SEARCH_URL, json=query_payload, timeout=60)
    response.raise_for_status()
    return response.json()


def first(values):
    """First element of a list, or {} if missing/empty."""
    return values[0] if isinstance(values, list) and values else {}


def en(value):
    """Pull the English string out of a language map."""
    if isinstance(value, dict):
        return value.get("en-US") or value.get("en") or next(iter(value.values()), "")
    return value or ""


def to_row(item):
    credit = first(item.get("ceterms:creditValue"))
    unit = first(credit.get("ceterms:creditUnitType")) if isinstance(
        credit.get("ceterms:creditUnitType"), list) else credit.get("ceterms:creditUnitType") or {}
    status = item.get("ceterms:lifeCycleStatusType") or {}
    return [
        item.get("@id", ""),
        item.get("@type", "").replace("ceterms:", ""),
        item.get("ceterms:ctid", ""),
        en(item.get("ceterms:name")),
        item.get("ceterms:codedNotation", ""),
        item.get("ceterms:subjectWebpage", ""),
        credit.get("schema:value", ""),
        (unit.get("ceterms:targetNode", "") if isinstance(unit, dict) else "").split(":")[-1],
        en(status.get("ceterms:targetNodeName")) if isinstance(status, dict) else "",
        en(item.get("ceterms:description"))[:300],
    ]


def main():
    token = os.environ.get("CE_ASSISTANT_API_TOKEN")
    if not token:
        sys.exit("Set the CE_ASSISTANT_API_TOKEN environment variable first.")

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    all_data = []
    skip = 0
    while True:
        print(f"Fetching data, skip={skip}")
        batch = fetch_page(session, skip).get("data") or []
        if not batch:
            break
        all_data.extend(batch)
        skip += PAGE_SIZE

    with open(PUBLISHED_COURSES_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS_OUT)
        writer.writerows(to_row(item) for item in all_data)

    courses = sum(1 for item in all_data if item.get("@type") == "ceterms:Course")
    print(f"Saved {len(all_data)} learning opportunities ({courses} courses) to {PUBLISHED_COURSES_CSV}")


if __name__ == "__main__":
    main()
