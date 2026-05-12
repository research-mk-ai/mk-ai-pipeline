# MK AI Visibility Tracker — Pipeline

AI search visibility measurement for **modrykonik.sk** and **modrykonik.cz** across major LLMs and AI Overview surfaces.

## What it does

For each query in the source Google Sheet, the pipeline calls 5 AI surfaces and records whether `modrykonik` is mentioned and/or cited:

- **GPT-4o** (OpenAI)
- **Gemini 2.5 Pro** (Google)
- **Sonar** (Perplexity)
- **Google AI Overview** (via SerpAPI)
- **Claude Sonnet 4.6** (Anthropic, with web_search tool)

Results are written back to the Google Sheet (`Log` tab for SK, `Log_CZ` for CZ) and raw responses are archived to `Raw_Outputs/`.

## Modes

- **`COUNTRY = "SK"`** — runs against `Queries` tab, SerpAPI `gl=sk`, `modrykonik.sk` pattern.
- **`COUNTRY = "CZ"`** — runs against `Queries_CZ` tab, SerpAPI `gl=cz`, `modrykonik.cz` pattern. Requires Czech VPN (Windscribe Prague) to control IP geolocation.
- **`TEST_MODE = True`** — uses hardcoded `TEST_QUERIES` instead of Sheet input.
- **`DRY_RUN = True`** — limits to first `DRY_RUN_LIMIT` queries.
- **`SERP_ONLY = True`** — calls only SerpAPI, skips other models.

## Where it runs

Single production server: **Mac Mini** (`doma-mac-mini` on Tailscale), accessed via SSH from any device on the tailnet. Pipeline is launched manually for now; cron via `launchd` is planned.

## Secrets

`.env` (API keys) and `service_account.json` (Google Sheets) live in `secrets/` with `chmod 600`, symlinked to repo root. Both are gitignored.
