# E23Ready v0.1 — vendor-AI intake triage kit for OSFI E-23 / B-10

**Public release — open source under the MIT License. Runs entirely inside a bank's own network; no data leaves.**

An open-source CLI that runs entirely inside a bank's own network. It loads a
vendor pack (public-docs research on one AI vendor), runs a 20-question intake with a
model-risk analyst, and emits the four artifacts OSFI E-23 demands for every
third-party AI tool: the model-inventory entry, the E-23 risk-tier classification,
the B-10 due-diligence gap report, and a board-ready one-pager.

Zero-spend stack: Python 3 stdlib only. No backend, no database, no inference.

## Run it

```bash
cd ~/workspace/lane3-e23ready

# validate pack + question set (checks schema and that every control has a question)
python3 e23ready.py validate

# list the 20 intake questions
python3 e23ready.py questions

# interactive intake on the example pack (prompts; Enter = unknown)
python3 e23ready.py assess

# non-interactive with canned answers
python3 e23ready.py assess --answers sample-answers.yaml --out output --analyst "Model Risk"
```

Artifacts land in `output/`:
`01-model-inventory-entry.md`, `02-e23-risk-tier-classification.md`,
`03-b10-due-diligence-gap-report.md`, `04-board-ready-one-pager.md`, plus `answers.yaml`.

## How to add a vendor pack

1. Copy `packs/example-vendor.yaml` to `packs/<vendor-slug>.yaml`.
2. Set `vendor`, `product`, `pack_version`, `pack_status: draft`, `last_reviewed`.
3. Fill the 13 checklist entries from the vendor's **trust center, DPA, and
   sub-processor pages** — not marketing pages. Rule: if you cannot cite it, mark `unknown`.
4. Run `python3 e23ready.py validate --pack packs/<vendor-slug>.yaml`.
5. Run an assessment and read the gap report like a banker would.

Write packs in the supported YAML subset only (documented in `packs/SCHEMA.md` and
the `e23ready.py` header): nested mappings by indentation, `- ` sequences,
`key: value` scalars, quoted strings, `#` comments. No anchors, no block scalars,
no inline lists — the parser will reject anything else.

## What's stubbed in v0.1

- **Vendor data is a worked example, not evidence.** `packs/example-vendor.yaml`
  (Muse) is built from public research with several `unknown`/`partial`
  entries. Verify every control against the trust center before real use.
- **No PDF output.** Artifacts are Markdown; Markdown→PDF export is not built.
- **No GRC export.** Real banks would map the inventory entry into ServiceNow /
  Archer / their E-23 spreadsheet — that mapping is a stub note, not code.
- **Fixed tier rules.** Overall tier = worst of the four E-23 dimensions; the
  board verdict rules are defaults. A bank would calibrate these.
- **Templated recommendations.** Gap actions are defaults, not legal advice.
- **Mini YAML parser.** Supports the documented subset only.
- **No pack library.** The wedge's distribution strategy is ~20 pre-built vendor
  packs; v0.1 ships one example. Packs 2–5 (Cursor, dbt Cloud AI, Monte Carlo AI
  monitors, Claude Code) are the next build step.
