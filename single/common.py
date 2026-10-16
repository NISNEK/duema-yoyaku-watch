"""シングル通知で共通に使う道具（設定の読み込み・カード名の比べ方・ページの取得）。

予約確認（monitor フォルダ）の部品のうち、名乗り方・時刻やファイルの扱いを使い回す。
"""
import os
import re
import sys
import time
import unicodedata
import urllib.robotparser
from datetime import timedelta
from urllib.parse import urlsplit

import requests
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "monitor"))

import fetcher  # noqa: E402  予約確認と同じ名乗り方
import state    # noqa: E402  予約確認と同じ時刻・ファイルの扱い

FetchError = fetcher.FetchError

SETTINGS_FILE = os.path.join(ROOT, "single_settings.yml")
WATCHLIST_FILE = os.path.join(ROOT, "data", "watchlist.enc")   # 登録リスト（暗号化・リポジトリに保存）
PUBLIC_FILE = os.path.join(ROOT, "docs", "single.json")         # 一覧ページ用（リポジトリに保存）
WORK_FILE = os.path.join(ROOT, ".state-single", "state.json")   # 毎回の作業用（キャッシュに保存）

WAIT_SECONDS = 3            # 同じお店に続けてアクセスする時の間隔
ROBOTS_RECHECK = timedelta(hours=24)


def load_settings():
    with open(SETTINGS_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def norm(text):
    """カード名を比べやすくする（全角半角・空白・中黒・大文字小文字の違いをなくす）。"""
    text = unicodedata.normalize("NFKC", text or "").casefold()
    return re.sub(r"[\s・･]", "", text)


def card_matches(card, title):
    """登録したカード名が商品名に含まれているか。"""
    key = norm(card)
    return bool(key) and key in norm(title)


def _get(url):
    try:
        return requests.get(url, headers={"User-Agent": fetcher.user_agent(), "Accept-Language": "ja"},
                            timeout=20)
    except requests.RequestException as e:
        raise FetchError(f"接続できませんでした（{type(e).__name__}）") from e


class Http:
    """お店へのアクセス係。正直に名乗り、robots.txt を守り、続けてアクセスする時は間を空ける。

    robots.txt はお店ごとに1日1回だけ取りに行き、中身を覚えておく（RFC 9309 に従う）。
    """

    def __init__(self, work):
        self.robots = work.setdefault("robots", {})
        self.parsers = {}
        self.last_access = {}
        self.count = 0

    def get(self, url):
        host = urlsplit(url).netloc
        if not self._allowed(url, host):
            raise FetchError("robots.txt でアクセスが禁止されているため、取りに行きませんでした")
        self._wait(host)
        res = _get(url)
        self.last_access[host] = time.time()
        self.count += 1
        if res.status_code != 200:
            raise FetchError(f"ページが開けませんでした（HTTP {res.status_code}）")
        if not res.encoding or res.encoding.lower() == "iso-8859-1":
            res.encoding = res.apparent_encoding
        return res

    def _wait(self, host):
        wait = WAIT_SECONDS - (time.time() - self.last_access.get(host, 0))
        if wait > 0:
            time.sleep(wait)

    def _allowed(self, url, host):
        now = state.now()
        rec = self.robots.get(host)
        checked = state.parse_iso(rec["checked_at"]) if rec else None
        if checked is None or now - checked >= ROBOTS_RECHECK:
            parts = urlsplit(url)
            self._wait(host)
            res = _get(f"{parts.scheme}://{host}/robots.txt")
            self.last_access[host] = time.time()
            rec = {"checked_at": state.iso(now), "status": res.status_code,
                   "text": res.text if res.status_code == 200 else ""}
            self.robots[host] = rec
            self.parsers.pop(host, None)
        if rec["status"] >= 500:
            raise FetchError(f"robots.txt が取得できません（HTTP {rec['status']}・サーバー不調）")
        if rec["status"] >= 400:
            return True  # robots.txt が無いのと同じ扱い
        if host not in self.parsers:
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(rec["text"].splitlines())
            self.parsers[host] = parser
        return self.parsers[host].can_fetch(fetcher.user_agent(), url)
