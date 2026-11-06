#!/usr/bin/env python3
"""Fetch DCE LH (生猪) futures from Sina and write quotes.json for GitHub Pages."""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "quotes.json"
TZ = ZoneInfo("Asia/Shanghai")

# Active listed months around now + continuous
MONTHS = ["2611", "2701", "2703", "2705", "2707", "2709"]
CODES = [f"nf_LH{m}" for m in MONTHS] + ["nf_LH0"]

POSITION = {
    "symbol": "LH2705",
    "side": "long",
    "lots": 7,
    "cost": 12000,  # 元/吨
    "multiplier": 16,  # 吨/手
}


def fetch(lst: str) -> str:
    req = urllib.request.Request(
        "https://hq.sinajs.cn/list=" + lst,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"},
    )
    with urllib.request.urlopen(req, timeout=12) as r:
        return r.read().decode("gbk", errors="replace")


def parse_map(raw: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r'hq_str_([^=]+)="([^"]*)"', raw)
        if m.group(2)
    }


def fnum(x: str) -> float:
    try:
        return float(x or 0)
    except ValueError:
        return 0.0


def parse_lh(code: str, s: str) -> dict | None:
    """Sina commodity futures (nf_LH*): name,time,open,high,low,last,bid,ask,...,settle,prev?,bvol,svol,vol,oi,..."""
    p = s.split(",")
    if len(p) < 15:
        return None
    last = fnum(p[5])
    open_ = fnum(p[2])
    high = fnum(p[3])
    low = fnum(p[4])
    bid = fnum(p[6])
    ask = fnum(p[7])
    settle = fnum(p[9]) if len(p) > 9 else 0.0
    prev = fnum(p[10]) if len(p) > 10 else 0.0
    # Prefer yesterday settle for change; fall back to prev / open
    base = settle or prev or open_ or last
    change = last - base if base else 0.0
    change_pct = (change / base * 100.0) if base else 0.0
    volume = fnum(p[13]) if len(p) > 13 else 0.0
    oi = fnum(p[14]) if len(p) > 14 else 0.0
    date = (p[17] if len(p) > 17 else "").strip()
    traw = (p[1] if len(p) > 1 else "").strip().zfill(6)
    time_s = f"{traw[0:2]}:{traw[2:4]}:{traw[4:6]}" if len(traw) >= 6 else traw
    symbol = code.replace("nf_", "")
    return {
        "symbol": symbol,
        "name": (p[0] or symbol).strip(),
        "last": last,
        "open": open_,
        "high": high,
        "low": low,
        "settle": settle,
        "prev": prev,
        "change": round(change, 2),
        "changePct": round(change_pct, 2),
        "volume": int(volume),
        "oi": int(oi),
        "bid": bid,
        "ask": ask,
        "time": f"{date} {time_s}".strip(),
        "isMain": False,
        "isPosition": False,
    }


def main() -> None:
    raw = fetch(",".join(CODES))
    mm = parse_map(raw)
    contracts: list[dict] = []
    for code in CODES:
        if code not in mm:
            continue
        row = parse_lh(code, mm[code])
        if row and (row["last"] or row["oi"] or row["volume"]):
            contracts.append(row)

    # Main = largest OI among dated months (exclude LH0 continuous)
    dated = [c for c in contracts if c["symbol"] != "LH0"]
    if dated:
        main = max(dated, key=lambda c: (c["oi"], c["volume"]))
        # Prefer LH2701 if it is close to max OI (explicit highlight), else heuristic winner
        for c in contracts:
            c["isMain"] = c["symbol"] == main["symbol"]
        # Force-highlight LH2701 as 主力 when present (user expectation)
        if any(c["symbol"] == "LH2701" for c in contracts):
            for c in contracts:
                c["isMain"] = c["symbol"] == "LH2701"

    for c in contracts:
        c["isPosition"] = c["symbol"] == POSITION["symbol"]

    now = datetime.now(TZ)
    payload = {
        "updatedAt": now.strftime("%Y-%m-%d %H:%M:%S") + " Asia/Shanghai",
        "source": "sina",
        "contracts": contracts,
        "position": POSITION,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    marks = {c["symbol"]: c["last"] for c in contracts}
    print(
        f"ok {OUT} updatedAt={payload['updatedAt']} n={len(contracts)} "
        f"LH2701={marks.get('LH2701')} LH2705={marks.get('LH2705')}"
    )


if __name__ == "__main__":
    main()
