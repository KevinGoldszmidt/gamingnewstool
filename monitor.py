#!/usr/bin/env python3
"""
Gaming News Watch — Digest Edition
Runs a few times a day (morning / afternoon / evening), pulls new items
from all watched feeds since the last run, filters out non-news content
(reviews, previews, opinion, recaps, etc, see filters.json), ranks what's
left (primary sources first, then most recent), and sends a single
Telegram digest with the top N stories. Items outside the top N, and
items that fail the news filter, are recorded as seen and are not
resent later.
"""

import json
import os
import sys
import time
import html
import urllib.request
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

import feedparser

FEEDS_FILE = "feeds.json"
FILTERS_FILE = "filters.json"
SEEN_FILE = "seen.json"
MAX_SEEN_PER_FEED = 300
SUMMARY_MAX_CHARS = 220
TOP_N = 5
LOCAL_TZ = ZoneInfo("Europe/Madrid")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

DEFAULT_FILTERS = {"deny_title_keywords": [], "deny_categories": []}


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def entry_id(entry):
    return entry.get("id") or entry.get("link") or (
        entry.get("title", "") + entry.get("published", "")
    )


def clean_summary(entry):
    raw = entry.get("summary", "") or entry.get("description", "")
    text = html.unescape(raw)
    out, in_tag = [], False
    for ch in text:
        if ch == "<":
            in_tag = True
            continue
        if ch == ">":
            in_tag = False
            continue
        if not in_tag:
            out.append(ch)
    text = " ".join("".join(out).split())
    if len(text) > SUMMARY_MAX_CHARS:
        text = text[:SUMMARY_MAX_CHARS].rsplit(" ", 1)[0] + "..."
    return text


def published_ts(entry):
    for key in ("published_parsed", "updated_parsed"):
        val = entry.get(key)
        if val:
            return time.mktime(val)
    return 0


def is_news(entry, filters):
    """Returns False for reviews/previews/opinion/recap-style posts."""
    title = (entry.get("title") or "").lower()
    for kw in filters.get("deny_title_keywords", []):
        if kw.lower() in title:
            return False

    categories = []
    for tag in entry.get("tags", []) or []:
        term = tag.get("term") if isinstance(tag, dict) else None
        if term:
            categories.append(term.lower())
    deny_cats = {c.lower() for c in filters.get("deny_categories", [])}
    if any(cat in deny_cats for cat in categories):
        return False

    return True


def digest_label():
    hour = datetime.now(LOCAL_TZ).hour
    if 5 <= hour < 12:
        return "Morning Digest"
    if 12 <= hour < 18:
        return "Afternoon Digest"
    return "Evening Digest"


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
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except urllib.error.URLError as e:
        print(f"Telegram send failed: {e}", file=sys.stderr)


def collect_new_items(feeds, filters, seen):
    """Returns a list of new, news-relevant item dicts. Mutates `seen`."""
    items = []
    for category in ("primary", "secondary"):
        for feed in feeds.get(category, []):
            name, url = feed["name"], feed["url"]
            seen_ids = set(seen.get(url, []))
            try:
                parsed = feedparser.parse(url)
            except Exception as e:
                print(f"ERROR checking {name} ({url}): {e}", file=sys.stderr)
                continue
            if parsed.bozo and not parsed.entries:
                print(f"WARNING: could not parse {name} ({url}): {parsed.bozo_exception}")
                continue

            new_ids = []
            passed = 0
            for entry in parsed.entries:
                eid = entry_id(entry)
                if not eid or eid in seen_ids:
                    continue
                new_ids.append(eid)  # mark seen regardless of filter outcome
                if not is_news(entry, filters):
                    continue
                passed += 1
                items.append({
                    "category": category,
                    "source": name,
                    "entry": entry,
                    "ts": published_ts(entry),
                })
            if new_ids:
                updated = new_ids + list(seen_ids)
                seen[url] = updated[:MAX_SEEN_PER_FEED]
            print(f"{name}: {len(new_ids)} new item(s), {passed} passed news filter")
            time.sleep(1)
    return items


def rank_items(items):
    # primary sources before secondary, then most recent first
    return sorted(
        items,
        key=lambda i: (0 if i["category"] == "primary" else 1, -i["ts"]),
    )


def format_digest(top_items, total_found):
    lines = [f"<b>{digest_label()} — Top {len(top_items)} gaming stories</b>"]
    for idx, item in enumerate(top_items, start=1):
        entry = item["entry"]
        title = html.escape(entry.get("title", "(no title)"))
        link = entry.get("link", "")
        summary = html.escape(clean_summary(entry))
        tag = "🚨" if item["category"] == "primary" else "👀"
        block = [f"{tag} <b>{idx}. {title}</b>", f"<i>{html.escape(item['source'])}</i>"]
        if summary:
            block.append(summary)
        if link:
            block.append(link)
        lines.append("\n".join(block))
    if total_found > len(top_items):
        lines.append(f"({total_found - len(top_items)} other news item(s) not shown)")
    return "\n\n".join(lines)


def main():
    feeds = load_json(FEEDS_FILE, {"primary": [], "secondary": []})
    filters = load_json(FILTERS_FILE, DEFAULT_FILTERS)
    seen = load_json(SEEN_FILE, {})
    first_run = not os.path.exists(SEEN_FILE)

    items = collect_new_items(feeds, filters, seen)

    if first_run:
        print("First run: recording current feed state, no digest sent.")
    else:
        ranked = rank_items(items)
        top = ranked[:TOP_N]
        if top:
            send_telegram(format_digest(top, len(items)))
            print(f"Sent digest with {len(top)} stories (of {len(items)} news-relevant item(s) found).")
        else:
            print("No new news-relevant items since last check, no digest sent.")

    save_json(SEEN_FILE, seen)


if __name__ == "__main__":
    main()
