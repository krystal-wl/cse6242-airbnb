#!/usr/bin/env python3
"""Download Inside Airbnb datasets for one or more cities, including archived snapshots.

Data source: https://insideairbnb.com/get-the-data/

Inside Airbnb scrapes each city roughly every quarter and keeps the last ~12
months of snapshots online (a few cities have longer, monthly histories). The
date attached to a snapshot is the day the scrape ran. Files are saved as::

    data/<city-slug>/<YYYY-MM-DD>/<file>

so several snapshots of one city can live side by side.

Examples
--------
List every city with its number of snapshots and date range::

    python scripts/download_data.py --list

List every snapshot date of specific cities::

    python scripts/download_data.py --list boston new-york-city

Download the latest snapshot (all seven files) of several cities::

    python scripts/download_data.py new-york-city boston chicago

Download every available snapshot of a city (the archive)::

    python scripts/download_data.py boston --all-snapshots

Only snapshots on/after a date, only some files, and gunzip them::

    python scripts/download_data.py vaud --since 2026-01-01 --files listings calendar --extract

One specific archived snapshot::

    python scripts/download_data.py boston@2026-03-28

Files per snapshot (the names accepted by ``--files``):

    listings                data/listings.csv.gz             detailed listings
    calendar                data/calendar.csv.gz             daily availability/price, 365 days ahead
    reviews                 data/reviews.csv.gz              detailed reviews, full history (largest file)
    listings-summary        visualisations/listings.csv      summary listings (small)
    reviews-summary         visualisations/reviews.csv       listing_id + review date only
    neighbourhoods          visualisations/neighbourhoods.csv
    neighbourhoods-geojson  visualisations/neighbourhoods.geojson

Local file names mirror the remote ones except the two summary CSVs, which are
saved as ``listings_summary.csv`` and ``reviews_summary.csv`` so that
``--extract`` can gunzip ``listings.csv.gz`` -> ``listings.csv`` without a clash.
"""

from __future__ import annotations

import argparse
import difflib
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover - friendly message for teammates
    sys.exit(
        f"Missing dependency ({exc.name}). Install the project requirements first:\n"
        "    pip install -r requirements.txt"
    )

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / "data"

SITE = "https://insideairbnb.com"
DATA_PAGE_URL = f"{SITE}/get-the-data/"
# The page is a Gatsby site: page-data.json names the static-query JSON files it
# loads, one of which is the full dataset catalog (all cities, all snapshots).
PAGE_DATA_URL = f"{SITE}/page-data/get-the-data/page-data.json"
STATIC_QUERY_URL = f"{SITE}/page-data/sq/d/{{hash}}.json"
DATA_HOST = "https://data.insideairbnb.com"

CATALOG_CACHE_NAME = ".catalog.json"
CATALOG_VERSION = 2
CATALOG_MAX_AGE_S = 24 * 3600

USER_AGENT = "cse6242-airbnb-downloader/1.0 (+https://github.com/krystal-wl/cse6242-airbnb)"

# key -> (remote sub-directory, remote file name, local file name)
FILES: dict[str, tuple[str, str, str]] = {
    "listings": ("data", "listings.csv.gz", "listings.csv.gz"),
    "calendar": ("data", "calendar.csv.gz", "calendar.csv.gz"),
    "reviews": ("data", "reviews.csv.gz", "reviews.csv.gz"),
    "listings-summary": ("visualisations", "listings.csv", "listings_summary.csv"),
    "reviews-summary": ("visualisations", "reviews.csv", "reviews_summary.csv"),
    "neighbourhoods": ("visualisations", "neighbourhoods.csv", "neighbourhoods.csv"),
    "neighbourhoods-geojson": ("visualisations", "neighbourhoods.geojson", "neighbourhoods.geojson"),
}

