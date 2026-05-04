import os, json
from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

response = client.models.generate_content(
    model="gemini-2.5-pro",
    contents="najlepší kočík pre mestské prostredie",
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
    ),
)

print("=" * 60)
print("TOP-LEVEL RESPONSE ATTRIBUTES")
print("=" * 60)
for attr in dir(response):
    if not attr.startswith("_"):
        print(f"  {attr}")

print()
print("=" * 60)
print("GROUNDING METADATA")
print("=" * 60)

for ci, candidate in enumerate(response.candidates or []):
    gm = getattr(candidate, "grounding_metadata", None)
    if gm is None:
        print("  No grounding_metadata on candidate", ci)
        continue

    print(f"\n--- candidate {ci} grounding_metadata ---")
    print("  type:", type(gm))
    print("  dir():", [a for a in dir(gm) if not a.startswith("_")])

    # Try JSON serialisation
    try:
        print("\n  JSON dump:")
        print(json.dumps(type(gm).to_json(gm) if hasattr(type(gm), "to_json")
              else json.loads(gm.__class__.__module__), indent=2))
    except Exception:
        pass

    # Try proto-style dict
    for method in ("to_dict", "__dict__", "_pb"):
        try:
            val = getattr(gm, method)() if callable(getattr(gm, method, None)) else getattr(gm, method)
            print(f"\n  via {method}:")
            print(json.dumps(str(val)[:2000], indent=2))
        except Exception as e:
            print(f"  {method}: {e}")

    chunks = getattr(gm, "grounding_chunks", None) or []
    print(f"\n  grounding_chunks count: {len(chunks)}")

    for i, chunk in enumerate(chunks[:5]):
        print(f"\n  --- chunk[{i}] ---")
        print(f"  type: {type(chunk)}")
        print(f"  dir: {[a for a in dir(chunk) if not a.startswith('_')]}")

        try:
            print(f"  vars: {vars(chunk)}")
        except Exception as e:
            print(f"  vars() failed: {e}")

        # Proto _pb
        try:
            pb = chunk._pb
            print(f"  _pb: {pb}")
        except Exception as e:
            print(f"  _pb: {e}")

        # Web sub-object
        web = getattr(chunk, "web", None)
        if web is not None:
            print(f"\n  chunk.web:")
            print(f"    type: {type(web)}")
            print(f"    dir: {[a for a in dir(web) if not a.startswith('_')]}")
            for field in ("uri", "title", "domain", "displayed_link",
                          "original_uri", "redirect_uri", "url"):
                try:
                    val = getattr(web, field, "ATTR_MISSING")
                    print(f"    .{field}: {val!r}")
                except Exception as e:
                    print(f"    .{field}: ERROR {e}")
            try:
                print(f"    vars(web): {vars(web)}")
            except Exception as e:
                print(f"    vars(web) failed: {e}")
            try:
                print(f"    web._pb: {web._pb}")
            except Exception as e:
                print(f"    web._pb: {e}")
        else:
            print("  chunk.web: None")

    # grounding_supports (contains text segments + chunk indices)
    supports = getattr(gm, "grounding_supports", None) or []
    print(f"\n  grounding_supports count: {len(supports)}")
    if supports:
        s = supports[0]
        print(f"  first support dir: {[a for a in dir(s) if not a.startswith('_')]}")
        try:
            print(f"  first support _pb: {s._pb}")
        except Exception as e:
            print(f"  first support _pb: {e}")

    # search_entry_point
    sep = getattr(gm, "search_entry_point", None)
    if sep:
        print(f"\n  search_entry_point dir: {[a for a in dir(sep) if not a.startswith('_')]}")
        try:
            print(f"  search_entry_point._pb: {sep._pb}")
        except Exception as e:
            print(f"  search_entry_point._pb: {e}")
