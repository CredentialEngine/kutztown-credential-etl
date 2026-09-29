"""
Step 4: Download every credential Kutztown already has in the Credential
Registry, via the Credential Engine Assistant Search API.

Requires an API token in the environment:
    export CE_ASSISTANT_API_TOKEN=your-token-here

Output: KutztownCredentialsAll.csv
"""

import csv
import os
import sys

import requests

from ku_common import ORG_CTID, PUBLISHED_CREDENTIALS_CSV, infer_credential_type

SEARCH_URL = "https://apps.credentialengine.org/assistant/search/ctdl"
PAGE_SIZE = 100

# Name-inferred types that may replace the Registry class in the
# "Credential Type" column. Other inferences (e.g. BachelorOfFineArtsDegree,
# PostBaccalaureateCertificate) fall back to the generic Registry class,
# matching what was previously published.
NAME_TYPE_ALLOWLIST = {
    "BachelorOfArtsDegree", "BachelorOfScienceDegree", "BachelorDegree",
    "MasterOfArtsDegree", "MasterOfScienceDegree", "MasterDegree",
    "DoctoralDegree", "Certificate",
}

HEADERS_OUT = [
    "ID", "Type", "CTID", "Name", "Credential Type", "Owned By",
    "Requires - Name", "Requires - Asserted By", "Requires - Credit Value",
    "Requires - Credit Description", "Description", "Subject Webpage",
    "TargetNode", "TargetNodeName",
]


def fetch_page(session, skip, take=PAGE_SIZE):
    query_payload = {
        "Query": {
            "@type": {
                "search:value": "ceterms:Credential",
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
    requires = first(item.get("ceterms:requires"))
    credit = first(requires.get("ceterms:creditValue"))
    status = item.get("ceterms:credentialStatusType") or {}
    ctdl_type = item.get("@type", "")
    name = en(item.get("ceterms:name"))
    name_type = infer_credential_type(name)
    if name_type not in NAME_TYPE_ALLOWLIST:
        name_type = ""

    return [
        item.get("@id", ""),
        ctdl_type,
        item.get("ceterms:ctid", ""),
        name,
        # BU credential type: prefer the more specific type implied by the
        # name (e.g. BachelorOfArtsDegree), else the Registry class
        name_type or ctdl_type.replace("ceterms:", ""),
        "|".join(item.get("ceterms:ownedBy", [])),
        en(requires.get("ceterms:name")),
        "|".join(requires.get("ceterms:assertedBy", [])),
        credit.get("schema:value", ""),
        en(credit.get("schema:description")),
        en(item.get("ceterms:description")),
        item.get("ceterms:subjectWebpage", ""),
        status.get("ceterms:targetNode", ""),
        en(status.get("ceterms:targetNodeName")),
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

    with open(PUBLISHED_CREDENTIALS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS_OUT)
        writer.writerows(to_row(item) for item in all_data)

    print(f"Saved {len(all_data)} credentials to {PUBLISHED_CREDENTIALS_CSV}")


if __name__ == "__main__":
    main()
