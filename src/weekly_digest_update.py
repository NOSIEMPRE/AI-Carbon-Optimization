"""
weekly_digest_update.py

Fetches new arXiv preprints relevant to the thesis topic (AI data center
carbon-aware scheduling) and appends a draft Issue to Essays/weekly_digest.md.

Usage:
    python src/weekly_digest_update.py              # last 7 days
    python src/weekly_digest_update.py --days 14    # last 14 days
    python src/weekly_digest_update.py --dry-run    # print without writing

Requires: requests (pip install requests)
"""

import argparse
import re
import sys
import textwrap
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────

DIGEST_PATH = Path(__file__).parent.parent / "Essays" / "weekly_digest.md"

# arXiv categories to search
CATEGORIES = ["cs.DC", "eess.SY", "cs.NI", "cs.LG"]

# Required: at least one of these must appear in title or abstract
REQUIRED_TERMS = [
    "carbon",
    "CO2",
    "CO₂",
    "carbon-aware",
    "carbon intensity",
    "carbon footprint",
    "greenhouse",
    "decarbonization",
]

# At least one of these must also appear (narrows to relevant subfield)
RELEVANCE_TERMS = [
    "data center",
    "datacenter",
    "workload",
    "scheduling",
    "cloud",
    "AI",
    "machine learning",
    "LLM",
    "neural network",
    "training",
    "inference",
    "grid",
    "renewable",
    "electricity",
    "energy",
    "carbon-free",
]

# Skip papers whose abstracts are dominated by these topics (off-topic)
EXCLUDE_IF_ONLY = [
    "autonomous vehicle",
    "electric vehicle",
    "battery storage",
    "transportation",
    "supply chain",
]

# Already-known arXiv IDs (from references.bib) — don't re-surface these
KNOWN_ARXIV_IDS = {
    "2505.18357",  # hanafy2025 CarbonFlex
    "2405.00036",  # riepin2024spatiotemporal
    "2512.08725",  # attenni2024shifting
    "2408.07831",  # lechowicz2025stclip
    "2306.06502",  # wiesner2024limitations
    "2507.00909",  # colangelo2025
    "1906.02629",  # strubell2019energy
    "2505.01959",  # yan2025ensembleci
    "2407.02390",  # li2024uncertainty
    "2404.15211",  # bostandoost2024lacs
    "2410.21510",  # hall2024probabilistic
    "2405.18070",  # breukelman2024hierarchical
    "2403.07876",  # riepin2024cfe247costs
    "2201.10036",  # acun2023carbonexplorer
    "2403.14792",  # souza2023casper
    "2307.05494",  # li2024equitable
    "2311.03615",  # bian2024cafe
    "2502.09717",  # lechowicz2025pcaps
    "2203.00826",  # lindberg2022geographic
    "2304.03271",  # li2023thirsty
    "2512.18819",  # cote2024locational
    "2204.05149",  # patterson2022carbon
    "2210.04951",  # souza2023ecovisor
    "2309.14477",  # thiede2023carboncontainers
    "2306.09774",  # wiesner2024vessim
    "2309.14393",  # faiz2024llmcarbon
    "2501.01990",  # nguyen2024sustainabllm
    "2412.20322",  # shi2024greenllm
    "2007.07610",  # lannelongue2021greenalgorithms
    "2505.09598",  # hungryllm2025
    "2510.01521",  # carbonx2025
    "2505.23554",  # li2025llm (Moore et al.)
}

# ── arXiv API ─────────────────────────────────────────────────────────────────

