"""シングル通知の司令塔。GitHub Actions から5分おきに呼ばれる。

使い方:
  python single/main.py               … 通常の見回り
  python single/main.py --dry-run     … Discord に送らず内容だけ表示する（記録も保存しない）
  python single/main.py --test-dm     … オーナーにテストのDMを送り、チャンネルにも書き込む
"""
import argparse
import os
import sys
from datetime import date, timedelta

import common
import commands
import discord_api
import shops
import watchlist as wl

import notifier  # 予約確認と同じ ntfy 通知（全体が止まった時の連絡用）
import state

SHOPS = ("torecat", "amenity")
ERROR_WARN_COUNT = 3
FIRST_RUN_LOOKBACK = timedelta(minutes=30)   # 初回は直近30分の発言だけ処理する
SEEN_KEEP = timedelta(days=30)
WATCH_KEEP = timedelta(days=7)


class Context:
    def __init__(self, settings, work, http, at):
        self.settings = settings
        self.work = work
        self.http = http
        self.at = at
        self.events = []
        self.owner_warnings = []


# ---------------- 1. Discord のコマンド ----------------

def process_commands(ctx, discord, channel_id, owner_id, data):
    last_id = ctx.work.get("last_message_id") or data.get("last_message_id")
    messages = discord.messages_after(channel_id, last_id)
    handler = commands.Handler(data, ctx.settings, owner_id, make_searcher(ctx))
    for msg in messages:
        last_id = msg["id"]
        if msg["author"].get("bot"):
            continue
        if not (ctx.work.get("last_message_id") or data.get("last_message_id")):
            if ctx.at - _snowflake_time(msg["id"]) > FIRST_RUN_LOOKBACK:
                continue
        reply, dm_text = handler.handle(msg)
        if reply is None:
            continue
        uid = msg["author"]["id"]
        if dm_text and not discord.dm(uid, dm_text):
            reply = "DMを受け取れない設定のようなので、ここに書きます。\n" + dm_text
        discord.send(channel_id, f"<@{uid}> {reply}", reply_to=msg["id"])
        print("- コマンドを1件処理しました")  # 公開ログに「何を登録したか」を残さない
    ctx.work["last_message_id"] = last_id
    return last_id


def _snowflake_time(message_id):
    ms = (int(message_id) >> 22) + 1420070400000
    return state.datetime.fromtimestamp(ms / 1000, state.JST)


def make_searcher(ctx):
    def search(keyword):
        lines = [f"🔎 **「{keyword}」の検索結果**"]
        lines += _search_amenity(ctx, keyword)
        lines += _search_torecat(ctx, keyword)
        return "\n".join(lines)
    return search


def _search_amenity(ctx, keyword):
    cfg = ctx.settings["amenity"]
    try:
        found = shops.amenity_search(ctx.http, cfg, keyword)
    except (common.FetchError, ValueError) as e:
        return [f"**{cfg['name']}**：調べられませんでした（{e}）"]
    return _format_found(cfg["name"], found)


def _search_torecat(ctx, keyword):
    cfg = ctx.settings["torecat"]
    catalog = (ctx.work.get("torecat_catalog") or {}).get("items")
    if not catalog:
        return [f"**{cfg['name']}**：値段検索の準備中です（カード一覧を作っています。1時間ほどお待ちください）"]
    matches = [it for it in catalog.values() if common.card_matches(keyword, it["title"])]
    found = []
    for item in matches[:5]:
        try:
            found.append(shops.torecat_live(ctx.http, cfg, item))
        except (common.FetchError, ValueError):
            continue
    lines = _format_found(cfg["name"], found)
    if len(matches) > 5:
        lines.append(f"　…ほか {len(matches) - 5} 件（カード名をもっと詳しく書くと絞り込めます）")
    return lines


def _format_found(shop_name, found):
    if not found:
        return [f"**{shop_name}**：見つかりませんでした"]
    found = sorted(found, key=lambda p: not p.available)[:5]
    lines = [f"**{shop_name}**"]
    for p in found:
        mark = "🟢" if p.available else "⚪"
        lines.append(f"{mark} {p.title}　{p.price}　{p.stock}\n　<{p.url}>")
    return lines


# ---------------- 2. お店の見回り ----------------

