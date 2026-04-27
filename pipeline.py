import subprocess
import sys

def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

for pkg in ["python-dotenv", "openai", "google-genai", "requests", "gspread", "google-search-results"]:
    install(pkg)

import os
import csv
import re
import datetime
import pathlib
from collections import Counter
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

# ── Constants ─────────────────────────────────────────────────────────────────

OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY")
PERPLEXITY_API_KEY  = os.getenv("PERPLEXITY_API_KEY")
SERPAPI_KEY         = os.getenv("SERPAPI_KEY")

SPREADSHEET_ID       = "1ietJCNHqVp6wYyUCssnMmUEp-SaHtKmX66A5M7QmUSE"
SHEET_GID            = 910794173
SERVICE_ACCOUNT_FILE = pathlib.Path(__file__).parent / "service_account.json"
RAW_OUTPUT_DIR       = pathlib.Path(__file__).parent / "Raw_Outputs"
LANGUAGE             = "SK"

# ── Run mode flags ────────────────────────────────────────────────────────────

TEST_MODE        = False  # True  → use TEST_QUERIES below instead of Sheets
SERP_ONLY        = False  # True  → only call_serp(); reads col E (Google query SK)
DRY_RUN          = False  # True  → limit to first DRY_RUN_LIMIT queries
DRY_RUN_LIMIT    = 6
QUERY_SET_FILTER = ""        # empty: load ALL queries with MVP=ANO
SKIP_LOGGED      = True   # True → skip Query_IDs already present in Log sheet
RETRY_QIDS_FILE  = ""     # path to file with one Query_ID per line; if set, overrides all other query filters

TEST_QUERIES = [
    ("Q001", "najlepší kočík do mesta 2026"),
    ("Q002", "najlepšia detská formula pre novorodenca"),
    ("Q003", "ako vybrať správnu veľkosť plienok"),
]

# ── Patterns & lookups ────────────────────────────────────────────────────────

MK_PATTERN    = re.compile(r"modrykonik|modrý\s*koník|modrykonik\.sk", re.IGNORECASE)
MK_DOMAIN_PAT = re.compile(r"modrykonik\.(sk|cz)", re.IGNORECASE)
SK_CHARS      = set("ľĽšŠčČžŽýÝáÁíÍéÉúÚäÄôÔ")
CZ_CHARS      = set("ůě")

MODEL_SHORT = {
    "gpt-4o":             "gpt4o",
    "gemini-2.5-pro":     "gemini",
    "sonar (perplexity)": "sonar",
    "google-ai-overview": "serp",
    "claude":             "claude",
}

SERP_LOCALE = {
    "SK": {"location": "Slovakia",      "hl": "sk", "gl": "sk", "google_domain": "google.sk"},
    "CZ": {"location": "Czech Republic","hl": "cs", "gl": "cz", "google_domain": "google.cz"},
}

CSV_FIELDS = [
    "query_id", "query", "model", "model_actual", "timestamp",
    "response_text", "mk_mention", "mk_citation", "mk_position",
    "input_tokens", "output_tokens", "response_language",
]

# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class CallResult:
    text:          str
    model_actual:  str
    input_tokens:  int
    output_tokens: int
    citations:     list[str]


# ── Detection & classification helpers ───────────────────────────────────────

def detect_mk(text: str) -> bool:
    return bool(MK_PATTERN.search(text))


def detect_language(text: str) -> str:
    if not text:
        return "OTHER"
    chars = set(text)
    if chars & SK_CHARS:
        return "SK"
    if chars & CZ_CHARS:
        return "CZ"
    if sum(1 for c in text if ord(c) < 128) / len(text) > 0.95:
        return "EN"
    return "OTHER"


