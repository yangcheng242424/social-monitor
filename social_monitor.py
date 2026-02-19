"""
social_monitor.py  v4  —  GitHub Actions 版
状态保存在仓库里的 seen_posts.json，由 GitHub Actions 自动 commit 回去。
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from email.utils import parsedate_to_datetime

import feedparser
import requests
from bs4 import BeautifulSoup

# ══════════════════════════════════════════════════════════════════
#  配置（从 GitHub Actions Secrets 读取）
# ══════════════════════════════════════════════════════════════════
SERVERCHAN_KEY = os.getenv("SERVERCHAN_KEY", "").strip()
LOOKBACK_HOURS = 14   # 只推送过去 14h 内发布的内容（12h 间隔 + 2h 容错）

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.cz",
]

TARGETS = {
    "Boris Cherny": {
        "rss": [
            "https://borischerny.com/feed.xml",
            "https://bsky.app/profile/bcherny.bsky.social/rss",
        ],
        "nitter_user": "bcherny",
    },
    "Dario Amodei (Anthropic CEO)": {
        "rss": [
            "https://darioamodei.substack.com/feed",
            "https://darioamodei.com/feed.xml",
            "https://olshansk.github.io/rss-feeds/feeds/feed_anthropic_news.xml",
        ],
        "nitter_user": "DarioAmodei",
        "anthropic_scrape": True,
    },
    "Peter Steinberger": {
        "rss": [
            "https://steipete.me/rss.xml",
            "https://bsky.app/profile/steipete.me/rss",
            "https://mastodon.social/@steipete.rss",
        ],
        "nitter_user": "steipete",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

BASE_DIR   = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "seen_posts.json"


# ══════════════════════════════════════════════════════════════════
#  状态管理（本地文件，由 CI 负责持久化到仓库）
# ══════════════════════════════════════════════════════════════════
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def make_id(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════════
#  时间过滤
# ══════════════════════════════════════════════════════════════════
def parse_pub_date(raw: str):
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def is_within_window(post: dict, hours: int) -> bool:
    pub = parse_pub_date(post.get("published", ""))
    if pub is None:
        return False
    return pub >= datetime.now(timezone.utc) - timedelta(hours=hours)


# ══════════════════════════════════════════════════════════════════
#  抓取
# ══════════════════════════════════════════════════════════════════
def fetch_rss(url: str) -> list:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        posts = []
        for entry in feed.entries[:10]:
            link      = entry.get("link", "")
            title     = entry.get("title", "无标题")
            published = entry.get("published", "") or entry.get("updated", "")
            posts.append({
                "id":        make_id(link or title),
                "title":     title,
                "link":      link,
                "published": published,
                "source":    url,
            })
        return posts
    except Exception as e:
        log(f"  [RSS 失败] {url} -> {e}")
        return []


def fetch_nitter(username: str) -> list:
    for base in NITTER_INSTANCES:
        posts = fetch_rss(f"{base}/{username}/rss")
        if posts:
            return posts
        time.sleep(0.5)
    log(f"  [nitter 全部失败] @{username}")
    return []


def scrape_anthropic_news() -> list:
    url = "https://www.anthropic.com/news"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        posts, seen = [], set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/news/" not in href or href in seen:
                continue
            if href.startswith("/"):
                href = "https://www.anthropic.com" + href
            title_el = a.find(["h2", "h3", "h4", "p"]) or a
            title = title_el.get_text(strip=True)
            if len(title) < 5:
                continue
            seen.add(href)
            posts.append({"id": make_id(href), "title": title,
                          "link": href, "published": "", "source": "anthropic.com/news"})
            if len(posts) >= 8:
                break
        return posts
    except Exception as e:
        log(f"  [Anthropic 抓取失败] {e}")
        return []


# ══════════════════════════════════════════════════════════════════
#  通知
# ══════════════════════════════════════════════════════════════════
def notify(person: str, post: dict):
    title_msg = f"新内容提醒：{person}"
    desp = "\n".join([
        f"**人物**：{person}",
        f"**标题**：{post.get('title', '')}",
        f"**链接**：{post.get('link', '')}",
        f"**发布时间**：{post.get('published', '未知')}",
        f"**来源**：{post.get('source', '')}",
    ])
    log(f"  >>> 推送：{post.get('title','')}")
    log(f"      {post.get('link','')}")
    _send_serverchan(title_msg, desp)


def _send_serverchan(title: str, desp: str) -> bool:
    if not SERVERCHAN_KEY:
        log("  [警告] 未设置 SERVERCHAN_KEY，跳过微信推送")
        return False
    try:
        resp = requests.post(
            f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send",
            data={"title": title, "desp": desp},
            headers=HEADERS, timeout=15,
        )
        data = resp.json()
        ok = str(data.get("code")) == "0"
        if not ok:
            log(f"  [Server酱异常] {data}")
        return ok
    except Exception as e:
        log(f"  [Server酱失败] {e}")
        return False


def log(msg: str):
    print(msg, flush=True)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


# ══════════════════════════════════════════════════════════════════
#  主逻辑
# ══════════════════════════════════════════════════════════════════
def check_all():
    log(f"\n{'='*55}")
    log(f"[{now()}] 开始检查（时间窗口：过去 {LOOKBACK_HOURS}h）")
    log(f"{'='*55}")

    state     = load_state()
    new_count = 0

    for person, sources in TARGETS.items():
        log(f"\n> {person}")
        if person not in state:
            state[person] = []

        all_posts = []
        for feed_url in sources.get("rss", []):
            all_posts.extend(fetch_rss(feed_url))
        if nitter_user := sources.get("nitter_user"):
            all_posts.extend(fetch_nitter(nitter_user))
        if sources.get("anthropic_scrape"):
            all_posts.extend(scrape_anthropic_news())

        for post in all_posts:
            pid = post["id"]
            if pid in state[person]:
                continue
            state[person].append(pid)
            if not is_within_window(post, LOOKBACK_HOURS):
                continue
            notify(person, post)
            new_count += 1

        state[person] = state[person][-300:]

    save_state(state)
    log(f"\n[{now()}] 完毕，本次推送 {new_count} 条新内容\n")


if __name__ == "__main__":
    check_all()
