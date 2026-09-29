"""
Step 6: Build the final Credential Publisher bulk-upload files from the
hand-reviewed step 5 / step 3 outputs.

Inputs (see README, "Manual review"):
  - KutztownCredentialsPublished_with_matches4_editted.csv
  - kutztown_competencies4_reviewed.csv
  - kutztown_credentials4.csv            (step 3, for Keywords)

Outputs (in Review/):
  - KutztownCredentialsUpdateWithCompetencies.csv   credential update BU
  - kutztown_competencies.csv                       competency framework BU
  - KutztownCredentialsDeprecated.csv               published credentials
                                                    with no match, for follow-up
Upload the competency file first so the frameworks exist before the
credentials that require them.
"""

import pandas as pd

from ku_common import (
    DEPRECATED_CREDENTIALS_CSV,
    ORG_REGISTRY_URI,
    PARSED_CREDENTIALS_CSV,
    REVIEWED_COMPETENCIES_CSV,
    REVIEWED_PUBLISHED_CSV,
    UPLOAD_COMPETENCIES_CSV,
    UPLOAD_CREDENTIALS_CSV,
    UPLOAD_DIR,
    generate_ctid,
)

CRED_COLUMNS = [
    "CTID", "Name", "Credential Type", "Description", "Subject Webpage",
    "Credential Status", "ConditionProfile: External Identifier",
    "ConditionProfile: Condition Type",
    "Condition Profile: Required Competency Framework", "Keywords",
]

COMP_COLUMNS = [
    "@id", "@type", "ceasn:description", "ceasn:inLanguage", "ceasn:name",
    "ceasn:publicationStatusType", "ceasn:source", "ceasn:codedNotation",
    "ceasn:competencyCategory", "ceasn:competencyText", "ceasn:isPartOf",
    "ceasn:listID", "ceasn:publisher",
]

CF_COL = "Condition Profile: Required Competency Framework"


def read_csv(path):
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
    # Drop blank "Unnamed: N" columns Excel leaves behind
    df = df.loc[:, ~df.columns.str.startswith("Unnamed:")]
    return df.apply(lambda s: s.str.strip())


def split_pipes(value):
    return [v.strip() for v in value.split("|") if v.strip()]


# ---------- COMPETENCY FRAMEWORKS ----------

comp = read_csv(REVIEWED_COMPETENCIES_CSV)

# Competencies hang directly off their framework
if "ceasn:isPartOf" not in comp.columns:
    comp = comp.rename(columns={"ceasn:isTopChildOf": "ceasn:isPartOf"})

is_framework = comp["@type"] == "ceasn:CompetencyFramework"
comp["ceasn:publisher"] = ""
comp.loc[is_framework, "ceasn:publisher"] = ORG_REGISTRY_URI

comp_out = comp.reindex(columns=COMP_COLUMNS, fill_value="")
framework_ids = set(comp_out.loc[is_framework, "@id"])


# ---------- CREDENTIALS ----------

published = read_csv(REVIEWED_PUBLISHED_CSV)
is_deprecated = published["Credential Status"].str.lower() == "deprecated"
creds = published[~is_deprecated].copy()

# Keywords are the <meta name="keywords"> of the program page, so look them
# up by the (reviewed) Subject Webpage
parsed = read_csv(PARSED_CREDENTIALS_CSV)
keywords = (
    parsed[parsed["Keywords"] != ""]
    .drop_duplicates(subset=["Subject Webpage"])
    .set_index("Subject Webpage")["Keywords"]
)
creds["Keywords"] = creds["Subject Webpage"].map(keywords).fillna("")

creds["Credential Status"] = "Active"
if CF_COL not in creds.columns:
    creds[CF_COL] = ""
creds["ConditionProfile: External Identifier"] = [generate_ctid() for _ in range(len(creds))]
creds["ConditionProfile: Condition Type"] = "requires"

cred_out = creds.reindex(columns=CRED_COLUMNS, fill_value="")


# ---------- QA ----------

problems = 0

referenced = {cf for v in cred_out[CF_COL] for cf in split_pipes(v)}
missing_frameworks = referenced - framework_ids
if missing_frameworks:
    problems += len(missing_frameworks)
    print(f"ERROR: {len(missing_frameworks)} required frameworks are not in the competency file:")
    for cf in sorted(missing_frameworks):
        print(f"  {cf}")

orphan_competencies = comp_out[~is_framework & ~comp_out["ceasn:isPartOf"].isin(framework_ids)]
if not orphan_competencies.empty:
    problems += len(orphan_competencies)
    print(f"ERROR: {len(orphan_competencies)} competencies point at a framework not in the file")

for col in ["CTID", "Name", "Credential Type", "Description", "Subject Webpage"]:
    n = (cred_out[col] == "").sum()
    if n:
        problems += n
        print(f"WARNING: {n} credentials are missing {col}")

dupes = cred_out["CTID"].duplicated().sum()
if dupes:
    problems += dupes
    print(f"ERROR: {dupes} duplicate credential CTIDs")

unreferenced = framework_ids - referenced
if unreferenced:
    print(f"Note: {len(unreferenced)} frameworks are not required by any credential in this upload")


# ---------- WRITE ----------

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
comp_out.to_csv(UPLOAD_COMPETENCIES_CSV, index=False, encoding="utf-8-sig")
cred_out.to_csv(UPLOAD_CREDENTIALS_CSV, index=False, encoding="utf-8-sig")
published[is_deprecated].to_csv(DEPRECATED_CREDENTIALS_CSV, index=False, encoding="utf-8-sig")

print(f"Competency BU: {len(framework_ids)} frameworks, "
      f"{(~is_framework).sum()} competencies -> {UPLOAD_COMPETENCIES_CSV}")
print(f"Credential BU: {len(cred_out)} credentials, "
      f"{(cred_out[CF_COL] != '').sum()} with a required framework -> {UPLOAD_CREDENTIALS_CSV}")
print(f"Deprecated (not uploaded): {is_deprecated.sum()} -> {DEPRECATED_CREDENTIALS_CSV}")
if problems:
    print(f"{problems} QA problems found; fix them before uploading.")