ARXIV_API = "https://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def fetch_arxiv(category: str, days: int, max_results: int = 100) -> list[dict]:
    """Return list of paper dicts from arXiv for the given category and window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    params = {
        "search_query": f"cat:{category}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    }

    try:
        resp = requests.get(ARXIV_API, params=params, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [warn] arXiv fetch failed for {category}: {e}", file=sys.stderr)
        return []

    root = ET.fromstring(resp.content)
    papers = []

    for entry in root.findall("atom:entry", NS):
        published_str = entry.findtext("atom:published", default="", namespaces=NS)
        try:
            published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        if published < cutoff:
            break  # results are sorted newest-first; stop early

        arxiv_id_raw = entry.findtext("atom:id", default="", namespaces=NS)
        # Extract just the ID e.g. "2506.12345" from the URL
        arxiv_id = re.search(r"abs/([\d.]+)", arxiv_id_raw)
        arxiv_id = arxiv_id.group(1) if arxiv_id else arxiv_id_raw

        papers.append(
            {
                "id": arxiv_id,
                "title": (entry.findtext("atom:title", default="", namespaces=NS) or "").strip(),
                "abstract": (entry.findtext("atom:summary", default="", namespaces=NS) or "").strip(),
                "authors": [
                    a.findtext("atom:name", default="", namespaces=NS)
                    for a in entry.findall("atom:author", NS)
                ],
                "published": published.date().isoformat(),
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "categories": [
                    t.get("term", "")
                    for t in entry.findall("atom:category", NS)
                ],
            }
        )

    return papers


# ── Filtering ─────────────────────────────────────────────────────────────────

def _text(paper: dict) -> str:
    return (paper["title"] + " " + paper["abstract"]).lower()


def is_relevant(paper: dict) -> bool:
    if paper["id"] in KNOWN_ARXIV_IDS:
        return False

    text = _text(paper)

    has_carbon = any(t.lower() in text for t in REQUIRED_TERMS)
    has_relevance = any(t.lower() in text for t in RELEVANCE_TERMS)

    if not (has_carbon and has_relevance):
        return False

    # Exclude if abstract is dominated by off-topic subjects
    off_topic_hits = sum(1 for t in EXCLUDE_IF_ONLY if t.lower() in text)
    if off_topic_hits >= 2:
        return False

    return True


# ── Formatting ────────────────────────────────────────────────────────────────

def format_author(authors: list[str]) -> str:
    if not authors:
        return "Unknown"
    if len(authors) == 1:
        return authors[0]
    if len(authors) <= 3:
        return ", ".join(authors)
    return f"{authors[0]} et al."


def truncate(text: str, max_chars: int = 280) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + " …"


def format_paper(paper: dict) -> str:
    author = format_author(paper["authors"])
    abstract_snippet = truncate(paper["abstract"])
    return (
        f"**{author} ({paper['published']})**  \n"
        f"*{paper['title']}*  \n"
        f"arXiv:{paper['id']} — {paper['url']}  \n"
        f"{abstract_snippet}  \n"
        f"*Thesis relevance: [fill in]*"
    )


# ── Digest issue builder ───────────────────────────────────────────────────────

def next_issue_number(digest_text: str) -> int:
    """Extract the highest existing Issue N and return N+1."""
    matches = re.findall(r"## Issue (\d+)", digest_text)
    if not matches:
        return 2
    return max(int(m) for m in matches) + 1


def build_issue(papers: list[dict], issue_n: int, days: int) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    window_start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    header = textwrap.dedent(f"""\
        ## Issue {issue_n} — Week of {today}
        *Auto-generated draft. Review, trim, and fill in "Thesis relevance" before finalizing.*
        *arXiv window: {window_start} → {today} | Categories searched: {", ".join(CATEGORIES)}*

        ### New Papers This Week ({len(papers)} found)

    """)

    if not papers:
        body = "_No new relevant preprints found in this window._\n"
    else:
        body = "\n\n---\n\n".join(format_paper(p) for p in papers) + "\n"

    footer = textwrap.dedent("""\

        ### Field Developments
        - [Fill in: industry news, policy, grid data updates]

        ### Thesis Implications
        - [Fill in: how new findings affect your model or argument]

        ### Reading Queue Update
        Added to reading_notes.md:
        - [ ] *[list papers you decide to keep]*

        ---

    """)

    return header + body + footer


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Update AI+Carbon weekly digest")
    parser.add_argument("--days", type=int, default=7, help="Look-back window in days (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="Print draft without writing to file")
    args = parser.parse_args()

    print(f"Fetching arXiv papers from last {args.days} days …")
    all_papers: list[dict] = []
    seen_ids: set[str] = set()

    for cat in CATEGORIES:
        print(f"  → {cat} … ", end="", flush=True)
        fetched = fetch_arxiv(cat, args.days)
        before = len(all_papers)
        for p in fetched:
            if p["id"] not in seen_ids and is_relevant(p):
                all_papers.append(p)
                seen_ids.add(p["id"])
        print(f"{len(all_papers) - before} new relevant papers")

    # Sort by published date descending
    all_papers.sort(key=lambda p: p["published"], reverse=True)

    print(f"\nTotal relevant papers: {len(all_papers)}")

    digest_text = DIGEST_PATH.read_text(encoding="utf-8")
    issue_n = next_issue_number(digest_text)
    draft = build_issue(all_papers, issue_n, args.days)

    if args.dry_run:
        print("\n" + "─" * 70)
        print(draft)
        print("─" * 70)
        print("[dry-run] Not written to file.")
        return

    # Insert after the "## How to Update" block (before the first existing Issue)
    insert_marker = "---\n\n## Issue"
    if insert_marker in digest_text:
        digest_text = digest_text.replace(insert_marker, f"---\n\n{draft}## Issue", 1)
    else:
        # Fallback: append at end before "## Archived Issues"
        archived_marker = "## Archived Issues"
        if archived_marker in digest_text:
            digest_text = digest_text.replace(archived_marker, f"{draft}{archived_marker}")
        else:
            digest_text += "\n" + draft

    DIGEST_PATH.write_text(digest_text, encoding="utf-8")
    print(f"Draft Issue {issue_n} written to {DIGEST_PATH}")
    print("Next steps: open the file, fill in 'Thesis relevance' fields, and remove off-topic entries.")


if __name__ == "__main__":
    main()