def _classify_response(text: str | None, exc: Exception | None) -> str:
    if exc is not None:
        s = str(exc).lower()
        if "timeout" in s or type(exc).__name__ in ("APITimeoutError", "TimeoutError", "ReadTimeout"):
            return "ERR-TIMEOUT"
        if hasattr(exc, "status_code"):
            return "ERR-API"
        if re.match(r"^\d{3}\s", str(exc)):
            return "ERR-API"
        return "ERR-API"
    if not text or not text.strip():
        return "ERR-EMPTY"
    if len(text.strip()) < 50:
        return "ERR-SHORT"
    return "ANO" if detect_mk(text) else "NIE"


def mk_position(text: str, mk_value: str) -> tuple[str, float]:
    """Return (label, pct) — label is Top/Middle/Bottom/N/A, pct is -1 when N/A."""
    if mk_value != "ANO":
        return "N/A", -1.0
    match = MK_PATTERN.search(text)
    if not match:
        return "N/A", -1.0
    pct = match.start() / max(len(text), 1) * 100
    label = "Top" if pct < 20 else ("Middle" if pct <= 70 else "Bottom")
    return label, pct


def check_mk_citation(citations: list[str], exc: Exception | None) -> str:
    if exc is not None:
        return "ERR"
    if not citations:
        return "NO_CITATIONS"
    return "ANO" if any(MK_DOMAIN_PAT.search(u) for u in citations) else "NIE"


# ── Citation extractors ───────────────────────────────────────────────────────

_URL_RE = re.compile(r"https://[^\s\)\"'>\]]+")

def _citations_openai(response) -> list[str]:
    """Extract citation URLs from OpenAI Responses API.

    Primary source: structured url_citation annotations on response output.
    These contain only URLs that were actually grounded as citations.

    Fallback: regex over response.output_text. Used only if annotations are
    missing (defensive — should not happen with web_search_preview tool).
    """
    urls = []
    for output_item in getattr(response, "output", []) or []:
        for content_part in getattr(output_item, "content", []) or []:
            for annotation in getattr(content_part, "annotations", []) or []:
                if getattr(annotation, "type", None) == "url_citation":
                    url = getattr(annotation, "url", None)
                    if url:
                        urls.append(url)

    # Fallback to regex if annotations returned nothing but we have text
    if not urls:
        text = response.output_text or ""
        urls = _URL_RE.findall(text)

    return list(dict.fromkeys(urls))


def _citations_gemini(response) -> list[str]:
    """Return grounding sources from Gemini response.

    chunk.web.title  = real domain ('modrykonik.sk')   — used for MK detection
    chunk.web.uri    = Vertex AI redirect URL           — kept for debugging only
    Each entry is formatted as 'domain_title | redirect_uri' so both are
    preserved in raw files while MK_DOMAIN_PAT still matches on the title part.
    """
    entries = []
    for candidate in getattr(response, "candidates", []) or []:
        gm = getattr(candidate, "grounding_metadata", None)
        for chunk in getattr(gm, "grounding_chunks", []) or []:
            web = getattr(chunk, "web", None)
            if web:
                title = getattr(web, "title", None)
                uri   = getattr(web, "uri",   None)
                if title:
                    entries.append(f"{title} | {uri}" if uri else title)
    return list(dict.fromkeys(entries))


def _citations_perplexity(response) -> list[str]:
    return list(dict.fromkeys(getattr(response, "citations", None) or []))


# ── Raw .txt output ───────────────────────────────────────────────────────────

