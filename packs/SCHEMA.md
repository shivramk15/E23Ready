# E23Ready vendor packs — schema documentation
# Packs live in this directory as <vendor-slug>.yaml. Write them in the
# supported YAML subset (see e23ready.py header): nested mappings by
# indentation, "- " sequences, "key: value" scalars, quoted strings, "#"
# comments. No anchors, no multi-line block scalars, no inline lists.

# Required pack fields:
#   vendor            string   legal vendor name
#   product           string   product name being assessed
#   pack_version      string   semver-ish; bump on every re-triage
#   pack_status       string   "example" | "draft" | "published"
#   pack_status_note  string   how this pack was built and what it is NOT
#   last_reviewed     string   YYYY-MM-DD
#   checklist         list     one entry per control below

# Required checklist entry fields:
#   id         string   one of the 13 control ids (see below)
#   item       string   human-readable control name
#   status     string   supported | partial | no | unknown
#   evidence   string   one-line summary of the public evidence found
#   source_url string   where the evidence came from (URL or "vendor trust center — VERIFY")

# The 13 control ids (stable — do not rename; questions map to these):
#   soc2_type2            SOC 2 Type II report (12-month period, under NDA)
#   iso27001              ISO 27001 certificate
#   data_residency_canada Canadian region / customer VPC / on-prem; PIPEDA documented
#   self_hosted           self-hosted or customer-VPC inference option
#   sub_processor_register sub-processor register + change-notification terms
#   zero_retention        zero-retention / no-training-on-customer-data DPA clause
#   ai_model_card         AI model card (models, versions, data touched, human-in-loop)
#   pen_test_summary      annual pen-test summary + vuln disclosure program
#   incident_sla_24h      incident notification SLA beating the 24h OSFI clock
#   exit_continuity       business continuity + exit (export format, termination help)
#   audit_rights          bank's right to audit or commission an audit
#   ip_indemnity          IP indemnity for AI-generated output
#   iso_42001             AI management posture (ISO 42001 or equivalent)

# Status discipline:
#   supported — control met; evidence cites a verifiable source
#   partial   — met in part (e.g. inherited from parent platform, region gaps)
#   no        — vendor does not offer it
#   unknown   — not found in public docs; needs vendor outreach

# Rule: a pack may ship with "unknown" entries, but may NEVER ship with
# statuses guessed from marketing pages. If you cannot cite it, mark unknown.
