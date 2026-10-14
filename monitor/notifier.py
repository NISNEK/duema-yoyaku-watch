"""ntfy と Discord に通知を送る係。

秘密情報（ntfy のトピック名・Discord の Webhook URL）は環境変数から受け取り、
画面やログには絶対に表示しない。
"""
import os

import requests

from state import now

NTFY_SERVER = "https://ntfy.sh"
SUMMARY_THRESHOLD = 5   # 1つのショップで一度にこれより多く見つかったら、まとめて1通にする

TITLES = {
    "page": "👀 予約ページ公開！ {shop}",
    "open": "🔔 予約開始！ {shop}",
    "restock": "🔁 再販開始！ {shop}",
    "warning": "⚠️ {shop} の監視に失敗しています",
}


def build_messages(events, product_name):
    """出来事のリストから、送る通知の中身を作る。"""
    time_text = now().strftime("%m/%d %H:%M")
    messages = []
    by_shop_kind = {}
    for ev in events:
        by_shop_kind.setdefault((ev.shop_id, ev.kind), []).append(ev)

    for (_, kind), evs in by_shop_kind.items():
        shop = evs[0].shop_name
        title = TITLES[kind].format(shop=shop)
        if kind == "warning":
            body = f"{evs[0].title}\n（{time_text} 時点。3回続けて失敗しました）"
            messages.append({"title": title, "body": body, "url": evs[0].url, "priority": 4})
            continue
        if len(evs) > SUMMARY_THRESHOLD:
            names = "\n".join(f"・{e.title}" for e in evs[:SUMMARY_THRESHOLD])
            body = (f"{product_name} の商品が {len(evs)} 件見つかりました（{time_text} 検知）\n"
                    f"{names}\n…ほか {len(evs) - SUMMARY_THRESHOLD} 件")
            messages.append({"title": title, "body": body, "url": evs[0].url, "priority": 5})
            continue
        for e in evs:
            body = {
                "page": f"{e.title} の予約ページが公開されました（{time_text} 検知）",
                "open": f"{e.title} の予約受付が始まりました（{time_text} 検知）",
                "restock": f"{e.title} が再び購入できるようになりました（{time_text} 検知）",
            }[kind]
            messages.append({"title": title, "body": body, "url": e.url, "priority": 5})
    return messages


def send_ntfy(topic, msg):
    payload = {
        "topic": topic,
        "title": msg["title"],
        "message": msg["body"],
        "priority": msg["priority"],
        "click": msg["url"],
        "actions": [{"action": "view", "label": "ページを開く", "url": msg["url"]}],
    }
    res = requests.post(NTFY_SERVER, json=payload, timeout=15)
    res.raise_for_status()


def send_discord(webhook_url, msg):
    payload = {"embeds": [{
        "title": msg["title"],
        "description": msg["body"],
        "url": msg["url"],
        "color": 0xF5A623 if msg["priority"] < 5 else 0xE53935,
    }]}
    res = requests.post(webhook_url, json=payload, timeout=15)
    res.raise_for_status()


def send_all(messages, dry_run=False):
    """すべての通知を送る。dry_run のときは送らずに内容だけ表示する。"""
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    sent = 0
    for msg in messages:
        if dry_run:
            print(f"[通知テスト・送信しません] {msg['title']} / {msg['body']} / {msg['url']}")
            continue
        if not topic and not webhook:
            print("::warning::NTFY_TOPIC も DISCORD_WEBHOOK_URL も設定されていないため、通知を送れません")
            return 0
        for name, target, func in (("ntfy", topic, send_ntfy), ("Discord", webhook, send_discord)):
            if not target:
                continue
            try:
                func(target, msg)
                sent += 1
            except requests.RequestException as e:
                # エラー内容に秘密情報が含まれないよう、種類だけを表示する
                print(f"::warning::{name} への通知に失敗しました（{type(e).__name__}）")
    return sent
