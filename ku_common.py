"""
Shared configuration and helpers for the Kutztown University credential ETL.

All scripts read and write files relative to DATA_DIR. Set the
KUTZTOWN_DATA_DIR environment variable to point at your working folder
(the folder that holds the saved A-Z Programs page, the downloaded
programHTML/ folder, and the intermediate CSVs). If it is not set, the
current working directory is used.
"""

import os
import re
import uuid
from pathlib import Path

# ---------- ORGANIZATION ----------

# Kutztown University's organization CTID in the Credential Registry
ORG_CTID = "ce-e483e7b6-9dd9-4588-a4f8-1d57ee313842"
ORG_REGISTRY_URI = f"https://credentialengineregistry.org/resources/{ORG_CTID}"

# ---------- PATHS ----------

DATA_DIR = Path(os.environ.get("KUTZTOWN_DATA_DIR", ".")).resolve()

# Step 1 input: the A-Z Programs page saved from
# https://www.kutztown.edu/academics/a-z-programs.html
AZ_PROGRAMS_HTML = DATA_DIR / "A-Z Programs - Kutztown University.html"
PROGRAMS_CSV = DATA_DIR / "kutztown_programs.csv"

# Step 2 output / Step 3 input
PROGRAM_HTML_DIR = DATA_DIR / "programHTML"

# Step 3 outputs
PARSED_CREDENTIALS_CSV = DATA_DIR / "kutztown_credentials4.csv"
PARSED_COMPETENCIES_CSV = DATA_DIR / "kutztown_competencies4.csv"

# Step 4 output: credentials already published in the Registry
PUBLISHED_CREDENTIALS_CSV = DATA_DIR / "KutztownCredentialsAll.csv"

# Step 5 outputs
MATCHED_CREDENTIALS_CSV = DATA_DIR / "kutztown_credentials_with_ctid4.csv"
PUBLISHED_WITH_MATCHES_CSV = DATA_DIR / "KutztownCredentialsPublished_with_matches4.csv"

# Manual review (between steps 5 and 6): copies of the step 5/3 outputs
# edited by hand in Excel. Step 6 reads these.
REVIEWED_PUBLISHED_CSV = DATA_DIR / "KutztownCredentialsPublished_with_matches4_editted.csv"
REVIEWED_COMPETENCIES_CSV = DATA_DIR / "kutztown_competencies4_reviewed.csv"

# Step 6 outputs: the files uploaded through the Credential Publisher
UPLOAD_DIR = DATA_DIR / "Review"
UPLOAD_CREDENTIALS_CSV = UPLOAD_DIR / "KutztownCredentialsUpdateWithCompetencies.csv"
UPLOAD_COMPETENCIES_CSV = UPLOAD_DIR / "kutztown_competencies.csv"
DEPRECATED_CREDENTIALS_CSV = UPLOAD_DIR / "KutztownCredentialsDeprecated.csv"

# ---------- CONSTANTS ----------

LANGUAGE = "en"
PUBLISHED_STATUS = "http://credreg.net/ctdlasn/vocabs/publicationStatus/Published"


# ---------- HELPERS ----------

def generate_ctid() -> str:
    """Generate a new CTID (ce- + UUID4)."""
    return f"ce-{uuid.uuid4()}"


# ---------- CREDENTIAL TYPE INFERENCE ----------

# Abbreviation found in parentheses at the end of a program name
credential_type_mapping = {
    "B.S.": "BachelorOfScienceDegree",
    "B.S. & B.S.Ed.": "BachelorOfScienceDegree",
    "B.S.Ed": "BachelorOfScienceInEducationDegree",
    "BA": "BachelorOfArtsDegree",
    "BFA": "BachelorOfFineArtsDegree",
    "BS": "BachelorOfScienceDegree",
    "BSBA": "BachelorOfScienceDegree",
    "BSW": "BachelorOfSocialWorkDegree",
    "Certificate": "Certificate",
    "DSW": "DoctoralDegree",
    "Ed.D.": "DoctoralDegree",
    "M.Ed.": "MasterDegree",
    "MA or MS": "MasterDegree",
    "MFA": "MasterOfFineArtsDegree",
    "MLS": "MasterDegree",
    "MPA": "MasterDegree",
    "MS": "MasterOfScienceDegree",
    "MSW": "MasterOfSocialWorkDegree",
    "Minor": "UndergraduateMinor",
    "Post-Baccalaureate Certification": "PostBaccalaureateCertificate",
    # Not a credential; fall through to the other rules
    "Core": "",
}

# Abbreviation appearing anywhere in the name as its own token
prefix_mapping = {
    "BA": "BachelorOfArtsDegree",
    "BS": "BachelorOfScienceDegree",
    "BSBA": "BachelorOfScienceDegree",
    "BFA": "BachelorOfFineArtsDegree",
    "BSED": "BachelorOfScienceInEducationDegree",
    "MED": "MasterDegree",
    "MA": "MasterDegree",
    "MS": "MasterOfScienceDegree",
    "MFA": "MasterOfFineArtsDegree",
    "MPA": "MasterDegree",
    "DSW": "DoctoralDegree",
    "EDD": "DoctoralDegree",
}

# Spelled-out phrases. Order matters: more specific first
keyword_mapping = {
    "post-baccalaureate": "PostBaccalaureateCertificate",
    "bachelor of arts": "BachelorOfArtsDegree",
    "bachelor of science": "BachelorOfScienceDegree",
    "bachelor of fine arts": "BachelorOfFineArtsDegree",
    "master of arts": "MasterOfArtsDegree",
    "master of science": "MasterOfScienceDegree",
    "master of fine arts": "MasterOfFineArtsDegree",
    "master of social work": "MasterOfSocialWorkDegree",
    "doctor": "DoctoralDegree",
    "master": "MasterDegree",
    "bachelor": "BachelorDegree",
    "certificate": "Certificate",
    "certification": "Certificate",
}

paren_pattern = re.compile(r"\(([^()]*)\)\s*$")


def extract_paren_value(name: str) -> str:
    """
    Extract the last (...) at the end of a string.
    e.g., "Business Administration, Accounting (BSBA)" -> "BSBA"
    """
    if not name:
        return ""
    m = paren_pattern.search(name)
    return m.group(1).strip() if m else ""


def infer_credential_type(credential_name: str) -> str:
    """
    Infer a CTDL Credential Type from a program name:
      1. Value in parentheses at end of name -> credential_type_mapping
         (a mapping of "" falls through to the other rules)
      2. Any token in the name matching prefix_mapping (BA, BS, BSBA, MED, ...)
      3. Keyword-based mapping (bachelor of arts, certificate, ...)
    Returns "" if no rule applies.
    """
    if not credential_name:
        return ""

    clean_name = re.sub(r"\s+", " ", credential_name).strip().strip('"').strip("'")

    # 1) Parentheses at end
    paren_value = extract_paren_value(clean_name)
    if paren_value:
        mapped = credential_type_mapping.get(paren_value)
        if mapped:
            return mapped

    # 2) Token-based mapping
    for t in clean_name.split(" "):
        norm = re.sub(r"[^A-Za-z]", "", t).upper()
        mapped = prefix_mapping.get(norm)
        if mapped:
            return mapped

    # 3) Keyword-based mapping
    lower_name = clean_name.lower()
    for kw, mapped in keyword_mapping.items():
        if kw in lower_name:
            return mapped

    return ""