# Used only by the HTML fallback. Matches both city-level paths
# (united-states/ny/new-york-city) and the shorter country-level ones (ireland).
LINK_RE = re.compile(
    r"https://data\.insideairbnb\.com/"
    r"(?P<path>[^\s\"'?#]+?)/"
    r"(?P<date>\d{4}-\d{2}-\d{2})/"
    r"(?P<kind>data|visualisations)/"
    r"(?P<file>[^\s\"'?#]+)"
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CHUNK_SIZE = 1 << 20  # 1 MiB


# --------------------------------------------------------------------------- #
# Catalog: which cities and snapshots does the website currently offer?
# --------------------------------------------------------------------------- #


def normalize(text: str) -> str:
    """'São Paulo' -> 'sao-paulo', 'New York City' -> 'new-york-city'."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return text.strip("-")


@dataclass(frozen=True)
class City:
    name: str  # e.g. "New York City, New York, United States"
    path: str  # e.g. "united-states/ny/new-york-city" (exact remote spelling, may contain accents)
    slug: str  # e.g. "new-york-city" - ASCII-only, used for matching and as the local folder name
    dates: tuple[str, ...]  # snapshot dates available for download, newest first

    @property
    def latest(self) -> str:
        return self.dates[0]

    def url(self, key: str, date: str) -> str:
        kind, remote_name, _ = FILES[key]
        return f"{DATA_HOST}/{self.path}/{date}/{kind}/{remote_name}"


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def parse_catalog_json(datasets: list[dict]) -> list[City]:
    """Build City entries from the site's dataset records (one record per snapshot)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in datasets:
        groups[record["link"]].append(record)

    cities = []
    for link, records in groups.items():
        first = records[0]
        parts = [first.get("city"), first.get("region"), first.get("country")]
        name = ", ".join(dict.fromkeys(p for p in parts if p))  # drop empties and repeats
        path = first["dataRoot"].removeprefix(DATA_HOST + "/").strip("/")
        dates = tuple(sorted({r["publishDate"] for r in records}, reverse=True))
        cities.append(City(name=name, path=path, slug=normalize(link), dates=dates))
    return sorted(cities, key=lambda c: c.slug)


def parse_catalog_html(html: str) -> list[City]:
    """Fallback: scrape the page tables. Only the latest snapshot per city is visible there."""
    soup = BeautifulSoup(html, "html.parser")
    cities: dict[str, City] = {}
    for table in soup.find_all("table", class_="data"):
        link = table.find("a", href=LINK_RE)
        match = LINK_RE.search(link["href"]) if link else None
        if match is None:
            continue
        heading = table.find_previous("h3")
        path = match.group("path")
        slug = normalize(path.rsplit("/", 1)[-1])
        name = heading.get_text(" ", strip=True) if heading else slug
        cities.setdefault(slug, City(name=name, path=path, slug=slug, dates=(match.group("date"),)))
    if not cities:
        raise RuntimeError(f"no datasets found on {DATA_PAGE_URL}; its HTML layout may have changed")
    return sorted(cities.values(), key=lambda c: c.slug)


def fetch_catalog(session: requests.Session) -> tuple[list[City], str]:
    """Return (cities, source). source is 'json' (full archive) or 'html' (latest snapshots only)."""
    try:
        page = session.get(PAGE_DATA_URL, timeout=30)
        page.raise_for_status()
        for query_hash in page.json().get("staticQueryHashes", []):
            resp = session.get(STATIC_QUERY_URL.format(hash=query_hash), timeout=30)
            resp.raise_for_status()
            datasets = resp.json().get("data", {}).get("allData", {}).get("datasets")
            if datasets:
                return parse_catalog_json(datasets), "json"
        raise RuntimeError("no static query with allData.datasets found")
    except (requests.RequestException, ValueError, KeyError, RuntimeError) as exc:
        print(f"warning: could not read the site's dataset catalog ({exc}); "
              "falling back to scraping the page, which lists only the latest snapshot per city", file=sys.stderr)

    resp = session.get(DATA_PAGE_URL, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"  # the server omits charset; requests would otherwise guess latin-1
    return parse_catalog_html(resp.text), "html"


def load_catalog(
    data_dir: Path, refresh: bool = False, session: requests.Session | None = None
) -> tuple[list[City], str]:
    """Return (cities, source), using a <24h cache in data_dir when available."""
    cache_path = data_dir / CATALOG_CACHE_NAME

    def read_cache() -> tuple[list[City], str] | None:
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if payload.get("version") != CATALOG_VERSION:
                return None
            return [City(**{**c, "dates": tuple(c["dates"])}) for c in payload["cities"]], payload["source"]
        except (OSError, ValueError, KeyError, TypeError):
            return None

    if not refresh and cache_path.exists() and time.time() - cache_path.stat().st_mtime < CATALOG_MAX_AGE_S:
        cached = read_cache()
        if cached and cached[1] == "json":  # never reuse a cache built from the weaker HTML fallback
            return cached

    session = session or _make_session()
    try:
        cities, source = fetch_catalog(session)
    except (requests.RequestException, RuntimeError) as exc:
        cached = read_cache()
        if cached:
            print(f"warning: could not refresh catalog ({exc}); using stale cache", file=sys.stderr)
            return cached
        raise

    data_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "version": CATALOG_VERSION,
                "source": source,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "cities": [asdict(c) for c in cities],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return cities, source


# --------------------------------------------------------------------------- #
# City / snapshot selection
# --------------------------------------------------------------------------- #


def resolve_city(query: str, catalog: list[City]) -> City:
    """Map user input (slug, full path, or display name) to a catalog entry."""
    q = normalize(query)
    by_slug = {c.slug: c for c in catalog}
    by_path = {normalize(c.path): c for c in catalog}
    by_city_name = {normalize(c.name.split(",")[0]): c for c in catalog}

    for table in (by_slug, by_path, by_city_name):
        if q in table:
            return table[q]

    prefix = [c for slug, c in by_slug.items() if slug.startswith(q)]
    if len(prefix) == 1:
        return prefix[0]

    suggestions = difflib.get_close_matches(q, list(by_slug), n=5, cutoff=0.5)
    if prefix:
        suggestions = sorted({c.slug for c in prefix} | set(suggestions))
    hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
    raise SystemExit(f"error: unknown city '{query}'.{hint}  (run with --list to see all cities)")


def parse_city_arg(arg: str) -> tuple[str, str | None]:
    """'boston' -> ('boston', None); 'boston@2026-03-28' -> ('boston', '2026-03-28')."""
    if "@" not in arg:
        return arg, None
    name, date = arg.rsplit("@", 1)
    if not DATE_RE.match(date):
        raise SystemExit(f"error: bad date '{date}' in '{arg}' (expected YYYY-MM-DD)")
    return name, date


def select_dates(
    city: City,
    *,
    date: str | None = None,
    all_snapshots: bool = False,
    since: str | None = None,
    validate: bool = True,
) -> list[str]:
    """Decide which snapshot dates of a city to download (newest first)."""
    if date:
        if validate and date not in city.dates:
            raise SystemExit(
                f"error: {city.slug} has no snapshot dated {date}. Available: {', '.join(city.dates)}\n"
                "       (if the site was updated recently, try --refresh)"
            )
        return [date]
    if all_snapshots or since:
        return [d for d in city.dates if since is None or d >= since]
    return [city.latest]


# --------------------------------------------------------------------------- #
# Downloading
# --------------------------------------------------------------------------- #


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:,.1f} GB"


class _Progress:
    """Minimal progress line; quiet when stderr is not a terminal."""

    def __init__(self, label: str, total: int | None):
        self.label, self.total = label, total
        self.tty = sys.stderr.isatty()
        self.start = self.last = time.monotonic()
        self.next_step = 0.25

    def update(self, done: int) -> None:
        now = time.monotonic()
        if self.tty:
            if now - self.last < 0.5:
                return
        else:
            frac = done / self.total if self.total else 0
            if frac < self.next_step:
                return
            self.next_step += 0.25
        self.last = now
        rate = done / max(now - self.start, 1e-6)
        if self.total:
            msg = f"{done / self.total:6.1%}  {_fmt_bytes(done)} / {_fmt_bytes(self.total)}  {_fmt_bytes(rate)}/s"
        else:
            msg = f"{_fmt_bytes(done)}  {_fmt_bytes(rate)}/s"
        end = "" if self.tty else "\n"
        print(f"\r  {self.label:<28} {msg:<48}", end=end, file=sys.stderr, flush=True)

    def close(self, done: int) -> None:
        elapsed = time.monotonic() - self.start
        print(
            f"\r  {self.label:<28} done  {_fmt_bytes(done)} in {elapsed:.1f}s{' ' * 20}",
            file=sys.stderr,
            flush=True,
        )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(
    url: str,
    dest: Path,
    session: requests.Session,
    *,
    force: bool = False,
    retries: int = 3,
    label: str | None = None,
) -> dict:
    """Download url -> dest with resume support. Returns a manifest record."""
    label = label or dest.name
    if dest.exists() and not force:
        print(f"  {label:<28} exists, skipping ({_fmt_bytes(dest.stat().st_size)})", file=sys.stderr)
        return {"status": "skipped", "bytes": dest.stat().st_size}

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    if force and part.exists():
        part.unlink()

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        resume_from = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}
        try:
            with session.get(url, headers=headers, stream=True, timeout=(15, 120)) as resp:
                if resp.status_code == 416:  # our .part is already >= the file; start over
                    part.unlink(missing_ok=True)
                    continue
                if resp.status_code in (403, 404):
                    raise FileNotFoundError(
                        f"{resp.status_code} for {url} - this snapshot/file is not hosted (anymore). "
                        "Run --list <city> to see the available dates, or --refresh to update the catalog."
                    )
                resp.raise_for_status()

                if resp.status_code == 206 and resume_from:
                    mode, done = "ab", resume_from
                else:  # 200: server ignored/didn't get a Range header -> full download
                    mode, done = "wb", 0
                length = resp.headers.get("Content-Length")
                total = (int(length) + done) if length else None

                if done:
                    print(f"  {label:<28} resuming at {_fmt_bytes(done)}", file=sys.stderr)
                progress = _Progress(label, total)
                with part.open(mode) as fh:
                    for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                        fh.write(chunk)
                        done += len(chunk)
                        progress.update(done)
                if total is not None and done != total:
                    raise IOError(f"incomplete download: got {done} of {total} bytes")
                progress.close(done)

            os.replace(part, dest)
            return {"status": "downloaded", "bytes": done, "sha256": _sha256(dest)}

        except FileNotFoundError:
            part.unlink(missing_ok=True)
            raise
        except (requests.RequestException, IOError) as exc:
            last_error = exc
            wait = 2 ** attempt
            print(f"  {label:<28} attempt {attempt}/{retries} failed: {exc}; retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)

    raise IOError(f"giving up on {url}: {last_error}")


def extract_gzip(gz_path: Path, force: bool = False) -> Path:
    """Gunzip listings.csv.gz -> listings.csv next to it (skips if up to date)."""
    out = gz_path.with_suffix("")  # strip ".gz"
    if out.exists() and not force and out.stat().st_mtime >= gz_path.stat().st_mtime:
        print(f"  {out.name:<28} already extracted, skipping", file=sys.stderr)
        return out
    tmp = out.with_name(out.name + ".part")
    with gzip.open(gz_path, "rb") as src, tmp.open("wb") as dst:
        shutil.copyfileobj(src, dst, CHUNK_SIZE)
    os.replace(tmp, out)
    print(f"  {out.name:<28} extracted ({_fmt_bytes(out.stat().st_size)})", file=sys.stderr)
    return out


def _update_manifest(snapshot_dir: Path, city: City, date: str, key: str, record: dict) -> None:
    manifest_path = snapshot_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest.update(
        {"city": city.name, "slug": city.slug, "path": city.path, "snapshot_date": date, "source": DATA_PAGE_URL}
    )
    files = manifest.setdefault("files", {})
    files[key] = {
        "local_name": FILES[key][2],
        "url": city.url(key, date),
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **{k: v for k, v in record.items() if k != "status"},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def download_snapshot(
    city: City,
    date: str,
    keys: list[str],
    data_dir: Path,
    session: requests.Session,
    *,
    force: bool = False,
    extract: bool = False,
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    """Download the requested files of one snapshot. Returns [(key, status), ...]."""
    snapshot_dir = data_dir / city.slug / date
    print(f"\n{city.name}  [{city.slug}]  snapshot {date}  ->  {snapshot_dir}", file=sys.stderr)

    results: list[tuple[str, str]] = []
    for key in keys:
        url = city.url(key, date)
        dest = snapshot_dir / FILES[key][2]
        if dry_run:
            print(f"  {dest.name:<28} {url}", file=sys.stderr)
            results.append((key, "dry-run"))
            continue
        try:
            record = download_file(url, dest, session, force=force, label=dest.name)
        except (IOError, requests.RequestException) as exc:
            print(f"  {dest.name:<28} FAILED: {exc}", file=sys.stderr)
            results.append((key, "failed"))
            continue
        if record["status"] == "downloaded":
            _update_manifest(snapshot_dir, city, date, key, record)
        if extract and dest.suffix == ".gz":
            extract_gzip(dest, force=force)
        results.append((key, record["status"]))
    return results


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download Inside Airbnb data for one or more cities into the repo's data/ folder.\n"
            "Each snapshot (scrape date) goes to data/<city>/<YYYY-MM-DD>/."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "file keys for --files:\n  " + "\n  ".join(f"{k:<24}{v[0]}/{v[1]}" for k, v in FILES.items())
            + "\n\nexamples:\n"
            "  python scripts/download_data.py --list\n"
            "  python scripts/download_data.py --list boston new-york-city\n"
            "  python scripts/download_data.py new-york-city boston\n"
            "  python scripts/download_data.py boston --all-snapshots\n"
            "  python scripts/download_data.py vaud --since 2026-01-01 --files listings calendar\n"
            "  python scripts/download_data.py boston@2026-03-28\n"
        ),
    )
    parser.add_argument(
        "cities",
        nargs="*",
        help="city slug or name, optionally with @YYYY-MM-DD for one specific snapshot "
        "(e.g. boston, 'New York City', boston@2026-03-28)",
    )
    parser.add_argument("--list", action="store_true", help="list available cities (or, with city args, their snapshot dates) and exit")
    parser.add_argument(
        "--all-snapshots", action="store_true", help="download every available snapshot of each city, not just the latest"
    )
    parser.add_argument("--since", metavar="YYYY-MM-DD", help="download all snapshots on or after this date (implies --all-snapshots)")
    parser.add_argument("--date", metavar="YYYY-MM-DD", help="download this one snapshot date for every city (city@date overrides it)")
    parser.add_argument(
        "--files",
        nargs="+",
        default=["all"],
        metavar="KEY",
        help="which files to fetch (default: all). See the list of keys below.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_DATA_DIR, help=f"output directory (default: {DEFAULT_DATA_DIR})")
    parser.add_argument("--force", action="store_true", help="re-download files that already exist")
    parser.add_argument("--extract", action="store_true", help="also gunzip the .csv.gz files (pandas can read .gz directly, so this is optional)")
    parser.add_argument("--refresh", action="store_true", help="re-fetch the city catalog instead of using the cached copy")
    parser.add_argument("--dry-run", action="store_true", help="show what would be downloaded without downloading")
    return parser


def _print_list(catalog: list[City], source: str, cities: list[City] | None = None) -> None:
    if cities:
        for c in cities:
            print(f"{c.name}  [{c.slug}]  {len(c.dates)} snapshot(s)")
            for i, d in enumerate(c.dates):
                print(f"  {d}{'  (latest)' if i == 0 else ''}")
            print()
    else:
        width = max(len(c.name) for c in catalog)
        print(f"{'city':<{width}}  {'slug':<24}  snapshots  oldest      latest")
        for c in catalog:
            print(f"{c.name:<{width}}  {c.slug:<24}  {len(c.dates):>9}  {c.dates[-1]}  {c.latest}")
        print(f"\n{len(catalog)} cities available (source: {DATA_PAGE_URL})")
    if source == "html":
        print("note: catalog came from the HTML page, so only the latest snapshot per city is known", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    for label, value in (("--date", args.date), ("--since", args.since)):
        if value and not DATE_RE.match(value):
            parser.error(f"{label} must look like YYYY-MM-DD, got '{value}'")
    if args.date and (args.all_snapshots or args.since):
        parser.error("--date cannot be combined with --all-snapshots/--since")

    bad = [k for k in args.files if k != "all" and k not in FILES]
    if bad:
        parser.error(f"unknown file key(s) {bad}. Valid keys: {', '.join(FILES)}")
    keys = list(FILES) if "all" in args.files else list(dict.fromkeys(args.files))

    session = _make_session()
    catalog, source = load_catalog(args.out, refresh=args.refresh, session=session)

    if args.list:
        _print_list(catalog, source, [resolve_city(parse_city_arg(raw)[0], catalog) for raw in args.cities])
        return 0

    if not args.cities:
        parser.print_usage()
        parser.exit(2, "error: give at least one city, or use --list to see what is available\n")

    # (city, [dates]) pairs to download
    plan: list[tuple[City, list[str]]] = []
    for raw in args.cities:
        name, pinned = parse_city_arg(raw)
        city = resolve_city(name, catalog)
        dates = select_dates(
            city,
            date=pinned or args.date,
            all_snapshots=args.all_snapshots,
            since=args.since,
            validate=(source == "json"),
        )
        if not dates:
            print(f"warning: {city.slug} has no snapshots on/after {args.since} (available: {', '.join(city.dates)})", file=sys.stderr)
        plan.append((city, dates))

    summary: list[tuple[str, str, str, str]] = []
    for city, dates in plan:
        for date in dates:
            for key, status in download_snapshot(
                city, date, keys, args.out, session, force=args.force, extract=args.extract, dry_run=args.dry_run
            ):
                summary.append((city.slug, date, key, status))

    failed = [s for s in summary if s[3] == "failed"]
    print("\nsummary:", file=sys.stderr)
    for slug, date, key, status in summary:
        print(f"  {slug:<22} {date}  {key:<24} {status}", file=sys.stderr)
    if failed:
        print(f"\n{len(failed)} file(s) failed - re-run the same command to retry/resume.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
