"""
Targeted fetch of specific NCUA URLs not yet in the corpus.
Uses Apify website-content-crawler; falls back to Firecrawl per URL.
Saves markdown to sample_data/ncua_letters/ and updates manifest.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from datetime import timedelta

from apify_client import ApifyClient
from dotenv import load_dotenv
from firecrawl import V1FirecrawlApp
from rich.console import Console
from rich.table import Table

OUTPUT_DIR = Path("sample_data/ncua_letters")
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
APIFY_ACTOR_ID = "apify/website-content-crawler"

console = Console()

# ---------------------------------------------------------------------------
# Targeted URLs — documents NOT yet in corpus that unlock new adversarial Qs
# ---------------------------------------------------------------------------
TARGETS = [
    {
        "url": "https://ncua.gov/newsroom/ncua-report/2017/have-questions-about-implementing-new-mbl-rule-these-faqs-can-help",
        "topic": "mbl_policy_faq",
        "title": "MBL Rule Implementation FAQs 2017",
    },
    {
        "url": "https://publishedguides.ncua.gov/examiner/content/examinersguide/loans/commercial&mbl/CommLoanPolicy/CommLoanPolicy.htm",
        "topic": "mbl_commercial_loan_policy",
        "title": "Commercial Loan Policy — Examiner's Guide",
    },
    {
        "url": "https://publishedguides.ncua.gov/examiner/Content/ExaminersGuide/SensitivityMarketRisk/EvaluatingIRR/Methods/NEV.htm",
        "topic": "irr_nev_method",
        "title": "Net Economic Value — IRR Examiner's Guide",
    },
    {
        "url": "https://publishedguides.ncua.gov/examiner/Content/ExaminersGuide/SensitivityMarketRisk/EvaluatingIRR/Methods/Methods.htm",
        "topic": "irr_measurement_methods",
        "title": "IRR Measurement Methods — Examiner's Guide",
    },
    {
        "url": "https://ncua.gov/regulation-supervision/letters-credit-unions-other-guidance/updates-interest-rate-risk-supervisory-framework-0",
        "topic": "irr_supervisory_framework",
        "title": "Updates to Interest Rate Risk Supervisory Framework",
    },
    {
        "url": "https://ncua.gov/newsroom/press-release/2021/ncua-federal-banking-agencies-fincen-issue-faqs-sar-and-other-aml-requirements/answers-faqs-regarding-suspicious-activity-reporting-and-other-anti-money",
        "topic": "sar_aml_faq_2021",
        "title": "Interagency FAQ — SAR and AML Requirements 2021",
    },
    {
        "url": "https://ncua.gov/regulation-supervision/manuals-guides/federal-consumer-financial-protection-guide/compliance-management/lending-regulations/home-mortgage-disclosure-act-regulation-c",
        "topic": "hmda_regulation_c",
        "title": "HMDA Regulation C — NCUA Consumer Protection Guide",
    },
    {
        "url": "https://ncua.gov/regulation-supervision/regulatory-compliance-resources/consumer-compliance-regulatory-resources/fair-lending-compliance-resources/faq",
        "topic": "fair_lending_faq",
        "title": "Fair Lending Compliance FAQs | NCUA",
    },
    {
        "url": "https://ncua.gov/regulation-supervision/regulatory-compliance-resources/cybersecurity-resources/ncuas-information-security-examination-and-cybersecurity-assessment",
        "topic": "cybersecurity_exam",
        "title": "NCUA Information Security Examination and Cybersecurity Assessment",
    },
    {
        "url": "https://ncua.gov/regulation-supervision/letters-credit-unions-other-guidance/board-director-engagement-cybersecurity-oversight",
        "topic": "cybersecurity_board",
        "title": "Board of Director Engagement in Cybersecurity Oversight",
    },
    {
        "url": "https://ncua.gov/regulation-supervision/letters-credit-unions-other-guidance/ncuas-2026-supervisory-priorities",
        "topic": "supervisory_priorities_2026",
        "title": "NCUA 2026 Supervisory Priorities",
    },
    {
        "url": "https://publishedguides.ncua.gov/examiner/content/examinersguide/Lending/MBL/Intro.htm",
        "topic": "mbl_examiner_guide_intro",
        "title": "Commercial and Member Business Loans — Examiner's Guide (Updated)",
    },
    {
        "url": "https://publishedguides.ncua.gov/examiner/content/examinersguide/loans/commercial&mbl/CommLoanAdmin/Administration.htm",
        "topic": "mbl_loan_admin",
        "title": "Commercial Loan Administration — Examiner's Guide",
    },
    {
        "url": "https://publishedguides.ncua.gov/examiner/Content/ExaminersGuide/RegulatoryCompliance/BSA/ExamProcedures/ReportingRecordkeeping.htm",
        "topic": "bsa_reporting_recordkeeping",
        "title": "BSA Reporting and Recordkeeping — Examiner's Guide",
    },
    {
        "url": "https://publishedguides.ncua.gov/examiner/Content/ExaminersGuide/RegulatoryCompliance/BSA/ExamProcedures/BSAPoliciesProcedures.htm",
        "topic": "bsa_policies_procedures",
        "title": "BSA Policies and Procedures — Examiner's Guide",
    },
]


@dataclass
class FetchedDoc:
    url: str
    topic: str
    filename: str
    title: str
    date_fetched: str
    char_count: int
    apify_run_id: str | None
    error: str | None


def load_env() -> dict[str, str]:
    load_dotenv()
    keys = {}
    for k in ["APIFY_TOKEN", "FIRECRAWL_API_KEY"]:
        v = os.getenv(k)
        if v:
            keys[k] = v
    return keys


def make_slug(url: str) -> str:
    parsed = urlparse(url)
    last = parsed.path.rstrip("/").split("/")[-1] or "index"
    last = re.sub(r"[^a-zA-Z0-9_-]", "-", last)[:40].lower()
    short_hash = hashlib.sha256(url.encode()).hexdigest()[:6]
    return f"{last}-{short_hash}.md"


def load_existing_urls() -> set[str]:
    if not MANIFEST_PATH.exists():
        return set()
    try:
        data = json.loads(MANIFEST_PATH.read_text())
        return {item["url"] for item in data.get("letters", [])}
    except Exception:
        return set()


def load_existing_manifest() -> list[dict]:
    if not MANIFEST_PATH.exists():
        return []
    try:
        return json.loads(MANIFEST_PATH.read_text()).get("letters", [])
    except Exception:
        return []


def save_markdown(doc: FetchedDoc, content: str) -> None:
    front = (
        f"---\n"
        f"url: {doc.url}\n"
        f"topic: {doc.topic}\n"
        f"title: {doc.title}\n"
        f"date_fetched: {doc.date_fetched}\n"
        f"source: ncua.gov\n"
        f"---\n\n"
    )
    (OUTPUT_DIR / doc.filename).write_text(front + content, encoding="utf-8")


def fetch_with_apify(urls: list[dict], token: str) -> dict[str, dict]:
    """Batch-fetch all URLs in a single Apify run. Returns url → {markdown, title, run_id}."""
    client = ApifyClient(token)
    run_input = {
        "startUrls": [{"url": t["url"]} for t in urls],
        "crawlerType": "playwright:firefox",
        "maxCrawlPages": len(urls),
        "maxCrawlDepth": 0,
        "outputFormats": ["markdown"],
        "saveMarkdown": True,
        "saveHtml": False,
        "removeCookieWarnings": True,
        "removeElementsCssSelector": "nav, header, footer, .breadcrumb, .sidebar, .menu, .cookie-banner",
        "htmlTransformer": "readableText",
    }
    console.print(f"[cyan]Running Apify on {len(urls)} URL(s)...")
    run = client.actor(APIFY_ACTOR_ID).call(
        run_input=run_input,
        run_timeout=timedelta(seconds=300),
        memory_mbytes=8192,
    )
    # apify-client v3.x returns a Run object; earlier versions returned a dict
    if hasattr(run, "id"):
        run_id = run.id
        dataset_id = run.default_dataset_id
    else:
        run_id = run["id"]
        dataset_id = run["defaultDatasetId"]
    results: dict[str, dict] = {}
    items = client.dataset(dataset_id).list_items().items
    for item in items:
        url = item.get("url", "")
        md = item.get("markdown") or item.get("text") or ""
        title = item.get("metadata", {}).get("title", "") or item.get("title", "")
        results[url] = {"markdown": md, "title": title, "run_id": run_id}
    return results


def fetch_with_firecrawl(url: str, api_key: str) -> str | None:
    try:
        app = V1FirecrawlApp(api_key=api_key)
        result = app.scrape_url(url, formats=["markdown"])
        md = getattr(result, "markdown", None) or getattr(result, "content", None) or ""
        return md
    except Exception as e:
        console.print(f"[yellow]Firecrawl failed for {url}: {e}")
        return None


def write_manifest(existing: list[dict], new_docs: list[FetchedDoc]) -> None:
    all_docs = existing + [asdict(d) for d in new_docs]
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(all_docs),
        "letters": all_docs,
    }
    MANIFEST_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> int:
    keys = load_env()
    apify_token = keys.get("APIFY_TOKEN", "")
    firecrawl_key = keys.get("FIRECRAWL_API_KEY", "")

    existing_urls = load_existing_urls()
    existing_manifest = load_existing_manifest()

    # Filter out already-fetched URLs
    to_fetch = [t for t in TARGETS if t["url"] not in existing_urls]
    if not to_fetch:
        console.print("[green]All target URLs already in corpus — nothing to fetch.")
        return 0

    console.print(f"[bold]Fetching {len(to_fetch)} new URLs[/bold] ({len(TARGETS) - len(to_fetch)} already in corpus)")
    for t in to_fetch:
        console.print(f"  • {t['url'][:80]}")

    new_docs: list[FetchedDoc] = []

    # --- Apify batch fetch ---
    apify_results: dict[str, dict] = {}
    if apify_token:
        try:
            apify_results = fetch_with_apify(to_fetch, apify_token)
            console.print(f"[green]Apify returned {len(apify_results)} result(s)")
        except Exception as e:
            console.print(f"[yellow]Apify batch failed: {e} — will fall back to Firecrawl per URL")

    # --- Process each target ---
    now = datetime.now(timezone.utc).isoformat()
    for target in to_fetch:
        url = target["url"]
        slug = make_slug(url)
        apify_data = apify_results.get(url, {})
        markdown = apify_data.get("markdown", "")
        run_id = apify_data.get("run_id")
        title = apify_data.get("title") or target["title"]

        # Firecrawl fallback if Apify got nothing
        if not markdown or len(markdown) < 200:
            console.print(f"[yellow]  Apify empty for {url[:60]}... trying Firecrawl")
            if firecrawl_key:
                markdown = fetch_with_firecrawl(url, firecrawl_key) or ""
            run_id = None

        doc = FetchedDoc(
            url=url,
            topic=target["topic"],
            filename=slug,
            title=title,
            date_fetched=now,
            char_count=len(markdown),
            apify_run_id=run_id,
            error=None if len(markdown) >= 200 else "fetch_failed",
        )

        if len(markdown) >= 200:
            save_markdown(doc, markdown)
            console.print(f"[green]  ✓ {slug} ({len(markdown):,} chars)")
        else:
            console.print(f"[red]  ✗ {slug} — fetch failed (got {len(markdown)} chars)")
            # Save empty stub so manifest records the attempt
            save_markdown(doc, f"[fetch failed — no content retrieved]\n\nURL: {url}\n")

        new_docs.append(doc)
        time.sleep(0.5)  # gentle rate limit

    # --- Update manifest ---
    write_manifest(existing_manifest, new_docs)
    console.print(f"\n[bold green]Done.[/bold green] Fetched {len(new_docs)} document(s). Manifest updated.")

    # --- Summary table ---
    table = Table(title="Fetch Results", show_lines=True)
    table.add_column("File", style="cyan")
    table.add_column("Chars", justify="right")
    table.add_column("Status")
    for doc in new_docs:
        status = "[green]OK" if not doc.error else "[red]FAILED"
        table.add_row(doc.filename, f"{doc.char_count:,}", status)
    console.print(table)

    return 0


if __name__ == "__main__":
    sys.exit(main())
