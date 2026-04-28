# FMS Banner Campaign Pipeline — Build Spec

This is the engineering brief that drove the v1 build. The implementation in `src/fms_campaigns/` follows this structure.

---

## 1. Context

FabricMegaStore.com (FMS) sells quilting fabrics on Shopify. Marketing runs through Omnisend. Every few weeks we ship a multi-day "banner series" email campaign — typically 7 to 15 daily emails, each one a vertical stack of around 19 banner images, each banner linking to its matching `/collections/<handle>` page on the storefront. Plus a fixed Mystery Bundle promo at the bottom and a standard logo/menu/footer.

Producing a series is a repetitive, error-prone manual job in the Omnisend UI. We previously semi-automated it via a Cowork skill (`omnisend-banner-campaigns`) that calls the Omnisend API and runs OCR/match scripts locally. It worked, but was brittle: scripts ran ad-hoc, state was scattered across `day{N}_content.json` files in random folders, mistakes (wrong link on a banner, deleted collection still featured, banner art that didn't match its alt text) regularly slipped through.

**The need:** turn this into a proper software system — a CLI tool plus a small persistence layer — that owns the full lifecycle of a series end to end, with a real audit pass that catches the bugs we keep hitting.

## 2. Goals

1. **Reproducibility.** Given a folder of banner images and a Shopify store + Omnisend account, produce a complete, scheduled, audited series with a single command.
2. **Auditability.** Every campaign that goes out has been programmatically verified.
3. **Recoverability.** State persists locally (SQLite + versioned content folder). Any run can be resumed.
4. **Reusability across stores.** Brand-specific defaults live in per-brand TOML, not code.
5. **Mass-edit safety.** Editing an existing draft is a first-class command.

## 3. Non-goals

- Not a GUI (CLI only for v1).
- Not multi-tenant SaaS.
- Not an email design tool.
- Not a Shopify product manager (read-only).
- Not replacing Omnisend analytics.

## 4. Architecture

Single CLI binary backed by:

- Local SQLite database for state.
- Versioned content folder (`./campaigns/<series>/day{N}_*.json`).
- External clients for Shopify Storefront, Omnisend.
- OCR (tesseract) + optional vision LLM for deep audit.

See `src/fms_campaigns/` for the full implementation.

## 5. Decisions resolved (per spec §15)

| # | Decision | Pick | Notes |
|---|---|---|---|
| 1 | Language | Python 3.11+ | tesseract bindings, existing skill |
| 2 | Vision LLM | Anthropic SDK direct | simpler, cheaper |
| 3 | Shopify Files ingestion | Folder-only v1 | Admin API path is a follow-up |
| 4 | Multi-store | FMS-only with config seams | adding QFP = new toml |
| 5 | SQLite location | Per-project `./.fms/` | easier to back up + reset |
| 6 | Audit-before-schedule | Hard gate, `--force` escape | spec §15 |
| 7 | Cowork plugin | Post-v1 | |
| 8 | Logging | stdout (rich) + rotating file log | systemd/cron-friendly |

## 6. Rate limiting

- **Shopify storefront**: 1 request per 2.5 s per IP. 429 = ~60 s cool-off. Single-worker, polite-spacing default.
- **Omnisend CDN** (`fabric.fabricmegastore.com`): vanity CNAME; must be allowlisted explicitly in any sandboxed environment.

All HTTP traffic goes through `http_client.HttpClient` with per-host token-bucket buckets and exponential backoff on 429/5xx.

## 7. v1 scope (Appendix B of original spec)

- `ingest` + `match` + `build` + `audit` (cheap+medium) + `schedule`
- Skipped for v1: `review`, full `plan`, `edit *`, `--deep` audit (vision LLM)

## 8. Known Omnisend quirks (encoded in code)

1. PUT requires the FULL document.
2. GET response has echo artifacts in footer text block.
3. Block IDs are reused from the template.
4. `resizeHeight = 800 * height / 850` (computed, never hardcoded).
5. Mystery Bundle is `/products/`, not `/collections/`.
6. Cloning preserves block IDs; POST-from-scratch generates new ones.

## Reference

The original Cowork skill (`omnisend-banner-campaigns/`) is preserved at `reference_skill/` for shape lookups and edge-case knowledge. Do not import from it — it's archived reference material only.