def shop_status(ctx, key):
    return ctx.work.setdefault("status", {}).setdefault(key, {
        "checked_at": None, "error_count": 0, "error_notified": False, "last_error": None})


def guarded(ctx, key, func):
    """お店ごとの処理。失敗しても全体は止めず、3回続いたらオーナーに1回だけ知らせる。"""
    st = shop_status(ctx, key)
    try:
        func()
    except (common.FetchError, ValueError, KeyError) as e:
        st["error_count"] += 1
        st["last_error"] = str(e)
        print(f"- {ctx.settings[key]['name']}: 失敗 … {e}")
        if st["error_count"] >= ERROR_WARN_COUNT and not st["error_notified"]:
            st["error_notified"] = True
            ctx.owner_warnings.append(f"⚠️ {ctx.settings[key]['name']} の見回りに3回続けて失敗しています：{e}")
        return
    st.update(checked_at=state.iso(ctx.at), error_count=0, error_notified=False, last_error=None)


def add_event(ctx, kind, shop_key, product):
    ctx.events.append({
        "kind": kind, "shop": ctx.settings[shop_key]["name"], "id": product.id, "title": product.title,
        "url": product.url, "price": product.price, "stock": product.stock, "at": state.iso(ctx.at)})


def track(ctx, store_key, shop_key, products, notify_new):
    """前回との違いから「新規入荷」「再入荷」を見つける。初回は覚えるだけ。"""
    seen = ctx.work.setdefault(store_key, {})
    baseline = bool(seen)
    for p in products:
        prev = seen.get(p.id)
        if prev is None:
            if baseline and notify_new and p.available:
                add_event(ctx, "new", shop_key, p)
        elif not prev["a"] and p.available:
            add_event(ctx, "restock", shop_key, p)
        seen[p.id] = {"a": p.available, "t": state.iso(ctx.at),
                      "f": prev.get("f", prev["t"]) if prev else state.iso(ctx.at)}  # f = 初めて見た時刻
    keep = SEEN_KEEP if notify_new else WATCH_KEEP
    for pid in [k for k, v in seen.items() if ctx.at - state.parse_iso(v["t"]) > keep]:
        del seen[pid]


def snapshot(ctx, shop_key, products):
    """一覧ページに載せるため、いまお店の入荷一覧に並んでいる商品を覚えておく。"""
    ctx.work.setdefault("arrivals", {})[shop_key] = [
        {"id": p.id, "title": p.title, "url": p.url, "price": p.price,
         "stock": p.stock, "available": p.available} for p in products]


def watch_arrivals(ctx):
    def torecat():
        products = shops.torecat_arrivals(ctx.http, ctx.settings["torecat"])
        track(ctx, "torecat_seen", "torecat", products, notify_new=True)
        snapshot(ctx, "torecat", products)
        print(f"- トレキャット 本日の入荷品: {len(products)} 件")

    def amenity():
        products = shops.amenity_new(ctx.http, ctx.settings["amenity"])
        track(ctx, "amenity_seen", "amenity", products, notify_new=True)
        snapshot(ctx, "amenity", products)
        print(f"- アメニティードリーム 新着: デュエマ {len(products)} 件")

    guarded(ctx, "torecat", torecat)
    guarded(ctx, "amenity", amenity)


def rotate(ctx, key, items):
    """登録カードが多くても、1回に確かめる数を決めて順番に回す。"""
    if not items:
        return []
    n = ctx.settings["checks"]["restock_checks_per_run"]
    start = ctx.work.get(key, 0) % len(items)
    picked = (items[start:] + items[:start])[:n]
    ctx.work[key] = (start + n) % len(items)
    return picked


def watch_registered(ctx, data):
    """登録カードの再入荷を、1店あたり決まった数ずつ確かめる。"""
    cards = wl.active_cards(data)

    def amenity():
        cfg = ctx.settings["amenity"]
        products = []
        for card in rotate(ctx, "amenity_pointer", [c["name"] for c in cards]):
            products += [p for p in shops.amenity_search(ctx.http, cfg, card) if common.card_matches(card, p.title)]
        track(ctx, "amenity_watch", "amenity", products, notify_new=False)

    def torecat():
        catalog = (ctx.work.get("torecat_catalog") or {}).get("items") or {}
        targets = {}
        for c in cards:
            for item in [it for it in catalog.values() if common.card_matches(c["name"], it["title"])][:10]:
                targets[item["id"]] = item
        cfg = ctx.settings["torecat"]
        products = [shops.torecat_live(ctx.http, cfg, it)
                    for it in rotate(ctx, "torecat_pointer", sorted(targets.values(), key=lambda x: x["id"]))]
        track(ctx, "torecat_watch", "torecat", products, notify_new=False)

    if cards:
        guarded(ctx, "amenity", amenity)
        guarded(ctx, "torecat", torecat)


