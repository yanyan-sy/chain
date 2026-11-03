#!/usr/bin/env python3
"""Download public Chinese RSS headlines and create static JSON for the mobile site.

No paid API or cross-origin fetch in the browser. Requires feedparser and requests.
Items carry publisher/source, article URL, publication time; summaries are excerpted
from the feed and never invented by this script.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "site" / "data" / "news.json"
STATUS_PATH = ROOT / "site" / "data" / "status.json"
NOW = datetime.now(timezone.utc)
AGENT = "ChineseSupplyChainNewsBoard/1.0 (+static RSS feed reader; GitHub Actions)"
CUTOFF = NOW - timedelta(days=8)

# Separately queried to avoid under-filled searches from over-specific AND expressions.
SEARCHES = [
    ("全球供应链", "综合"),
    ("供应链重构", "产能布局"),
    ("企业 海外建厂", "产能布局"),
    ("制造业 海外投资", "产能布局"),
    ("贸易 关税 企业", "贸易政策"),
    ("出口管制 半导体", "科技原料"),
    ("港口 海运 物流", "物流风险"),
    ("关键矿产 稀土", "科技原料"),
    ("新能源 电池 供应链", "科技原料"),
    ("国际采购 供应商", "产能布局"),
]

TOPIC_TERMS = {
    "产能布局": ["海外建厂", "海外工厂", "建厂", "投产", "扩产", "产能", "迁厂", "生产基地", "供应商", "制造业", "出海", "布局", "投资", "本地化", "转移"],
    "贸易政策": ["关税", "出口管制", "进口限制", "贸易战", "贸易政策", "原产地", "制裁", "反倾销", "贸易壁垒", "禁令", "海关", "贸易协定"],
    "物流风险": ["物流", "航运", "海运", "港口", "集装箱", "货运", "仓储", "运费", "航线", "红海", "运输", "延误", "供应链中断"],
    "科技原料": ["半导体", "芯片", "存储", "稀土", "锂", "铜矿", "关键矿产", "电池", "光伏", "人工智能", "ai", "晶圆", "原材料", "设备出口", "新能源"],
}
RELEVANCE_TERMS = list(dict.fromkeys([
    "供应链", "全球制造", "贸易", "出口", "进口", "外贸", "跨境", "关税", "工厂", "海外", "海运", "航运", "港口", "物流", "采购", "供应商", "扩产", "产能", "芯片", "半导体", "稀土", "矿产", "制造", "投资", "转口", "贸易壁垒", "出口管制", "新能源", "电池", "仓储", "订单", "生产基地", "集装箱", "本地化", "工厂", "产业链", "货运", "晶圆", "原材料",
]))
NOISE = ["招聘", "课程培训", "研讨班招生", "考研", "期货喊单", "股价预测", "股票推荐", "概念股涨停"]
CJK = re.compile(r"[\u3400-\u9fff]")
TAG = re.compile(r"<[^>]*>")
SPACE = re.compile(r"\s+")


def chinese(s: str) -> str:
    s = html.unescape(str(s or ""))
    return s


def plain(s: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", " ", str(s or ""))
    text = TAG.sub(" ", text)
    return SPACE.sub(" ", chinese(text)).strip()


def parse_date(entry):
    raw = entry.get("published") or entry.get("updated")
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    except (ValueError, TypeError, IndexError):
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
        except ValueError:
            return None


def category(title: str, summary: str, fallback: str) -> str:
    lower = (title + " " + summary[:180]).lower()
    scores = {k: sum(2 if term in title.lower() else 1 for term in set(terms) if term.lower() in lower) for k, terms in TOPIC_TERMS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else fallback


def normalize_title(title, source):
    title = plain(title)
    suffix = " - " + source
    if source and title.endswith(suffix):
        title = title[:-len(suffix)].strip()
    return title[:160]


def good_url(link):
    try:
        p = urlparse(link)
        return p.scheme in {"https", "http"} and bool(p.netloc)
    except Exception:
        return False


def process_entry(entry, fallback):
    src = plain(entry.get("source", {}).get("title", "")) if entry.get("source") else ""
    title = normalize_title(entry.get("title", ""), src)
    desc = plain(entry.get("summary", ""))
    # Google News contains related-link lists, not an article excerpt: don't call them summaries.
    if "news.google.com" in entry.get("link", ""):
        desc = ""
    else:
        if desc.startswith(title):
            desc = desc[len(title):].strip(" ：:-")
        desc = desc[:240]
    if len(CJK.findall(title)) < 5 or len(title) < 9:
        return None
    if not any(w in (title + " " + desc[:120]).lower() for w in RELEVANCE_TERMS):
        return None
    if any(x in title for x in NOISE):
        return None
    dt = parse_date(entry)
    if not dt or dt < CUTOFF or dt > NOW + timedelta(hours=3):
        return None
    link = str(entry.get("link", "")).strip()
    if not good_url(link):
        return None
    source = src or urlparse(link).hostname or "新闻来源未标注"
    key = hashlib.sha1((title[:65].lower() + "|" + source.lower()).encode()).hexdigest()[:16]
    return {
        "id": key, "title": title, "summary": desc,
        "source": source, "url": link,
        "published_at": dt.isoformat().replace("+00:00", "Z"),
        "category": category(title, desc, fallback),
        "language": "中文", "origin": "RSS自动聚合"
    }


def google_urls(query):
    encoded = quote(query + " when:7d", safe=":")
    return [
        "https://news.google.com/rss/search?q=" + encoded + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "https://news.google.com/rss/search?q=" + encoded + "&hl=zh-CN&gl=SG&ceid=SG:zh-Hans",
    ]


def bing_url(query):
    return "https://www.bing.com/news/search?q=" + quote(query) + "&format=rss&mkt=zh-CN"


def xml_text(el, *names):
    for name in names:
        child = el.find(name)
        if child is not None:
            return "".join(child.itertext()) if len(child) else (child.text or "")
    return ""


def parse_rss(raw):
    root = ET.fromstring(raw)
    parsed = []
    ns = "{http://www.w3.org/2005/Atom}"
    items = root.findall("./channel/item")
    for x in items:
        parsed.append({
            "title": xml_text(x, "title"),
            "summary": xml_text(x, "description", "{http://purl.org/rss/1.0/modules/content/}encoded"),
            "link": xml_text(x, "link"),
            "published": xml_text(x, "pubDate", "{http://purl.org/dc/elements/1.1/}date"),
            "source": {"title": xml_text(x, "source")},
        })
    if not items:
        for x in root.findall(f"./{ns}entry"):
            link = ""
            for child in x.findall(f"{ns}link"):
                if child.attrib.get("rel", "alternate") == "alternate":
                    link = child.attrib.get("href", "")
                    break
            parsed.append({
                "title": xml_text(x, f"{ns}title"),
                "summary": xml_text(x, f"{ns}summary", f"{ns}content"),
                "link": link,
                "published": xml_text(x, f"{ns}published", f"{ns}updated"),
                "source": {"title": ""},
            })
    if not (root.tag.lower().endswith("rss") or root.tag.endswith("feed") or items):
        raise ValueError("这不是RSS或Atom订阅文档")
    return parsed


def fetch(url, timeout=16):
    last = None
    for tries in range(2):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ChainBrief/1.0)", "Accept": "application/rss+xml, application/xml, text/xml, */*"})
            with urlopen(req, timeout=timeout) as response:
                raw = response.read(3 * 1024 * 1024)
            if not raw or b"<html" in raw[:500].lower() or b"<!doctype html" in raw[:500].lower():
                raise ValueError("返回的是网页而非RSS")
            return parse_rss(raw)
        except Exception as exc:
            last = exc
            if tries == 0:
                time.sleep(0.4)
    raise RuntimeError(str(last))


def load_old():
    if not DATA_PATH.exists():
        return []
    try:
        return json.loads(DATA_PATH.read_text(encoding="utf-8")).get("articles", [])
    except Exception:
        return []


def rank(a):
    title = a["title"]
    bonus = sum(1 for w in ["企业", "建厂", "供应商", "出口管制", "关税", "投产", "采购", "供应链", "物流", "海外", "扩产", "海运"] if w in title)
    dt = datetime.fromisoformat(a["published_at"].replace("Z", "+00:00"))
    return (dt.timestamp() / 86400) + bonus * 0.07


def main():
    diagnostics = []
    received = []
    jobs = []
    for ix, (query, fallback) in enumerate(SEARCHES):
        urls = google_urls(query)
        if ix < 5:
            urls.append(bing_url(query))
        for url in urls:
            label = ("Google 新闻 CN" if "gl=CN" in url else "Google 新闻 SG" if "news.google" in url else "Bing 新闻") + " / " + query
            jobs.append((url, label, fallback))

    # Parallel requests avoid a 20-minute blank job if some feeds hang.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch, url, 10): (label, fallback) for url, label, fallback in jobs}
        for future in as_completed(futures):
            label, fallback = futures[future]
            try:
                entries = future.result()
                accepted = [x for e in entries if (x := process_entry(e, fallback))]
                received.extend(accepted)
                diagnostics.append({"source": label, "ok": True, "items": len(entries), "accepted": len(accepted)})
                print(f"OK {label}: fetched={len(entries)} filtered={len(accepted)}", flush=True)
            except Exception as exc:
                diagnostics.append({"source": label, "ok": False, "error": str(exc)[:200]})
                print(f"WARN {label}: {exc}", file=sys.stderr, flush=True)

    old = load_old()
    # Keep last known working data when fetch fails; merge rather than erase.
    # Dedupe in two stages: exact title and tokenized title without punctuation.
    seen = set()
    merged = []
    for item in sorted(received + old, key=rank, reverse=True):
        try:
            dt = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        if dt < CUTOFF or dt > NOW + timedelta(hours=3):
            continue
        title = unicodedata.normalize("NFKC", item["title"])
        dedup = re.sub(r"[^\w\u3400-\u9fff]", "", title).lower()
        if len(dedup) < 8 or dedup in seen:
            continue
        seen.add(dedup)
        merged.append(item)
        if len(merged) >= 180:
            break

    updated = NOW.isoformat(timespec="seconds").replace("+00:00", "Z")
    succeeded = sum(bool(d.get("ok")) for d in diagnostics)
    if received:
        generated_at = updated
    else:
        try:
            generated_at = json.loads(DATA_PATH.read_text(encoding="utf-8")).get("generated_at")
        except Exception:
            generated_at = None
    payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "articles": merged,
        "note": "公开中文RSS自动聚合；标题和发布时间以新闻来源为准，未经逐条人工核实。",
    }
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if received or not DATA_PATH.exists():
        DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    STATUS_PATH.write_text(json.dumps({
        "checked_at": updated, "success_sources": succeeded,
        "total_sources": len(diagnostics), "new_items_found": len(received),
        "kept_items": len(merged), "sources": diagnostics,
        "message": "完成更新" if received else "没有获取到新的新闻；保留上次成功的数据，请检查网络和来源。",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"RESULT: new={len(received)}, saved={len(merged)}, feeds_ok={succeeded}/{len(diagnostics)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
