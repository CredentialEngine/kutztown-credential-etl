"""
Step 9: Build the course bulk-upload file from the hand-reviewed step 7 output.

CTIDs: a course keeps its existing CTID when one is known, matched on course
code (External Identifier / Coded Notation), from
  1. courses already in the Registry (step 8), then
  2. the previous run's upload file (Review/KutztownCourses.csv), for courses
     uploaded but not yet published.
Other courses get a new CTID ("ce-" + random UUID v4). The crosswalk used is
saved for the record.

Inputs:  kutztown_courses_reviewed.csv              (see README, "Course review")
         KutztownCoursesPublished.csv               (step 8, optional)
         LearningOpportunity_Bulk_Upload_Template.csv (optional Publisher template;
                                                     sets the upload columns)
Outputs (in Review/):
  - KutztownCourses.csv                course BU (Learning Type = Course)
  - KutztownCourses_QA.csv             one row per issue
  - KutztownCourses_QA_summary.md      counts, credit coverage, issues by type
  - KutztownCourses_CTID_crosswalk.csv course code -> CTID, with source
  - KutztownCoursesNotInCatalog.csv    published courses missing from the
                                       catalog, for follow-up (not uploaded)
"""

import csv
import re

from catalog2ctdl.config import load_config, validate
from catalog2ctdl.pipeline import read_csv, write_csv
from catalog2ctdl.qa import QA_COLUMNS, run_qa, summary_markdown
from catalog2ctdl.transform import drop_empty_columns, to_bulk_upload

from ku_common import (
    COURSE_CTID_CROSSWALK_CSV,
    COURSE_PROFILE,
    COURSE_QA_CSV,
    COURSE_QA_SUMMARY_MD,
    COURSE_TEMPLATE_CSV,
    COURSES_NOT_IN_CATALOG_CSV,
    ORG_CTID,
    PUBLISHED_COURSES_CSV,
    REVIEWED_COURSES_CSV,
    UPLOAD_COURSES_CSV,
    UPLOAD_DIR,
)

CODE_AT_START = re.compile(r"^\s*([A-Z]{2,5})[\s-]?(\d{1,4}[A-Z]?)\b")


def norm_code(value):
    return " ".join((value or "").upper().split())


def published_code(row):
    """Course code of a published record in "ACCT 121" form, from Coded Notation
    ("ACCT 121", "ACCT-121", "ACCT121") or else the start of the name
    ("ACCT 121: Financial Accounting")."""
    for text in (row.get("Coded Notation", ""), row.get("Name", "")):
        m = CODE_AT_START.match(text.upper())
        if m:
            return f"{m.group(1)} {m.group(2)}"
    return ""


def build_crosswalk():
    """Return {External Identifier: (CTID, source)} and the published course rows."""
    crosswalk = {}
    published = []
    if PUBLISHED_COURSES_CSV.exists():
        published = [r for r in read_csv(PUBLISHED_COURSES_CSV) if r.get("Type") == "Course"]
        for r in published:
            code = published_code(r)
            if code and r.get("CTID") and code not in crosswalk:
                crosswalk[code] = (r["CTID"], "registry")
    else:
        print(f"Note: {PUBLISHED_COURSES_CSV.name} not found; run step 8 to reuse published CTIDs")
    if UPLOAD_COURSES_CSV.exists():
        for r in read_csv(UPLOAD_COURSES_CSV):
            key = norm_code(r.get("External Identifier"))
            if key and r.get("CTID") and key not in crosswalk:
                crosswalk[key] = (r["CTID"], "previous upload")
    return crosswalk, published


def main():
    if not REVIEWED_COURSES_CSV.exists():
        raise SystemExit(f"{REVIEWED_COURSES_CSV.name} not found. Review the step 7 output "
                         "and save it under that name (see README).")

    crosswalk, published = build_crosswalk()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with open(COURSE_CTID_CROSSWALK_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["External Identifier", "CTID", "Source"])
        w.writerows([k, v[0], v[1]] for k, v in sorted(crosswalk.items()))

    overrides = {
        "organization": {"ctid": ORG_CTID},
        "transform": {"ctid_crosswalk": str(COURSE_CTID_CROSSWALK_CSV) if crosswalk else None},
    }
    if COURSE_TEMPLATE_CSV.exists():
        overrides["transform"]["template_csv"] = str(COURSE_TEMPLATE_CSV)
    cfg = load_config(COURSE_PROFILE, overrides)
    warnings = validate(cfg)
    for warning in warnings:
        print(f"warning: {warning}")

    courses = read_csv(REVIEWED_COURSES_CSV)
    bu_rows, notes, columns, ctid_stats = to_bulk_upload(courses, cfg)
    report = run_qa(courses, bu_rows, notes)
    all_columns = len(columns)
    columns, removed = drop_empty_columns(bu_rows, columns)

    write_csv(UPLOAD_COURSES_CSV, bu_rows, columns, strict=True)
    write_csv(COURSE_QA_CSV, report.rows, QA_COLUMNS)
    stats = {"section": "from reviewed file", **ctid_stats,
             "columns_written": len(columns), "columns_removed": len(removed)}
    COURSE_QA_SUMMARY_MD.write_text(summary_markdown(courses, bu_rows, report, stats, warnings),
                                    encoding="utf-8")

    # Published courses the catalog no longer lists: follow up, don't upload
    catalog_codes = {norm_code(c["code"]) for c in courses}
    gone = [r for r in published if published_code(r) and published_code(r) not in catalog_codes]
    if published:
        write_csv(COURSES_NOT_IN_CATALOG_CSV, gone, list(published[0].keys()))

    errors = sum(1 for r in report.rows if r["Severity"] == "error")
    print(f"Course BU: {len(bu_rows)} courses, {len(columns)} columns "
          f"({len(removed)} of {all_columns} empty columns removed) -> {UPLOAD_COURSES_CSV}")
    print(f"CTIDs: {ctid_stats['ctids_reused']} reused, {ctid_stats['ctids_minted']} new")
    if published:
        print(f"Published courses not in this catalog (not uploaded): {len(gone)} -> {COURSES_NOT_IN_CATALOG_CSV}")
    print(f"QA -> {COURSE_QA_CSV} and {COURSE_QA_SUMMARY_MD.name}")
    if errors:
        print(f"{errors} QA errors found; fix them before uploading.")


if __name__ == "__main__":
    main()