def save_raw_output(
    query_id: str, query_text: str,
    model_name: str, model_short: str, model_actual: str,
    timestamp: datetime.datetime,
    text: str, citations: list[str],
    input_tokens: int, output_tokens: int,
    detected_lang: str, mk_value: str, mk_citation: str,
    mk_pos_label: str, mk_pos_pct: float,
) -> pathlib.Path:
    week_tag = f"{timestamp.strftime('%Y')}-{timestamp.strftime('W%V')}"
    week_dir = RAW_OUTPUT_DIR / week_tag
    week_dir.mkdir(parents=True, exist_ok=True)

    qid_num   = query_id.lstrip("Q")
    filepath  = week_dir / f"Q{qid_num}_{model_short}_{LANGUAGE}.txt"
    mk_pos_raw = f"{mk_pos_label} ({mk_pos_pct:.1f}%)" if mk_pos_pct >= 0 else "N/A"

    content = "\n".join([
        "=== METADATA ===",
        f"timestamp: {timestamp.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"query_id: {query_id}",
        f"query_text: {query_text}",
        f"model_requested: {model_name}",
        f"model_actual: {model_actual}",
        f"language: {LANGUAGE}",
        f"input_tokens: {input_tokens}",
        f"output_tokens: {output_tokens}",
        f"response_length_chars: {len(text)}",
        f"response_length_words: {len(text.split())}",
        f"response_language: {detected_lang}",
        f"mk_mention: {mk_value}",
        f"mk_citation: {mk_citation}",
        f"mk_position_raw: {mk_pos_raw}",
        "",
        "=== CITATIONS ===",
        # Gemini entries: "domain_title | redirect_uri" (title used for MK detection, URI kept for debugging)
        # All other models: plain URLs
        *citations,
        "",
        "=== RESPONSE ===",
        text,
    ])
    filepath.write_text(content, encoding="utf-8")
    return filepath


# ── Google Sheets ─────────────────────────────────────────────────────────────

def setup_sheets():
    import gspread
    gc = gspread.service_account(filename=str(SERVICE_ACCOUNT_FILE))
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.get_worksheet_by_id(SHEET_GID)
    return sh, ws


def get_logged_query_ids(ws) -> set[str]:
    """Return the set of Query_IDs that already have at least one logged row."""
    # Log sheet column C (index 2) = Query_ID
    ids = ws.col_values(3)   # 1-based column number
    return {v.strip() for v in ids[1:] if v.strip()}


def get_starting_log_num(ws) -> int:
    ids = ws.col_values(1)
    max_num = 0
    for val in ids[1:]:
        if val.upper().startswith("L"):
            num_part = val[1:].split("_")[0]   # handles both L0001 and L0001_SK
            if num_part.isdigit():
                max_num = max(max_num, int(num_part))
    return max_num + 1


def load_queries(
    sh,
    use_google_query: bool = False,
    query_set_filter: str = "",
    limit: int = 0,
) -> list[tuple[str, str]]:
    ws = sh.worksheet("Queries")
    rows = ws.get_all_values()
    # Column layout (14 cols):
    # A=ID  B=Kategória  C=Podkategória  D=Otázka_SK  E=Google_query_SK
    # F=Otázka_CZ  G=Google_query_CZ  H=Prioritne_MVP
    # I=B2B_persona  J=Prečo  K=Query_Set  L=Query_Source  M=GSC_Position  N=GSC_Impressions
    MVP_COL   = 7   # H
    QSET_COL  = 10  # K
    QUERY_COL = 4 if use_google_query else 3   # E vs D

    results = []
    for row in rows[1:]:
        if not row[0]:
            continue
        if len(row) <= MVP_COL or row[MVP_COL].strip().upper() != "ANO":
            continue
        if query_set_filter:
            row_set = row[QSET_COL].strip() if len(row) > QSET_COL else ""
            if row_set != query_set_filter:
                continue
        if len(row) <= QUERY_COL or not row[QUERY_COL]:
            continue
        results.append((row[0], row[QUERY_COL]))

    if limit:
        results = results[:limit]
    return results


