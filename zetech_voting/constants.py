"""
Static reference data for the Zetech University Elections Portal.

COURSES defines every admission-number prefix the system will accept.
DOCKETS defines every student-government seat that can be contested.
Edit these lists to add/remove programmes or dockets - everything else
(admission validation, ballot generation, results) derives from them.
"""
import re

COURSES = [
    {"code": "BIRD",   "name": "Bachelor of Arts in International Relations & Diplomacy", "school": "Education, Arts & Social Sciences"},
    {"code": "BED",    "name": "Bachelor of Education (Arts)",                            "school": "Education, Arts & Social Sciences"},
    {"code": "BAJC",   "name": "Bachelor of Arts in Journalism & Communication",          "school": "Education, Arts & Social Sciences"},
    {"code": "BCOM",   "name": "Bachelor of Commerce",                                    "school": "Business & Economics"},
    {"code": "BBM",    "name": "Bachelor of Business Management",                         "school": "Business & Economics"},
    {"code": "BBIT",   "name": "Bachelor of Business Information Technology",             "school": "Business & Economics"},
    {"code": "BSCCS",  "name": "Bachelor of Science in Computer Science",                 "school": "ICT, Media & Engineering"},
    {"code": "BSCIT",  "name": "Bachelor of Science in Information Technology",           "school": "ICT, Media & Engineering"},
    {"code": "BSCSE",  "name": "Bachelor of Science in Software Engineering",             "school": "ICT, Media & Engineering"},
    {"code": "BSCEE",  "name": "Bachelor of Science in Electrical & Electronics Engineering", "school": "ICT, Media & Engineering"},
    {"code": "BSN",    "name": "Bachelor of Science in Nursing",                          "school": "Health Sciences"},
    {"code": "BSCCHS", "name": "Bachelor of Science in Clinical Health Sciences",         "school": "Health Sciences"},
    {"code": "LLB",    "name": "Bachelor of Laws",                                        "school": "Zetech Law School"},
]

COURSE_CODES = [c["code"] for c in COURSES]
COURSE_BY_CODE = {c["code"]: c for c in COURSES}

DOCKETS = [
    "President",
    "Deputy President",
    "Secretary General",
    "Deputy Secretary General",
    "Treasurer General",
    "Academic Affairs Secretary",
    "Sports & Games Secretary",
    "Welfare & Entertainment Secretary",
    "Publicity & Information Secretary",
]

# Matches e.g. BIRD/0124/25  -> course code / 3-4 digit serial / 2 digit year
# Sorting codes longest-first avoids a short code (e.g. "BED") swallowing
# a prefix of a longer one (e.g. "BSCEE") inside the alternation.
_sorted_codes = sorted(COURSE_CODES, key=len, reverse=True)
ADMISSION_PATTERN = re.compile(
    r"^(" + "|".join(_sorted_codes) + r")/(\d{3,4})/(\d{2})$",
    re.IGNORECASE,
)


def normalize_admission(raw: str) -> str:
    return (raw or "").strip().upper().replace(" ", "")


def is_valid_admission(raw: str) -> bool:
    return bool(ADMISSION_PATTERN.match(normalize_admission(raw)))
