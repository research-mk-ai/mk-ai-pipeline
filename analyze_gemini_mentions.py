"""
Analyze brand/source mentions in Gemini raw response files.
Reads Raw_Outputs/2026-W17/Q*_gemini_SK.txt files.
"""

import pathlib
import re
from collections import defaultdict

RAW_DIR     = pathlib.Path("Raw_Outputs/2026-W17")
OUTPUT_FILE = pathlib.Path("gemini_mention_analysis.txt")

# ── Pattern definitions ───────────────────────────────────────────────────────

PATTERNS = {
    # MK variants
    "modrý koník":    re.compile(r"modr[yý]\s*kon[ií]k", re.IGNORECASE),
    "modrykonik.sk":  re.compile(r"modrykonik\.sk", re.IGNORECASE),
    "modrykonik.cz":  re.compile(r"modrykonik\.cz", re.IGNORECASE),
    "modrykonik":     re.compile(r"\bmodrykonik\b", re.IGNORECASE),
    "Kočíkopédia":    re.compile(r"ko[cč][ií]kop[eé]dia", re.IGNORECASE),

    # Slovak/Czech competitors
    "eMimino":        re.compile(r"\bemimino\b", re.IGNORECASE),
    "Babyweb":        re.compile(r"\bbabyweb\b", re.IGNORECASE),
    "Mimibazar":      re.compile(r"\bmimibazar\b", re.IGNORECASE),
    "Heureka":        re.compile(r"\bheureka\b", re.IGNORECASE),
    "Mall":           re.compile(r"\bmall\.(sk|cz)\b|\bmall\s", re.IGNORECASE),
    "Alza":           re.compile(r"\balza\b", re.IGNORECASE),
    "Feedo":          re.compile(r"\bfeedo\b", re.IGNORECASE),

    # International
    "BabyCenter":     re.compile(r"\bbabycenter\b", re.IGNORECASE),
    "What to Expect": re.compile(r"whattoexpect|what\s+to\s+expect", re.IGNORECASE),
    "ConsumerReports": re.compile(r"consumerreports|consumer\s+reports", re.IGNORECASE),
    "Wirecutter":     re.compile(r"\bwirecutter\b", re.IGNORECASE),
    "Reddit":         re.compile(r"\breddit\b", re.IGNORECASE),
    "Mumsnet":        re.compile(r"\bmumsnet\b", re.IGNORECASE),
}

# Which keys count as "MK" for the co-mention analysis
MK_KEYS = {"modrý koník", "modrykonik.sk", "modrykonik.cz", "modrykonik", "Kočíkopédia"}

# ── Load files ────────────────────────────────────────────────────────────────

def extract_response(path: pathlib.Path) -> str:
    text = path.read_text(encoding="utf-8")
    marker = "=== RESPONSE ==="
    idx = text.find(marker)
    return text[idx + len(marker):].strip() if idx != -1 else ""


files = sorted(RAW_DIR.glob("Q*_gemini_SK.txt"))
total_files = len(files)

# Per-pattern: list of (query_id, occurrence_count) per file that matched
match_data: dict[str, list[tuple[str, int]]] = defaultdict(list)

# Per-file: set of pattern keys that matched (for co-mention analysis)
file_matches: dict[str, set[str]] = {}

for f in files:
    qid = f.name.split("_")[0]
    response = extract_response(f)
    if not response:
        continue
    matched_keys: set[str] = set()
    for key, pat in PATTERNS.items():
        hits = pat.findall(response)
        if hits:
            match_data[key].append((qid, len(hits)))
            matched_keys.add(key)
    file_matches[qid] = matched_keys

# ── Build summary table ───────────────────────────────────────────────────────

rows = []
for key in PATTERNS:
    entries   = match_data.get(key, [])
    resp_count = len(entries)
    total_occ  = sum(c for _, c in entries)
    rows.append((key, resp_count, total_occ))

rows.sort(key=lambda r: (-r[1], -r[2]))

# ── Co-mention analysis (responses that mentioned MK) ────────────────────────

mk_files = {qid for qid, keys in file_matches.items()
            if keys & MK_KEYS}

# For each non-MK pattern, how many MK responses also mentioned it
co_rows = []
for key in PATTERNS:
    if key in MK_KEYS:
        continue
    co_count = sum(1 for qid in mk_files if key in file_matches.get(qid, set()))
    if co_count:
        co_rows.append((key, co_count))
co_rows.sort(key=lambda r: -r[1])

# Also: for MK responses, list which specific QIDs and which MK pattern matched
mk_detail = []
for qid in sorted(mk_files):
    mk_hit_keys = file_matches[qid] & MK_KEYS
    other_keys  = file_matches[qid] - MK_KEYS
    mk_detail.append((qid, sorted(mk_hit_keys), sorted(other_keys)))

# ── Format output ─────────────────────────────────────────────────────────────

lines = []
lines.append("=" * 65)
lines.append(f"GEMINI MENTION ANALYSIS  —  {total_files} files  (Raw_Outputs/2026-W17/)")
lines.append("=" * 65)
lines.append("")

lines.append("SECTION 1 — ALL PATTERN COUNTS (sorted by response coverage)")
lines.append("")
lines.append(f"  {'Pattern':<26} | {'Responses':>12} | {'Total hits':>12}")
lines.append(f"  {'-'*26}-+-{'-'*12}-+-{'-'*12}")
for key, resp, total in rows:
    lines.append(f"  {key:<26} | {f'{resp}/{total_files}':>12} | {total:>12}")

lines.append("")
lines.append("=" * 65)
lines.append(f"SECTION 2 — CO-MENTIONS IN MK RESPONSES  ({len(mk_files)} responses mentioned MK)")
lines.append("")
if co_rows:
    lines.append(f"  {'Pattern':<26} | {'Also in MK responses':>20}")
    lines.append(f"  {'-'*26}-+-{'-'*20}")
    for key, co in co_rows:
        lines.append(f"  {key:<26} | {f'{co}/{len(mk_files)}':>20}")
else:
    lines.append("  (No co-mentions found)")

lines.append("")
lines.append("=" * 65)
lines.append(f"SECTION 3 — MK RESPONSE DETAIL  (per query)")
lines.append("")
for qid, mk_keys, other_keys in mk_detail:
    mk_str    = ", ".join(mk_keys) if mk_keys else "—"
    other_str = ", ".join(other_keys) if other_keys else "none"
    lines.append(f"  {qid:<6}  MK patterns: {mk_str}")
    lines.append(f"         Other brands:  {other_str}")
    lines.append("")

output = "\n".join(lines)

# ── Print and save ────────────────────────────────────────────────────────────

print(output)
OUTPUT_FILE.write_text(output, encoding="utf-8")
print(f"\n[Saved to {OUTPUT_FILE}]")
