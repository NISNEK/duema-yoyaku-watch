"""見張りの司令塔。GitHub Actions から5分おきに呼ばれる。

使い方:
  python monitor/main.py                 … 通常の見張り
  python monitor/main.py --dry-run       … 通知を送らず、内容だけ表示する（記録も保存しない）
  python monitor/main.py --test-notify   … テスト通知を1件だけ送って終わる
"""
import argparse
import math
import os
import sys
from datetime import timedelta

import yaml

import fetcher
import notifier
import page_parser
import state

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOPS_FILE = os.path.join(ROOT, "shops.yml")
PUBLIC_FILE = os.path.join(ROOT, "docs", "status.json")     # 一覧ページ用（リポジトリに保存）
WORK_FILE = os.path.join(ROOT, ".state", "state.json")       # 毎回の作業用（キャッシュに保存）
PUBLISH_EVERY = timedelta(hours=1)
ROBOTS_RECHECK = timedelta(hours=24)


def load_config():
    with open(SHOPS_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    ids = [s["id"] for s in config["shops"]]
    if len(ids) != len(set(ids)):
        raise ValueError("shops.yml の id が重複しています。id はショップごとに別の名前にしてください。")
    return config


def effective_interval(shop, rec):
    """設定の間隔と robots.txt の指定のうち、長い方を使う。"""
    minutes = max(5, int(shop.get("interval_minutes", 5)))
    delay = (rec.get("robots") or {}).get("crawl_delay")
    if delay:
        # 実行時刻のずれ（最大1分早まる）を見込んで1分足し、指定より短くならないようにする
        minutes = max(minutes, math.ceil(float(delay) / 60) + 1)
    return minutes


def robots_allows(shop, rec, at):
    """robots.txt の確認は1日1回だけ行い、結果を覚えておく（取りに行けない時は1時間ごとに確認し直す）。"""
    robots = rec.get("robots") or {}
    checked = state.parse_iso(robots.get("checked_at"))
    recheck = ROBOTS_RECHECK if robots.get("allowed") else timedelta(hours=1)
    if checked is None or "status" not in robots or at - checked >= recheck:
        allowed, delay, status = fetcher.check_robots(shop["url"])
        robots = {"checked_at": state.iso(at), "allowed": allowed,
                  "crawl_delay": delay, "status": status}
        rec["robots"] = robots
    return robots["allowed"]


def check_shop(shop, rec, target, at):
    if not robots_allows(shop, rec, at):
        status = rec["robots"]["status"]
        if status >= 500:
            raise fetcher.FetchError(f"robots.txt が取得できません（HTTP {status}・サーバー不調）")
        raise fetcher.FetchError("robots.txt でアクセスが禁止されたため、見張りを中止しました")
    html, final_url = fetcher.fetch_html(shop["url"])
    rules = shop.get("rules", {})
    if shop.get("mode", "list") == "product":
        return page_parser.parse_product(html, final_url, rules, target.get("product", ""))
    return page_parser.parse_list(html, final_url, rules, target)


def run(dry_run):
    config = load_config()
    target = config.get("target", {})
    include_restock = bool(target.get("include_restock", True))
    shops = [s for s in config["shops"] if s.get("enabled", True)]

    data = state.load(WORK_FILE)
    if not data["shops"]:
        data = state.load(PUBLIC_FILE)  # 作業用の記録が無ければ、公開用から引き継ぐ
    published_before = state.load(PUBLIC_FILE)

    at = state.now()
    events = []
    for shop in shops:
        rec = state.shop_record(data, shop)
        if not state.is_due(rec, effective_interval(shop, rec), at):
            print(f"- {shop['name']}: 間隔待ちのため今回は見ません")
            continue
        try:
            items = check_shop(shop, rec, target, at)
        except (fetcher.FetchError, page_parser.ParseError) as e:
            print(f"- {shop['name']}: 失敗 … {e}")
            events += state.apply_failure(rec, shop, str(e), at)
            continue
        # 対象外の言葉が後から追加された時のため、記録済みの該当商品も消す
        for item_id in [k for k, v in rec["items"].items()
                        if page_parser.is_excluded(v["title"], target)]:
            del rec["items"][item_id]
        new_events = state.apply_success(rec, shop, items, include_restock, at)
        counts = {s: sum(1 for i in items if i.state == s) for s in ("open", "before", "soldout")}
        print(f"- {shop['name']}: 商品 {len(items)} 件（受付中 {counts['open']} / "
              f"受付前 {counts['before']} / 売り切れ {counts['soldout']}）、通知 {len(new_events)} 件")
        events += new_events

    messages = notifier.build_messages(events, target.get("product", ""))
    notifier.send_all(messages, dry_run=dry_run)

    if dry_run:
        print("（テストモードのため、記録は保存しません）")
        return

    data["saved_at"] = state.iso(at)
    state.save(WORK_FILE, data)

    public = state.publishable(data, config["shops"])
    last_publish = state.parse_iso(published_before.get("saved_at"))
    changed = state.without_times(public) != state.without_times(published_before)
    stale = last_publish is None or at - last_publish >= PUBLISH_EVERY - timedelta(minutes=1)
    if changed or stale:
        state.save(PUBLIC_FILE, public)
        print("一覧ページ用の記録を更新しました" + ("（変化あり）" if changed else "（1時間ごとの更新）"))


def test_notify():
    msg = {
        "title": "✅ テスト通知",
        "body": f"デュエマ予約監視ツールからのテスト通知です（{state.now():%m/%d %H:%M}）",
        "url": "https://ntfy.sh/",
        "priority": 3,
    }
    sent = notifier.send_all([msg])
    print(f"テスト通知を {sent} 件送りました")
    if sent == 0:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="通知を送らず内容だけ表示する")
    ap.add_argument("--test-notify", action="store_true", help="テスト通知を1件送る")
    args = ap.parse_args()
    if args.test_notify:
        test_notify()
        return
    try:
        run(dry_run=args.dry_run)
    except Exception as e:  # 設定ミスなどでプログラム全体が動けない時
        report_fatal(e, dry_run=args.dry_run)


def report_fatal(error, dry_run):
    """全体が止まった時、ntfy で1日1回だけ知らせる。

    失敗のまま終わると GitHub から5分ごとにエラーメールが届いてしまうため、
    ここでは「警告を出して正常終了」にする（Actions の画面には警告として残る）。
    """
    message = f"{type(error).__name__}: {error}"
    print(f"::error::見張りが動けませんでした … {message}")
    if dry_run:
        raise error
    marker = os.path.join(ROOT, ".state", "fatal.json")
    last = state.load(marker).get("saved_at")
    at = state.now()
    if last and at - state.parse_iso(last) < timedelta(hours=24):
        return
    notifier.send_all([{
        "title": "⚠️ 見張りプログラムが止まっています",
        "body": f"shops.yml の書き間違いなどが考えられます。\n{message[:300]}",
        "url": f"https://github.com/{os.environ.get('GITHUB_REPOSITORY', '')}/actions",
        "priority": 4,
    }])
    state.save(marker, {"saved_at": state.iso(at), "shops": {}})


if __name__ == "__main__":
    main()
