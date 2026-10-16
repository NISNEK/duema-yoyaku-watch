"""登録リスト（誰がどのカードを登録したか）の係。

リポジトリは公開なので、登録リストは暗号化して保存する。鍵は GitHub Secrets（WATCHLIST_KEY）にだけ置く。
"""
import json
import os
from datetime import date, timedelta

from cryptography.fernet import Fernet, InvalidToken

import common
import state


class WatchlistError(Exception):
    pass


def _fernet():
    key = os.environ.get("WATCHLIST_KEY", "").strip()
    if not key:
        raise WatchlistError("WATCHLIST_KEY（暗号化の鍵）が設定されていません")
    try:
        return Fernet(key.encode())
    except ValueError as e:
        raise WatchlistError("WATCHLIST_KEY の形が正しくありません（作り直してください）") from e


def check_key():
    _fernet()


def empty():
    return {"users": {}, "global": {"paused": False, "timer": None}, "last_message_id": None}


def load():
    if not os.path.exists(common.WATCHLIST_FILE):
        return empty()
    with open(common.WATCHLIST_FILE, "rb") as f:
        token = f.read()
    try:
        data = json.loads(_fernet().decrypt(token))
    except InvalidToken as e:
        raise WatchlistError("登録リストを開けません（WATCHLIST_KEY が作った時と違う可能性）") from e
    base = empty()
    base.update(data)
    return base


def dump(data):
    """比べる用の文字列（暗号化すると毎回中身が変わるので、変化の確認は暗号化前で行う）。"""
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def save(data):
    os.makedirs(os.path.dirname(common.WATCHLIST_FILE), exist_ok=True)
    token = _fernet().encrypt(dump(data).encode())
    with open(common.WATCHLIST_FILE, "wb") as f:
        f.write(token)


# ---------------- 登録の操作 ----------------

def user(data, user_id, name):
    rec = data["users"].setdefault(user_id, {"name": name, "paused": False, "cards": []})
    rec["name"] = name
    return rec


def find_card(rec, card):
    key = common.norm(card)
    return next((c for c in rec["cards"] if common.norm(c["name"]) == key), None)


def active_cards(data):
    """今登録されているカード名（重複なし）と、それぞれの登録者。"""
    cards = {}
    for uid, rec in data["users"].items():
        for c in rec["cards"]:
            cards.setdefault(common.norm(c["name"]), {"name": c["name"], "users": set()})["users"].add(uid)
    return list(cards.values())


def timer_active(data, today):
    timer = data["global"].get("timer")
    if not timer:
        return True
    start = date.fromisoformat(timer["start"])
    return start <= today < start + timedelta(days=int(timer["days"]))


def can_notify(data, uid, today):
    if data["global"].get("paused") or not timer_active(data, today):
        return False
    rec = data["users"].get(uid)
    return bool(rec) and not rec.get("paused")


def expires_at(settings):
    return state.iso(state.now() + timedelta(days=settings["limits"]["expire_days"]))
