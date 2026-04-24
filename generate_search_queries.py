import pathlib
import re
import subprocess
import sys

for pkg in ["python-dotenv", "gspread"]:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

import gspread

SPREADSHEET_ID       = "1ietJCNHqVp6wYyUCssnMmUEp-SaHtKmX66A5M7QmUSE"
SERVICE_ACCOUNT_FILE = pathlib.Path(__file__).parent / "service_account.json"

SK_PREFIXES = [
    "Kedy a ako ", "Kde môžem ", "Kde kúpiť ", "Kde nájdem ", "Kde sa ",
    "Aký je ", "Aká je ", "Aké sú ", "Ako vybrať ", "Ako ",
    "Ktorý je ", "Ktorá je ", "Čo je ", "Čo na ",
    "Porovnaj ", "Stojí za ", "Oplatí sa ", "Avis ",
]

CZ_PREFIXES = [
    "Kdy a jak ", "Kde koupit ", "Kde najdu ", "Kde se ",
    "Jaký je ", "Jaká je ", "Jaké jsou ", "Jak vybrat ", "Jak ",
    "Který je ", "Která je ", "Co je ", "Co na ",
    "Porovnej ", "Stojí za ", "Vyplatí se ",
]

# Sort longest first so more specific prefixes match before shorter ones
SK_PREFIXES.sort(key=len, reverse=True)
CZ_PREFIXES.sort(key=len, reverse=True)


def clean_query(text: str, prefixes: list[str]) -> str:
    if not text or not text.strip():
        return ""
    q = text.strip().rstrip("?").rstrip()
    for prefix in prefixes:
        if q.lower().startswith(prefix.lower()):
            q = q[len(prefix):]
            # Lowercase the first letter after prefix removal
            if q:
                q = q[0].lower() + q[1:]
            break
    return q.strip()


def main():
    gc = gspread.service_account(filename=str(SERVICE_ACCOUNT_FILE))
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet("Queries")

    rows = ws.get_all_values()
    header = rows[0]
    data   = rows[1:]

    print(f"Loaded {len(data)} rows from Queries sheet.\n")

    # Collect (row_index, sk_query, cz_query) — row_index is 1-based sheet row
    updates_e = []   # column E — Google query SK
    updates_g = []   # column G — Google query CZ

    preview_rows = []

    for i, row in enumerate(data):
        sheet_row = i + 2  # 1-based + skip header

        query_id = row[0].strip() if len(row) > 0 else ""
        sk_raw   = row[3].strip() if len(row) > 3 else ""
        cz_raw   = row[5].strip() if len(row) > 5 else ""

        if not query_id:
            continue

        sk_clean = clean_query(sk_raw, SK_PREFIXES)
        cz_clean = clean_query(cz_raw, CZ_PREFIXES)

        updates_e.append((sheet_row, sk_clean))
        updates_g.append((sheet_row, cz_clean))

        preview_rows.append((query_id, sk_raw, sk_clean))

    # Print preview
    print(f"{'ID':<6}  {'Otázka SK':<65}  {'Google query SK'}")
    print("-" * 130)
    for query_id, original, cleaned in preview_rows:
        print(f"{query_id:<6}  {original:<65}  {cleaned}")

    # Batch write to sheet using individual cell updates grouped per column
    print(f"\nWriting {len(updates_e)} SK queries to column E...")
    ws.batch_update([
        {
            "range": f"E{row}",
            "values": [[val]],
        }
        for row, val in updates_e
    ], value_input_option="USER_ENTERED")

    print(f"Writing {len(updates_g)} CZ queries to column G...")
    ws.batch_update([
        {
            "range": f"G{row}",
            "values": [[val]],
        }
        for row, val in updates_g
    ], value_input_option="USER_ENTERED")

    print("\nDone. Columns E and G updated.")


if __name__ == "__main__":
    main()
