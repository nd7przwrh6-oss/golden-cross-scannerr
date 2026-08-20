"""Fetch current index constituent lists (S&P 500, Nasdaq-100, Dow 30, TSX 60).

Scrapes Wikipedia's constituent tables. These pages are maintained close to
real-time by editors when index providers announce changes, which is good
enough for a daily scan (we're not trading on index-membership latency).
"""
from __future__ import annotations

import io

import pandas as pd

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; golden-cross-scanner/1.0)"}


def _read_tables(url: str) -> list[pd.DataFrame]:
    import requests

    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return pd.read_html(io.StringIO(resp.text))


def _find_table(tables: list[pd.DataFrame], required_cols: list[str]) -> pd.DataFrame:
    for t in tables:
        cols = [str(c).strip().lower() for c in t.columns]
        if all(any(rc in c for c in cols) for rc in required_cols):
            return t
    raise ValueError(f"No table found with columns matching {required_cols}")


def _col(t: pd.DataFrame, name: str) -> str:
    for c in t.columns:
        if name in str(c).strip().lower():
            return c
    raise KeyError(name)


def _normalize(sym: str) -> str:
    return str(sym).strip().replace(".", "-").replace("\n", "")


def _symbols(t: pd.DataFrame, col_hint: str) -> list[str]:
    col = _col(t, col_hint)
    return [_normalize(s) for s in t[col].dropna().tolist()]


def get_sp500() -> set[str]:
    tables = _read_tables("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    t = _find_table(tables, ["symbol"])
    return set(_symbols(t, "symbol"))


def get_nasdaq100() -> set[str]:
    tables = _read_tables("https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies")
    t = _find_table(tables, ["ticker"])
    return set(_symbols(t, "ticker"))


def get_dow30() -> set[str]:
    tables = _read_tables("https://en.wikipedia.org/wiki/List_of_Dow_Jones_Industrial_Average_companies")
    t = _find_table(tables, ["symbol"])
    return set(_symbols(t, "symbol"))


def get_tsx60() -> set[str]:
    tables = _read_tables("https://en.wikipedia.org/wiki/S%26P/TSX_60")
    t = _find_table(tables, ["symbol"])
    raw = set(_symbols(t, "symbol"))
    # Toronto Stock Exchange tickers need the .TO suffix for Yahoo Finance.
    return {f"{s}.TO" if not s.endswith(".TO") else s for s in raw}


def get_universe() -> dict[str, set[str]]:
    """Return {ticker: {index_names it belongs to}}."""
    sources = {
        "S&P 500": get_sp500,
        "Nasdaq-100": get_nasdaq100,
        "Dow 30": get_dow30,
        "TSX 60": get_tsx60,
    }
    universe: dict[str, set[str]] = {}
    errors = []
    for name, fn in sources.items():
        try:
            tickers = fn()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
            continue
        for tk in tickers:
            universe.setdefault(tk, set()).add(name)
    if errors:
        import sys

        print("WARNING: failed to load some index lists:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
    return universe


if __name__ == "__main__":
    u = get_universe()
    print(f"Loaded {len(u)} unique tickers")
    for name in ["S&P 500", "Nasdaq-100", "Dow 30", "TSX 60"]:
        count = sum(1 for idx in u.values() if name in idx)
        print(f"  {name}: {count}")