def refresh_catalog(ctx):
    """トレキャットの値段検索用カード一覧を、1日1回、数回に分けて作り直す。"""
    cfg = ctx.settings["torecat"]
    catalog = ctx.work.get("torecat_catalog") or {}
    done_at = state.parse_iso(catalog.get("complete_at"))
    if done_at and ctx.at - done_at < timedelta(hours=24):
        return
    building = ctx.work.setdefault("torecat_building", {"page": 1, "items": {}})

    def step():
        for _ in range(cfg.get("catalog_pages_per_run", 10)):
            page = shops.torecat_catalog_page(ctx.http, cfg, building["page"])
            for item in page:
                building["items"][item["id"]] = item
            building["page"] += 1
            if len(page) < 250:
                ctx.work["torecat_catalog"] = {"items": building["items"], "complete_at": state.iso(ctx.at)}
                del ctx.work["torecat_building"]
                print(f"- トレキャット カード一覧を作り直しました（{len(building['items'])} 件）")
                return
        print(f"- トレキャット カード一覧を作成中（{building['page'] - 1} ページまで）")

    guarded(ctx, "torecat", step)


# ---------------- 3. 通知 ----------------

LABEL = {"new": "🆕 新規入荷", "restock": "🔁 再入荷"}


def notify(ctx, discord, data, channel_id):
    today = ctx.at.date()
    cards = wl.active_cards(data)
    per_user = {}
    for ev in ctx.events:
        for c in cards:
            if common.card_matches(c["name"], ev["title"]):
                for uid in c["users"]:
                    per_user.setdefault(uid, {})[(ev["shop"], ev["id"])] = (c["name"], ev)
    for uid, hits in per_user.items():
        if not wl.can_notify(data, uid, today):
            continue
        lines = ["📦 **登録カードが入荷しました！**"]
        for card, ev in hits.values():
            lines.append(f"{LABEL[ev['kind']]}【{ev['shop']}】{ev['title']}\n"
                         f"　{ev['price']}　{ev['stock']}（登録: {card}）\n　{ev['url']}")
        text = "\n".join(lines)
        if not discord.dm(uid, text):
            discord.send(channel_id, f"<@{uid}> DMを受け取れない設定のようなので、ここでお知らせします。\n{text}")
        print(f"- 通知しました（{len(hits)} 件）")


def expire(ctx, discord, data):
    """1時間に1回、期限切れの登録を消し、期限が近い登録をお知らせする。"""
    checked = state.parse_iso(ctx.work.get("expiry_checked_at"))
    if checked and ctx.at - checked < timedelta(hours=1):
        return
    ctx.work["expiry_checked_at"] = state.iso(ctx.at)
    remind = timedelta(days=ctx.settings["limits"]["remind_before_days"])
    for uid in list(data["users"]):
        rec = data["users"][uid]
        gone, soon = [], []
        for c in list(rec["cards"]):
            exp = state.parse_iso(c["expires"])
            if exp <= ctx.at:
                rec["cards"].remove(c)
                gone.append(c["name"])
            elif exp - remind <= ctx.at and not c.get("reminded"):
                c["reminded"] = True
                soon.append(f"{c['name']}（{exp:%m/%d}まで）")
        if not rec["cards"]:
            del data["users"][uid]
        lines = []
        if soon:
            lines += ["⏰ **登録の期限が近づいています**", *[f"・{s}" for s in soon],
                      "続けたい場合は `!延長 カード名`（または `!延長 全部`）と書いてください。"]
        if gone:
            lines += ["🗑️ **期限切れのため登録を消しました**", *[f"・{g}" for g in gone]]
        if lines:
            discord.dm(uid, "\n".join(lines))


