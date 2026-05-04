"""
Diagnostic: identify exact error type for Gemini ERR-API failures.

Calls Gemini directly (not through pipeline.call_gemini) so we see the raw
exception before any pipeline retry or error-masking logic.
"""

import os, traceback
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

import gspread
from google import genai
from google.genai import types

SPREADSHEET_ID   = "1ietJCNHqVp6wYyUCssnMmUEp-SaHtKmX66A5M7QmUSE"
GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")

SAMPLE = [
    "Q017",   # Nutrilon vs Hipp — detská výživa
    "Q093",   # Vzťah po narodení dieťaťa — relationships
    "Q111",   # Tatra banka — banking/finance
    "Q132",   # Autizmus u detí — sensitive medical
    "Q282",   # Martinus — books (control, less sensitive)
]

# ── Load query texts from Sheets ──────────────────────────────────────────────

print("Loading queries from Sheets...", flush=True)
gc  = gspread.service_account(filename="service_account.json")
sh  = gc.open_by_key(SPREADSHEET_ID)
ws  = sh.worksheet("Queries")
rows = ws.get_all_values()[1:]   # skip header

query_map = {}
for row in rows:
    qid = row[0].strip() if len(row) > 0 else ""
    if qid in SAMPLE:
        query_text = row[3].strip() if len(row) > 3 else ""   # col D — Otázka SK
        query_map[qid] = query_text

print(f"Loaded {len(query_map)} queries.\n")

# ── Run diagnostic calls ──────────────────────────────────────────────────────

client = genai.Client(api_key=GEMINI_API_KEY)

for qid in SAMPLE:
    query_text = query_map.get(qid, "QUERY NOT FOUND")
    print("=" * 70)
    print(f"QUERY_ID : {qid}")
    print(f"TEXT     : {query_text}")
    print("-" * 70)

    response = None
    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=query_text,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )

        # ── Success path — check finish_reason anyway ──────────────────────
        candidates = getattr(response, "candidates", []) or []
        if candidates:
            c = candidates[0]
            finish_reason = getattr(c, "finish_reason", None)
            print(f"RESULT       : SUCCESS (no exception)")
            print(f"finish_reason: {finish_reason}")
            text_parts = [
                p.text for p in getattr(c, "content", None) and getattr(c.content, "parts", []) or []
                if getattr(p, "text", None) and not getattr(p, "thought", False)
            ]
            print(f"Text length  : {sum(len(t) for t in text_parts)} chars")
        else:
            print(f"RESULT       : SUCCESS but NO candidates")

        # ── prompt_feedback (block reason set before model ran) ────────────
        pf = getattr(response, "prompt_feedback", None)
        if pf:
            block_reason = getattr(pf, "block_reason", None)
            safety_ratings = getattr(pf, "safety_ratings", []) or []
            print(f"prompt_feedback.block_reason: {block_reason}")
            for sr in safety_ratings:
                cat  = getattr(sr, "category", "?")
                prob = getattr(sr, "probability", "?")
                print(f"  safety_rating: {cat} = {prob}")
        else:
            print(f"prompt_feedback: None")

    except Exception as exc:
        exc_type = type(exc).__module__ + "." + type(exc).__qualname__
        print(f"RESULT       : EXCEPTION")
        print(f"Exception type   : {exc_type}")
        print(f"Exception message: {exc}")
        print()
        print("Full traceback:")
        traceback.print_exc()

        # Try to get response-level details even on exception
        if response is not None:
            print()
            print("Response object existed before exception:")
            candidates = getattr(response, "candidates", []) or []
            for i, c in enumerate(candidates):
                print(f"  candidate[{i}].finish_reason: {getattr(c, 'finish_reason', 'N/A')}")
            pf = getattr(response, "prompt_feedback", None)
            if pf:
                print(f"  prompt_feedback.block_reason: {getattr(pf, 'block_reason', 'N/A')}")

    print()

print("=" * 70)
print("DONE")
