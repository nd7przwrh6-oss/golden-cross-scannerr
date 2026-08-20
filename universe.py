"""Index constituent lists (S&P 500, Nasdaq-100, Dow 30, TSX 60).

Constituents are bundled as static JSON in data/ rather than scraped live
from Wikipedia on every run: the scheduled cloud routine that runs this
script executes behind an egress proxy that only allows a small allowlist
of hosts (package registries, GitHub, Yahoo Finance) and blocks
en.wikipedia.org, so live scraping isn't viable there. Index membership
also doesn't change often enough to justify a live fetch on every run.

To refresh the bundled lists (run locally, NOT from the cloud routine,
since it needs Wikipedia access):
    python universe.py --refresh
"""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

INDEX_FILES = {
    "S&P 500": "sp500.json",
    "Nasdaq-100": "nasdaq100.json",
    "Dow 30": "dow30.json",
    "TSX 60": "tsx60.json",
}


def get_universe() -> dict[str, set[str]]:
    """Return {ticker: {index_names it belongs to}} from the bundled JSON files."""
    universe: dict[str, set[str]] = {}
    for name, filename in INDEX_FILES.items():
        path = DATA_DIR / filename
        tickers = json.loads(path.read_text())
        for tk in tickers:
            universe.setdefault(tk, set()).add(name)
    return universe


# --- Live scraping, used only to refresh the bundled JSON (run locally) ---

def _read_tables(url: str):
    import io

    import pandas as pd
    import requests

    headers = {"User-Agent": "Mozilla/5.0 (compatible; golden-cross-scanner/1.0)"}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return pd.read_html(io.StringIO(resp.text))


def _find_table(tables, required_cols: list[str]):
    for t in tables:
        cols = [str(c).strip().lower() for c in t.columns]
        if all(any(rc in c for c in cols) for rc in required_cols):
            return t
    raise ValueError(f"No table found with columns matching {required_cols}")


def _col(t, name: str) -> str:
    for c in t.columns:
        if name in str(c).strip().lower():
            return c
    raise KeyError(name)


def _normalize(sym: str) -> str:
    return str(sym).strip().replace(".", "-").replace("\n", "")


def _symbols(t, col_hint: str) -> list[str]:
    col = _col(t, col_hint)
    return [_normalize(s) for s in t[col].dropna().tolist()]


def refresh_sp500() -> list[str]:
    tables = _read_tables("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    t = _find_table(tables, ["symbol"])
    return sorted(set(_symbols(t, "symbol")))


def refresh_nasdaq100() -> list[str]:
    tables = _read_tables("https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies")
    t = _find_table(tables, ["ticker"])
    return sorted(set(_symbols(t, "ticker")))


def refresh_dow30() -> list[str]:
    tables = _read_tables("https://en.wikipedia.org/wiki/List_of_Dow_Jones_Industrial_Average_companies")
    t = _find_table(tables, ["symbol"])
    return sorted(set(_symbols(t, "symbol")))


def refresh_tsx60() -> list[str]:
    tables = _read_tables("https://en.wikipedia.org/wiki/S%26P/TSX_60")
    t = _find_table(tables, ["symbol"])
    raw = set(_symbols(t, "symbol"))
    return sorted({f"{s}.TO" if not s.endswith(".TO") else s for s in raw})


def refresh_all() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    fns = {
        "sp500.json": refresh_sp500,
        "nasdaq100.json": refresh_nasdaq100,
        "dow30.json": refresh_dow30,
        "tsx60.json": refresh_tsx60,
    }
    for filename, fn in fns.items():
        tickers = fn()
        (DATA_DIR / filename).write_text(json.dumps(tickers, indent=2) + "\n")
        print(f"{filename}: {len(tickers)} tickers")


if __name__ == "__main__":
    import sys

    if "--refresh" in sys.argv:
        refresh_all()
    else:
        u = get_universe()
        print(f"Loaded {len(u)} unique tickers")
        for name in INDEX_FILES:
            count = sum(1 for idx in u.values() if name in idx)
            print(f"  {name}: {count}")
