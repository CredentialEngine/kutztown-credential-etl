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

`ku_common.py` holds the shared file paths, the organization CTID, CTID
generation, and the program-name → CTDL credential type rules.

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
exist before the credentials that require them.

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

### Credentials

Step 4 calls the Credential Engine Assistant Search API and expects an API
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