def append_sheet_row(
    ws, log_num: int, query_id: str, model: str,
    mk_value: str, mk_citation: str, mk_pos: str,
):
    today  = datetime.date.today().strftime("%Y-%m-%d")
    log_id = f"L{log_num:04d}_{LANGUAGE}"
    row = [
        log_id,       # Log_ID        — Part 8: L0001_SK
        today,        # Date
        query_id,     # Query_ID
        model,        # Model
        LANGUAGE,     # Language
        mk_citation,  # MK_Citation   — Part 2
        mk_value,     # MK_Mention
        "N/A",        # MK_Sentiment
        mk_pos,       # MK_Position   — Part 7
        "",           # Competitor_Sources
        "",           # Brands_Mentioned
        "",           # Response_URL
        "",           # Notes
        "API",        # Tester
        "",           # Kategória
    ]
    ws.append_row(row, value_input_option="USER_ENTERED")


# ── API callers ───────────────────────────────────────────────────────────────

def call_openai(query: str) -> CallResult:
    from openai import OpenAI
    client   = OpenAI(api_key=OPENAI_API_KEY)
    response = client.responses.create(
        model="gpt-4o",
        tools=[{"type": "web_search_preview"}],
        input=query,
    )
    usage = response.usage
    return CallResult(
        text          = response.output_text or "",
        model_actual  = response.model or "gpt-4o",
        input_tokens  = getattr(usage, "input_tokens", 0) or 0,
        output_tokens = getattr(usage, "output_tokens", 0) or 0,
        citations     = _citations_openai(response),
    )


def _extract_gemini_text(response) -> str:
    for candidate in response.candidates or []:
        parts = [
            p.text for p in (candidate.content.parts or [])
            if p.text and not getattr(p, "thought", False)
        ]
        if parts:
            return "\n".join(parts)
    return response.text or ""


def call_gemini(query: str) -> CallResult:
    from google import genai
    from google.genai import types
    client        = genai.Client(api_key=GEMINI_API_KEY)
    last_response = None
    text          = ""
    for _ in range(3):
        response      = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=query,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
        last_response = response
        text          = _extract_gemini_text(response)
        if text:
            break
    usage = getattr(last_response, "usage_metadata", None)
    return CallResult(
        text          = text,
        model_actual  = getattr(last_response, "model_version", None) or "gemini-2.5-pro",
        input_tokens  = getattr(usage, "prompt_token_count", 0) or 0,
        output_tokens = getattr(usage, "candidates_token_count", 0) or 0,
        citations     = _citations_gemini(last_response),
    )


def call_perplexity(query: str) -> CallResult:
    from openai import OpenAI
    client   = OpenAI(api_key=PERPLEXITY_API_KEY, base_url="https://api.perplexity.ai")
    response = client.chat.completions.create(
        model="sonar",
        messages=[{"role": "user", "content": query}],
    )
    usage = response.usage
    return CallResult(
        text          = response.choices[0].message.content or "",
        model_actual  = response.model or "sonar",
        input_tokens  = getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens = getattr(usage, "completion_tokens", 0) or 0,
        citations     = _citations_perplexity(response),
    )


def _extract_serp_overview(results: dict) -> tuple[str, list[str]]:
    """Return (ai_overview_text, citation_urls) from a SerpAPI result dict."""
    text_parts: list[str] = []
    urls:       list[str] = []

    ai = results.get("ai_overview") or {}
    if ai:
        # Direct text field
        if ai.get("text"):
            text_parts.append(ai["text"])

        # Step-1 style: blocks with text/links
        for block in ai.get("blocks") or []:
            if block.get("text"):
                text_parts.append(block["text"])
            for link in block.get("links") or []:
                if link.get("url"):
                    urls.append(link["url"])

        # Step-2 style: text_blocks with snippet or list items
        for block in ai.get("text_blocks") or []:
            if block.get("snippet"):
                text_parts.append(block["snippet"])
            for item in block.get("list") or []:
                if item.get("snippet"):
                    text_parts.append("- " + item["snippet"])

        # References / sources (both step-1 and step-2 names)
        for ref in (ai.get("references") or ai.get("sources") or []):
            url = ref.get("link") or ref.get("url") or ""
            # Strip fragment anchors added by SerpAPI (…#:~:text=…)
            clean = url.split("#:~:")[0]
            if clean:
                urls.append(clean)

    # Fallback to answer_box (featured snippet) if no AI Overview
    if not text_parts:
        ab = results.get("answer_box") or {}
        for field in ("answer", "snippet", "result"):
            if ab.get(field):
                text_parts.append(ab[field])
                break
        if ab.get("link"):
            urls.append(ab["link"])

    return "\n".join(text_parts), list(dict.fromkeys(urls))


