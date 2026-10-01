# Kutztown Credential ETL

Scripts for extracting Kutztown University's degree, certificate, and minor
programs and their Student Learning Outcomes from
[kutztown.edu](https://www.kutztown.edu/academics/a-z-programs.html), matching
them to the credentials Kutztown already has in the Credential Registry, and
producing "BU" (bulk-upload) files for Credential Engine's Credential
Publisher:

- a **credential update** file for the existing published credentials, with
  refreshed descriptions, webpages, and keywords, and a *requires* condition
  profile pointing at each program's competency framework
- a **competency framework** file (CTDL-ASN) with one framework per program's
  Student Learning Outcomes and one competency per outcome
- a **course** file (Learning Opportunity, `Learning Type = Course`) with every
  course in the undergraduate catalog: code, title, description, credits, and
  subject area (steps 7–9)

Kutztown's organization CTID is `ce-e483e7b6-9dd9-4588-a4f8-1d57ee313842`.

## Pipeline

Scripts are numbered in the order they run. All paths are relative to a
data folder (see [Setup](#setup)).

| Step | Script | Reads | Writes |
|---|---|---|---|
| 1 | `1ParseProgramLinks.py` | `A-Z Programs - Kutztown University.html` (saved from the website) | `kutztown_programs.csv` |
| 2 | `2DownloadProgramHTML.py` | `kutztown_programs.csv` | `programHTML/*.html` |
| 3 | `3ParseCredentialsAndCompetencies.py` | `programHTML/` | `kutztown_credentials4.csv`, `kutztown_competencies4.csv` |
| 4 | `4GetPublishedCredentials.py` | Credential Engine Assistant Search API | `KutztownCredentialsAll.csv` |
| 5 | `5MatchPublishedCTIDs.py` | steps 3 and 4 | `kutztown_credentials_with_ctid4.csv`, `KutztownCredentialsPublished_with_matches4.csv` |
| — | *manual review* | step 5 and step 3 outputs | `KutztownCredentialsPublished_with_matches4_editted.csv`, `kutztown_competencies4_reviewed.csv` |
| 6 | `6ProduceBulkUpload.py` | reviewed files + `kutztown_credentials4.csv` | `Review/kutztown_competencies.csv`, `Review/KutztownCredentialsUpdateWithCompetencies.csv`, `Review/KutztownCredentialsDeprecated.csv` |
| 7 | `7ExtractCatalogCourses.py` | `KU-Undergraduate-Catalog-2025-2026.pdf` | `kutztown_courses_extracted.csv`, `kutztown_courses_extract_qa.csv` |
| 8 | `8GetPublishedCourses.py` | Credential Engine Assistant Search API | `KutztownCoursesPublished.csv` |
| — | *course review* | step 7 outputs | `kutztown_courses_reviewed.csv` |
| 9 | `9ProduceCourseBulkUpload.py` | reviewed courses + step 8 (+ optional Publisher template) | `Review/KutztownCourses.csv`, `Review/KutztownCourses_QA.csv`, `Review/KutztownCourses_QA_summary.md`, `Review/KutztownCourses_CTID_crosswalk.csv`, `Review/KutztownCoursesNotInCatalog.csv` |

Steps 1–6 (credentials and competencies) and steps 7–9 (courses) are
independent; either set can be run on its own.

`ku_common.py` holds the shared file paths, the organization CTID, CTID
generation, and the program-name → CTDL credential type rules.
`profiles/kutztown-undergraduate-2025-2026.yaml` describes the catalog layout for
the course steps.

### What each step does

1. **Parse links:** reads every `li.azProgram > a.azProgramLink` on the
   saved A-Z Programs page.
2. **Download:** fetches each program page (1 second apart) and prepends an
   HTML comment with the source URL, program name, and download date.
   Pages already on disk are skipped, so it can be re-run to resume.
3. **Parse:** for every *Student Learning Outcomes* accordion on a page,
   writes one credential row and one competency framework (a framework row
   plus one competency row per outcome), linked by a new framework CTID.
   Also extracts the page description (stopping at *Student Learning
   Outcomes*), meta keywords, and a credential type inferred from the
   program name. The extra columns on the right (`FileName`,
   `FrameworkTitle`, `rawHTML`, …) are there to help review.
4. **Get published credentials:** pages through every credential owned by
   Kutztown in the Registry.
5. **Match:** fuzzy-matches each parsed credential to a published one
   (`rapidfuzz` `token_set_ratio`, narrowed by degree level; matches under
   40 are dropped). Copies description, webpage, keywords, and framework
   links onto the matched published credential; a published credential
   matched by several parsed frameworks (e.g. core + concentration) gets all
   of them, pipe-separated. Published credentials with no match are marked
   `Deprecated`.
6. **Produce BU:** formats the reviewed files for upload. Deprecated rows
   are left out of the upload and written to a separate file for follow-up.
   Every other credential gets `Credential Status = Active`, keywords looked
   up by Subject Webpage, and a new condition profile identifier.
   Competencies are linked to their framework with `ceasn:isPartOf`, and
   framework rows get `ceasn:publisher`. Runs QA checks: required
   frameworks missing from the competency file, competencies pointing at
   missing frameworks, blank required fields, and duplicate CTIDs.

7. **Extract courses:** reads the catalog's *Course Descriptions* section
   (pp. 343–676) with [pdf-catalog-to-bulk-upload](https://github.com/CredentialEngine/pdf-catalog-to-bulk-upload),
   using the profile in `profiles/`. Each bold `ACCT 121: Title` heading starts a
   course; the large headings above them (*Accounting*, *Biology*) become the
   subject area. The PDF draws much of its text twice and repeats the last lines
   of each page at the top of the next; both are removed before parsing. Every
   entry ends with the same *"current prerequisites … can be found in the online
   Course Description"* sentence, which is dropped. Writes a QA preview of issues
   to check during review.
8. **Get published courses:** pages through every learning opportunity owned by
   Kutztown in the Registry, so courses already published keep their CTIDs.
9. **Produce course BU:** formats the reviewed courses for upload. CTIDs are
   reused, matched on course code, from the Registry (step 8) and then from the
   previous run's `Review/KutztownCourses.csv`; other courses get a new CTID. If
   `LearningOpportunity_Bulk_Upload_Template.csv` (a template downloaded from the
   Publisher) is in the data folder, its header row sets the columns. Columns
   with no values are removed. Published courses the catalog no longer lists are
   written to a follow-up file and not uploaded.

### Manual review

Automatic matching gets you most of the way; the rest is human judgment.
Between steps 5 and 6, open the step 5 output in Excel and:

- fix wrong or missing matches, and re-link frameworks to the right
  published credential (in the 2025 run, review brought the deprecated count
  from 128 down to 25)
- tidy descriptions and Subject Webpages
- review `kutztown_competencies4.csv`: drop duplicate or unwanted frameworks
  and split outcomes that were scraped as one

Save the results as `KutztownCredentialsPublished_with_matches4_editted.csv`
and `kutztown_competencies4_reviewed.csv` (UTF-8 CSV), then run step 6. In
the Credential Publisher, upload the competency file first so the frameworks
exist before the credentials that require them. The course file is uploaded on
its own through the Learning Opportunity bulk upload.

### Course review

Copy `kutztown_courses_extracted.csv` to `kutztown_courses_reviewed.csv`, work
through `kutztown_courses_extract_qa.csv` (errors first), then run step 9. In the
2025–26 catalog:

- **Missing descriptions (9 courses).** Description is required; write one or
  delete the row.
- **Duplicates.** ARTH 315 is printed twice, and ENGL 126 appears with two
  different titles. Keep one row per course.
- **Unusual course numbers.** `ARTH 27`, `ASTR 26`, `MATH 3` and a few others are
  likely typos in the catalog. Two-digit numbers such as `ANTH 10` are real.
- **Credits.** Course entries in this catalog state no credits. About half are
  filled from program requirement lists (`credit_source = cross_reference`) or
  description notes (`description`); 22 have conflicting values across program
  pages. The rest are blank and upload without credit information unless filled
  from registrar data (`credit_min`, `credit_max`).

Edit the extracted columns (`code`, `title`, `description`, `credit_min`, …), not
the bulk-upload column names; step 9 does the formatting.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Point the scripts at your data folder. If you don't set it, they use the
current directory:

```bash
export KUTZTOWN_DATA_DIR=/path/to/Kutztown
```

Steps 7–9 use the [pdf-catalog-to-bulk-upload](https://github.com/CredentialEngine/pdf-catalog-to-bulk-upload)
package, which `requirements.txt` installs from GitHub. Step 7 expects the
catalog PDF in the data folder:

```
$KUTZTOWN_DATA_DIR/KU-Undergraduate-Catalog-2025-2026.pdf
```

(from <https://www.kutztown.edu/Departments-Offices/A-F/Catalog/Documents/KU-Undergraduate-Catalog-2025-2026.pdf>).
For a new catalog year, copy the profile, update `catalog.url`,
`version_identifier` and the file names in `ku_common.py`, and run
`pdf-catalog-bu inspect` on a few course pages to confirm the headings still match.

### Credentials

Steps 4 and 8 call the Credential Engine Assistant Search API and expects an API
token in the environment:

```bash
export CE_ASSISTANT_API_TOKEN=your-token-here
```

## Page-specific handling

Kutztown's program pages share one template, with a few exceptions handled
in step 3:

- On the B.S. Computer Science page, the outcomes accordion comes *before*
  the *Student Learning Outcomes* label instead of after it.
- Description extraction skips boilerplate paragraphs (*Sample Career
  Options*, *Degree Information*, admission links, …), turns one-column
  tables and lead-in lists into sentences, and skips tables with 3+ columns.
- If a page has no description text, it falls back to the meta description,
  then `og:description`, then the first `featureText` paragraph.

## What's not here

Only the scripts are in this repo. The saved website pages, the downloaded
program HTML, the undergraduate catalog PDF, and the generated CSV/Excel
files stay local, both for size and because the page content belongs to
Kutztown University.
