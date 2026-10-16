"""Discord にスラッシュコマンド（/登録 など）を登録する。最初に1回だけ実行する。

自分のサーバー専用のコマンドとして登録するので、すぐに使えるようになる。
"""
import os
import sys

import requests

API = "https://discord.com/api/v10"
ADMIN_ONLY = "8"  # 管理者（サーバーの持ち主）にだけ表示する

CARD = [{"type": 3, "name": "カード名", "description": "カード名（一部だけでもOK）", "required": True, "max_length": 40}]
CARD_OR_ALL = [{"type": 3, "name": "カード名", "description": "カード名、または「全部」", "required": True,
                "max_length": 40}]

COMMANDS = [
    {"name": "ヘルプ", "description": "使い方を表示する"},
    {"name": "登録", "description": "入荷を知らせてほしいカードを登録する（14日間）", "options": CARD},
    {"name": "解除", "description": "登録を消す（「全部」ですべて消す）", "options": CARD_OR_ALL},
    {"name": "一覧", "description": "自分の登録カードを見る"},
    {"name": "延長", "description": "登録の期限を延ばす（「全部」ですべて）", "options": CARD_OR_ALL},
    {"name": "検索", "description": "トレキャット・アメニティードリームの値段と在庫を調べる", "options": CARD},
    {"name": "停止", "description": "自分への通知を止める"},
    {"name": "再開", "description": "自分への通知を再開する"},
    {"name": "全体停止", "description": "【オーナー用】全員への通知を止める", "default_member_permissions": ADMIN_ONLY},
    {"name": "全体再開", "description": "【オーナー用】全員への通知を再開する", "default_member_permissions": ADMIN_ONLY},
    {"name": "タイマー", "description": "【オーナー用】指定日から○日間だけ通知する",
     "default_member_permissions": ADMIN_ONLY,
     "options": [{"type": 3, "name": "設定", "description": "例: 2026-11-15 2（解除する時は「解除」）",
                  "required": False}]},
    {"name": "トークン期限", "description": "【オーナー用】GitHub トークンの期限を登録する（近づくとDMでお知らせ）",
     "default_member_permissions": ADMIN_ONLY,
     "options": [{"type": 3, "name": "日付", "description": "例: 2027-01-14", "required": False}]},
]


def main():
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    channel_id = os.environ.get("SINGLE_CHANNEL_ID", "").strip()
    headers = {"Authorization": f"Bot {token}", "User-Agent": "DiscordBot (duema-yoyaku-watch, 1.0)"}

    app = requests.get(f"{API}/oauth2/applications/@me", headers=headers, timeout=20)
    app.raise_for_status()
    app_id = app.json()["id"]
    channel = requests.get(f"{API}/channels/{channel_id}", headers=headers, timeout=20)
    channel.raise_for_status()
    guild_id = channel.json()["guild_id"]

    for c in COMMANDS:
        c.setdefault("type", 1)
        c["dm_permission"] = False
    res = requests.put(f"{API}/applications/{app_id}/guilds/{guild_id}/commands",
                       headers=headers, json=COMMANDS, timeout=20)
    if res.status_code >= 400:
        print(f"::error::登録に失敗しました（HTTP {res.status_code}）: {res.text[:300]}")
        return 1
    print(f"スラッシュコマンドを {len(res.json())} 個登録しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
