#!/usr/bin/env python3
"""
E23Ready v0.1 — vendor-AI intake triage kit for OSFI E-23 / B-10.

An open-source CLI that loads a vendor pack (YAML), runs a 20-question intake
(YAML-driven), and emits the four artifacts OSFI E-23 demands for every
third-party AI tool at a Canadian bank:
  1. model inventory entry
  2. E-23 risk-tier classification
  3. B-10 due-diligence gap report
  4. board-ready one-pager

Stdlib only. No network calls. No inference. No data leaves the machine.
"""

import argparse
import datetime
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PACK = os.path.join(BASE_DIR, "packs", "example-vendor.yaml")
DEFAULT_QUESTIONS = os.path.join(BASE_DIR, "intake-questions.yaml")
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

TIER_ORDER = {"low": 0, "moderate": 1, "high": 2}
EVIDENCE_OPTS = ["supported", "partial", "no", "unknown"]


# ---------------------------------------------------------------------------
# Minimal YAML-subset parser.
# Supports exactly what this project's YAML files use: indentation-based
# nested mappings, "- " sequences, "key: value" scalars, quoted strings and
# "#" comments. Anything fancier (anchors, multi-line blocks, inline lists)
# is NOT supported — write packs inside the subset documented in SCHEMA.md.
# ---------------------------------------------------------------------------
def _strip_comment(line):
    in_s, in_d = False, False
    for i, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            return line[:i].rstrip()
    return line.rstrip()


def _inline_list(text):
    """Parse a single-line [a, b, "c"] list. Returns list, or None if not one."""
    text = text.strip()
    if not (text.startswith("[") and text.endswith("]")):
        return None
    inner = text[1:-1]
    items, cur, in_s, in_d = [], "", False, False
    for ch in inner:
        if ch == "'" and not in_d:
            in_s = not in_s
            cur += ch
        elif ch == '"' and not in_s:
            in_d = not in_d
            cur += ch
        elif ch == "," and not in_s and not in_d:
            items.append(_scalar(cur))
            cur = ""
        else:
            cur += ch
    if cur.strip():
        items.append(_scalar(cur))
    return items


