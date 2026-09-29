"""
Step 5: Match each parsed credential (step 3) to a credential already in the
Registry (step 4) by fuzzy name matching, so updates go to existing CTIDs
instead of creating duplicates.

Outputs:
  - kutztown_credentials_with_ctid4.csv
        step 3 credentials with MatchedName, MatchScore, and the matched
        published CTID (blank when the best score is under THRESHOLD)
  - KutztownCredentialsPublished_with_matches4.csv
        copy of the published list with Description, Subject Webpage,
        Keywords, and Required Competency Framework filled in from the
        matched parsed row. Published credentials with no match are marked
        Credential Status = Deprecated.

Review both files by hand before running step 6 (see README).
"""

import pandas as pd
from rapidfuzz import fuzz, process

from ku_common import (
    MATCHED_CREDENTIALS_CSV,
    PARSED_CREDENTIALS_CSV,
    PUBLISHED_CREDENTIALS_CSV,
    PUBLISHED_WITH_MATCHES_CSV,
)

# Minimum token_set_ratio score to accept a match
THRESHOLD = 40

df_creds = pd.read_csv(PARSED_CREDENTIALS_CSV, dtype=str, encoding="utf-8-sig").fillna("")
df_all = pd.read_csv(PUBLISHED_CREDENTIALS_CSV, dtype=str, encoding="utf-8-sig").fillna("")


# ---------- HELPER FUNCTIONS ----------

def infer_ce_type(cred_type: str) -> str | None:
    """
    Map BU Credential Type values like 'BachelorOfScienceDegree' to the
    Registry class ('ceterms:BachelorDegree') to narrow match candidates.
    """
    lt = (cred_type or "").lower()
    if "bachelor" in lt:
        return "ceterms:BachelorDegree"
    if "associate" in lt:
        return "ceterms:AssociateDegree"
    if "master" in lt:
        return "ceterms:MasterDegree"
    if "doctor" in lt or "doctoral" in lt or "phd" in lt:
        return "ceterms:DoctoralDegree"
    if "certificate" in lt:
        return "ceterms:Certificate"
    return None


def build_query_string(row: pd.Series) -> str:
    """Combine the most useful text fields into one string to match on."""
    pieces = [
        row.get("Credential Name", ""),
        row.get("ProgramName", ""),
        row.get("FrameworkTitle", ""),
        row.get("Description", ""),
        row.get("Subject Webpage", ""),
    ]
    return " | ".join(p.strip() for p in pieces if p and p.strip())


df_creds["_match_query"] = df_creds.apply(build_query_string, axis=1)
df_creds["_ce_type"] = df_creds["Credential Type"].apply(infer_ce_type)


# ---------- MATCHING ----------

best_match_names = []
best_match_ctids = []
best_match_scores = []

for _, row in df_creds.iterrows():
    query = row["_match_query"]
    ce_type = row["_ce_type"]

    if not query.strip():
        best_match_names.append("")
        best_match_ctids.append("")
        best_match_scores.append(0)
        continue

    # Narrow candidates by credential type when we can; fall back to all
    candidates_df = df_all
    if ce_type:
        typed = df_all[df_all["Type"] == ce_type]
        if not typed.empty:
            candidates_df = typed

    # token_set_ratio handles reordered words and extra text reasonably well
    match_name, score, match_idx = process.extractOne(
        query,
        candidates_df["Name"].tolist(),
        scorer=fuzz.token_set_ratio,
    )

    best_match_names.append(match_name)
    best_match_ctids.append(candidates_df.iloc[match_idx]["CTID"])
    best_match_scores.append(score)

df_creds["MatchedName"] = best_match_names
df_creds["MatchScore"] = best_match_scores
df_creds["CTID"] = best_match_ctids

# Drop matches below the threshold
below = df_creds["MatchScore"] < THRESHOLD
df_creds.loc[below, "CTID"] = ""
df_creds.loc[below, "MatchedName"] = ""

df_creds.to_csv(MATCHED_CREDENTIALS_CSV, encoding="utf-8-sig", index=False)
print(f"Done! Wrote {len(df_creds)} rows to {MATCHED_CREDENTIALS_CSV}")
print(f"  {below.sum()} rows scored under {THRESHOLD} and were left unmatched")


# ---------- UPDATED COPY OF THE PUBLISHED LIST ----------

# Fields to carry from the parsed row onto the matched published credential
transfer_cols = [
    "CTID",
    "Description",
    "Subject Webpage",
    "Keywords",
    "Condition Profile: Required Competency Framework",
]
transfer_cols = [c for c in transfer_cols if c in df_creds.columns]

df_matches = df_creds[df_creds["CTID"] != ""]

# A published credential can match several parsed rows (e.g. a degree page
# with a core framework and a concentration framework). Keep the first row's
# text fields, but link every matched framework.
df_transfer = df_matches[transfer_cols].drop_duplicates(subset=["CTID"]).set_index("CTID")
cf_col = "Condition Profile: Required Competency Framework"
if cf_col in df_matches.columns:
    df_transfer[cf_col] = (
        df_matches.groupby("CTID")[cf_col]
        .agg(lambda s: "|".join(dict.fromkeys(v for v in s if v)))
    )
df_transfer = df_transfer.reset_index()

df_all_out = df_all.copy()
if "Credential Status" not in df_all_out.columns:
    df_all_out["Credential Status"] = ""

# Published credentials with no parsed match are no longer on the website
mask_deprecated = ~df_all_out["CTID"].isin(set(df_transfer["CTID"]))
df_all_out.loc[mask_deprecated, "Credential Status"] = "Deprecated"

df_all_out = df_all_out.merge(df_transfer, on="CTID", how="left", suffixes=("", "_from_match"))

# Prefer the value from the match when present
for col in transfer_cols[1:]:
    col_match = col + "_from_match"
    if col_match in df_all_out.columns:
        from_match = df_all_out[col_match].fillna("")
        df_all_out[col] = from_match.where(from_match != "", df_all_out[col].fillna(""))
        df_all_out.drop(columns=[col_match], inplace=True)

df_all_out = df_all_out.fillna("")
df_all_out.to_csv(PUBLISHED_WITH_MATCHES_CSV, encoding="utf-8-sig", index=False)

print(f"Done! Wrote {len(df_all_out)} rows to {PUBLISHED_WITH_MATCHES_CSV}")
print(f"  {mask_deprecated.sum()} published credentials had no match and are marked Deprecated")
