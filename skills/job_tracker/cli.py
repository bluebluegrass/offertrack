"""CLI for job_tracker package."""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from .pipeline import run


def _resolve_dates(args: argparse.Namespace) -> tuple[str, str]:
    if args.days is not None:
        end = date.today()
        start = end - timedelta(days=args.days)
        return start.isoformat(), end.isoformat()

    if not args.start or not args.end:
        raise SystemExit("Provide --days OR both --start and --end")
    return args.start, args.end


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run job tracker")
    parser.add_argument("--source", choices=["gmail", "sample", "csv"], required=True)
    parser.add_argument("--start", help="YYYY-MM-DD")
    parser.add_argument("--end", help="YYYY-MM-DD")
    parser.add_argument("--days", type=int)
    parser.add_argument("--out", default="output")
    parser.add_argument("--title", default="Job Search Summary")
    parser.add_argument("--max-messages", type=int, default=2000)
    parser.add_argument("--dry-run", action="store_true", help="Fetch/classify only; do not write files")
    parser.add_argument("--debug-sample", type=int, default=0, help="Print N sampled classified rows")
    parser.add_argument("--audit", action="store_true", help="Write one-row-per-application audit table CSV")
    parser.add_argument("--audit-path", default="output/audit_table.csv")
    parser.add_argument("--report", action="store_true", help="Write rule-hit confusion report")
    parser.add_argument("--report-path", default="output/rule_report.md")
    parser.add_argument("--report-topk", type=int, default=20)
    parser.add_argument("--key-debug", action="store_true", help="Write application-key quality debug CSVs")
    parser.add_argument("--key-debug-dir", default="output/debug/")
    parser.add_argument("--domain-debug", action="store_true", help="Write per-message domain/company extraction report")
    parser.add_argument("--domain-debug-path", default="output/debug/domain_report.csv")
    parser.add_argument("--reconcile", action="store_true", help="Write OA reconciliation debug reports")
    parser.add_argument("--reconcile-path", default="output/debug/reconcile_oa.csv")
    parser.add_argument("--gmail-query-mode", choices=["broad", "strict"], default="strict")
    parser.add_argument("--first-scan-report", action="store_true")
    parser.add_argument("--first-scan-report-path", default="output/debug/first_scan_report.csv")
    parser.add_argument("--ai-classify", action="store_true", help="Use LLM to classify relevant emails and build application table")
    parser.add_argument("--ai-model", default="gpt-4.1-mini")
    parser.add_argument("--ai-api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--ai-base-url", default="https://api.openai.com/v1")
    parser.add_argument("--ai-max-body-chars", type=int, default=7000)
    parser.add_argument("--relevant-emails-path", default="output/relevant_emails.csv")
    parser.add_argument("--ai-message-classification-path", default="output/ai_message_classification.csv")
    parser.add_argument("--ai-application-table-path", default="output/ai_application_table.csv")
    parser.add_argument("--ai-result-summary-path", default="output/ai_result_summary.json")
    parser.add_argument("--ai-sankey-path", default="output/ai_sankey.png")
    parser.add_argument("--email")
    parser.add_argument("--csv-path")
    parser.add_argument("--credentials", default="credentials.json")
    parser.add_argument("--token-dir", default=".tokens")
    parser.add_argument(
        "--no-interactive-auth",
        action="store_true",
        help="Disable browser/console OAuth fallback and require existing Gmail token",
    )
    return parser


