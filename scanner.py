"""Scan the S&P 500, Nasdaq-100, Dow 30, and TSX 60 for golden/death crosses.

A golden cross = 50-day SMA crosses ABOVE the 200-day SMA (bullish signal).
A death cross  = 50-day SMA crosses BELOW the 200-day SMA (bearish signal).

Run twice a day (market open / market close) by a scheduled cloud routine.
Persists state.json so each run only reports *new* crosses, not the same
event re-detected on every run until the next crossover.

Usage:
    python scanner.py --mode open
    python scanner.py --mode close
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from universe import get_universe

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state.json"
REPORTS_DIR = ROOT / "reports"

SMA_FAST = 50
SMA_SLOW = 200
LOOKBACK_PERIOD = "18mo"  # enough trading days for a 200-day SMA plus buffer


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))


def fetch_prices(tickers: list[str]) -> "pd.DataFrame":
    import yfinance as yf

    data = yf.download(
        tickers,
        period=LOOKBACK_PERIOD,
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )
    return data


def detect_crosses(universe: dict[str, set[str]]) -> tuple[list[dict], list[dict], list[str]]:
    tickers = sorted(universe.keys())
    golden: list[dict] = []
    death: list[dict] = []
    failed: list[str] = []

    raw = fetch_prices(tickers)
    multi = isinstance(raw.columns, pd.MultiIndex)

    for tk in tickers:
        try:
            close = raw[tk]["Close"] if multi else raw["Close"]
            close = close.dropna()
            if len(close) < SMA_SLOW + 2:
                failed.append(tk)
                continue
            sma_fast = close.rolling(SMA_FAST).mean()
            sma_slow = close.rolling(SMA_SLOW).mean()
            diff = (sma_fast - sma_slow).dropna()
            if len(diff) < 2:
                failed.append(tk)
                continue
            prev, last = diff.iloc[-2], diff.iloc[-1]
            cross_date = str(diff.index[-1].date())
            price = float(close.iloc[-1])

            if prev <= 0 and last > 0:
                golden.append({
                    "ticker": tk,
                    "indexes": sorted(universe[tk]),
                    "date": cross_date,
                    "price": round(price, 2),
                })
            elif prev >= 0 and last < 0:
                death.append({
                    "ticker": tk,
                    "indexes": sorted(universe[tk]),
                    "date": cross_date,
                    "price": round(price, 2),
                })
        except Exception:  # noqa: BLE001
            failed.append(tk)

    return golden, death, failed


def filter_new(events: list[dict], state: dict, cross_type: str) -> list[dict]:
    new = []
    for e in events:
        prior = state.get(e["ticker"])
        if not prior or prior.get("date") != e["date"] or prior.get("type") != cross_type:
            new.append(e)
    return new


def update_state(state: dict, golden: list[dict], death: list[dict]) -> None:
    for e in golden:
        state[e["ticker"]] = {"type": "golden", "date": e["date"]}
    for e in death:
        state[e["ticker"]] = {"type": "death", "date": e["date"]}


def render_report(mode: str, new_golden: list[dict], new_death: list[dict],
                   total_golden: int, total_death: int, scanned: int, failed: int) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# Golden/Death Cross Scan — {mode} — {now}", ""]

    if new_golden:
        lines.append(f"## New golden crosses ({len(new_golden)})")
        for e in sorted(new_golden, key=lambda x: x["ticker"]):
            lines.append(f"- **{e['ticker']}** — ${e['price']} — {e['date']} — {', '.join(e['indexes'])}")
        lines.append("")
    if new_death:
        lines.append(f"## New death crosses ({len(new_death)})")
        for e in sorted(new_death, key=lambda x: x["ticker"]):
            lines.append(f"- **{e['ticker']}** — ${e['price']} — {e['date']} — {', '.join(e['indexes'])}")
        lines.append("")
    if not new_golden and not new_death:
        lines.append("No new golden or death crosses since the last run.")
        lines.append("")

    lines.append("---")
    lines.append(
        f"Scanned {scanned} tickers ({failed} skipped due to missing/insufficient data). "
        f"{total_golden} golden-cross and {total_death} death-cross events detected in this run's "
        f"data window (before de-duplication against previously reported crosses)."
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["open", "close"], required=True)
    args = parser.parse_args()

    REPORTS_DIR.mkdir(exist_ok=True)
    state = load_state()

    universe = get_universe()
    if not universe:
        print("ERROR: could not load any index constituents", file=sys.stderr)
        sys.exit(1)

    golden, death, failed = detect_crosses(universe)
    new_golden = filter_new(golden, state, "golden")
    new_death = filter_new(death, state, "death")
    update_state(state, golden, death)
    save_state(state)

    report = render_report(
        args.mode, new_golden, new_death,
        total_golden=len(golden), total_death=len(death),
        scanned=len(universe), failed=len(failed),
    )

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (REPORTS_DIR / f"{date_str}-{args.mode}.md").write_text(report)
    (REPORTS_DIR / "latest.md").write_text(report)

    print(report)


if __name__ == "__main__":
    main()
