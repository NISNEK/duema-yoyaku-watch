"""ページを取ってくる係。

- 正直に名乗る（User-Agent にツール名と連絡先を書く）
- robots.txt を確認し、禁止されていたら取りに行かない
- 1回につき1ページだけ取る
"""
import os
import urllib.robotparser
from urllib.parse import urlsplit

import requests

TIMEOUT_SECONDS = 20


class FetchError(Exception):
    """ページが取れなかった時のエラー。"""


def user_agent():
    repo = os.environ.get("GITHUB_REPOSITORY", "local-test")
    return (
        "DuemaYoyakuWatcher/1.0 "
        f"(+https://github.com/{repo}; personal pre-order notifier, no auto-purchase)"
    )


def _get(url):
    headers = {"User-Agent": user_agent(), "Accept-Language": "ja,en;q=0.5"}
    try:
        return requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as e:
        raise FetchError(f"接続できませんでした（{type(e).__name__}）") from e


def check_robots(url):
    """robots.txt を読み、(取りに行ってよいか, 指定された待ち秒数) を返す。"""
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    res = _get(robots_url)
    if res.status_code in (401, 403):
        return False, None  # robots.txt 自体を拒否 → 全部ダメとみなす
    if res.status_code >= 400:
        return True, None  # robots.txt が無い → 制限なし
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(res.text.splitlines())
    ua = user_agent()
    return parser.can_fetch(ua, url), parser.crawl_delay(ua)


def fetch_html(url):
    res = _get(url)
    if res.status_code != 200:
        raise FetchError(f"ページが開けませんでした（HTTP {res.status_code}）")
    if not res.encoding or res.encoding.lower() == "iso-8859-1":
        res.encoding = res.apparent_encoding
    return res.text, res.url
