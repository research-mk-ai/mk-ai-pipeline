# Project: MK AI Visibility Research Pipeline

## Repository
- GitHub: https://github.com/research-mk-ai/mk-ai-pipeline (public)
- Local path: ~/Projects/MK_AI_Research_Automation/

## Git workflow (MANDATORY)
After every successful code change to any tracked file in this project:
1. Run `git add -A`
2. Run `git commit -m "<descriptive message based on what changed>"`
3. Run `git push origin main`

Do this automatically without asking for confirmation. Use clear commit messages that describe what was changed and why.

## What NOT to commit
The `.gitignore` already excludes:
- Secrets: `.env`, `service_account.json`
- Generated data: `Raw_Outputs/`, `*.csv`
- Python virtual env: `.venv/`
- Local config: `.claude/`, `.DS_Store`

Never use `git add -f` to force-add ignored files unless I explicitly ask.

## Project context
- Main script: `pipeline.py` — measures AI visibility of modrykonik.sk across 4 models (GPT-4o, Gemini 2.5 Pro, Perplexity Sonar, Google AI Overview via SerpAPI)
- Logs results to Google Sheets (Spreadsheet ID: 1ietJCNHqVp6wYyUCssnMmUEp-SaHtKmX66A5M7QmUSE)
- Saves raw outputs to `Raw_Outputs/YYYY-WNN/` folders

## Communication
- Reply in English (default for Claude Code)
- Be concise and step-by-step
- Show command outputs when running bash commands
