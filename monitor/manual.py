"""手動登録：人が見つけた予約ページ（manual.yml）を一覧ページに載せる係。

自動では見張れないショップ（Amazon・イオンなど）の情報を、人が書き足すためのもの。
プログラムがそのショップにアクセスすることはない。
"""
import os
from datetime import date

import yaml

import state

STATES = ("open", "before", "soldout")


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("items") or []


def build(path, data, at):
    """manual.yml を読み、一覧ページ用の「手動登録」欄を作る。書き間違いがあっても見張り全体は止めない。"""
    try:
        entries = load(path)
    except yaml.YAMLError as e:
        print(f"::warning::manual.yml の書き方に誤りがあるため、手動登録は表示しません（{e}）")
        return None

    seen = data.setdefault("manual_seen", {})
    items = {}
    today = at.date()
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("url") or not entry.get("title"):
            print("::warning::manual.yml に url か title が無い行があるため、その行は飛ばしました")
            continue
        until = entry.get("until")
        if isinstance(until, str):
            until = date.fromisoformat(until)
        if until and until < today:
            continue  # 期限切れは載せない
        url = str(entry["url"]).strip()
        first_seen = seen.setdefault(url, state.iso(at))
        st = entry.get("state", "open")
        items[url] = {
            "title": str(entry["title"]).strip(),
            "url": url,
            "shop": str(entry.get("shop", "手動登録")).strip(),
            "state": st if st in STATES else "open",
            "first_seen": first_seen,
            "changed_at": first_seen,
            "last_seen": first_seen,
        }

    # manual.yml から消された行の記録も片付ける
    for url in [u for u in seen if u not in items]:
        del seen[url]

    if not items:
        return None
    return {
        "name": "手動登録",
        "url": "",
        "state": next((s for s in STATES if any(i["state"] == s for i in items.values())), "open"),
        "enabled": True,
        "checked_at": None,
        "changed_at": None,
        "error_count": 0,
        "error_notified": False,
        "last_error": None,
        "items": items,
    }
