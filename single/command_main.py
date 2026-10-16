"""スラッシュコマンド（/登録 など）を1件処理して、Discord に返事する係。

Cloudflare の受付係から GitHub の「シングル即答」が起動され、そこから呼ばれる。
依頼の中身は環境変数 PAYLOAD（JSON）で受け取る。

登録リストの保存は、5分おきの見回りと同時になってもぶつからないよう、
「最新を取り込む → 処理 → 保存」を最大3回やり直す。
"""
import base64
import importlib.util
import json
import os
import subprocess
import sys

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import common  # noqa: I001  先に読み込む（予約確認の部品を使えるようにするため）
import commands
import discord_api
import state
import watchlist as wl

# 「main」という名前は予約確認（monitor/main.py）と同じなので、場所を指定してシングル側を読み込む
_spec = importlib.util.spec_from_file_location("single_main", os.path.join(os.path.dirname(__file__), "main.py"))
single_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(single_main)

API = "https://discord.com/api/v10"
MAX_LEN = 1900

# スラッシュコマンドの「オプション名」→ ! コマンドの引数
ARG_OPTION = {"登録": "カード名", "解除": "カード名", "延長": "カード名", "検索": "カード名", "タイマー": "設定", "トークン期限": "日付"}


def git(*args, check=True):
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True)


def to_text_command(payload):
    """スラッシュコマンドの依頼を、今までの「!登録 カード名」の形に直す。"""
    cmd = payload["command"]
    arg = str(payload.get("options", {}).get(ARG_OPTION.get(cmd, ""), "")).strip()
    return f"!{cmd} {arg}".strip()


def process(payload, settings, owner_id, work):
    """最新の登録リストを読み、コマンドを処理する。(返事, DMで送る内容, 登録リストが変わったか) を返す。"""
    data = wl.load()
    before = wl.dump({**data, "last_message_id": None})
    ctx = single_main.Context(settings, work, common.Http(work), state.now())
    handler = commands.Handler(data, settings, owner_id, single_main.make_searcher(ctx))
    msg = {"author": {"id": payload["user"]["id"], "global_name": payload["user"].get("name", "")},
           "content": to_text_command(payload)}
    reply, private_text = handler.handle(msg)
    # チャンネル（本人にだけ見える返事）には今まで通り一覧などを表示し、同じ内容をDMにも送る
    text = private_text or reply or "（返事はありません）"
    changed = wl.dump({**data, "last_message_id": None}) != before
    if changed:
        wl.save(data)
    return text, private_text, changed


def save_with_retry(payload, settings, owner_id, work):
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    for attempt in range(1, 4):
        git("fetch", "--quiet", "origin", branch)
        git("reset", "--quiet", "--hard", f"origin/{branch}")
        text, private_text, changed = process(payload, settings, owner_id, work)
        if not changed:
            return text, private_text
        git("add", os.path.relpath(common.WATCHLIST_FILE, common.ROOT))
        git("commit", "--quiet", "-m", "シングル通知の登録を更新（スラッシュコマンド）")
        if git("push", "--quiet", "origin", f"HEAD:{branch}", check=False).returncode == 0:
            return text, private_text
        print(f"保存がほかの更新とぶつかったため、やり直します（{attempt}回目）")
    raise RuntimeError("登録の保存に3回失敗しました。少し待ってからもう一度お試しください。")


def respond(payload, text):
    """「考え中…」の表示を、結果に書き換える（長い時は続きを追加で送る）。"""
    base = f"{API}/webhooks/{payload['application_id']}/{payload['token']}"
    parts = [text[i:i + MAX_LEN] for i in range(0, len(text), MAX_LEN)] or [""]
    res = requests.patch(f"{base}/messages/@original", json={"content": parts[0]}, timeout=20)
    res.raise_for_status()
    for part in parts[1:]:
        requests.post(base, json={"content": part, "flags": 64}, timeout=20).raise_for_status()


def decrypt_payload(text):
    """Cloudflare の受付係が暗号化した依頼を元に戻す（ログに中身を残さないため）。"""
    key_text = os.environ.get("PAYLOAD_KEY", "").strip()
    if not key_text:
        raise RuntimeError("PAYLOAD_KEY が設定されていません")
    key = base64.urlsafe_b64decode(key_text + "=" * (-len(key_text) % 4))
    blob = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    return json.loads(AESGCM(key).decrypt(blob[:12], blob[12:], None))


def main():
    payload = decrypt_payload(os.environ["PAYLOAD"])
    settings = common.load_settings()
    owner_id = os.environ.get("OWNER_DISCORD_ID", "").strip()
    work = state.load(common.WORK_FILE)  # 値段検索用のカード一覧（読むだけ・保存しない）
    print(f"コマンド: /{payload.get('command')}")
    private_text = None
    try:
        text, private_text = save_with_retry(payload, settings, owner_id, work)
    except Exception as e:  # 失敗しても、本人には理由を伝える
        text = f"⚠️ 処理に失敗しました：{e}"
        print(f"::error::{e}")
    respond(payload, text)
    print("返事を送りました")
    if private_text:
        send_dm(payload["user"]["id"], private_text)


def send_dm(user_id, text):
    """一覧などを、チャンネルの表示に加えてDMにも送る（送れなくてもチャンネルには表示済み）。"""
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        print("::warning::DISCORD_BOT_TOKEN が無いため、DMは送りませんでした")
        return
    try:
        ok = discord_api.Discord(token).dm(user_id, text)
        print("DMも送りました" if ok else "DMを受け取れない設定のため、DMは送れませんでした")
    except discord_api.DiscordError as e:
        print(f"::warning::DMを送れませんでした（{e}）")


if __name__ == "__main__":
    sys.exit(main())