def call_serp(query: str, language: str = "SK") -> CallResult:
    from serpapi import GoogleSearch
    locale = SERP_LOCALE.get(language, SERP_LOCALE["SK"])
    params = {
        "engine":       "google",
        "q":            query,
        "api_key":      SERPAPI_KEY,
        **locale,
    }
    results = GoogleSearch(params).get_dict()

    # Two-step pattern: initial search may return only a page_token for AI Overview.
    # Fetch actual content with a second call when no text/blocks are present.
    ai = results.get("ai_overview") or {}
    page_token = ai.get("page_token")
    if page_token and not ai.get("text") and not ai.get("blocks"):
        r2 = GoogleSearch({
            "engine":     "google_ai_overview",
            "page_token": page_token,
            "api_key":    SERPAPI_KEY,
        }).get_dict()
        results = r2

    text, urls = _extract_serp_overview(results)
    return CallResult(
        text          = text,
        model_actual  = "google-ai-overview",
        input_tokens  = 0,
        output_tokens = 0,
        citations     = urls,
    )


MODELS = [
    ("gpt-4o",             call_openai),
    ("gemini-2.5-pro",     call_gemini),
    ("sonar (perplexity)", call_perplexity),
    ("google-ai-overview", lambda q: call_serp(q, LANGUAGE)),
]


# ── Setup ─────────────────────────────────────────────────────────────────────

print("Connecting to Google Sheets...", end=" ", flush=True)
try:
    sh, ws  = setup_sheets()
    log_num = get_starting_log_num(ws)
    if RETRY_QIDS_FILE:
        retry_ids    = {l.strip() for l in open(RETRY_QIDS_FILE) if l.strip()}
        all_queries  = load_queries(sh, use_google_query=False, query_set_filter="")
        queries_data = [(qid, q) for qid, q in all_queries if qid in retry_ids]
        mode_label   = f"RETRY ({len(queries_data)} qids from {RETRY_QIDS_FILE})"
    elif TEST_MODE:
        queries_data = TEST_QUERIES
        mode_label   = "TEST MODE"
    elif SERP_ONLY:
        queries_data = load_queries(sh, use_google_query=True,
                                    query_set_filter=QUERY_SET_FILTER,
                                    limit=DRY_RUN_LIMIT if DRY_RUN else 0)
        mode_label   = "SERP-ONLY (col E)"
    else:
        queries_data = load_queries(sh, use_google_query=False,
                                    query_set_filter=QUERY_SET_FILTER,
                                    limit=DRY_RUN_LIMIT if DRY_RUN else 0)
        mode_label   = "FULL RUN (col D)"

    if SKIP_LOGGED and not TEST_MODE and not RETRY_QIDS_FILE:
        already_logged  = get_logged_query_ids(ws)
        before          = len(queries_data)
        queries_data    = [(qid, q) for qid, q in queries_data if qid not in already_logged]
        skipped         = before - len(queries_data)
        skip_tag        = f" | skipped {skipped} already-logged"
    else:
        skip_tag        = ""

    dry_tag  = f" — DRY RUN first {DRY_RUN_LIMIT}" if DRY_RUN and not TEST_MODE else ""
    qset_tag = f" | filter: {QUERY_SET_FILTER!r}" if QUERY_SET_FILTER else ""
    print(f"OK — last Log_ID in sheet: L{log_num - 1:04d}_{LANGUAGE} → next: L{log_num:04d}_{LANGUAGE}")
    print(f"Mode: {mode_label}{qset_tag}{skip_tag}{dry_tag} | {len(queries_data)} queries to run")
