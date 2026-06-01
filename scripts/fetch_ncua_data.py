"""
Fetch NCUA Letters to Credit Unions and save as markdown files.

Uses Tavily to discover URLs, Apify to extract content, and Firecrawl as fallback.
Output goes to sample_data/ncua_letters/ with a manifest.json index.

See docs/fetch_ncua_data_plan.md for full design rationale.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from apify_client import ApifyClient
from dotenv import load_dotenv
from firecrawl import FirecrawlApp
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from tavily import TavilyClient

OUTPUT_DIR = Path("sample_data/ncua_letters")
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
NCUA_DOMAIN = "ncua.gov"
APIFY_ACTOR_ID = "apify/website-content-crawler"
APIFY_ACTOR_TIMEOUT_SECS = 300
APIFY_MEMORY_MBYTES = 1024
MAX_URLS_PER_QUERY = 5

console = Console()
_DEDUPE_SEEN: set[str] = set()


@dataclass
class SearchResult:
    url: str
    title: str
    topic: str


@dataclass
class DownloadedLetter:
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
    required = ["TAVILY_API_KEY", "APIFY_TOKEN", "FIRECRAWL_API_KEY"]
    keys: dict[str, str] = {}
    missing = []
    for key in required:
        val = os.getenv(key)
        if not val:
            missing.append(key)
        else:
            keys[key] = val
    if missing:
        console.print(f"[red]Missing required env vars: {', '.join(missing)}")
        sys.exit(1)
    return keys


def get_search_queries() -> list[dict]:
    return [
        {"topic": "heloc_ltv", "query": "HELOC home equity line of credit loan-to-value ratio lending limits credit union"},
        {"topic": "heloc_collateral", "query": "HELOC real estate lending policy collateral requirements credit union"},
        {"topic": "bsa_compliance", "query": "BSA Bank Secrecy Act compliance program requirements credit union"},
        {"topic": "fincen_cdd", "query": "FinCEN beneficial ownership customer due diligence rule credit union"},
        {"topic": "capital_adequacy", "query": "capital adequacy net worth requirements well-capitalized thresholds credit union"},
        {"topic": "prompt_corrective_action", "query": "prompt corrective action PCA net worth ratio credit union regulation"},
        {"topic": "asset_threshold", "query": "asset threshold examination schedule large complex credit unions"},
        {"topic": "exam_schedule", "query": "examination program risk-based supervision asset size eligibility credit union"},
        {"topic": "sar_filing", "query": "suspicious activity report SAR filing requirements deadlines credit union"},
        {"topic": "pep_due_diligence", "query": "politically exposed person PEP wire transfer enhanced due diligence credit union"},
        {"topic": "cybersecurity", "query": "cybersecurity information security guidance letter credit union"},
        {"topic": "interest_rate_risk", "query": "interest rate risk liquidity management investment policy credit union"},
        {"topic": "irr_nev_supervision", "query": "net economic value NEV threshold supervisory action board notification interest rate risk credit union NCUA"},
        {"topic": "irr_action_plan", "query": "interest rate risk action plan policy program requirements part 741 appendix credit union NCUA"},
        {"topic": "irr_examination", "query": "interest rate risk examination procedures supervisory expectations measurement program credit union NCUA examiner guide"},
        {"topic": "member_business_lending", "query": "member business lending MBL commercial loan limits credit union"},
    ]


# Direct-target URLs that Tavily won't discover (e.g. eCFR, examiner guide deep pages).
# These bypass the ncua.gov domain filter but are still authoritative federal sources.
DIRECT_URLS: list[dict] = [
    {
        "url": "https://ecfr.gov/current/title-12/chapter-VII/subchapter-A/part-741/appendix-Appendix%20A",
        "topic": "irr_action_plan",
        "title": "Part 741 Appendix A — Guidance for an Interest Rate Risk Policy and an Effective Program",
    },
    {
        "url": "https://publishedguides.ncua.gov/examiner/Content/ExaminersGuide/SensitivityMarketRisk/SMRRisks/IRR/IRRProgram.htm",
        "topic": "irr_examination",
        "title": "NCUA Examiner Guide — Interest Rate Risk Program Requirements",
    },
    {
        "url": "https://publishedguides.ncua.gov/examiner/Content/ExaminersGuide/SensitivityMarketRisk/SMRRisks/IRR/Measurement.htm",
        "topic": "irr_nev_supervision",
        "title": "NCUA Examiner Guide — Interest Rate Risk Measurement and NEV",
    },
    # PCA mandatory supervisory actions — needed so Q8 (dual-framework IRR+PCA) can answer
    # "what specific obligations apply to Undercapitalized classification"
    {
        "url": "https://ecfr.gov/current/title-12/chapter-VII/subchapter-A/part-702/section-702.107",
        "topic": "prompt_corrective_action",
        "title": "12 CFR 702.107 — Mandatory supervisory actions for undercapitalized credit unions",
    },
    {
        "url": "https://ecfr.gov/current/title-12/chapter-VII/subchapter-A/part-702/section-702.108",
        "topic": "prompt_corrective_action",
        "title": "12 CFR 702.108 — Mandatory supervisory actions for significantly undercapitalized credit unions",
    },
    {
        "url": "https://www.ncua.gov/regulation-supervision/regulatory-compliance-resources/net-worth-ratio-plan-and-prompt-corrective-action-resources",
        "topic": "prompt_corrective_action",
        "title": "NCUA PCA Resources — Net Worth Ratio Plan and Prompt Corrective Action",
    },
]


def is_valid_ncua_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if not parsed.netloc.endswith(NCUA_DOMAIN):
        return False
    path_segments = [s for s in parsed.path.strip("/").split("/") if s]
    if len(path_segments) < 4:
        return False
    if url in _DEDUPE_SEEN:
        return False
    _DEDUPE_SEEN.add(url)
    return True


def search_tavily(query: str, api_key: str) -> list[SearchResult]:
    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=MAX_URLS_PER_QUERY,
            include_domains=[NCUA_DOMAIN],
        )
        results = []
        for r in response.get("results", []):
            url = r.get("url", "")
            title = r.get("title", url)
            if is_valid_ncua_url(url):
                results.append(SearchResult(url=url, title=title, topic=""))
        return results
    except Exception as exc:
        console.print(f"[yellow]WARN Tavily search failed for '{query[:50]}...': {exc}")
        return []


def collect_all_urls(api_key: str) -> list[SearchResult]:
    queries = get_search_queries()
    all_results: list[SearchResult] = []

    # Seed with direct-target URLs (not discoverable via Tavily)
    for entry in DIRECT_URLS:
        url = entry["url"]
        if url not in _DEDUPE_SEEN:
            _DEDUPE_SEEN.add(url)
            all_results.append(SearchResult(url=url, title=entry["title"], topic=entry["topic"]))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Searching Tavily...", total=len(queries))
        for q in queries:
            hits = search_tavily(q["query"], api_key)
            for hit in hits:
                hit.topic = q["topic"]
                all_results.append(hit)
            progress.advance(task)
            time.sleep(1)
    console.print(f"[green]Found {len(all_results)} unique URLs across {len(queries)} Tavily queries + {len(DIRECT_URLS)} direct targets")
    return all_results


def make_slug(url: str) -> str:
    parsed = urlparse(url)
    last_segment = parsed.path.rstrip("/").split("/")[-1]
    last_segment = re.sub(r"\.pdf$", "", last_segment, flags=re.IGNORECASE)
    last_segment = re.sub(r"[^a-z0-9-]", "-", last_segment.lower())
    last_segment = re.sub(r"-+", "-", last_segment).strip("-")
    last_segment = last_segment[:80]
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:6]
    return f"{last_segment}-{url_hash}.md"


def fetch_with_apify(urls: list[str], apify_token: str) -> dict[str, dict]:
    if not urls:
        return {}
    console.print(f"[blue]Running Apify actor on {len(urls)} URLs...")
    client = ApifyClient(token=apify_token)
    run_input = {
        "startUrls": [{"url": u} for u in urls],
        "crawlerType": "playwright:firefox",
        "maxCrawlPages": len(urls),
        "maxCrawlDepth": 0,
        "outputFormats": ["markdown"],
        "saveMarkdown": True,
        "saveHtml": False,
        "removeCookieWarnings": True,
        "removeElementsCssSelector": "nav, header, footer, .breadcrumb, .sidebar, .menu",
        "htmlTransformer": "readability",
        "maxSessionRotations": 3,
        "requestHandlerTimeoutSecs": 60,
    }
    try:
        run = client.actor(APIFY_ACTOR_ID).call(
            run_input=run_input,
            run_timeout=timedelta(seconds=APIFY_ACTOR_TIMEOUT_SECS),
            memory_mbytes=APIFY_MEMORY_MBYTES,
        )
        if not run:
            console.print("[red]Apify actor returned no run object")
            return {}
        run_id = run.id
        items = client.dataset(run.default_dataset_id).list_items().items
        results: dict[str, dict] = {}
        for item in items:
            item_url = item.get("url") or item.get("loadedUrl", "")
            markdown = item.get("markdown") or item.get("text", "")
            title = item.get("title", item_url)
            if item_url and markdown:
                results[item_url] = {"markdown": markdown, "title": title, "run_id": run_id}
        console.print(f"[green]Apify returned content for {len(results)}/{len(urls)} URLs (run: {run_id})")
        return results
    except Exception as exc:
        console.print(f"[red]Apify actor run failed: {exc}")
        return {}


def fetch_with_firecrawl_fallback(url: str, api_key: str) -> str | None:
    try:
        app = FirecrawlApp(api_key=api_key)
        result = app.scrape_url(url, formats=["markdown"])
        markdown = result.markdown if hasattr(result, "markdown") else ""
        return markdown if markdown and len(markdown) > 100 else None
    except Exception as exc:
        console.print(f"[yellow]WARN Firecrawl fallback failed for {url}: {exc}")
        return None


def save_letter(result: SearchResult, markdown: str, title: str, output_dir: Path, run_id: str | None) -> DownloadedLetter:
    slug = make_slug(result.url)
    now = datetime.now(timezone.utc).isoformat()
    front_matter = (
        f"---\n"
        f"url: {result.url}\n"
        f"topic: {result.topic}\n"
        f"title: {title}\n"
        f"date_fetched: {now}\n"
        f"source: ncua.gov\n"
        f"---\n\n"
    )
    content = front_matter + markdown
    (output_dir / slug).write_text(content, encoding="utf-8")
    return DownloadedLetter(
        url=result.url,
        topic=result.topic,
        filename=slug,
        title=title,
        date_fetched=now,
        char_count=len(content),
        apify_run_id=run_id,
        error=None,
    )


def load_existing_manifest(manifest_path: Path) -> list[dict]:
    if not manifest_path.exists():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return data.get("letters", [])
    except Exception:
        return []


def write_manifest(letters: list[DownloadedLetter], existing: list[dict], manifest_path: Path) -> None:
    new_entries = [asdict(l) for l in letters]
    all_entries = existing + new_entries
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(all_entries),
        "letters": all_entries,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def print_summary(letters: list[DownloadedLetter]) -> None:
    table = Table(title="Download Summary", show_lines=True)
    table.add_column("Topic", style="cyan")
    table.add_column("Filename", style="green")
    table.add_column("Chars", justify="right")
    table.add_column("Status", justify="center")
    for l in letters:
        status = "[green]OK" if l.error is None else f"[red]{l.error}"
        table.add_row(l.topic, l.filename, str(l.char_count) if l.error is None else "-", status)
    console.print(table)
    ok = sum(1 for l in letters if l.error is None)
    console.print(f"\n[bold]Result: {ok}/{len(letters)} letters downloaded successfully")


def main() -> int:
    console.print("[bold blue]NCUA Letter Fetcher")
    keys = load_env()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    existing = load_existing_manifest(MANIFEST_PATH)
    skip_urls = {e["url"] for e in existing}
    if skip_urls:
        console.print(f"[dim]Skipping {len(skip_urls)} already-downloaded URLs from manifest")
        _DEDUPE_SEEN.update(skip_urls)

    all_results = collect_all_urls(keys["TAVILY_API_KEY"])
    new_results = [r for r in all_results if r.url not in skip_urls]

    if not new_results:
        console.print("[yellow]No new URLs to fetch. All results already in manifest.")
        return 0

    console.print(f"[blue]Fetching {len(new_results)} new letters...")
    apify_data = fetch_with_apify([r.url for r in new_results], keys["APIFY_TOKEN"])

    downloaded: list[DownloadedLetter] = []
    for result in new_results:
        apify_hit = apify_data.get(result.url)
        if apify_hit and apify_hit.get("markdown"):
            letter = save_letter(
                result,
                apify_hit["markdown"],
                apify_hit.get("title") or result.title,
                OUTPUT_DIR,
                apify_hit.get("run_id"),
            )
            downloaded.append(letter)
        else:
            console.print(f"[yellow]Trying Firecrawl fallback for {result.url}")
            markdown = fetch_with_firecrawl_fallback(result.url, keys["FIRECRAWL_API_KEY"])
            if markdown:
                letter = save_letter(result, markdown, result.title, OUTPUT_DIR, None)
                downloaded.append(letter)
            else:
                downloaded.append(DownloadedLetter(
                    url=result.url,
                    topic=result.topic,
                    filename="",
                    title=result.title,
                    date_fetched=datetime.now(timezone.utc).isoformat(),
                    char_count=0,
                    apify_run_id=None,
                    error="fetch_failed",
                ))

    write_manifest(downloaded, existing, MANIFEST_PATH)
    print_summary(downloaded)

    failed = sum(1 for l in downloaded if l.error is not None)
    return 1 if failed == len(downloaded) else 0


if __name__ == "__main__":
    sys.exit(main())
