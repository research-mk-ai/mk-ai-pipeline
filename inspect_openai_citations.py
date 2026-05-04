"""
Diagnostic: audit GPT-4o / web_search_preview citation structure.

Questions we want answered:
  1. Are the URLs in response text real domains or OpenAI/Bing redirect proxies?
  2. Does the Responses API expose any structured citation fields
     (annotations, url_citations, etc.) that _citations_openai() is missing?
"""

import os, re, json
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

from openai import OpenAI

MK_DOMAIN_PAT = re.compile(r"modrykonik\.(sk|cz)", re.IGNORECASE)
_URL_RE        = re.compile(r"https://[^\s\)\"'>\]]+")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

QUERY = "najlepší kočík pre mestské prostredie modrykonik diskusia recenzie"

print("=" * 70)
print("QUERY:", QUERY)
print("=" * 70)

response = client.responses.create(
    model="gpt-4o",
    tools=[{"type": "web_search_preview"}],
    input=QUERY,
)

# ── SECTION 1: full output_text ───────────────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 1 — response.output_text")
print("=" * 70)
print(response.output_text)

# ── SECTION 2: URLs extracted by current _citations_openai ───────────────────

extracted_urls = list(dict.fromkeys(_URL_RE.findall(response.output_text or "")))

print("\n" + "=" * 70)
print("SECTION 2 — URLs extracted by _citations_openai() regex")
print("=" * 70)
if extracted_urls:
    for url in extracted_urls:
        mk = " ← MK_DOMAIN_PAT MATCH" if MK_DOMAIN_PAT.search(url) else ""
        print(f"  {url}{mk}")
else:
    print("  (none found)")

print(f"\nMK match in extracted URLs: {any(MK_DOMAIN_PAT.search(u) for u in extracted_urls)}")

# ── SECTION 3: top-level response object ─────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 3 — top-level response attributes")
print("=" * 70)
for attr in sorted(dir(response)):
    if attr.startswith("_"):
        continue
    try:
        val = getattr(response, attr)
        if callable(val):
            continue
        print(f"  .{attr}: {repr(val)[:200]}")
    except Exception as e:
        print(f"  .{attr}: ERROR {e}")

# ── SECTION 4: response.output items ─────────────────────────────────────────

print("\n" + "=" * 70)
print("SECTION 4 — response.output items (type + attributes)")
print("=" * 70)
for i, item in enumerate(response.output or []):
    print(f"\n--- output[{i}] ---")
    print(f"  type(item): {type(item).__name__}")
    try:
        print(f"  item.type: {item.type!r}")
    except Exception:
        pass

    for attr in sorted(dir(item)):
        if attr.startswith("_"):
            continue
        try:
            val = getattr(item, attr)
            if callable(val):
                continue
            print(f"  .{attr}: {repr(val)[:300]}")
        except Exception as e:
            print(f"  .{attr}: ERROR {e}")

    # If item has .content (list), drill in
    content = getattr(item, "content", None)
    if content:
        for j, part in enumerate(content):
            print(f"\n  content[{j}]:")
            print(f"    type: {type(part).__name__}")
            for pattr in sorted(dir(part)):
                if pattr.startswith("_"):
                    continue
                try:
                    pval = getattr(part, pattr)
                    if callable(pval):
                        continue
                    print(f"    .{pattr}: {repr(pval)[:300]}")
                except Exception as e:
                    print(f"    .{pattr}: ERROR {e}")

            # annotations are often nested under content parts
            annotations = getattr(part, "annotations", None)
            if annotations:
                print(f"\n  content[{j}].annotations ({len(annotations)}):")
                for k, ann in enumerate(annotations[:10]):
                    print(f"    [{k}] type={type(ann).__name__}")
                    for aattr in sorted(dir(ann)):
                        if aattr.startswith("_"):
                            continue
                        try:
                            aval = getattr(ann, aattr)
                            if callable(aval):
                                continue
                            print(f"      .{aattr}: {repr(aval)[:200]}")
                        except Exception as e:
                            print(f"      .{aattr}: ERROR {e}")

# ── SECTION 5: structured URL citations summary ───────────────────────────────

print("\n" + "=" * 70)
print("SECTION 5 — structured URL citations (all annotations flattened)")
print("=" * 70)

structured_urls = []
for item in response.output or []:
    for part in getattr(item, "content", []) or []:
        for ann in getattr(part, "annotations", []) or []:
            url = getattr(ann, "url", None)
            title = getattr(ann, "title", None)
            if url:
                mk = " ← MK MATCH" if MK_DOMAIN_PAT.search(url) else ""
                structured_urls.append(url)
                print(f"  url:   {url}{mk}")
                if title:
                    print(f"  title: {title}")
                print()

if not structured_urls:
    print("  (no structured URL annotations found)")

print(f"\nMK match in structured citations: {any(MK_DOMAIN_PAT.search(u) for u in structured_urls)}")
print("\n" + "=" * 70)
print("DONE")
print("=" * 70)