except Exception as e:
    print(f"FAILED ({e})")
    raise SystemExit(1)

active_models = [("google-ai-overview", lambda q: call_serp(q, LANGUAGE))] if SERP_ONLY else MODELS


# ── Main loop ─────────────────────────────────────────────────────────────────

results = []

for query_id, query in queries_data:
    print(f"\n{'='*70}")
    print(f"QUERY [{query_id}]: {query}")
    print("="*70)

    for model_name, fn in active_models:
        model_short = MODEL_SHORT.get(model_name, model_name)
        print(f"\n  [{model_name}]")

        result, exc = None, None
        try:
            result = fn(query)
        except Exception as e:
            exc = e

        # Part 6 — timestamp at moment of response
        timestamp = datetime.datetime.now()

        text          = result.text          if result else ""
        citations     = result.citations     if result else []
        model_actual  = result.model_actual  if result else model_name
        input_tokens  = result.input_tokens  if result else 0
        output_tokens = result.output_tokens if result else 0

        # Part 2/5/7
        mk_value      = _classify_response(text, exc)
        mk_cit        = check_mk_citation(citations, exc)
        mk_pos_label, mk_pos_pct = mk_position(text, mk_value)
        detected_lang = detect_language(text)

        if exc:
            print(f"  ERROR:       {exc}")
        else:
            snippet = text[:300].replace("\n", " ")
            print(f"  MK_Mention:  {mk_value}")
            print(f"  MK_Citation: {mk_cit}  ({len(citations)} URLs)")
            print(f"  MK_Position: {mk_pos_label}")
            print(f"  Language:    {detected_lang}")
            print(f"  Tokens:      in={input_tokens}  out={output_tokens}")
            print(f"  Model:       {model_actual}")
            print(f"  Response:    {snippet}{'...' if len(text) > 300 else ''}")

        # Part 1 — raw .txt file
        raw_path = save_raw_output(
            query_id=query_id, query_text=query,
            model_name=model_name, model_short=model_short, model_actual=model_actual,
            timestamp=timestamp, text=text, citations=citations,
            input_tokens=input_tokens, output_tokens=output_tokens,
            detected_lang=detected_lang, mk_value=mk_value,
            mk_citation=mk_cit, mk_pos_label=mk_pos_label, mk_pos_pct=mk_pos_pct,
        )
        print(f"  Saved:       {raw_path.relative_to(pathlib.Path.cwd())}")

        # Sheets
        try:
            append_sheet_row(ws, log_num, query_id, model_name, mk_value, mk_cit, mk_pos_label)
            print(f"  Sheets:      L{log_num:04d}_{LANGUAGE} [{mk_value} / cit:{mk_cit} / pos:{mk_pos_label}]")
            log_num += 1
        except Exception as e:
            print(f"  Sheets:      ERROR — {e}")

        results.append({
            "query_id":          query_id,
            "query":             query,
            "model":             model_name,
            "model_actual":      model_actual,
            "timestamp":         timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "response_text":     text or f"ERROR: {exc}",
            "mk_mention":        mk_value,
            "mk_citation":       mk_cit,
            "mk_position":       mk_pos_label,
            "input_tokens":      input_tokens,
            "output_tokens":     output_tokens,
            "response_language": detected_lang,
        })


# ── CSV output ────────────────────────────────────────────────────────────────

output_path = pathlib.Path(__file__).parent / "test_output.csv"
with open(output_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows(results)

print(f"\n\nResults saved to {output_path}")
mk_counts  = Counter(r["mk_mention"]  for r in results)
cit_counts = Counter(r["mk_citation"] for r in results)
print(f"MK_Mention:  { {k: mk_counts[k]  for k in sorted(mk_counts)} }")
print(f"MK_Citation: { {k: cit_counts[k] for k in sorted(cit_counts)} }")
