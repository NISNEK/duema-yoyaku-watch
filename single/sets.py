"""新弾のシングル相場の係。

1日1回読んでいるトレキャットの「デュエマシングル全て」から（アクセスは増やさない）、
  ・発売（＝トレキャットに初めて並んだ日）から3か月以内の弾を自動で見つけ、
  ・その弾のシングルを「カード名 → 枠（㊙・超・通常など）と状態（美品・状態Bなど）」に整理し、
  ・1日1本のローソク足（始値＝前日の値段、終値＝今日の値段）を記録する。
アメニティードリームは、新弾ごとに型番（例: DM_26EX4）の検索結果を1日1回だけ読み（1弾あたり2〜3ページ）、
カード番号でトレキャットのカードと結びつけて、比べるための値段とレアリティ（SR・VRなど）を記録する。
3か月を過ぎた弾は、結果（最初・最高・最安・最後の値段）だけを archive.json にまとめて、毎日のデータは消す。

保存先: docs/prices/sets/index.json（弾の一覧）、<弾>.json（弾ごとのグラフ）、archive.json（過去の弾のまとめ）
"""
import json
import os
import re
import unicodedata
from datetime import date, timedelta

import common
import state

SETS_DIR = os.path.join(common.ROOT, "docs", "prices", "sets")
INDEX_FILE = os.path.join(SETS_DIR, "index.json")
ARCHIVE_FILE = os.path.join(SETS_DIR, "archive.json")
KEEP_DAYS = 90                                   # 発売から何日グラフを残すか（3か月）
SET_TAG = re.compile(r"^DM\d{2}-[A-Z]+\d+[A-Z]?$")   # 例: DM26-EX4, DM26-RP1, DM23-RP4X

_COND = re.compile(r"^\s*【([^】]*)】")                       # 【状態B】など
_NUMBER = re.compile(r"[（(]\s*(?:DM\w+\s+)?([^()（）/\s]*\d+[^()（）/\s]*)\s*/\s*([^()（）\s]+)\s*[)）]\s*([A-Z]{1,4})?\s*$")
_LOOSE_NUMBER = re.compile(r"\s+(\S*\d+\S*)\s*/\s*(\S+)\s+DM\S*\s*$")   # 例: マーシャル・クロウラー 19/98 DMEX06


def parse_title(title):
    """商品名を (カード名, 枠, 状態, 番号) に分ける。

    例: 「【状態B】切札混成 ドギラダンテ刈（㊙15/㊙25）」→ ("切札混成 ドギラダンテ刈", "㊙", "状態B", "㊙15/㊙25")
    枠は番号の数字以外の部分（「㊙」「超」「超G」「DCR」など。無ければ「通常」。商品名の最後に SR などがあればそれを付ける）
    """
    text = title.strip()
    cond = "美品"
    m = _COND.match(text)
    while m:
        if "状態" in m.group(1):
            cond = m.group(1)
        text = text[m.end():]
        m = _COND.match(text)
    number, frame = "", "通常"
    m = _NUMBER.search(text) or _LOOSE_NUMBER.search(text)
    if m:
        number = f"{m.group(1)}/{m.group(2)}"
        prefix = re.sub(r"\d+", "", m.group(1))
        rarity = m.group(3) if m.re is _NUMBER else None
        frame = rarity or prefix or "通常"
        text = text[:m.start()]
    name = re.sub(r"\s+", " ", text.replace("　", " ")).strip()
    return name or title, frame, cond, number


def set_code(tags):
    return next((t for t in (tags or []) if SET_TAG.match(t)), None)


