import pathlib
import re
import subprocess
import sys

for pkg in ["python-dotenv", "gspread"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

import gspread

SPREADSHEET_ID       = "1ietJCNHqVp6wYyUCssnMmUEp-SaHtKmX66A5M7QmUSE"
SERVICE_ACCOUNT_FILE = pathlib.Path(__file__).parent / "service_account.json"

# ── Explicit row fixes (override all other logic) ─────────────────────────────

EXPLICIT_SK = {
    "Q002": "Cybex Priam a Bugaboo Fox porovnanie",
    "Q051": "oplatí sa nakupovať potraviny pre rodinu porovnanie reťazcov",
    "Q096": "udržať kamarátky po tridsiatke",
    "Q097": "nájsť čas na seba ako matka",
}
EXPLICIT_CZ = {
    "Q002": "Cybex Priam a Bugaboo Fox porovnání",
    "Q051": "vyplatí se nakupovat potraviny pro rodinu srovnání řetězců",
    "Q096": "udržet kamarádky po třicítce",
    "Q097": "najít čas na sebe jako matka",
}

# ── Systematic patterns ───────────────────────────────────────────────────────

# Leading particles left behind by the prefix-stripping in generate_search_queries.py
SK_LEADING = re.compile(r'^(si|sa|ktorý|ktorá|ktoré)\s+', re.IGNORECASE)
CZ_LEADING = re.compile(r'^(se|si|který|která|které)\s+', re.IGNORECASE)

# Comparative tail clauses: ", ktorý je lepší" / ", ktoré je lepšie" etc.
SK_COMPARATIVE = re.compile(
    r',?\s+(ktorý|ktorá|ktoré)\s+je\s+(lepší|lepšia|lepšie|najlepší|najlepšia|najlepšie)\??\s*$',
    re.IGNORECASE,
)
CZ_COMPARATIVE = re.compile(
    r',?\s+(který|která|které)\s+je\s+(lepší|lepší|nejlepší|nejlepší|lepší|lepší)\??\s*$',
    re.IGNORECASE,
)


def _fix(text: str, leading_re: re.Pattern, comparative_re: re.Pattern) -> str:
    if not text:
        return text
    # 1. Remove comparative tail
    text = comparative_re.sub("", text).rstrip(",").strip()
    # 2. Strip leading particle and capitalise
    m = leading_re.match(text)
    if m:
        text = text[m.end():]
        if text:
            text = text[0].upper() + text[1:]
    return text


def main():
    gc = gspread.service_account(filename=str(SERVICE_ACCOUNT_FILE))
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet("Queries")

    rows = ws.get_all_values()
    data = rows[1:]  # skip header row

    changes: list[tuple] = []

    for i, row in enumerate(data):
        sheet_row = i + 2
        query_id  = row[0].strip() if len(row) > 0 else ""
        if not query_id:
            continue

        cur_sk = row[4].strip() if len(row) > 4 else ""   # col E
        cur_cz = row[6].strip() if len(row) > 6 else ""   # col G

        # Explicit fixes take precedence
        if query_id in EXPLICIT_SK:
            new_sk = EXPLICIT_SK[query_id]
        else:
            new_sk = _fix(cur_sk, SK_LEADING, SK_COMPARATIVE)

        if query_id in EXPLICIT_CZ:
            new_cz = EXPLICIT_CZ[query_id]
        else:
            new_cz = _fix(cur_cz, CZ_LEADING, CZ_COMPARATIVE)

        if new_sk != cur_sk or new_cz != cur_cz:
            changes.append((sheet_row, query_id, cur_sk, new_sk, cur_cz, new_cz))

    # ── Print all changes ─────────────────────────────────────────────────────
    print(f"Found {len(changes)} row(s) to update:\n")
    for _, qid, old_sk, new_sk, old_cz, new_cz in changes:
        if old_sk != new_sk:
            tag = "[explicit]" if qid in EXPLICIT_SK else "[systematic]"
            print(f"  {qid} SK {tag}")
            print(f"    before: {old_sk!r}")
            print(f"    after:  {new_sk!r}")
        if old_cz != new_cz:
            tag = "[explicit]" if qid in EXPLICIT_CZ else "[systematic]"
            print(f"  {qid} CZ {tag}")
            print(f"    before: {old_cz!r}")
            print(f"    after:  {new_cz!r}")
        print()

    if not changes:
        print("Nothing to do.")
        return

    # ── Write to sheet ────────────────────────────────────────────────────────
    batch = []
    for sheet_row, _, old_sk, new_sk, old_cz, new_cz in changes:
        if old_sk != new_sk:
            batch.append({"range": f"E{sheet_row}", "values": [[new_sk]]})
        if old_cz != new_cz:
            batch.append({"range": f"G{sheet_row}", "values": [[new_cz]]})

    ws.batch_update(batch, value_input_option="USER_ENTERED")
    print(f"Written {len(batch)} cell update(s) to the sheet.")


if __name__ == "__main__":
    main()
