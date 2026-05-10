#!/usr/bin/env python3
"""
ART: Analyze WebSecSim security_events.jsonl for bursts of failed logins,
attack spikes, and optional webhook notification.

Default log path: backend/logs/security_events.jsonl
Override: WEBSECSIM_SECURITY_LOG=/path/to/file.jsonl

Example:
  python3 scripts/art/analyze_security_log.py
  python3 scripts/art/analyze_security_log.py --window 300 --failed-threshold 8
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from collections import defaultdict
from typing import Any


def load_events(path: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        print(f"No log file at {path} (start the API and perform some actions).", file=sys.stderr)
    return events


def analyze(events: list[dict[str, Any]], window_sec: float, failed_threshold: int) -> list[str]:
    """Return human-readable alerts."""
    alerts: list[str] = []
    if not events:
        alerts.append("No events to analyze.")
        return alerts

    # Failed login bursts per IP (using ts field)
    by_ip: dict[str, list[float]] = defaultdict(list)
    for e in events:
        if e.get("event") != "login_failed":
            continue
        ip = str(e.get("ip", "unknown"))
        ts = float(e.get("ts", 0))
        by_ip[ip].append(ts)

    latest_ts = max(float(e.get("ts", 0)) for e in events)
    for ip, stamps in by_ip.items():
        recent = [t for t in stamps if latest_ts - t <= window_sec]
        if len(recent) >= failed_threshold:
            alerts.append(
                f"[ALERT] Possible credential stuffing: {len(recent)} failed logins from {ip} "
                f"in the last {int(window_sec)}s (threshold {failed_threshold})."
            )

    attack_count = sum(1 for e in events if e.get("event") == "attack_executed")
    if attack_count >= 10:
        alerts.append(f"[INFO] High attack volume: {attack_count} executed attack events in log.")

    login_ok = sum(1 for e in events if e.get("event") == "login_ok")
    alerts.append(f"[SUMMARY] login_ok={login_ok}, login_failed_events={sum(1 for e in events if e.get('event') == 'login_failed')}, attacks={attack_count}")
    return alerts


def post_webhook(url: str, text: str) -> None:
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        _ = resp.read()


def main() -> int:
    default_log = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "backend",
        "logs",
        "security_events.jsonl",
    )
    parser = argparse.ArgumentParser(description="Analyze WebSecSim security JSONL log.")
    parser.add_argument("--log", default=os.environ.get("WEBSECSIM_SECURITY_LOG", default_log))
    parser.add_argument("--window", type=float, default=120.0, help="Sliding window in seconds")
    parser.add_argument("--failed-threshold", type=int, default=5)
    parser.add_argument("--webhook", default=os.environ.get("WEBSECSIM_ALERT_WEBHOOK", ""))
    args = parser.parse_args()

    events = load_events(args.log)
    lines = analyze(events, args.window, args.failed_threshold)
    report = "\n".join(lines)
    print(report)

    if args.webhook and "[ALERT]" in report:
        try:
            post_webhook(args.webhook, report)
            print("(webhook sent)", file=sys.stderr)
        except Exception as exc:
            print(f"Webhook failed: {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
