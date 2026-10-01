"""
Step 7: Extract every course from the undergraduate catalog PDF.

Uses the catalog2ctdl package with the Kutztown profile in
profiles/kutztown-undergraduate-2025-2026.yaml. The profile records how this
catalog is laid out: the "Course Descriptions" section (pp. 343-676), bold
"ACCT 121: Title" headings, subject-area headings, and the boilerplate
prerequisite sentence to discard.

The catalog's course entries state no credits. They are filled from the
program requirement lists elsewhere in the catalog ("ARTH 302: ... (3
credits)") and from notes such as "(6 c.h., 3 s.h.)" in descriptions; the
credit_source column says which.

Input:   KU-Undergraduate-Catalog-2025-2026.pdf   (saved in the data folder)
Outputs: kutztown_courses_extracted.csv           one row per course
         kutztown_courses_extract_qa.csv          issues to look at in review
"""

from catalog2ctdl.config import load_config, validate
from catalog2ctdl.parser import INTERMEDIATE_COLUMNS
from catalog2ctdl.pipeline import extract, write_csv
from catalog2ctdl.qa import QA_COLUMNS, run_qa
from catalog2ctdl.transform import to_bulk_upload

from ku_common import (
    CATALOG_PDF,
    COURSE_PROFILE,
    COURSES_EXTRACT_QA_CSV,
    COURSES_EXTRACTED_CSV,
    ORG_CTID,
)


def main():
    if not CATALOG_PDF.exists():
        raise SystemExit(f"Catalog PDF not found: {CATALOG_PDF}\n"
                         "Download it from kutztown.edu into the data folder.")

    cfg = load_config(COURSE_PROFILE, {"organization": {"ctid": ORG_CTID}})
    for warning in validate(cfg):
        print(f"warning: {warning}")

    print(f"Reading {CATALOG_PDF.name} ...")
    courses, stats = extract(str(CATALOG_PDF), cfg)
    write_csv(COURSES_EXTRACTED_CSV, courses, INTERMEDIATE_COLUMNS)

    # QA preview on the extracted data, so review can start from the issue list
    bu_rows, notes, _, _ = to_bulk_upload(courses, cfg)
    report = run_qa(courses, bu_rows, notes)
    write_csv(COURSES_EXTRACT_QA_CSV, report.rows, QA_COLUMNS)

    with_credits = sum(1 for c in courses if c["credit_min"])
    subjects = len({c["subject_area"] for c in courses if c["subject_area"]})
    print(f"Section: pages {stats['section_pages']} ({stats['section']})")
    print(f"Cleanup: {stats['layer_duplicates']} duplicate-layer lines and "
          f"{stats['overlap_lines']} repeated page-top lines removed")
    print(f"Extracted {len(courses)} courses in {subjects} subject areas -> {COURSES_EXTRACTED_CSV}")
    print(f"Credits found for {with_credits} courses ({with_credits / max(len(courses), 1):.0%})")
    errors = sum(1 for r in report.rows if r["Severity"] == "error")
    warnings = sum(1 for r in report.rows if r["Severity"] == "warning")
    print(f"QA: {errors} errors, {warnings} warnings -> {COURSES_EXTRACT_QA_CSV}")
    print("Next: run step 8, then review (see README) and save as kutztown_courses_reviewed.csv")


if __name__ == "__main__":
    main()