TOKEN_REMIND_DAYS = (90, 60, 30, 14, 7, 3, 1, 0)   # 3か月前・2か月前・1か月前・2週間前・1週間前・3日前・前日・当日

TOKEN_GUIDE = """\
🔑 **GitHub トークンの期限のお知らせ**（オーナーだけに送っています）
{status}
期限が切れると、`/登録` などのスラッシュコマンドが「⚠️ 受付に失敗しました」になります（`!登録` などは今まで通り使えます）。

**作り直しの手順（10分ほど）**
① https://github.com/settings/personal-access-tokens を開き、**duema-bot** を押す
② **「Regenerate token」**（作り直す）を押し、有効期限を選んで、もう一度 **Regenerate token**
③ 表示された `github_pat_…` をコピー（閉じると二度と見られません）
④ Cloudflare → **Workers & Pages** → **duema-bot** → **Settings** → **Variables and Secrets**
⑤ **GITHUB_TOKEN** の右の編集ボタンを押し、③を貼り付けて保存 → **Deploy**
⑥ Discord で `!トークン期限 新しい期限の日付`（例: `!トークン期限 2027-04-14`）と送る
⑦ `/ヘルプ` を試して、約1分で返事が来れば完了です
"""


def token_reminder(ctx, discord, data, owner_id):
    """GitHub トークンの期限が近づいたら、オーナーにだけDMで知らせる（各段階1回ずつ）。"""
    expires = data["global"].get("token_expires")
    if not expires:
        return
    days_left = (date.fromisoformat(expires) - ctx.at.date()).days
    sent = data["global"].setdefault("token_reminded", [])
    due = [d for d in TOKEN_REMIND_DAYS if days_left <= d and d not in sent]
    if not due:
        return
    if days_left < 0:
        status = f"⚠️ **期限（{expires}）を過ぎています。**"
    elif days_left == 0:
        status = f"⚠️ **今日（{expires}）で期限が切れます。**"
    else:
        status = f"期限（{expires}）まで、あと **{days_left}日** です。"
    if discord.dm(owner_id, TOKEN_GUIDE.format(status=status)):
        sent.extend(due)  # 届いた時だけ「送った」と記録（届かなければ次の回にもう一度）
        print("- トークン期限のお知らせをオーナーに送りました")


# ---------------- 4. 一覧ページ ----------------

def publish(ctx):
    checks = ctx.settings["checks"]
    recent = ctx.work.setdefault("recent", [])
    recent += [{k: v for k, v in ev.items() if k != "id"} for ev in ctx.events]
    limit = ctx.at - timedelta(days=checks["recent_days"])
    recent[:] = [r for r in recent if state.parse_iso(r["at"]) >= limit][-300:]

    # いま入荷一覧に並んでいる商品（入荷）＋ 見つけた再入荷 を、新しい順に並べる
    items = []
    for key in SHOPS:
        seen = ctx.work.get(f"{key}_seen", {})
        for p in ctx.work.get("arrivals", {}).get(key, []):
            first = (seen.get(p["id"]) or {}).get("f") or state.iso(ctx.at)
            items.append({"kind": "new", "shop": ctx.settings[key]["name"], "at": first,
                          **{k: p[k] for k in ("title", "url", "price", "stock", "available")}})
    items += [{**r, "available": True} for r in recent if r["kind"] == "restock"]
    items.sort(key=lambda i: i["at"], reverse=True)

    public = {"saved_at": state.iso(ctx.at), "shops": {}, "items": items[:300]}
    for key in SHOPS:
        st = shop_status(ctx, key)
        public["shops"][key] = {"name": ctx.settings[key]["name"], **st,
                                "state": "error" if st["error_count"] else "ok"}
    before = state.load(common.PUBLIC_FILE) if os.path.exists(common.PUBLIC_FILE) else None
    if before:
        last = state.parse_iso(before.get("saved_at"))
        same = _without_times(before) == _without_times(public)
        if same or (last and ctx.at - last < timedelta(minutes=checks["page_update_minutes"]) - timedelta(minutes=1)):
            return
    state.save(common.PUBLIC_FILE, public)
    print("一覧ページ（シングル）の記録を更新しました")


