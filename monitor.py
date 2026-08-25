#!/usr/bin/env python3
"""
Gaming News Watch
Polls a list of RSS feeds (official press-release channels + publications
known for scoops), figures out which entries are new since the last run,
and pushes an alert to Telegram for each one.

State (which entries have already been seen) is stored in seen.json so the
script only ever alerts on genuinely new items, even if it runs every few
minutes forever.
"""

import json
import os
import sys
import time
import html
import urllib.request
import urllib.error

import feedparser

FEEDS_FILE = "feeds.json"
SEEN_FILE = "seen.json"
MAX_SEEN_PER_FEED = 300          # keep seen.json from growing forever
SUMMARY_MAX_CHARS = 300

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def entry_id(entry):
    # Prefer a stable guid/id, fall back to link, fall back to title+published
    return entry.get("id") or entry.get("link") or (
        entry.get("title", "") + entry.get("published", "")
    )


def clean_summary(entry):
    raw = entry.get("summary", "") or entry.get("description", "")
    # very light HTML strip, good enough for a Telegram message
    text = html.unescape(raw)
    for tag_start, tag_end in [("<", ">")]:
        out = []
        in_tag = False
        for ch in text:
            if ch == tag_start:
                in_tag = True
                continue
            if ch == tag_end:
                in_tag = False
                continue
            if not in_tag:
                out.append(ch)
        text = "".join(out)
    text = " ".join(text.split())
    if len(text) > SUMMARY_MAX_CHARS:
        text = text[:SUMMARY_MAX_CHARS].rsplit(" ", 1)[0] + "..."
    return text


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing, printing instead:\n", message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except urllib.error.URLError as e:
        print(f"Telegram send failed: {e}", file=sys.stderr)


def format_message(category, source_name, entry):
    title = html.escape(entry.get("title", "(no title)"))
    link = entry.get("link", "")
    summary = html.escape(clean_summary(entry))
    tag = "🚨 PRIMARY" if category == "primary" else "👀 secondary"
    lines = [
        f"{tag} — <b>{html.escape(source_name)}</b>",
        f"<b>{title}</b>",
    ]
    if summary:
        lines.append(summary)
    if link:
        lines.append(link)
    return "\n\n".join(lines)


def check_feed(category, source_name, url, seen):
    seen_ids = set(seen.get(url, []))
    new_ids = []
    alerts = []

    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        print(f"WARNING: could not parse {source_name} ({url}): {parsed.bozo_exception}")
        return alerts

    for entry in parsed.entries:
        eid = entry_id(entry)
        if not eid:
            continue
        if eid in seen_ids:
            continue
        new_ids.append(eid)
        alerts.append(format_message(category, source_name, entry))

    if new_ids:
        updated = new_ids + list(seen_ids)
        seen[url] = updated[:MAX_SEEN_PER_FEED]

    return alerts


def main():
    feeds = load_json(FEEDS_FILE, {"primary": [], "secondary": []})
    seen = load_json(SEEN_FILE, {})

    first_run = not os.path.exists(SEEN_FILE)
    all_alerts = []

    for category in ("primary", "secondary"):
        for feed in feeds.get(category, []):
            name, url = feed["name"], feed["url"]
            try:
                alerts = check_feed(category, name, url, seen)
                all_alerts.extend(alerts)
                print(f"{name}: {len(alerts)} new item(s)")
            except Exception as e:
                print(f"ERROR checking {name} ({url}): {e}", file=sys.stderr)
            time.sleep(1)  # be polite to feed servers

    if first_run:
        # On the very first run, just record current state, don't blast
        # every historical article as if it were breaking news.
        print("First run: recording current feed state, no alerts sent.")
    else:
        for msg in all_alerts:
            send_telegram(msg)
            time.sleep(1)
        print(f"Sent {len(all_alerts)} alert(s).")

    save_json(SEEN_FILE, seen)


if __name__ == "__main__":
    main()