def update(catalog_items, at, start_with=()):
    """1日1回、カード一覧を読み終わった時に呼ぶ。新弾のグラフを更新し、古い弾はまとめる。"""
    os.makedirs(SETS_DIR, exist_ok=True)
    today = at.date()
    by_set = {}
    for item in catalog_items:
        code = item.get("set")
        if code:
            by_set.setdefault(code, []).append(item)

    index = _load(INDEX_FILE) or {"sets": [], "seen_codes": []}
    known = {s["code"]: s for s in index["sets"]}
    seen = set(index.get("seen_codes", []))
    # トレキャットは古い弾のカードをまとめて出品し直すことがあり、出品日では新弾か分からない。
    # そこで「これまで一度も見たことのない弾の目印が現れた日」を発売日とする（デッキなど商品が少なくても新弾にする）。
    # 古い弾のカードが初めて出品された時に間違えないよう、型番の年（DM26 なら2026年）が今年より前なら新弾にしない。
    # 最初の1回だけは、設定の start_with に書いた弾から始める（それ以外の今ある弾は「見たことがある」扱い）。
    first_run = not seen
    for code, items in by_set.items():
        if code in seen or code in known:
            seen.add(code)
            continue
        if first_run and code not in start_with:
            seen.add(code)
            continue
        seen.add(code)
        if not first_run and int(code[2:4]) < today.year % 100:
            continue   # 古い年の型番は新弾にしない
        published = sorted(i["published"][:10] for i in items if i.get("published"))
        first = published[0] if first_run and published else today.isoformat()
        known[code] = {"code": code, "first_seen": min(first, today.isoformat())}
    index["seen_codes"] = sorted(seen)

    for code, info in list(known.items()):
        if date.fromisoformat(info["first_seen"]) < today - timedelta(days=KEEP_DAYS):
            _archive(code, info, today)
            del known[code]
            continue
        data = _record(code, info, by_set.get(code, []), today)
        info.update(frames=data["frames"], cards=len(data["cards"]), updated=today.isoformat())

    index["sets"] = sorted(known.values(), key=lambda s: s["first_seen"], reverse=True)
    index["updated"] = state.iso(at)
    _save(INDEX_FILE, index)
    return [s["code"] for s in index["sets"]]


def _record(code, info, items, today):
    path = os.path.join(SETS_DIR, f"{code}.json")
    data = _load(path) or {"code": code, "first_seen": info["first_seen"], "cards": {}}
    day = today.isoformat()
    for item in items:
        price = item.get("price_yen")
        if not price:
            continue
        name, frame, cond, number = parse_title(item["title"])
        card = data["cards"].setdefault(name, {"variants": {}})
        key = f"{frame}|{cond}"
        v = card["variants"].setdefault(key, {"frame": frame, "cond": cond, "number": number, "series": []})
        v.update(number=number or v.get("number", ""), img=item.get("image") or v.get("img", ""),
                 url=item.get("url") or v.get("url", ""), available=bool(item.get("available")))
        rows = v["series"]
        if rows and rows[-1][0] == day:
            # 同じ日にもう一度読んだ時は、終値を新しい値段にして高値・安値を広げる
            o, h, lo, _ = rows[-1][1:]
            rows[-1] = [day, o, max(h, price), min(lo, price), price]
        else:
            o = rows[-1][4] if rows else price   # 始値＝前日の終値（株の日足と同じ見え方にする）
            rows.append([day, o, max(o, price), min(o, price), price])
    frames = sorted({v["frame"] for c in data["cards"].values() for v in c["variants"].values()}, key=_frame_order)
    data["frames"] = frames
    _save(path, data)
    return data


def _frame_order(frame):
    order = {"㊙": 0, "超G": 1, "超": 2, "通常": 9}
    return (order.get(frame, 5), frame)


RARITY_ORDER = ["DMR", "KGM", "OR", "SR", "VR", "R", "U", "C"]


def _rarity_order(rarity):
    return (RARITY_ORDER.index(rarity) if rarity in RARITY_ORDER else len(RARITY_ORDER), rarity)


# ---------------- アメニティードリーム（比べる用の値段・レアリティ） ----------------

def active_codes():
    index = _load(INDEX_FILE) or {}
    return [s["code"] for s in index.get("sets", [])]


def amenity_code(code):
    """トレキャットの目印 DM26-EX4 → アメニティードリームの型番の頭 DM_26EX4"""
    return "DM_" + code[2:].replace("-", "")


def norm_number(number):
    """番号をそろえる（アメニティードリームの「秘15/秘25」とトレキャットの「㊙15/㊙25」を同じにする）。"""
    text = re.sub(r"\s", "", unicodedata.normalize("NFKC", number or ""))
    return re.sub(r"(\d+)[a-zA-Z]+(?=/)", r"\1", text)   # 「16a/99」「秘10b/秘25」（表裏のあるカード）は同じ番号として扱う