def _without_times(public):
    shops_part = {k: {kk: vv for kk, vv in v.items() if kk != "checked_at"} for k, v in public["shops"].items()}
    return shops_part, public["items"]


# ---------------- 全体の流れ ----------------

def read_ids():
    """Secrets の ID が「17〜20けたの数字だけ」になっているか確かめる。"""
    ids = {}
    for name in ("SINGLE_CHANNEL_ID", "OWNER_DISCORD_ID"):
        value = os.environ.get(name, "").strip()
        if not value:
            raise discord_api.DiscordError(f"{name} が設定されていません")
        if not value.isdigit() or not 17 <= len(value) <= 20:
            raise discord_api.DiscordError(
                f"{name} の形が正しくありません（{len(value)}文字・数字以外を含む={not value.isdigit()}）。"
                "17〜20けたの数字だけを入れてください")
        ids[name] = value
    return ids["SINGLE_CHANNEL_ID"], ids["OWNER_DISCORD_ID"]


def run(dry_run):
    settings = common.load_settings()
    channel_id, owner_id = read_ids()
    discord = discord_api.Discord(os.environ.get("DISCORD_BOT_TOKEN", "").strip(), dry_run=dry_run)

    data = wl.load()
    before = wl.dump({**data, "last_message_id": None})
    work = state.load(common.WORK_FILE)
    ctx = Context(settings, work, common.Http(work), state.now())

    last_id = process_commands(ctx, discord, channel_id, owner_id, data)
    watch_arrivals(ctx)
    watch_registered(ctx, data)
    refresh_catalog(ctx)
    notify(ctx, discord, data, channel_id)
    expire(ctx, discord, data)
    token_reminder(ctx, discord, data, owner_id)
    for warning in ctx.owner_warnings:
        discord.dm(owner_id, warning)
    print(f"お店へのアクセス: {ctx.http.count} 回、入荷の検知: {len(ctx.events)} 件")

    if dry_run:
        print("（テストモードのため、記録は保存しません）")
        return
    if wl.dump({**data, "last_message_id": None}) != before:
        data["last_message_id"] = last_id
        wl.save(data)
        print("登録リストを保存しました（暗号化）")
    work["saved_at"] = state.iso(ctx.at)
    state.save(common.WORK_FILE, work)
    publish(ctx)


def test_dm():
    """1つずつ確かめて、どこまでできたかを表示する。"""
    channel_id, owner_id = read_ids()
    print("① ID の形: OK")
    wl.check_key()
    wl.load()
    print("② 暗号化の鍵: OK")
    discord = discord_api.Discord(os.environ.get("DISCORD_BOT_TOKEN", "").strip())
    discord.bot_user_id()
    print("③ ボットのトークン: OK")
    discord.send(channel_id, "✅ シングル通知ボットは動いています。`!ヘルプ` と書くと使い方を表示します（返事まで5〜15分）。")
    print("④ チャンネルへの書き込み: OK")
    ok = discord.dm(owner_id, "✅ シングル通知のテストDMです。このメッセージが届けば、DMの設定は完了です。")
    print("⑤ オーナーへのDM: " + ("OK" if ok else "送れませんでした（Discord のプライバシー設定でDMがオフの可能性）"))


def report_fatal(error):
    message = f"{type(error).__name__}: {error}"
    print(f"::error::シングル通知が動けませんでした … {message}")
    marker = os.path.join(os.path.dirname(common.WORK_FILE), "fatal.json")
    last = state.load(marker).get("saved_at")
    at = state.now()
    if last and at - state.parse_iso(last) < timedelta(hours=24):
        return
    notifier.send_all([{"title": "⚠️ シングル通知が止まっています", "body": message[:300],
                        "url": f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}/actions",
                        "priority": 4}])
    state.save(marker, {"saved_at": state.iso(at), "shops": {}})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-dm", action="store_true")
    args = ap.parse_args()
    try:
        if args.test_dm:
            test_dm()
        else:
            run(dry_run=args.dry_run)
    except Exception as e:  # 設定ミスなどで全体が動けない時（5分ごとのエラーメールを防ぐため正常終了にする）
        if args.dry_run or args.test_dm:
            print(f"::error::{e}")
            sys.exit(1)
        report_fatal(e)


if __name__ == "__main__":
    main()
