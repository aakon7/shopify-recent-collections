# fms-campaigns

CLI pipeline for building, auditing, and scheduling FMS banner-stack email campaigns in Omnisend.

Replaces the ad-hoc Cowork skill at `omnisend-banner-campaigns/` with a reproducible, audited workflow. See `BUILD_SPEC.md` (when added) for the full design brief.

## What it does

A "banner series" is a multi-day Omnisend campaign where each email is a vertical stack of ~19 banner images, each linking to its `/collections/<handle>` page on the Shopify storefront, plus a fixed Mystery Bundle promo at the bottom.

This tool owns the lifecycle:

1. **ingest** — read a folder of banner files; upload to Omnisend's image library; dedupe by sha256
2. **match** — OCR each banner and fuzzy-match to a live Shopify collection handle
3. **build** — render `day{N}_*.json` per email and PUT to Omnisend
4. **audit** — verify every campaign has correct structure, valid links, no duplicate handles, no empty collections
5. **schedule** — set DST-aware send times; hard-gates on the most recent audit having passed

## Status

v1 / MVP per spec Appendix B. What works:

- Project skeleton, config loader (TOML + env), SQLite state, rate-limited HTTP client
- Omnisend + Shopify storefront clients
- Content builder (ports `build_day_content.py` from the reference skill)
- OCR + fuzzy-match (ports `match_banners.py`)
- Cheap + medium audit (ports + improves on `sanity_check.py` and `check_links.py`)
- DST-aware scheduling helpers
- CLI: `ingest`, `match`, `build`, `audit`, `schedule`, `brand show|refresh-collections`, `status`

What's deferred to v1.1+:

- Interactive `review` command for low-confidence matches
- Full `plan` command (currently auto-generates a naive plan if `series_plan.json` is absent)
- `edit` subcommands (`fix-link`, `swap-banner`, `fix-alt`)
- `--deep` audit (vision LLM banner-art check) — flag exists, no-op in v1
- Shopify Admin Files-tab ingestion (folder-only for now)

## Install

```bash
git clone <repo>
cd fms-email-campaign-system
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

System dependency for OCR:

```bash
# Debian/Ubuntu
sudo apt-get install tesseract-ocr

# macOS
brew install tesseract
```

## First-run setup

```bash
cp .env.example .env
# Edit .env: set OMNISEND_API_KEY (required) and ANTHROPIC_API_KEY (for --deep audit)

# Edit config/fms.toml: set brand.template.campaign_id to a known-good template campaign id
```

Then refresh the cached collections list:

```bash
fms-campaigns brand refresh-collections
```

## Happy path

```bash
fms-campaigns ingest --series spring-2026 --folder ./input/banners/spring-2026
fms-campaigns match  --series spring-2026
fms-campaigns build  --series spring-2026
fms-campaigns audit  --series spring-2026
fms-campaigns schedule --series spring-2026 --start 2026-05-04 --time 09:00
```

## Configuration

`config/<brand>.toml` — brand-specific defaults (sender, menu, template ids, rate limits). Secrets are NEVER in the toml — they go in `.env`.

State (SQLite + content/ + reports/) lives in the project directory by default. Override with `FMS_STATE_DIR` env var.

## Deployment notes

If running on a GoDaddy VPS or any Linux host:

- **Python 3.11+** required. Use `pyenv` if the system Python is older.
- **Tesseract** must be installed system-wide for the `match` stage. Shared/managed hosting where you can't apt-install Tesseract → run `match` locally and only use the server for `build`/`audit`/`schedule`.
- **Cron** for scheduled audits: `0 3 * * * fms-campaigns audit --series <current> --no-network`
- **Outbound CDN allowlist**: `fabric.fabricmegastore.com` must be reachable for the deep audit's banner downloads (this is a vanity CNAME on Omnisend's CDN, not part of the storefront apex).

## Development

```bash
pytest                                # run tests
ruff check src tests                  # lint
mypy src                              # type-check
```

Coverage target for `src/fms_campaigns/audit.py` specifically: > 90% (per spec §13).

## Known Omnisend quirks (don't relearn the hard way)

See spec §10. Highlights:

- PUT requires the **full document**; partial PUTs return 400.
- GET response has an echo artifact in the footer text block (`617907de59b3af4e5159b637`). Trust the local file, never write back what GET returned.
- Block IDs are reused from the template — don't generate new ones.
- `resizeHeight = 800 * height / 850`. Computed, never hardcoded.
- Mystery Bundle is at `/products/`, not `/collections/`.
