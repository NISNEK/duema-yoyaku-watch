"""グラフ（相場）用の値段の記録係。

お店へのアクセスは一切増やさず、見回りでもともと読んでいる値段だけを使う。
  1. 見回りで見た商品の「値段・在庫」を覚えておく
       トレキャット      … 1日1回のカード一覧（全シングル）＋ 本日の入荷品 ＋ 再入荷チェックで見た商品
       アメニティードリーム … 新着 ＋ 再入荷チェックで見た商品
  2. 登録カードごとに「在庫のある一番安い値段」を、その日のローソク足
     （始値・高値・安値・終値）に足していく
  3. 1時間に1回、docs/prices/ にカードごとのファイルで保存する（一覧ページの「相場」タブで表示）
"""
import hashlib
import json
import os
import re
from datetime import timedelta

import common
import state

PRICES_DIR = os.path.join(common.ROOT, "docs", "prices")
INDEX_FILE = os.path.join(PRICES_DIR, "index.json")
KEEP_DAYS = 365                     # グラフに残す日数
FLUSH_EVERY = timedelta(hours=1)    # ファイルに保存する間隔
FRESH = timedelta(days=2)           # これより古い値段は「今の値段」として使わない
SHOP_KEYS = ("torecat", "amenity")


def yen(text):
    digits = re.sub(r"[^\d]", "", str(text or ""))
    return int(digits) if digits else None


def card_id(name):
    return hashlib.sha1(common.norm(name).encode()).hexdigest()[:12]


def remember(work, shop_key, entries, at):
    """見回りで見た商品の値段・在庫を覚える。entries は (id, title, 値段の文字, 在庫あり?, 画像) の並び。"""
    book = work.setdefault("price_book", {}).setdefault(shop_key, {})
    stamp = state.iso(at)
    for pid, title, price_text, available, image in entries:
        price = yen(price_text)
        if price:
            book[pid] = {"title": title, "price": price, "a": bool(available), "t": stamp, "img": image or ""}
    for pid in [k for k, v in book.items() if at - state.parse_iso(v["t"]) > timedelta(days=7)]:
        del book[pid]


def observe(work, card_names, at):
    """登録カードごとに、いま在庫のある一番安い値段を、その日のローソク足に足す。"""
    book = work.get("price_book", {})
    candles = work.setdefault("candles", {})
    day = at.date().isoformat()
    # 「【状態B】」など傷ありの商品は、値段が大きく違うので除く（美品の一番安い値段を記録する）
    normalized = {shop: [(common.norm(e["title"]), e) for e in book.get(shop, {}).values()
                         if e["a"] and at - state.parse_iso(e["t"]) <= FRESH and "状態" not in e["title"]]
                  for shop in SHOP_KEYS}
    for name in card_names:
        key = common.norm(name)
        if not key:
            continue
        rec = candles.setdefault(card_id(name), {"name": name, "series": {}, "img": ""})
        rec["name"] = name
        for shop in SHOP_KEYS:
            matches = [e for title, e in normalized[shop] if key in title]
            if not matches:
                continue
            low = min(matches, key=lambda e: e["price"])
            rec["img"] = rec["img"] or low.get("img", "")
            c = rec["series"].setdefault(shop, {}).get(day)
            if c is None:
                rec["series"][shop][day] = [low["price"]] * 4          # 始値・高値・安値・終値
            else:
                c[1], c[2], c[3] = max(c[1], low["price"]), min(c[2], low["price"]), low["price"]


def flush(work, active_names, at):
    """1時間に1回、ローソク足をカードごとのファイルに保存する。保存したら True。"""
    last = state.parse_iso(work.get("prices_flushed_at"))
    candles = work.get("candles", {})
    if not candles or (last and at - last < FLUSH_EVERY - timedelta(minutes=1)):
        return False
    os.makedirs(PRICES_DIR, exist_ok=True)
    today = at.date().isoformat()
    oldest = (at.date() - timedelta(days=KEEP_DAYS)).isoformat()
    for cid, rec in candles.items():
        path = os.path.join(PRICES_DIR, f"{cid}.json")
        saved = _load(path) or {"name": rec["name"], "series": {}}
        saved["name"], saved["img"] = rec["name"], rec.get("img") or saved.get("img", "")
        for shop, days in rec["series"].items():
            rows = {r[0]: r[1:] for r in saved["series"].get(shop, [])}
            for day, c in days.items():
                if day in rows:   # 同じ日がすでに保存済みなら、始値は古い方・高値と安値は広い方・終値は新しい方
                    o, h, lo, _ = rows[day]
                    rows[day] = [o, max(h, c[1]), min(lo, c[2]), c[3]]
                else:
                    rows[day] = list(c)
            saved["series"][shop] = [[d, *v] for d, v in sorted(rows.items()) if d >= oldest]
        _save(path, saved)
        # 保存した過去の日の分は作業記録から消す（今日の分は続けて足していく）
        for days in rec["series"].values():
            for day in [d for d in days if d < today]:
                del days[day]
    _write_index(active_names, at)
    work["prices_flushed_at"] = state.iso(at)
    return True


def _write_index(active_names, at):
    active = {card_id(n) for n in active_names}
    cards = []
    for fname in sorted(os.listdir(PRICES_DIR)):
        if not fname.endswith(".json") or fname == "index.json":
            continue
        data = _load(os.path.join(PRICES_DIR, fname)) or {}
        cid = fname[:-5]
        last = max((rows[-1][0] for rows in data.get("series", {}).values() if rows), default="")
        cards.append({"id": cid, "name": data.get("name", ""), "img": data.get("img", ""),
                      "active": cid in active, "last": last})
    cards.sort(key=lambda c: (not c["active"], c["name"]))
    _save(INDEX_FILE, {"updated": state.iso(at), "cards": cards})


def _load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
