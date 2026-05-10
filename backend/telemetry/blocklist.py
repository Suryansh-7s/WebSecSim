#!/usr/bin/env python3
"""
ART: Emit an iptables-style blocklist from security_events.jsonl when IPs
cross a failed-login threshold. Does not modify the host firewall; writes
a machine-readable list for operators or downstream automation.

Output: ./art_blocklist_ips.txt (one IP per line, with timestamp comment in stderr)

Example:
  python3 scripts/art/remediation_blocklist.py --window 600 --threshold 20
  sudo xargs -a art_blocklist_ips.txt -I{} iptables -A INPUT -s {} -j DROP
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Any


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    default_log = os.path.join(root, "backend", "logs", "security_events.jsonl")
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default=os.environ.get("WEBSECSIM_SECURITY_LOG", default_log))
    parser.add_argument("--window", type=float, default=600.0)
    parser.add_argument("--threshold", type=int, default=20)
    parser.add_argument("--out", default="art_blocklist_ips.txt")
    args = parser.parse_args()

    events: list[dict[str, Any]] = []
    try:
        with open(args.log, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except FileNotFoundError:
        print("No events file; nothing to do.")
        return 0

    if not events:
        print("Empty log; nothing to do.")
        return 0

    latest = max(float(e.get("ts", 0)) for e in events)
    by_ip: dict[str, list[float]] = defaultdict(list)
    for e in events:
        if e.get("event") == "login_failed":
            by_ip[str(e.get("ip", "unknown"))].append(float(e.get("ts", 0)))

    blocked: list[str] = []
    for ip, stamps in by_ip.items():
        if ip in ("unknown", "127.0.0.1", "::1"):
            continue
        recent = [t for t in stamps if latest - t <= args.window]
        if len(recent) >= args.threshold:
            blocked.append(ip)

    with open(args.out, "w", encoding="utf-8") as f:
        for ip in sorted(set(blocked)):
            f.write(ip + "\n")

    print(
        f"Wrote {len(set(blocked))} IPs to {args.out} "
        f"(window={int(args.window)}s threshold={args.threshold}).",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
