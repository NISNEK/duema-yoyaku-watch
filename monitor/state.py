"""記録ノート（status.json）の読み書きと、「前回から何が変わったか」を見つける係。"""
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
ERROR_WARN_COUNT = 3          # 失敗がこの回数続いたら警告する
FORGET_AFTER_DAYS = 60        # これだけ一覧に出てこない商品は記録から消す


def now():
    return datetime.now(JST).replace(microsecond=0)


def iso(dt):
    return dt.isoformat()


def parse_iso(text):
    return datetime.fromisoformat(text) if text else None


@dataclass
class Event:
    kind: str        # page / open / restock / warning
    shop_id: str
    shop_name: str
    title: str
    url: str


def load(path):
    if not os.path.exists(path):
        return {"saved_at": None, "shops": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def shop_record(data, shop):
    rec = data["shops"].setdefault(shop["id"], {
        "items": {},
        "initialized": False,
        "checked_at": None,
        "changed_at": None,
        "error_count": 0,
        "error_notified": False,
        "last_error": None,
    })
    rec["name"] = shop["name"]
    rec["url"] = shop["url"]
    return rec


def is_due(rec, interval_minutes, at):
    """前回の確認から指定の間隔が経ったか。GitHub の実行時刻のずれを考えて1分の余裕を持たせる。"""
    last = parse_iso(rec.get("checked_at"))
    if last is None:
        return True
    return at - last >= timedelta(minutes=interval_minutes) - timedelta(minutes=1)


def apply_success(rec, shop, items, include_restock, at):
    """取得に成功した結果を記録し、通知すべき出来事のリストを返す。"""
    events = []
    first_time = not rec["initialized"]
    stamp = iso(at)

    for item in items:
        old = rec["items"].get(item.id)
        if old is None:
            rec["items"][item.id] = {
                "title": item.title,
                "url": item.url,
                "state": item.state,
                "first_seen": stamp,
                "changed_at": stamp,
                "last_seen": stamp,
                "notified_open": item.state == "open" and not first_time,
                "ever_open": item.state == "open",
            }
            rec["changed_at"] = stamp
            if first_time:
                continue  # 初回は「すでにある商品」を覚えるだけ
            kind = "open" if item.state == "open" else "page"
            events.append(Event(kind, shop["id"], shop["name"], item.title, item.url))
            continue

        old["title"] = item.title
        old["url"] = item.url
        old["last_seen"] = stamp
        if old["state"] == item.state:
            continue
        before_state = old["state"]
        old["state"] = item.state
        old["changed_at"] = stamp
        rec["changed_at"] = stamp
        if item.state != "open":
            continue
        if before_state == "soldout" and old.get("ever_open"):
            # 一度売られてから売り切れ、また買えるようになった＝再販
            if include_restock:
                events.append(Event("restock", shop["id"], shop["name"], item.title, item.url))
        elif not old.get("notified_open"):
            events.append(Event("open", shop["id"], shop["name"], item.title, item.url))
        old["notified_open"] = True
        old["ever_open"] = True

    forget_before = at - timedelta(days=FORGET_AFTER_DAYS)
    for item_id in [k for k, v in rec["items"].items()
                    if parse_iso(v["last_seen"]) < forget_before]:
        del rec["items"][item_id]

    rec["initialized"] = True
    rec["checked_at"] = stamp
    rec["error_count"] = 0
    rec["error_notified"] = False
    rec["last_error"] = None
    return events


def apply_failure(rec, shop, message, at):
    """取得や判定に失敗したことを記録する。続いた時だけ警告を1回返す。"""
    rec["checked_at"] = iso(at)
    rec["error_count"] = rec.get("error_count", 0) + 1
    rec["last_error"] = message
    if rec["error_count"] >= ERROR_WARN_COUNT and not rec.get("error_notified"):
        rec["error_notified"] = True
        return [Event("warning", shop["id"], shop["name"], message, shop["url"])]
    return []


def shop_state(rec):
    """一覧ページに出すショップ全体の状態。"""
    if rec.get("error_count"):
        return "error"
    states = {v["state"] for v in rec["items"].values()}
    for s in ("open", "before", "soldout"):
        if s in states:
            return s
    return "before"


def publishable(data, shops):
    """公開用の status.json の中身を作る（設定から外したショップは載せない）。"""
    out = {"saved_at": data.get("saved_at"), "shops": {}}
    for shop in shops:
        rec = data["shops"].get(shop["id"])
        if rec is None:
            continue
        entry = {k: rec.get(k) for k in (
            "name", "url", "checked_at", "changed_at",
            "error_count", "error_notified", "last_error", "items")}
        entry["state"] = shop_state(rec)
        entry["enabled"] = shop.get("enabled", True)
        out["shops"][shop["id"]] = entry
    return out


def without_times(public):
    """「中身が変わったか」を比べるため、毎回変わる時刻を取り除く。"""
    copy = json.loads(json.dumps(public))
    copy.pop("saved_at", None)
    for rec in copy["shops"].values():
        rec.pop("checked_at", None)
        for item in rec.get("items", {}).values():
            item.pop("last_seen", None)
    return copy
