# golden-cross-scanner

Scans every constituent of the S&P 500, Nasdaq-100, Dow 30, and TSX 60 for
50-day/200-day SMA golden crosses (bullish) and death crosses (bearish).

Runs automatically via two scheduled Claude Code cloud routines — one shortly
after market open, one shortly after market close, weekdays only. No manual
trigger needed. Each run:

1. Pulls current index membership from Wikipedia (`universe.py`).
2. Downloads ~18 months of daily price history per ticker via `yfinance`.
3. Computes 50-day and 200-day SMAs and detects crossovers.
4. Diffs against `state.json` so only *new* crosses are reported (not the
   same event re-flagged on every run).
5. Writes a report to `reports/YYYY-MM-DD-{open,close}.md` and commits it.
6. Emails a summary to the account owner via the Gmail MCP connector.

## Manual run

```bash
pip install -r requirements.txt
python scanner.py --mode close
```

## Notes

- Crossovers are based on daily closing prices, so the market-open run
  mostly reconfirms the prior close's signal — it will only show something
  under "new crosses" if state.json hasn't caught up yet.
- `state.json` is the source of truth for "have we already told the user
  about this cross" — don't delete it, or you'll get re-notified about every
  currently-active cross on the next run.
- Cross detection near the boundary (diff close to zero) can occasionally
  flicker between runs due to minor data timing differences from the
  upstream price feed. This is an inherent property of any live SMA-cross
  detector, not a bug.