def _print_summary(result) -> None:
    m = result.metrics
    r = result.rates
    print("Summary")
    print(
        f"applications={m.applications} replies={m.replies} no_replies={m.no_replies} "
        f"oa={m.oa} interviews={m.interviews} offers={m.offers} rejected={m.rejected} withdrawn={m.withdrawn}"
    )
    print(
        f"reply_rate_pct={r.reply_rate_pct} oa_rate_from_replies_pct={r.oa_rate_from_replies_pct} "
        f"interview_rate_from_oa_pct={r.interview_rate_from_oa_pct} "
        f"offer_rate_from_interviews_pct={r.offer_rate_from_interviews_pct} "
        f"application_to_offer_pct={r.application_to_offer_pct}"
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    start, end = _resolve_dates(args)

    if args.source == "gmail":
        print("Gmail run started. This can take 1-5 minutes depending on mailbox size and network.")
        print("Status: authenticating/fetching messages...")
    else:
        print("Run started.")

    result = run(
        source=args.source,
        start=start,
        end=end,
        out_dir=args.out,
        title=args.title,
        max_messages=args.max_messages,
        email=args.email,
        credentials_path=args.credentials,
        token_dir=args.token_dir,
        dry_run=args.dry_run,
        debug_sample=args.debug_sample,
        audit=args.audit,
        audit_path=args.audit_path,
        report=args.report,
        report_path=args.report_path,
        report_topk=args.report_topk,
        csv_path=args.csv_path,
        key_debug=args.key_debug,
        key_debug_dir=args.key_debug_dir,
        domain_debug=args.domain_debug,
        domain_debug_path=args.domain_debug_path,
        reconcile=args.reconcile,
        reconcile_path=args.reconcile_path,
        gmail_query_mode=args.gmail_query_mode,
        first_scan_report=args.first_scan_report,
        first_scan_report_path=args.first_scan_report_path,
        ai_classify=args.ai_classify,
        ai_model=args.ai_model,
        ai_api_key_env=args.ai_api_key_env,
        ai_base_url=args.ai_base_url,
        ai_max_body_chars=args.ai_max_body_chars,
        relevant_emails_path=args.relevant_emails_path,
        ai_message_classification_path=args.ai_message_classification_path,
        ai_application_table_path=args.ai_application_table_path,
        ai_result_summary_path=args.ai_result_summary_path,
        ai_sankey_path=args.ai_sankey_path,
        allow_interactive_auth=not args.no_interactive_auth,
    )

    print(f"Run ID: {result.run_id}")
    _print_summary(result)
    if args.dry_run:
        print("dry_run=true (no files written)")
    else:
        print(f"metrics.json: {result.artifacts['json_path']}")
        print(f"application_summary.csv: {result.artifacts.get('application_summary_csv_path','')}")
        print(f"sankey.png: {result.artifacts['png_path']}")
        if args.audit:
            print(f"audit_table.csv: {result.artifacts['audit_csv_path']}")
            print("Hint: Open audit_table.csv and filter by counted_interviews=1 to see which applications are counted as interviews.")
        if args.report and result.artifacts.get("rule_report_path"):
            print(f"rule_report.md: {result.artifacts['rule_report_path']}")
        if args.key_debug:
            print(f"applications_debug.csv: {result.artifacts.get('applications_debug_csv_path','')}")
            print(f"company_collisions.csv: {result.artifacts.get('company_collisions_csv_path','')}")
            print(f"role_extraction_debug.csv: {result.artifacts.get('role_extraction_debug_csv_path','')}")
        if args.domain_debug:
            print(f"domain_report.csv: {result.artifacts.get('domain_debug_csv_path','')}")
        if args.reconcile:
            print(f"reconcile_oa.csv: {result.artifacts.get('reconcile_csv_path','')}")
            print(f"oa_false_positives.csv: {result.artifacts.get('oa_false_positives_csv_path','')}")
        if args.first_scan_report:
            print(f"first_scan_report.csv: {result.artifacts.get('first_scan_report_csv_path','')}")
        if args.ai_classify:
            print(f"relevant_emails.csv: {result.artifacts.get('relevant_emails_csv_path','')}")
            print(f"ai_message_classification.csv: {result.artifacts.get('ai_message_classification_csv_path','')}")
            print(f"ai_application_table.csv: {result.artifacts.get('ai_application_table_csv_path','')}")
            print(f"ai_result_summary.json: {result.artifacts.get('ai_result_summary_json_path','')}")
            print(f"ai_sankey.png: {result.artifacts.get('ai_sankey_png_path','')}")
    if result.debug_samples:
        print("Debug sample")
        for row in result.debug_samples:
            print(
                f"{row['date']} | {row['from_domain']} | {row['subject']} | "
                f"{row['event_type']} | {row['stage']} | {row['confidence']} | "
                f"{row['application_key']} | ignored={row['ignored']}"
            )
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")


if __name__ == "__main__":
    main()