def _scalar(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def _parse_block(lines, i, indent):
    obj = None
    while i < len(lines):
        raw = lines[i]
        if not raw.strip():
            i += 1
            continue
        cur = len(raw) - len(raw.lstrip(" "))
        if cur < indent:
            break
        line = raw.strip()
        if line.startswith("- ") or line == "-":
            # sequence entry
            rest = _scalar(line[1:].strip())
            if obj is None:
                obj = []
            if not isinstance(obj, list):
                raise ValueError("mixed mapping and sequence at line %d" % (i + 1))
            if rest == "":
                sub, i = _parse_block(lines, i + 1, cur + 2)
                obj.append(sub)
            elif ": " in rest or rest.endswith(":"):
                # "- key: value" inline mapping, continued by following lines
                entry = {}
                k, _, v = rest.partition(":")
                v = v.strip()
                if v:
                    lst = _inline_list(v)
                    entry[_scalar(k)] = lst if lst is not None else _scalar(v)
                sub, i = _parse_block(lines, i + 1, cur + 2)
                if isinstance(sub, dict):
                    entry.update(sub)
                obj.append(entry)
            else:
                obj.append(rest)
                i += 1
        else:
            # mapping entry
            if obj is None:
                obj = {}
            if not isinstance(obj, dict):
                raise ValueError("mixed mapping and sequence at line %d" % (i + 1))
            if ":" not in line:
                raise ValueError("expected 'key: value' at line %d" % (i + 1))
            k, _, v = line.partition(":")
            k, v = _scalar(k), v.strip()
            if v:
                lst = _inline_list(v)
                obj[k] = lst if lst is not None else _scalar(v)
                i += 1
            else:
                sub, i = _parse_block(lines, i + 1, cur + 2)
                obj[k] = sub
    return (obj if obj is not None else {}), i


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as fh:
        lines = [_strip_comment(l) for l in fh.read().splitlines()]
    data, _ = _parse_block(lines, 0, 0)
    return data


def dump_answers_yaml(answers, date_str):
    out = ["# E23Ready intake answers — generated %s" % date_str, "answers:"]
    for qid, ans in answers.items():
        out.append("  %s: %s" % (qid, ans))
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Pack / questions loading + validation
# ---------------------------------------------------------------------------
REQUIRED_PACK_FIELDS = ["vendor", "product", "pack_version", "checklist"]
REQUIRED_ITEM_FIELDS = ["id", "item", "status", "evidence", "source_url"]
REQUIRED_Q_FIELDS = ["id", "category", "prompt", "options"]


def validate_pack(pack):
    errors = []
    if not isinstance(pack, dict):
        return ["pack is not a mapping"]
    for f in REQUIRED_PACK_FIELDS:
        if f not in pack:
            errors.append("missing pack field: %s" % f)
    if "checklist" in pack:
        if not isinstance(pack["checklist"], list) or not pack["checklist"]:
            errors.append("checklist must be a non-empty list")
        else:
            for n, item in enumerate(pack["checklist"], 1):
                if not isinstance(item, dict):
                    errors.append("checklist entry %d is not a mapping" % n)
                    continue
                for f in REQUIRED_ITEM_FIELDS:
                    if f not in item:
                        errors.append("checklist entry %d missing field: %s" % (n, f))
                if item.get("status") not in EVIDENCE_OPTS:
                    errors.append(
                        "checklist entry %d has bad status %r (must be one of %s)"
                        % (n, item.get("status"), "/".join(EVIDENCE_OPTS))
                    )
    return errors


def validate_questions(qdata):
    errors = []
    if not isinstance(qdata, dict) or not isinstance(qdata.get("questions"), list):
        return ["questions file must contain a 'questions' list"]
    for n, q in enumerate(qdata["questions"], 1):
        if not isinstance(q, dict):
            errors.append("question %d is not a mapping" % n)
            continue
        for f in REQUIRED_Q_FIELDS:
            if f not in q:
                errors.append("question %d missing field: %s" % (n, f))
    return errors


def parse_options(raw):
    if isinstance(raw, list):
        return [str(o) for o in raw]
    return [o.strip() for o in str(raw).split(",") if o.strip()]


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------
def run_interactive(questions):
    answers = {}
    print("\nE23Ready intake — press Enter for 'unknown' on any question.\n")
    for n, q in enumerate(questions, 1):
        opts = parse_options(q["options"])
        default = "unknown" if "unknown" in opts else opts[0]
        print("[%d/%d] %s" % (n, len(questions), q["prompt"]))
        if q.get("help"):
            print("         %s" % q["help"])
        print("         options: %s" % " / ".join(opts))
        while True:
            raw = input("         answer [%s]: " % default).strip().lower()
            ans = raw if raw else default
            if ans in opts:
                answers[q["id"]] = ans
                break
            print("         please answer one of: %s" % ", ".join(opts))
        print("")
    return answers


def load_answers_file(path, questions):
    data = load_yaml(path)
    ans = data.get("answers", data) if isinstance(data, dict) else {}
    if not isinstance(ans, dict):
        raise ValueError("answers file %r has no usable mapping" % path)
    answers = {}
    valid = {q["id"]: set(parse_options(q["options"])) for q in questions}
    for q in questions:
        qid = q["id"]
        raw = ans.get(qid, "unknown")
        if raw is None:
            raw = "unknown"
        val = str(raw).strip().lower()
        if val not in valid[qid]:
            raise ValueError(
                "answer for %s is %r, must be one of %s"
                % (qid, raw, ", ".join(sorted(valid[qid])))
            )
        answers[qid] = val
    return answers


# ---------------------------------------------------------------------------
# Assessment logic
# ---------------------------------------------------------------------------
def combined_status(evidence, deployment):
    if evidence == "no" or deployment == "no":
        return "GAP"
    if evidence == "unknown" or deployment == "unknown":
        return "UNVERIFIED"
    if evidence == "partial" or deployment == "partial":
        return "PARTIAL"
    return "OK"


GAP_ACTION = {
    "OK": "None — re-confirm on quarterly pack refresh.",
    "PARTIAL": "Confirm with vendor; get contract language before rollout.",
    "GAP": "Remediate before rollout: require this control or document formal risk acceptance.",
    "UNVERIFIED": "Obtain evidence from vendor trust center / DPA before proceeding.",
}

TIER_LABEL = {"low": "LOW", "moderate": "MODERATE", "high": "HIGH"}


def compute_tier(answers, questions):
    dims = {}
    for q in questions:
        if q.get("category") == "e23_dimension":
            dims[q["id"]] = answers.get(q["id"], "unknown")
    rated = {k: v for k, v in dims.items() if v in TIER_ORDER}
    if not rated:
        return "UNDETERMINED", "no E-23 dimension answers provided"
    worst = max(rated.values(), key=lambda v: TIER_ORDER[v])
    detail = ", ".join(
        "%s=%s" % (q.get("short", q["id"]), answers.get(q["id"], "?"))
        for q in questions
        if q.get("category") == "e23_dimension"
    )
    return TIER_LABEL[worst], "driven by worst dimension (%s)" % detail


def board_verdict(tier, gap_count, unverified_count):
    if gap_count > 0 or tier == "HIGH":
        return (
            "CONDITIONAL PROCEED",
            "remediate GAP items and HIGH risk dimensions before enterprise rollout.",
        )
    if tier == "UNDETERMINED" or unverified_count > 0:
        return (
            "HOLD — GATHER EVIDENCE",
            "too many UNVERIFIED items; obtain vendor evidence first.",
        )
    if tier == "MODERATE":
        return "PROCEED", "with standard ongoing monitoring."
    return "PROCEED", "low risk, standard monitoring."


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render(template, ctx):
    out = template
    for key in sorted(ctx.keys(), key=len, reverse=True):
        out = out.replace("{{" + key + "}}", str(ctx[key]))
    leftover = [l for l in out.splitlines() if "{{" in l and "}}" in l]
    if leftover:
        raise ValueError("unfilled template placeholders: %s" % leftover[:3])
    return out


def status_emoji(status):
    return {"OK": "[OK]", "PARTIAL": "[~]", "GAP": "[!!]", "UNVERIFIED": "[??]"}.get(
        status, "[ ]"
    )


def build_rows(pack_items, questions, answers):
    q_by_item = {}
    for q in questions:
        if q.get("checklist_item"):
            q_by_item[q["checklist_item"]] = q["id"]
    rows = []
    counts = {"OK": 0, "PARTIAL": 0, "GAP": 0, "UNVERIFIED": 0}
    for item in pack_items:
        iid = item["id"]
        qid = q_by_item.get(iid)
        deployment = answers.get(qid, "unknown") if qid else "unknown"
        combo = combined_status(item["status"], deployment)
        counts[combo] += 1
        rows.append(
            {
                "id": iid,
                "item": item["item"],
                "evidence": item["evidence"],
                "evidence_status": item["status"],
                "deployment": deployment,
                "combined": combo,
                "action": GAP_ACTION[combo],
            }
        )
    return rows, counts


def context_answers(questions, answers):
    ctx = {}
    for q in questions:
        if q.get("category") == "context":
            ctx[q.get("short", q["id"])] = answers.get(q["id"], "unknown")
    return ctx


def dim_answers(questions, answers):
    dims = []
    for q in questions:
        if q.get("category") == "e23_dimension":
            dims.append((q.get("short", q["id"]), answers.get(q["id"], "unknown")))
    return dims


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_validate(args):
    pack = load_yaml(args.pack)
    qdata = load_yaml(args.questions)
    errs = validate_pack(pack) + validate_questions(qdata)
    qids = [q["id"] for q in qdata.get("questions", []) if isinstance(q, dict)]
    item_ids = {
        i["id"] for i in pack.get("checklist", []) if isinstance(i, dict) and "id" in i
    }
    for q in qdata.get("questions", []):
        if isinstance(q, dict) and q.get("checklist_item"):
            if q["checklist_item"] not in item_ids:
                errs.append(
                    "question %s references unknown checklist item %r"
                    % (q["id"], q["checklist_item"])
                )
    covered = {
        q["checklist_item"]
        for q in qdata.get("questions", [])
        if isinstance(q, dict) and q.get("checklist_item")
    }
    for iid in sorted(item_ids - covered):
        errs.append("checklist item %r has no intake question" % iid)
    if errs:
        print("VALIDATION FAILED:")
        for e in errs:
            print("  - %s" % e)
        return 1
    print(
        "pack %r OK: %d checklist items, %d questions (%d evidence / %d context / %d E-23 dimensions)"
        % (
            pack.get("product"),
            len(pack["checklist"]),
            len(qids),
            sum(1 for q in qdata["questions"] if q.get("category") == "evidence"),
            sum(1 for q in qdata["questions"] if q.get("category") == "context"),
            sum(1 for q in qdata["questions"] if q.get("category") == "e23_dimension"),
        )
    )
    return 0


def cmd_questions(args):
    qdata = load_yaml(args.questions)
    errs = validate_questions(qdata)
    if errs:
        for e in errs:
            print("  - %s" % e, file=sys.stderr)
        return 1
    for n, q in enumerate(qdata["questions"], 1):
        print(
            "%s [%s] %s"
            % (q["id"], q.get("category", "?"), q["prompt"])
        )
        print("    options: %s" % ", ".join(parse_options(q["options"])))
    return 0


def cmd_assess(args):
    pack = load_yaml(args.pack)
    qdata = load_yaml(args.questions)
    errs = validate_pack(pack) + validate_questions(qdata)
    if errs:
        for e in errs:
            print("  - %s" % e, file=sys.stderr)
        return 1
    questions = qdata["questions"]

    if args.answers:
        answers = load_answers_file(args.answers, questions)
    else:
        answers = run_interactive(questions)

    date_str = args.date or datetime.date.today().isoformat()
    analyst = args.analyst or "unassigned"

    rows, counts = build_rows(pack["checklist"], questions, answers)
    tier, tier_reason = compute_tier(answers, questions)
    verdict, verdict_why = board_verdict(
        tier, counts["GAP"], counts["UNVERIFIED"]
    )
    ctx_ans = context_answers(questions, answers)
    dims = dim_answers(questions, answers)

    evidence_table = "\n".join(
        "| %s | %s | %s | %s |"
        % (
            status_emoji(r["combined"]),
            r["item"],
            r["evidence"],
            r["combined"],
        )
        for r in rows
    )
    gap_table = "\n".join(
        "| %s | %s | %s (%s) | %s | %s | %s |"
        % (
            status_emoji(r["combined"]),
            r["item"],
            r["evidence_status"],
            r["evidence"],
            r["deployment"],
            r["combined"],
            r["action"],
        )
        for r in rows
    )
    dim_table = "\n".join(
        "| %s | %s |" % (name, TIER_LABEL.get(val, "UNSET").upper() if val in TIER_ORDER else "UNSET")
        for name, val in dims
    )
    context_block = "\n".join(
        "- **%s:** %s" % (k.replace("_", " ").title(), v) for k, v in ctx_ans.items()
    )

    ctx = {
        "vendor": pack["vendor"],
        "product": pack["product"],
        "pack_version": pack["pack_version"],
        "pack_status_note": pack.get("pack_status_note", ""),
        "assessment_date": date_str,
        "analyst": analyst,
        "overall_tier": tier,
        "tier_reason": tier_reason,
        "ok_count": counts["OK"],
        "partial_count": counts["PARTIAL"],
        "gap_count": counts["GAP"],
        "unverified_count": counts["UNVERIFIED"],
        "evidence_table": evidence_table,
        "gap_table": gap_table,
        "dim_table": dim_table,
        "context_block": context_block,
        "verdict": verdict,
        "verdict_why": verdict_why,
    }

    templates = [
        ("01-model-inventory-entry.md", "model-inventory-entry.md"),
        ("02-e23-risk-tier-classification.md", "e23-risk-tier-classification.md"),
        ("03-b10-due-diligence-gap-report.md", "b10-due-diligence-gap-report.md"),
        ("04-board-ready-one-pager.md", "board-ready-one-pager.md"),
    ]
    os.makedirs(args.out, exist_ok=True)
    for out_name, tpl_name in templates:
        tpl_path = os.path.join(TEMPLATE_DIR, tpl_name)
        if not os.path.exists(tpl_path):
            print("missing template: %s" % tpl_path, file=sys.stderr)
            return 1
        with open(tpl_path, "r", encoding="utf-8") as fh:
            rendered = render(fh.read(), ctx)
        with open(os.path.join(args.out, out_name), "w", encoding="utf-8") as fh:
            fh.write(rendered)
    with open(os.path.join(args.out, "answers.yaml"), "w", encoding="utf-8") as fh:
        fh.write(dump_answers_yaml(answers, date_str))

    print("E23Ready assessment complete for %s (%s)" % (pack["product"], pack["vendor"]))
    print("  overall risk tier : %s (%s)" % (tier, tier_reason))
    print("  controls          : %d OK / %d PARTIAL / %d GAP / %d UNVERIFIED"
          % (counts["OK"], counts["PARTIAL"], counts["GAP"], counts["UNVERIFIED"]))
    print("  board verdict     : %s — %s" % (verdict, verdict_why))
    print("  artifacts written to %s" % os.path.abspath(args.out))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="e23ready",
        description="E23Ready v0.1 — vendor-AI intake triage kit for OSFI E-23 / B-10 (stdlib only).",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    a = sub.add_parser("assess", help="run the intake and emit the four E-23 artifacts")
    a.add_argument("--pack", default=DEFAULT_PACK, help="vendor pack YAML")
    a.add_argument("--questions", default=DEFAULT_QUESTIONS, help="intake questions YAML")
    a.add_argument("--answers", default=None, help="answers YAML (non-interactive); otherwise prompts")
    a.add_argument("--out", default=os.path.join(BASE_DIR, "output"), help="output directory")
    a.add_argument("--analyst", default=None, help="analyst name for the report header")
    a.add_argument("--date", default=None, help="assessment date (YYYY-MM-DD); default today")
    a.set_defaults(func=cmd_assess)

    v = sub.add_parser("validate", help="validate a vendor pack + question set")
    v.add_argument("--pack", default=DEFAULT_PACK)
    v.add_argument("--questions", default=DEFAULT_QUESTIONS)
    v.set_defaults(func=cmd_validate)

    q = sub.add_parser("questions", help="list the intake questions")
    q.add_argument("--questions", default=DEFAULT_QUESTIONS)
    q.set_defaults(func=cmd_questions)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