def parse_amenity(item):
    """アメニティードリームの商品を (番号, レアリティ, カード名, 状態) に分ける。
    例: 型番「DM_26EX4_秘1/秘25_シークレットレアVR」・商品名「【シークレットレアVR】切札連結 バロムレイズ」
        → ("秘1/秘25", "VR", "切札連結 バロムレイズ", "美品")"""
    parts = item.get("model", "").split("_")
    number = parts[2] if len(parts) >= 3 else ""
    m = re.search(r"([A-Z]+)$", parts[3]) if len(parts) >= 4 else None
    rarity = m.group(1) if m else ""
    title = item.get("title", "")
    cond_m = re.search(r"【(状態[^】]*)】", title)
    name = re.sub(r"\s+", " ", re.sub(r"^(\s*【[^】]*】)+", "", title)).strip()
    return number, rarity, name, (cond_m.group(1) if cond_m else "美品")


def record_amenity(code, items, today):
    """新弾のアメニティードリームの値段を、カード番号でトレキャットのカードに結びつけて記録する。"""
    path = os.path.join(SETS_DIR, f"{code}.json")
    data = _load(path)
    if not data:
        return 0
    by_number = {}
    for name, card in data["cards"].items():
        for v in card["variants"].values():
            by_number[(norm_number(v.get("number")), v["cond"])] = v
    day, matched = today.isoformat(), 0
    for item in items:
        number, rarity, name, cond = parse_amenity(item)
        price = item.get("price_yen")
        if not number or not price:
            continue
        v = by_number.get((norm_number(number), cond))
        if v is None:
            # トレキャットに無いカードは、アメニティードリームだけのカードとして加える
            frame = re.sub(r"\d+", "", number.split("/")[0]).replace("秘", "㊙") or "通常"
            card = data["cards"].setdefault(name, {"variants": {}})
            v = card["variants"].setdefault(f"{frame}|{cond}", {"frame": frame, "cond": cond, "number": number,
                                                               "series": []})
            by_number[(norm_number(number), cond)] = v
        else:
            matched += 1
        v["rarity"] = rarity or v.get("rarity", "")
        v["amenity_url"] = item.get("url") or v.get("amenity_url", "")
        v["img"] = v.get("img") or item.get("image", "")
        rows = v.setdefault("amenity", [])
        if rows and rows[-1][0] == day:
            o, h, lo, _ = rows[-1][1:]
            rows[-1] = [day, o, max(h, price), min(lo, price), price]
        else:
            o = rows[-1][4] if rows else price
            rows.append([day, o, max(o, price), min(o, price), price])
    data["rarities"] = sorted({v.get("rarity") for c in data["cards"].values() for v in c["variants"].values()
                               if v.get("rarity")}, key=_rarity_order)
    data["frames"] = sorted({v["frame"] for c in data["cards"].values() for v in c["variants"].values()},
                            key=_frame_order)
    _save(path, data)
    index = _load(INDEX_FILE) or {"sets": []}
    for s in index["sets"]:
        if s["code"] == code:
            s.update(rarities=data["rarities"], frames=data["frames"], cards=len(data["cards"]))
    _save(INDEX_FILE, index)
    return matched


def _archive(code, info, today):
    """3か月を過ぎた弾は、結果だけをまとめて残し、毎日のデータは消す。"""
    path = os.path.join(SETS_DIR, f"{code}.json")
    data = _load(path)
    archive = _load(ARCHIVE_FILE) or {"sets": []}
    if data and not any(s["code"] == code for s in archive["sets"]):
        cards = []
        for name, card in data["cards"].items():
            for v in card["variants"].values():
                rows = v["series"]
                if not rows:
                    continue
                first, last = rows[0][4], rows[-1][4]
                cards.append({"name": name, "frame": v["frame"], "cond": v["cond"], "first": first, "last": last,
                              "high": max(r[2] for r in rows), "low": min(r[3] for r in rows),
                              "change": round((last - first) / first * 100, 1) if first else 0})
        cards.sort(key=lambda c: c["last"], reverse=True)
        archive["sets"].insert(0, {"code": code, "first_seen": info["first_seen"],
                                   "archived": today.isoformat(), "cards": cards})
        _save(ARCHIVE_FILE, archive)
    if os.path.exists(path):
        os.remove(path)


def _load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
