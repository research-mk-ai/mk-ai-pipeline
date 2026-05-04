"""
Delete gemini-2.5-pro ERR-API rows from the Log sheet before a retry run.

Finds every row where:
  col D (Model)      = 'gemini-2.5-pro'
  col G (MK_Mention) = 'ERR-API'

Prints a preview and asks for confirmation before deleting.
Rows are deleted bottom-up to avoid shifting row numbers mid-operation.
"""

import os
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

import gspread

SPREADSHEET_ID = "1ietJCNHqVp6wYyUCssnMmUEp-SaHtKmX66A5M7QmUSE"

print("Connecting to Sheets...", flush=True)
gc = gspread.service_account(filename="service_account.json")
sh = gc.open_by_key(SPREADSHEET_ID)
ws = sh.worksheet("Log")

rows = ws.get_all_values()
data = rows[1:]  # skip header row

# Collect sheet row numbers (1-based) to delete
to_delete = []
for i, row in enumerate(data, start=2):
    model      = row[3].strip() if len(row) > 3 else ""
    mk_mention = row[6].strip() if len(row) > 6 else ""
    qid        = row[2].strip() if len(row) > 2 else ""
    log_id     = row[0].strip() if len(row) > 0 else ""
    if model == "gemini-2.5-pro" and mk_mention == "ERR-API":
        to_delete.append((i, log_id, qid))

print(f"\nFound {len(to_delete)} gemini-2.5-pro ERR-API rows to delete:\n")
for sheet_row, log_id, qid in to_delete:
    print(f"  row {sheet_row:4d}  {log_id:<14}  {qid}")

if not to_delete:
    print("Nothing to delete.")
    raise SystemExit(0)

print(f"\n{'='*50}")
print(f"About to DELETE {len(to_delete)} rows from the Log sheet.")
print(f"This cannot be undone from this script (but Sheets has version history).")
confirm = input("Type YES to confirm deletion: ").strip()

if confirm != "YES":
    print("Aborted — nothing deleted.")
    raise SystemExit(0)

# Delete bottom-up so row numbers don't shift
for sheet_row, log_id, qid in reversed(to_delete):
    ws.delete_rows(sheet_row)
    print(f"  Deleted row {sheet_row}  ({log_id}  {qid})")

print(f"\nDone — deleted {len(to_delete)} rows.")
